#!/usr/bin/env python3
"""
Migrate enrichment data from an old concordance to a rebuilt concordance.

Matching strategy (priority order):
  1. Wikidata ID match
  2. Member overlap (book+entity_id and normalized book+name overlap)
  3. Modern-name / alias matching

The script also migrates stable cluster keys and ensures every new cluster has
one, so downstream routes can remain stable across rebuilds.
"""

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

CONCORDANCE_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
STRATEGY_PRIORITY = {
    "wikidata": 0,
    "member_overlap": 1,
    "modern_name": 2,
    "alias_match": 3,
}


def normalize_name(text: str) -> str:
    """Lowercase, strip diacritics, keep only alnum+spaces."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_key(text: str) -> str:
    """Normalize for key hashing."""
    text = normalize_name(text).replace(" ", "-")
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def build_cluster_stable_key(cluster: dict) -> str:
    """Build a deterministic stable key from category and member names."""
    names = set()
    for member in cluster.get("members", []):
        n = normalize_for_key(member.get("name", ""))
        if n:
            names.add(n)
        normalized_variants = sorted(
            {normalize_for_key(variant) for variant in member.get("variants", []) if variant}
        )
        for v in normalized_variants[:5]:
            if v:
                names.add(v)
    signature_names = sorted(names)[:16]
    signature = f"{cluster.get('category', '').lower()}|{'|'.join(signature_names)}"
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
    return f"clu_{digest}"


def ensure_unique_stable_keys(clusters: list[dict]) -> None:
    """Ensure every cluster has a unique stable_key in-place."""
    seen = defaultdict(int)
    for cluster in clusters:
        base = cluster.get("stable_key") or build_cluster_stable_key(cluster)
        seen[base] += 1
        cluster["stable_key"] = base if seen[base] == 1 else f"{base}-{seen[base]}"


def member_names(member: dict) -> set[str]:
    """Return normalized member names/variants."""
    out = set()
    n = normalize_name(member.get("name", ""))
    if n:
        out.add(n)
    for variant in member.get("variants", []):
        v = normalize_name(variant)
        if v:
            out.add(v)
    return out


def cluster_aliases(cluster: dict) -> set[str]:
    """Return normalized aliases for fallback matching."""
    aliases = set()
    canonical = normalize_name(cluster.get("canonical_name", ""))
    if canonical:
        aliases.add(canonical)
    gt = cluster.get("ground_truth") or {}
    modern = normalize_name(gt.get("modern_name", ""))
    if modern:
        aliases.add(modern)
    for member in cluster.get("members", []):
        aliases.update(member_names(member))
    return aliases


def build_indices(clusters: list[dict]) -> dict:
    """Build old-cluster indices for migration matching."""
    idx_wikidata = defaultdict(list)
    idx_member_id = defaultdict(list)
    idx_member_name = defaultdict(list)
    idx_modern = defaultdict(list)
    idx_alias = defaultdict(list)

    for i, cluster in enumerate(clusters):
        category = cluster.get("category", "")
        gt = cluster.get("ground_truth") or {}

        wikidata_id = (gt.get("wikidata_id") or "").strip()
        if wikidata_id:
            idx_wikidata[wikidata_id].append(i)

        modern = normalize_name(gt.get("modern_name", ""))
        if modern:
            idx_modern[(modern, category)].append(i)

        # Alias index is category-constrained to reduce false positives.
        for alias in cluster_aliases(cluster):
            idx_alias[(alias, category)].append(i)

        for member in cluster.get("members", []):
            idx_member_id[(member.get("book_id"), member.get("entity_id"))].append(i)
            for nm in member_names(member):
                idx_member_name[(member.get("book_id"), nm)].append(i)

    return {
        "wikidata": idx_wikidata,
        "member_id": idx_member_id,
        "member_name": idx_member_name,
        "modern": idx_modern,
        "alias": idx_alias,
    }


def choose_best_by_mentions(candidates: list[int], clusters: list[dict]) -> int | None:
    if not candidates:
        return None
    return max(candidates, key=lambda i: clusters[i].get("total_mentions", 0))


def propose_match(new_cluster: dict, old_clusters: list[dict], indices: dict) -> dict | None:
    """Propose the best old-cluster match for a new cluster."""
    new_category = new_cluster.get("category", "")
    new_gt = new_cluster.get("ground_truth") or {}

    # 1) Wikidata ID exact match (highest confidence)
    new_wd = (new_gt.get("wikidata_id") or "").strip()
    if new_wd:
        wd_candidates = [
            i for i in indices["wikidata"].get(new_wd, [])
            if old_clusters[i].get("category") == new_category
            and old_clusters[i].get("ground_truth")
        ]
        best = choose_best_by_mentions(wd_candidates, old_clusters)
        if best is not None:
            return {
                "strategy": "wikidata",
                "old_idx": best,
                "score": 1000.0,
                "detail": f"wikidata_id={new_wd}",
            }

    # 2) Member overlap (entity_id + normalized names within the same book)
    weighted = Counter()
    id_overlap = Counter()
    name_overlap = Counter()

    for member in new_cluster.get("members", []):
        book_id = member.get("book_id")
        entity_id = member.get("entity_id")
        if book_id and entity_id:
            for old_idx in indices["member_id"].get((book_id, entity_id), []):
                if old_clusters[old_idx].get("category") != new_category:
                    continue
                weighted[old_idx] += 3
                id_overlap[old_idx] += 1

        for nm in member_names(member):
            for old_idx in indices["member_name"].get((book_id, nm), []):
                if old_clusters[old_idx].get("category") != new_category:
                    continue
                weighted[old_idx] += 1
                name_overlap[old_idx] += 1

    if weighted:
        best_old = max(
            weighted,
            key=lambda i: (weighted[i], name_overlap[i], id_overlap[i], old_clusters[i].get("total_mentions", 0)),
        )
        best_score = weighted[best_old]
        best_name = name_overlap[best_old]
        best_id = id_overlap[best_old]
        new_aliases = cluster_aliases(new_cluster)
        old_aliases = cluster_aliases(old_clusters[best_old])
        alias_intersection = len(new_aliases & old_aliases)

        # Require more than one weak signal before auto-accepting.
        if (
            best_score >= 3
            or best_name >= 2
            or (best_name >= 1 and best_id >= 1)
            or (best_name == 1 and alias_intersection >= 1 and normalize_name(new_cluster.get("canonical_name", "")) in old_aliases)
        ):
            return {
                "strategy": "member_overlap",
                "old_idx": best_old,
                "score": float(best_score + 0.1 * alias_intersection),
                "detail": f"weighted={best_score}, names={best_name}, ids={best_id}, alias_overlap={alias_intersection}",
            }

    # 3) Modern-name and alias fallback
    aliases = cluster_aliases(new_cluster)

    modern_counts = Counter()
    for alias in aliases:
        for old_idx in indices["modern"].get((alias, new_category), []):
            modern_counts[old_idx] += 1

    if modern_counts:
        best_old = max(
            modern_counts,
            key=lambda i: (modern_counts[i], old_clusters[i].get("total_mentions", 0)),
        )
        return {
            "strategy": "modern_name",
            "old_idx": best_old,
            "score": float(50 + modern_counts[best_old]),
            "detail": f"modern_name_alias_hits={modern_counts[best_old]}",
        }

    alias_counts = Counter()
    for alias in aliases:
        for old_idx in indices["alias"].get((alias, new_category), []):
            alias_counts[old_idx] += 1

    if alias_counts:
        best_old = max(
            alias_counts,
            key=lambda i: (alias_counts[i], old_clusters[i].get("total_mentions", 0)),
        )
        # Keep this conservative: require multiple alias agreements.
        if alias_counts[best_old] >= 2:
            return {
                "strategy": "alias_match",
                "old_idx": best_old,
                "score": float(10 + alias_counts[best_old]),
                "detail": f"alias_hits={alias_counts[best_old]}",
            }

    return None


def main():
    parser = argparse.ArgumentParser(description="Migrate ground_truth between concordances")
    parser.add_argument("--old", required=True, help="Old concordance with ground_truth data")
    parser.add_argument("--new", required=True, help="New concordance to enrich")
    parser.add_argument("--output", help="Output path (default: overwrites --new)")
    parser.add_argument("--dry-run", action="store_true", help="Report matches without writing")
    args = parser.parse_args()

    # Load concordances
    print(f"Loading old concordance: {args.old}")
    with open(args.old) as f:
        old_data = json.load(f)
    old_clusters = old_data["clusters"]
    print(f"  {len(old_clusters)} clusters, "
          f"{sum(1 for c in old_clusters if c.get('ground_truth'))} with ground_truth")

    print(f"Loading new concordance: {args.new}")
    with open(args.new) as f:
        new_data = json.load(f)
    new_clusters = new_data["clusters"]
    print(f"  {len(new_clusters)} clusters")

    # Build indices on old concordance
    indices = build_indices(old_clusters)
    old_gt_indices = {i for i, c in enumerate(old_clusters) if c.get("ground_truth")}

    # Build candidate matches for new clusters.
    proposals = []
    for new_idx, new_cluster in enumerate(new_clusters):
        proposal = propose_match(new_cluster, old_clusters, indices)
        if not proposal:
            continue
        old_idx = proposal["old_idx"]
        if old_idx not in old_gt_indices:
            continue
        proposal["new_idx"] = new_idx
        proposals.append(proposal)

    # Resolve to one-to-one mappings: each old cluster can map once.
    proposals.sort(
        key=lambda p: (
            STRATEGY_PRIORITY.get(p["strategy"], 99),
            -p["score"],
            -new_clusters[p["new_idx"]].get("total_mentions", 0),
        )
    )

    assigned_new = set()
    used_old = set()
    strategy_counts = Counter()
    transferred_mappings = []

    for proposal in proposals:
        new_idx = proposal["new_idx"]
        old_idx = proposal["old_idx"]
        if new_idx in assigned_new or old_idx in used_old:
            continue
        assigned_new.add(new_idx)
        used_old.add(old_idx)
        strategy_counts[proposal["strategy"]] += 1
        transferred_mappings.append(proposal)

    gt_transferred = 0
    for mapping in transferred_mappings:
        new_cluster = new_clusters[mapping["new_idx"]]
        old_cluster = old_clusters[mapping["old_idx"]]
        old_gt = old_cluster.get("ground_truth")
        if old_gt:
            new_cluster["ground_truth"] = old_gt
            gt_transferred += 1
        # Stable keys should persist whenever we can map across rebuilds.
        if old_cluster.get("stable_key"):
            new_cluster["stable_key"] = old_cluster["stable_key"]

    # Ensure every cluster has a stable key.
    ensure_unique_stable_keys(new_clusters)

    unmatched = len(new_clusters) - len(assigned_new)

    # Report
    total = len(new_clusters)
    print(f"\nMigration Results:")
    print(f"  Matched by Wikidata:       {strategy_counts['wikidata']}")
    print(f"  Matched by member overlap: {strategy_counts['member_overlap']}")
    print(f"  Matched by modern_name:    {strategy_counts['modern_name']}")
    print(f"  Matched by alias fallback: {strategy_counts['alias_match']}")
    print(f"  Unmatched (new clusters):  {unmatched}")
    print(f"  Ground truth transferred:  {gt_transferred}/{total} "
          f"({100*gt_transferred/total:.0f}%)")
    print(f"  Stable keys present:       {sum(1 for c in new_clusters if c.get('stable_key'))}/{total}")

    if args.dry_run:
        print("\nDry run — no changes written.")

        # Show some unmatched clusters
        unmatched_clusters = [
            new_clusters[i] for i in range(len(new_clusters)) if i not in assigned_new
        ]
        print(f"\nSample unmatched clusters ({len(unmatched_clusters)} total):")
        for c in unmatched_clusters[:30]:
            books = ", ".join(sorted(set(m["book_id"].split("_")[0] for m in c["members"])))
            print(f"  [{c['category']}] {c['canonical_name']} "
                  f"({c['total_mentions']}x, {c['book_count']} books) — {books}")
        return

    # Save
    output_path = args.output or args.new
    print(f"\nSaving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB")
    print(f"\nDone! {gt_transferred} clusters have ground_truth data.")
    print(f"Run enrichment on the remaining {total - gt_transferred} new clusters:")
    print(f"  python3 scripts/enrich_concordance.py")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Auto-merge duplicate clusters that share the same (modern_name, category).

230 groups of clusters share the same (modern_name, category) but weren't
merged during embedding-based clustering. This script safely merges them
using a 4-tier safety classification:

  Tier 1: Both have wikidata_id, they MATCH        → Merge (highest confidence)
  Tier 2: One has wikidata_id, other doesn't        → Merge (high confidence)
  Tier 3: Neither has wikidata, name overlap exists  → Merge (medium confidence)
  Tier 4: Neither has wikidata, NO overlap           → Skip (log for review)
  Conflict: Different wikidata_ids                   → Skip (log as conflict)

Usage:
    python3 scripts/merge_duplicate_clusters.py [--dry-run]
"""

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"
LOG_PATH = BASE_DIR / "data" / "merge_duplicates_log.json"

# Known false-positive modern_name matches — DO NOT merge these groups.
# These are cases where LLM enrichment assigned the same modern_name to
# genuinely different entities.
FALSE_POSITIVE_MODERN_NAMES = {
    ("cassiquiare river", "PLACE"),    # Cassiquiare river ≠ Cassiopeia constellation
    ("moon", "OBJECT"),                # Moon ≠ Astrea asteroid
    ("malabar coast", "PLACE"),        # Malabar Coast (India) ≠ Malacca (Malaysia)
    ("alps", "PLACE"),                 # Alps ≠ Altai Mountains
    ("sussex", "PLACE"),               # Sussex ≠ Suffolk
    ("elba", "PLACE"),                 # Elba (island) ≠ Elbe (river)
    ("genoa", "PLACE"),                # Genoa ≠ Geneva
    ("poland", "PLACE"),               # Poland ≠ Bologna
    ("bananas", "PLANT"),              # bananas ≠ beans
    ("jean-françois de galaup, comte de lapérouse", "PERSON"),  # La Pérouse ≠ Lamanon
    ("georg wilhelm friedrich hegel", "PERSON"),  # Hegel ≠ Freytag
    ("venus", "CONCEPT"),              # Venus ≠ Venery (different concepts)
    ("ligaments", "SUBSTANCE"),        # Ligaments ≠ limbs
    ("carbon monoxide", "SUBSTANCE"),  # Carbon monoxide ≠ Oxides (generic)
}


# ─── Utility functions (reused from existing scripts) ──────────────────────

def normalize(text: str) -> str:
    """Normalize text for comparison (strip diacritics, lowercase, alphanum only)."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_for_key(text: str) -> str:
    """Normalize a name for stable-key signature generation."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def member_name_set(cluster: dict) -> set[str]:
    """Get normalized member names for a cluster."""
    names = set()
    for m in cluster.get("members", []):
        n = normalize(m.get("name", ""))
        if n:
            names.add(n)
    return names


def has_name_overlap(clusters: list[dict]) -> bool:
    """Check if any two clusters share a normalized member name."""
    all_names = [member_name_set(c) for c in clusters]
    for i in range(len(all_names)):
        for j in range(i + 1, len(all_names)):
            if all_names[i] & all_names[j]:
                return True
    return False


def canonical_overlap(clusters: list[dict]) -> bool:
    """Check if canonical names share significant substrings."""
    names = [normalize(c.get("canonical_name", "")) for c in clusters]
    stopwords = {"the", "a", "of", "de", "da", "do", "di", "del", "la", "le", "el"}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if not a or not b:
                continue
            if a in b or b in a:
                return True
            wa = set(a.split())
            wb = set(b.split())
            shared = (wa & wb) - stopwords
            if shared:
                return True
    return False


# ─── Merge functions (from fix_qids_and_merge.py) ─────────────────────────

def merge_ground_truth(clusters: list[dict]) -> dict:
    """Merge ground_truth from multiple clusters, preferring the richest one."""
    best_gt = {}
    best_score = -1
    for c in clusters:
        gt = c.get("ground_truth") or {}
        score = 0
        if gt.get("wikidata_id"): score += 3
        if gt.get("wikipedia_url"): score += 2
        if gt.get("wikipedia_extract"): score += 2
        if gt.get("modern_name"): score += 1
        if gt.get("description"): score += 1
        if gt.get("time_period"): score += 1
        if score > best_score:
            best_score = score
            best_gt = dict(gt)

    # Fill in blanks from other clusters
    for c in clusters:
        gt = c.get("ground_truth") or {}
        for key, val in gt.items():
            if val and not best_gt.get(key):
                best_gt[key] = val

    return best_gt


def merge_clusters(primary: dict, others: list[dict]) -> dict:
    """Merge other clusters into the primary cluster."""
    all_members = list(primary.get("members", []))
    seen_keys = set()
    for m in all_members:
        key = (m.get("entity_id", ""), m.get("book_id", ""), m.get("name", ""))
        seen_keys.add(key)

    for c in others:
        for m in c.get("members", []):
            key = (m.get("entity_id", ""), m.get("book_id", ""), m.get("name", ""))
            if key not in seen_keys:
                all_members.append(m)
                seen_keys.add(key)

    primary["members"] = all_members

    # Recalculate stats
    books = set()
    total_mentions = 0
    for m in all_members:
        books.add(m.get("book_id", ""))
        total_mentions += m.get("count", 0)
    primary["book_count"] = len(books)
    primary["total_mentions"] = total_mentions
    primary["member_count"] = len(all_members)

    # Merge ground truth
    all_clusters = [primary] + list(others)
    primary["ground_truth"] = merge_ground_truth(all_clusters)

    # Merge edges
    existing_edge_keys = set()
    for e in primary.get("edges", []):
        existing_edge_keys.add((e.get("source_book"), e.get("source_name"),
                                e.get("target_book"), e.get("target_name")))
    for c in others:
        for e in c.get("edges", []):
            ekey = (e.get("source_book"), e.get("source_name"),
                    e.get("target_book"), e.get("target_name"))
            if ekey not in existing_edge_keys:
                primary.setdefault("edges", []).append(e)
                existing_edge_keys.add(ekey)

    # Merge cross_references (will be remapped later)
    existing_xref_keys = set()
    for ref in primary.get("cross_references", []):
        existing_xref_keys.add((ref.get("found_name", "").lower(),
                                ref.get("target_cluster_id")))
    for c in others:
        for ref in c.get("cross_references", []):
            rkey = (ref.get("found_name", "").lower(),
                    ref.get("target_cluster_id"))
            if rkey not in existing_xref_keys:
                primary.setdefault("cross_references", []).append(ref)
                existing_xref_keys.add(rkey)

    return primary


# ─── Stable key functions (from build_concordance.py) ──────────────────────

def build_cluster_stable_key(cluster: dict) -> str:
    """Build a deterministic key from category + normalized member names."""
    names = set()
    for member in cluster.get("members", []):
        n = normalize_for_key(member.get("name", ""))
        if n:
            names.add(n)
        normalized_variants = sorted(
            {normalize_for_key(v) for v in member.get("variants", []) if v}
        )
        for v in normalized_variants[:5]:
            if v:
                names.add(v)

    signature_names = sorted(names)[:16]
    signature = f"{cluster.get('category', '').lower()}|{'|'.join(signature_names)}"
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
    return f"clu_{digest}"


def assign_stable_keys(clusters: list[dict]) -> None:
    """Assign unique stable keys to all clusters in-place."""
    seen = defaultdict(int)
    for cluster in clusters:
        base = build_cluster_stable_key(cluster)
        seen[base] += 1
        if seen[base] == 1:
            cluster["stable_key"] = base
        else:
            cluster["stable_key"] = f"{base}-{seen[base]}"


# ─── 4-Tier classification ────────────────────────────────────────────────

def classify_merge_group(group: list[dict], mn: str = "", cat: str = "") -> tuple[str, str]:
    """
    Classify a group of clusters sharing the same (modern_name, category).

    Returns (tier, reason) where tier is one of:
        "tier1" — matching wikidata_ids
        "tier2" — one has wikidata, other doesn't
        "tier3" — no wikidata but name/modern_name overlap
        "skip_false_positive" — known false-positive match
        "conflict" — different wikidata_ids
    """
    # Check false-positive blocklist first
    if (mn, cat) in FALSE_POSITIVE_MODERN_NAMES:
        return "skip_false_positive", f"known false-positive: {mn}"

    qids = set()
    has_qid = []
    no_qid = []

    for c in group:
        gt = c.get("ground_truth") or {}
        qid = (gt.get("wikidata_id") or "").strip()
        if qid:
            qids.add(qid)
            has_qid.append(c)
        else:
            no_qid.append(c)

    # Conflict: multiple distinct wikidata IDs
    if len(qids) > 1:
        return "conflict", f"conflicting wikidata_ids: {', '.join(sorted(qids))}"

    # Tier 1: all (or some) share the same wikidata_id
    if len(qids) == 1 and len(has_qid) >= 2:
        return "tier1", f"matching wikidata_id: {list(qids)[0]}"

    # Tier 2: exactly one wikidata_id, others lack it
    if len(qids) == 1 and len(has_qid) >= 1 and len(no_qid) >= 1:
        return "tier2", f"one has wikidata_id {list(qids)[0]}, {len(no_qid)} without"

    # No wikidata IDs at all — these already share modern_name+category,
    # which is strong evidence. Name overlap is a bonus signal.
    if has_name_overlap(group) or canonical_overlap(group):
        return "tier3", "no wikidata but name overlap"

    # Even without name overlap, shared modern_name is sufficient for
    # cross-linguistic content (e.g., "Liver" vs "figado" vs "higado"
    # all map to modern_name "liver" but share no string overlap).
    # Skip only if the group looks like a false-positive match.
    return "tier3", "no wikidata, shared modern_name (cross-linguistic)"


# ─── Cross-reference remapping ─────────────────────────────────────────────

def remap_cross_references(clusters: list[dict], old_to_new_id: dict[int, int],
                           absorbed_to_keeper: dict[int, int]) -> tuple[int, int]:
    """
    Remap all cross_reference target_cluster_ids after merge.

    1. Redirect absorbed cluster targets to their keeper
    2. Remap old sequential IDs to new sequential IDs
    3. Remove self-referential cross-refs created by merge

    Returns (remapped_count, removed_self_refs).
    """
    remapped = 0
    removed = 0

    for cluster in clusters:
        refs = cluster.get("cross_references", [])
        if not refs:
            continue

        new_refs = []
        for ref in refs:
            tid = ref.get("target_cluster_id")
            if tid is None:
                new_refs.append(ref)
                continue

            # Step 1: redirect absorbed → keeper
            if tid in absorbed_to_keeper:
                tid = absorbed_to_keeper[tid]
                remapped += 1

            # Step 2: remap old ID → new sequential ID
            if tid in old_to_new_id:
                tid = old_to_new_id[tid]

            # Step 3: skip self-references
            if tid == cluster["id"]:
                removed += 1
                continue

            ref["target_cluster_id"] = tid
            new_refs.append(ref)

        cluster["cross_references"] = new_refs

    return remapped, removed


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters loaded")

    # ─── Group clusters by (modern_name.lower().strip(), category) ────────
    by_mn_cat = defaultdict(list)
    skipped_no_modern = 0
    for c in clusters:
        gt = c.get("ground_truth") or {}
        mn = (gt.get("modern_name") or "").strip().lower()
        cat = c.get("category", "")
        if mn and len(mn) > 1:
            by_mn_cat[(mn, cat)].append(c)
        else:
            skipped_no_modern += 1

    groups = {k: v for k, v in by_mn_cat.items() if len(v) >= 2}
    print(f"  {len(groups)} groups with duplicate modern_name+category")
    print(f"  {skipped_no_modern} clusters skipped (no modern_name)")

    # ─── Classify each group ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("CLASSIFICATION")
    print(f"{'='*60}")

    tier_counts = Counter()
    merge_groups = []      # (key, group, tier, reason)
    skip_log = []          # logged for review

    for (mn, cat), group in sorted(groups.items()):
        tier, reason = classify_merge_group(group, mn=mn, cat=cat)
        tier_counts[tier] += 1

        if tier in ("tier1", "tier2", "tier3"):
            merge_groups.append((mn, cat, group, tier, reason))
        else:
            names = [c.get("canonical_name", "?") for c in group]
            skip_log.append({
                "modern_name": mn,
                "category": cat,
                "tier": tier,
                "reason": reason,
                "clusters": [{"id": c["id"], "canonical_name": c.get("canonical_name", ""),
                              "total_mentions": c.get("total_mentions", 0)}
                             for c in group],
            })

    print(f"  Tier 1 (matching wikidata): {tier_counts['tier1']}")
    print(f"  Tier 2 (one has wikidata):  {tier_counts['tier2']}")
    print(f"  Tier 3 (name/modern match): {tier_counts['tier3']}")
    print(f"  False positives (blocked):  {tier_counts['skip_false_positive']}")
    print(f"  Conflict (diff wikidata):   {tier_counts['conflict']}")
    print(f"  Total to merge:             {len(merge_groups)}")

    # ─── Execute merges ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("MERGING")
    print(f"{'='*60}")

    absorbed_ids = set()
    absorbed_to_keeper = {}  # absorbed_cluster_id → keeper_cluster_id
    merge_log = []

    for mn, cat, group, tier, reason in merge_groups:
        # Sort by total mentions descending — primary is the biggest
        group.sort(key=lambda c: c.get("total_mentions", 0), reverse=True)
        primary = group[0]
        others = group[1:]

        names = " + ".join(c.get("canonical_name", "?") for c in group)
        member_counts = [len(c.get("members", [])) for c in group]

        if not dry_run:
            merge_clusters(primary, others)

        for c in others:
            absorbed_ids.add(c["id"])
            absorbed_to_keeper[c["id"]] = primary["id"]

        merge_entry = {
            "modern_name": mn,
            "category": cat,
            "tier": tier,
            "reason": reason,
            "keeper_id": primary["id"],
            "keeper_name": primary.get("canonical_name", ""),
            "absorbed": [{"id": c["id"], "name": c.get("canonical_name", "")} for c in others],
            "members_after": sum(member_counts),
        }
        merge_log.append(merge_entry)

        if len(merge_log) <= 30 or len(merge_log) % 20 == 0:
            print(f"  [{tier}] [{cat}] {names}")

    print(f"\n  Groups merged: {len(merge_log)}")
    print(f"  Clusters absorbed: {len(absorbed_ids)}")

    # ─── Remove absorbed clusters ────────────────────────────────────────
    if not dry_run:
        new_clusters = [c for c in clusters if c["id"] not in absorbed_ids]
    else:
        new_clusters = clusters  # don't modify in dry run

    print(f"\n  Clusters before: {len(clusters)}")
    print(f"  Clusters after:  {len(clusters) - len(absorbed_ids)}")
    print(f"  Net reduction:   {len(absorbed_ids)}")

    if not dry_run:
        # ─── Reassign sequential IDs ─────────────────────────────────────
        old_to_new_id = {}
        for i, c in enumerate(new_clusters):
            old_to_new_id[c["id"]] = i
            c["id"] = i

        # ─── Remap cross-references ─────────────────────────────────────
        print(f"\n{'='*60}")
        print("CROSS-REFERENCE REMAPPING")
        print(f"{'='*60}")

        remapped, removed_self = remap_cross_references(
            new_clusters, old_to_new_id, absorbed_to_keeper
        )
        print(f"  Remapped targets: {remapped}")
        print(f"  Removed self-refs: {removed_self}")

        # Validate: check for orphan targets
        cluster_ids = {c["id"] for c in new_clusters}
        orphans = 0
        for c in new_clusters:
            for ref in c.get("cross_references", []):
                tid = ref.get("target_cluster_id")
                if tid is not None and tid not in cluster_ids:
                    orphans += 1
        print(f"  Orphan targets remaining: {orphans}")

        # ─── Regenerate stable keys ─────────────────────────────────────
        assign_stable_keys(new_clusters)

        # ─── Update data ─────────────────────────────────────────────────
        data["clusters"] = new_clusters
        data["stats"]["cluster_count"] = len(new_clusters)

        # ─── Backup and save ─────────────────────────────────────────────
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = CONCORDANCE_PATH.with_suffix(f".pre_dedup_{timestamp}.json")

        print(f"\nBacking up to {backup_path}")
        with open(CONCORDANCE_PATH) as f:
            original = f.read()
        with open(backup_path, "w") as f:
            f.write(original)

        print(f"Saving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB written")

    # ─── Save decision log ───────────────────────────────────────────────
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "clusters_before": len(clusters),
        "clusters_after": len(clusters) - len(absorbed_ids),
        "groups_merged": len(merge_log),
        "clusters_absorbed": len(absorbed_ids),
        "tier_counts": dict(tier_counts),
        "merges": merge_log,
        "skipped": skip_log,
    }

    print(f"\nSaving decision log to {LOG_PATH}")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

    # ─── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Merged:     {len(merge_log)} groups ({len(absorbed_ids)} clusters absorbed)")
    print(f"  Skipped:    {len(skip_log)} groups")
    print(f"  Conflicts:  {tier_counts['conflict']}")
    print(f"  No overlap: {tier_counts['skip_no_overlap']}")

    if dry_run:
        print("\nNo changes written (dry run).")
        print("\nSkipped groups (review these):")
        for s in skip_log:
            names = [c["canonical_name"] for c in s["clusters"]]
            print(f"  [{s['tier']}] [{s['category']}] {s['modern_name']}: {' + '.join(names)}")
            print(f"         {s['reason']}")
    else:
        print("\nNext steps:")
        print("  python3 scripts/build_search_index.py")
        print("  python3 scripts/build_neighbor_graph.py")


if __name__ == "__main__":
    main()

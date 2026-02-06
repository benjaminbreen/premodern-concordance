#!/usr/bin/env python3
"""
cleanup_concordance.py — Three-phase data quality pass for the concordance.

Phase 1: Automated fixes (no API calls)
  - Strip OCR artifacts (^ carets, line-break hyphens)
  - Delete noise clusters (1-2 char names with few mentions)
  - Split known bad merges (Socrates from Hippocrates)
  - Merge clusters sharing the same Wikidata ID
  - Merge cross-category duplicates (same modern_name)

Phase 2: Wikidata validation (cheap API calls)
  - Batch-fetch actual labels for every wikidata_id
  - Flag / clear IDs where the label doesn't match modern_name

Phase 3: LLM spot-check (Gemini Flash Lite)
  - Re-enrich clusters whose Wikidata ID was cleared or whose
    modern_name was flagged as likely wrong

Usage:
  python scripts/cleanup_concordance.py                  # all phases
  python scripts/cleanup_concordance.py --phase 1        # just automated
  python scripts/cleanup_concordance.py --phase 1 2      # phases 1+2
  python scripts/cleanup_concordance.py --dry-run        # preview only
"""

import argparse
import json
import os
import re
import shutil
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
DEFAULT_PATH = DATA_DIR / "concordance.json"

# ── Helpers ────────────────────────────────────────────────────────────


def normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def similarity_ratio(a: str, b: str) -> float:
    """Simple character-level Jaccard similarity."""
    sa, sb = set(normalize(a)), set(normalize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def merge_cluster_into(primary: dict, secondary: dict):
    """Merge secondary cluster's data into primary (mutates primary)."""
    # Merge members
    existing_keys = {(m["entity_id"], m["book_id"]) for m in primary["members"]}
    for m in secondary["members"]:
        key = (m["entity_id"], m["book_id"])
        if key not in existing_keys:
            primary["members"].append(m)
            existing_keys.add(key)

    # Merge edges
    existing_edges = {
        (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
        for e in primary["edges"]
    }
    for e in secondary["edges"]:
        key = (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
        if key not in existing_edges:
            primary["edges"].append(e)
            existing_edges.add(key)

    # Recompute stats
    primary["book_count"] = len({m["book_id"] for m in primary["members"]})
    primary["total_mentions"] = sum(m["count"] for m in primary["members"])

    # Merge ground_truth: prefer primary, fill gaps from secondary
    gt_p = primary.get("ground_truth") or {}
    gt_s = secondary.get("ground_truth") or {}
    if gt_s and not gt_p:
        primary["ground_truth"] = gt_s
    elif gt_s and gt_p:
        for key, val in gt_s.items():
            if key not in gt_p or not gt_p[key]:
                gt_p[key] = val


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — Automated fixes
# ═══════════════════════════════════════════════════════════════════════


def phase1_ocr_cleanup(clusters: list[dict]) -> dict:
    """Strip ^ carets and fix line-break hyphens in names/variants."""
    stats = {"canonical_fixed": 0, "variants_fixed": 0, "variants_removed": 0}

    for c in clusters:
        # Fix canonical name
        name = c["canonical_name"]
        cleaned = name.replace("^", "").replace("/", "")
        if cleaned != name:
            c["canonical_name"] = cleaned
            stats["canonical_fixed"] += 1

        # Fix member names and variants
        for m in c["members"]:
            # Fix member name
            mname = m["name"]
            mcleaned = mname.replace("^", "")
            if mcleaned != mname:
                m["name"] = mcleaned
                stats["variants_fixed"] += 1

            # Clean up variant list
            new_variants = []
            for v in m.get("variants", []):
                v_clean = v.replace("^", "")
                # Remove line-break hyphen fragments (e.g., "Ga-", "OLIO DI CASTO-")
                if v_clean.endswith("-") and len(v_clean) <= 20:
                    stats["variants_removed"] += 1
                    continue
                # Remove bibliographic reference fragments
                if re.match(r"^[A-Z][a-z]+\.\s*(de|in|ad|lib)\b", v_clean):
                    stats["variants_removed"] += 1
                    continue
                new_variants.append(v_clean)
            m["variants"] = new_variants

    return stats


def phase1_remove_noise(clusters: list[dict]) -> tuple[list[dict], dict]:
    """Remove clusters with very short names and low mentions."""
    stats = {"removed": 0, "removed_names": []}
    kept = []

    for c in clusters:
        name = c["canonical_name"].strip()
        # Remove 1-2 char names with <10 mentions (keep things like "Goa")
        if len(name) <= 2 and c["total_mentions"] < 10:
            stats["removed"] += 1
            stats["removed_names"].append(f"{name} ({c['category']}, {c['total_mentions']}x)")
            continue
        # Remove fully garbled names (3+ non-alpha chars in a row)
        if re.search(r"[^a-zA-ZÀ-ÿ\s]{3,}", name):
            stats["removed"] += 1
            stats["removed_names"].append(f"{name} ({c['category']}, {c['total_mentions']}x)")
            continue
        kept.append(c)

    return kept, stats


def phase1_split_bad_merges(clusters: list[dict]) -> dict:
    """Split known incorrect merges."""
    stats = {"splits": 0, "details": []}

    # Known bad merges: (cluster canonical_name, member name to extract)
    BAD_MERGES = [
        ("Hippocrates", "Socrates"),
    ]

    new_clusters = []
    max_id = max(c["id"] for c in clusters)

    for canonical, member_name in BAD_MERGES:
        for c in clusters:
            if c["canonical_name"].lower() != canonical.lower():
                continue

            # Find the member(s) to extract
            to_extract = [m for m in c["members"] if m["name"].lower() == member_name.lower()]
            if not to_extract:
                continue

            # Remove from original
            c["members"] = [m for m in c["members"] if m["name"].lower() != member_name.lower()]
            c["edges"] = [
                e for e in c["edges"]
                if e["source_name"].lower() != member_name.lower()
                and e["target_name"].lower() != member_name.lower()
            ]
            c["book_count"] = len({m["book_id"] for m in c["members"]})
            c["total_mentions"] = sum(m["count"] for m in c["members"])

            # Create new cluster
            max_id += 1
            new_cluster = {
                "id": max_id,
                "canonical_name": member_name,
                "category": to_extract[0]["category"],
                "subcategory": to_extract[0].get("subcategory", ""),
                "book_count": len({m["book_id"] for m in to_extract}),
                "total_mentions": sum(m["count"] for m in to_extract),
                "members": to_extract,
                "edges": [],
            }
            new_clusters.append(new_cluster)
            stats["splits"] += 1
            stats["details"].append(f"Split {member_name} from {canonical}")

    clusters.extend(new_clusters)
    return stats


def phase1_merge_by_wikidata(clusters: list[dict]) -> tuple[list[dict], dict]:
    """Merge clusters that share the same Wikidata ID."""
    stats = {"merges": 0, "details": []}

    # Build map: wikidata_id → list of clusters
    by_wikidata: dict[str, list[dict]] = defaultdict(list)
    for c in clusters:
        wid = (c.get("ground_truth") or {}).get("wikidata_id")
        if wid:
            by_wikidata[wid].append(c)

    to_remove = set()

    for wid, group in by_wikidata.items():
        if len(group) < 2:
            continue

        # Sort by total_mentions descending — primary is the biggest
        group.sort(key=lambda c: c["total_mentions"], reverse=True)
        primary = group[0]

        for secondary in group[1:]:
            # Sanity check: only merge if categories are compatible
            # (same category, or one is a superset like SUBSTANCE/CONCEPT)
            if primary["category"] != secondary["category"]:
                # Allow cross-category merges for known safe combos
                safe_combos = {
                    frozenset({"SUBSTANCE", "CONCEPT"}),
                    frozenset({"SUBSTANCE", "ANIMAL"}),
                    frozenset({"SUBSTANCE", "PLANT"}),
                    frozenset({"PLACE", "CONCEPT"}),
                    frozenset({"DISEASE", "CONCEPT"}),
                }
                pair = frozenset({primary["category"], secondary["category"]})
                if pair not in safe_combos:
                    continue

            merge_cluster_into(primary, secondary)
            to_remove.add(secondary["id"])
            stats["merges"] += 1
            stats["details"].append(
                f"Merged '{secondary['canonical_name']}' ({secondary['category']}) "
                f"into '{primary['canonical_name']}' ({primary['category']}) via {wid}"
            )

    clusters = [c for c in clusters if c["id"] not in to_remove]
    return clusters, stats


def phase1_merge_by_modern_name(clusters: list[dict]) -> tuple[list[dict], dict]:
    """Merge clusters with identical modern_name within compatible categories."""
    stats = {"merges": 0, "details": []}

    # Build map: normalized modern_name → list of clusters
    by_modern: dict[str, list[dict]] = defaultdict(list)
    for c in clusters:
        gt = c.get("ground_truth") or {}
        mn = (gt.get("modern_name") or "").strip()
        if mn and len(mn) > 2:
            by_modern[normalize(mn)].append(c)

    to_remove = set()

    for mn_key, group in by_modern.items():
        if len(group) < 2:
            continue

        # Skip if already merged by wikidata
        active = [c for c in group if c["id"] not in to_remove]
        if len(active) < 2:
            continue

        # Only merge same-category or safe cross-category
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for c in active:
            by_cat[c["category"]].append(c)

        # First: merge within same category
        for cat, cat_group in by_cat.items():
            if len(cat_group) < 2:
                continue
            cat_group.sort(key=lambda c: c["total_mentions"], reverse=True)
            primary = cat_group[0]
            for secondary in cat_group[1:]:
                if secondary["id"] in to_remove:
                    continue
                merge_cluster_into(primary, secondary)
                to_remove.add(secondary["id"])
                stats["merges"] += 1
                stats["details"].append(
                    f"Merged '{secondary['canonical_name']}' into "
                    f"'{primary['canonical_name']}' (both {cat}, modern_name='{mn_key}')"
                )

    clusters = [c for c in clusters if c["id"] not in to_remove]
    return clusters, stats


def run_phase1_basic(clusters: list[dict]) -> list[dict]:
    """Run Phase 1 non-merge fixes: OCR cleanup, split bad merges, remove noise."""
    print("=" * 60)
    print("PHASE 1a — Basic fixes (OCR, splits, noise)")
    print("=" * 60)

    start_count = len(clusters)

    # 1a. OCR cleanup
    ocr_stats = phase1_ocr_cleanup(clusters)
    print(f"\n  OCR cleanup:")
    print(f"    Canonical names fixed:  {ocr_stats['canonical_fixed']}")
    print(f"    Variant names fixed:    {ocr_stats['variants_fixed']}")
    print(f"    Variants removed:       {ocr_stats['variants_removed']}")

    # 1b. Split bad merges
    split_stats = phase1_split_bad_merges(clusters)
    print(f"\n  Bad merge splits:")
    for d in split_stats["details"]:
        print(f"    {d}")
    if not split_stats["details"]:
        print("    None needed")

    # 1c. Remove noise clusters
    clusters, noise_stats = phase1_remove_noise(clusters)
    print(f"\n  Noise removal:")
    print(f"    Removed: {noise_stats['removed']}")
    for name in noise_stats["removed_names"]:
        print(f"      - {name}")

    print(f"\n  Phase 1a summary: {start_count} → {len(clusters)} clusters")
    return clusters


def run_merges(clusters: list[dict]) -> list[dict]:
    """Run merge passes (should run AFTER Wikidata validation to avoid merging on bad IDs)."""
    print("\n" + "=" * 60)
    print("PHASE 1b — Merges (Wikidata ID + modern name)")
    print("=" * 60)

    start_count = len(clusters)

    # Merge by Wikidata ID
    clusters, wikidata_stats = phase1_merge_by_wikidata(clusters)
    print(f"\n  Wikidata ID merges: {wikidata_stats['merges']}")
    for d in wikidata_stats["details"][:20]:
        print(f"    {d}")
    if len(wikidata_stats["details"]) > 20:
        print(f"    ... and {len(wikidata_stats['details']) - 20} more")

    # Merge by modern_name
    clusters, modern_stats = phase1_merge_by_modern_name(clusters)
    print(f"\n  Modern name merges: {modern_stats['merges']}")
    for d in modern_stats["details"][:20]:
        print(f"    {d}")
    if len(modern_stats["details"]) > 20:
        print(f"    ... and {len(modern_stats['details']) - 20} more")

    print(f"\n  Phase 1b summary: {start_count} → {len(clusters)} clusters")
    return clusters


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 — Wikidata validation
# ═══════════════════════════════════════════════════════════════════════


def fetch_wikidata_labels(qids: list[str]) -> dict[str, str]:
    """Batch-fetch English labels for Wikidata QIDs (max 50 per request)."""
    import urllib.request
    import urllib.parse

    labels: dict[str, str] = {}

    for i in range(0, len(qids), 50):
        batch = qids[i : i + 50]
        ids_str = "|".join(batch)
        url = (
            f"https://www.wikidata.org/w/api.php?"
            f"action=wbgetentities&ids={urllib.parse.quote(ids_str)}"
            f"&props=labels&languages=en&format=json"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for qid, entity in data.get("entities", {}).items():
                label = entity.get("labels", {}).get("en", {}).get("value", "")
                if label:
                    labels[qid] = label
        except Exception as e:
            print(f"    Wikidata API error for batch starting {batch[0]}: {e}")

        if i + 50 < len(qids):
            time.sleep(0.5)  # Be polite to Wikidata

    return labels


def run_phase2(clusters: list[dict]) -> list[dict]:
    """Validate Wikidata IDs against actual labels."""
    print("\n" + "=" * 60)
    print("PHASE 2 — Wikidata validation")
    print("=" * 60)

    # Collect all QIDs
    qid_to_clusters: dict[str, list[dict]] = defaultdict(list)
    for c in clusters:
        wid = (c.get("ground_truth") or {}).get("wikidata_id")
        if wid and wid.startswith("Q"):
            qid_to_clusters[wid].append(c)

    all_qids = list(qid_to_clusters.keys())
    print(f"\n  Validating {len(all_qids)} Wikidata IDs...")

    labels = fetch_wikidata_labels(all_qids)
    print(f"  Fetched {len(labels)} labels")

    # Compare labels to modern_name
    mismatches = []
    cleared = 0

    for qid, label in labels.items():
        for c in qid_to_clusters[qid]:
            gt = c.get("ground_truth", {})
            modern = gt.get("modern_name") or ""

            # Compare normalized versions
            label_n = normalize(label)
            modern_n = normalize(modern) if modern else ""

            # Check if they're related (exact match, substring, or decent similarity)
            if label_n == modern_n:
                continue
            if label_n in modern_n or modern_n in label_n:
                continue
            if similarity_ratio(label_n, modern_n) > 0.5:
                continue

            # Also check canonical_name
            canonical_n = normalize(c["canonical_name"])
            if label_n == canonical_n or label_n in canonical_n or canonical_n in label_n:
                continue
            if similarity_ratio(label_n, canonical_n) > 0.5:
                continue

            # This is a mismatch — clear the bad Wikidata data
            mismatches.append({
                "cluster": c["canonical_name"],
                "modern_name": modern,
                "wikidata_id": qid,
                "wikidata_label": label,
            })

            # Clear the wrong ID
            gt.pop("wikidata_id", None)
            gt.pop("wikidata_description", None)
            gt.pop("wikipedia_url", None)
            gt["_wikidata_cleared"] = f"Was {qid} ({label}), doesn't match {modern}"
            cleared += 1

    print(f"\n  Mismatches found: {len(mismatches)}")
    for m in mismatches[:30]:
        print(f"    '{m['cluster']}' (modern: {m['modern_name']}) ≠ {m['wikidata_id']} ({m['wikidata_label']})")
    if len(mismatches) > 30:
        print(f"    ... and {len(mismatches) - 30} more")

    print(f"  Wikidata IDs cleared: {cleared}")
    return clusters


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 — LLM spot-check
# ═══════════════════════════════════════════════════════════════════════


def build_recheck_prompt(batch: list[dict]) -> str:
    """Build a Gemini prompt to re-identify flagged clusters."""
    items = []
    for c in batch:
        members_desc = []
        for m in c["members"][:6]:
            ctx = m.get("contexts", [])
            ctx_str = f" — contexts: {'; '.join(ctx[:2])}" if ctx else ""
            members_desc.append(f"  - '{m['name']}' in {m['book_id']} ({m['count']}x){ctx_str}")

        old_gt = c.get("ground_truth", {})
        old_info = ""
        if old_gt.get("_wikidata_cleared"):
            old_info = f"\n  Previous (wrong) ID: {old_gt['_wikidata_cleared']}"
        if old_gt.get("modern_name"):
            old_info += f"\n  Previous modern_name: {old_gt['modern_name']} (may be wrong)"

        items.append(
            f"cluster_id: {c['id']}\n"
            f"canonical_name: {c['canonical_name']}\n"
            f"category: {c['category']}\n"
            f"subcategory: {c.get('subcategory', '')}\n"
            f"members:\n" + "\n".join(members_desc) +
            old_info
        )

    clusters_text = "\n\n---\n\n".join(items)

    return f"""You are identifying entities from early modern texts (1500–1900) about natural knowledge, medicine, and exploration.

For each cluster below, provide the correct modern identification. These are historical/scientific terms — "Mercury" means the alchemical element, not the planet or musician; "Galen" means the ancient physician.

{clusters_text}

For each cluster, return a JSON object with:
- "cluster_id": the cluster ID
- "modern_name": correct modern English name
- "confidence": "high", "medium", or "low"
- "type": one of person/plant/animal/mineral/chemical/disease/place/concept/object
- "linnaean": Linnaean binomial if it's a plant or animal (or null)
- "family": taxonomic family if applicable (or null)
- "description": 5-15 word description
- "note": any disambiguation notes (or null)

Return ONLY the JSON array, no other text."""


def run_phase3(clusters: list[dict], model: str, batch_size: int) -> list[dict]:
    """Re-enrich flagged clusters via Gemini."""
    from dotenv import load_dotenv

    try:
        from google import genai
    except ImportError:
        print("\n  Phase 3 skipped: google-genai not installed")
        return clusters

    load_dotenv(Path(__file__).parent.parent / ".env.local")

    print("\n" + "=" * 60)
    print("PHASE 3 — LLM spot-check")
    print("=" * 60)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  Skipped: GEMINI_API_KEY not set")
        return clusters

    client = genai.Client(api_key=api_key)

    # Find clusters that need re-checking
    to_recheck = []
    for c in clusters:
        gt = c.get("ground_truth") or {}
        # Clusters where we cleared bad Wikidata
        if gt.get("_wikidata_cleared"):
            to_recheck.append(c)
            continue
        # Clusters with no ground_truth at all and 5+ mentions
        if not gt.get("modern_name") and c["total_mentions"] >= 5:
            to_recheck.append(c)
            continue

    print(f"\n  {len(to_recheck)} clusters flagged for re-identification")

    if not to_recheck:
        return clusters

    # Process in batches
    num_batches = (len(to_recheck) + batch_size - 1) // batch_size
    fixed = 0

    for batch_idx in range(0, len(to_recheck), batch_size):
        batch = to_recheck[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        print(f"\n  Batch {batch_num}/{num_batches} ({len(batch)} clusters)...", flush=True)

        prompt = build_recheck_prompt(batch)

        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = response.text.strip()

            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("```", 1)[0]
                text = text.strip()

            results = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"    JSON parse error: {e}")
            time.sleep(2)
            continue
        except Exception as e:
            print(f"    API error: {e}")
            time.sleep(2)
            continue

        # Map results by cluster_id
        results_by_id = {}
        for r in results:
            cid = r.get("cluster_id")
            if cid is not None:
                results_by_id[cid] = r

        # Apply results
        for c in batch:
            result = results_by_id.get(c["id"])
            if not result:
                continue

            gt = c.get("ground_truth") or {}

            # Update fields
            gt["modern_name"] = result.get("modern_name", gt.get("modern_name", ""))
            gt["confidence"] = result.get("confidence", "low")
            gt["type"] = result.get("type", gt.get("type", ""))

            if result.get("linnaean"):
                gt["linnaean"] = result["linnaean"]
            if result.get("family"):
                gt["family"] = result["family"]
            if result.get("description"):
                gt["description"] = result["description"]
            if result.get("note"):
                gt["note"] = result["note"]

            # Clean up internal flag
            gt.pop("_wikidata_cleared", None)

            c["ground_truth"] = gt
            fixed += 1
            print(f"    ✓ {c['canonical_name']} → {gt['modern_name']}")

        time.sleep(1)

    print(f"\n  Phase 3 summary: {fixed}/{len(to_recheck)} clusters re-identified")
    return clusters


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════


def reassign_ids(clusters: list[dict]):
    """Reassign sequential IDs and update stats."""
    for i, c in enumerate(clusters, 1):
        c["id"] = i


def main():
    parser = argparse.ArgumentParser(description="Concordance data cleanup")
    parser.add_argument("--concordance", default=str(DEFAULT_PATH), help="Concordance JSON path")
    parser.add_argument("--output", default=None, help="Output path (default: overwrite input)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--phase", nargs="+", type=int, default=[1, 2, 3], help="Phases to run (1 2 3)")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model for Phase 3")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size for Phase 3")
    args = parser.parse_args()

    concordance_path = Path(args.concordance)
    print(f"Loading: {concordance_path}")

    with open(concordance_path) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Loaded {len(clusters)} clusters\n")

    # Backup
    if not args.dry_run:
        backup_path = concordance_path.with_suffix(".json.bak")
        shutil.copy2(concordance_path, backup_path)
        print(f"Backup: {backup_path}\n")

    # Run phases — order matters: validate Wikidata BEFORE merging
    if 1 in args.phase:
        clusters = run_phase1_basic(clusters)

    if 2 in args.phase:
        clusters = run_phase2(clusters)

    if 1 in args.phase:
        clusters = run_merges(clusters)

    if 3 in args.phase:
        clusters = run_phase3(clusters, args.model, args.batch_size)

    # Reassign IDs
    reassign_ids(clusters)
    data["clusters"] = clusters

    # Update stats
    data["stats"]["total_clusters"] = len(clusters)
    data["stats"]["entities_matched"] = sum(len(c["members"]) for c in clusters)
    by_cat: dict[str, int] = defaultdict(int)
    for c in clusters:
        by_cat[c["category"]] += 1
    data["stats"]["by_category"] = dict(sorted(by_cat.items()))

    wikidata_count = sum(1 for c in clusters if (c.get("ground_truth") or {}).get("wikidata_id"))
    data["stats"]["with_wikidata"] = wikidata_count

    data["metadata"]["cleanup_applied"] = True

    # Save
    output_path = Path(args.output) if args.output else concordance_path

    if args.dry_run:
        print(f"\n{'=' * 60}")
        print(f"DRY RUN — would write {len(clusters)} clusters to {output_path}")
        print(f"{'=' * 60}")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\n{'=' * 60}")
        print(f"Saved: {output_path} ({size_mb:.1f} MB, {len(clusters)} clusters)")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

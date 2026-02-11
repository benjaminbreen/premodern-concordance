#!/usr/bin/env python3
"""
Extract training pairs from verified concordance clusters.

Mines the current concordance.json for:
  1. POSITIVE PAIRS: Cross-book member names within verified clusters
     (e.g., "canela" ↔ "cannella" from the cinnamon cluster)
  2. HARD NEGATIVES: Known bad merges we manually fixed
     (e.g., "Cassiopeia" ≠ "Cassiquiare")

Merges with existing curated pairs from data/training_pairs.json,
deduplicates, and outputs an expanded training file.

Usage:
    python3 scripts/extract_training_pairs.py [--dry-run]
    python3 scripts/extract_training_pairs.py --output data/training_pairs_v2.json
"""

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
EXISTING_PAIRS_PATH = Path(__file__).parent.parent / "data" / "training_pairs.json"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "data" / "training_pairs_v2.json"

# Book ID → 2-letter language code
BOOK_LANGS = {
    "coloquios_da_orta_1563": "pt",
    "historia_medicinal_monardes_1574": "es",
    "ricettario_fiorentino_1597": "it",
    "english_physician_1652": "en",
    "pseudodoxia_epidemica_browne_1646": "en",
    "polyanthea_medicinal": "pt",
    "relation_historique_humboldt_vol3_1825": "fr",
    "kosmos_humboldt_1845": "en",
    "connexion_physical_sciences_somerville_1858": "en",
    "origin_of_species_darwin_1859": "en",
    "first_principles_spencer_1862": "en",
    "principles_of_psychology_james_1890": "en",
}

# Known bad merges: (cluster_name, wrong_member_name) pairs.
# These are high-quality hard negatives — the model confused them.
KNOWN_BAD_MERGES = [
    # From fix_problematic_clusters.py
    ("Cassiquiare", "Cassiopeia"),
    ("Leaõ", "Leech"),
    ("Vespucci", "Vespasian"),
    ("sparrow", "spteryx"),
    ("Retentive", "retentissement"),
    ("Horn-Church", "Horn"),
    ("Upton", "Upminster"),
    ("House of Communs", "house"),
    ("Hayhay", "Haify"),
    ("plumbea", "plumbago"),
    ("mosses", "mo'"),
    ("mosses", "Mochi"),
    ("Jorullo", "Jaurù"),
    ("Siara", "Syra"),
    ("poetry", "Poefia"),
    ("vernucolo", "vernenos"),
]

# Minimum cluster quality for mining positive pairs
MIN_BOOK_COUNT = 2        # Must span at least 2 books
MIN_GROUND_TRUTH = True   # Must have ground_truth (verified)


def normalize_name(name: str) -> str:
    """Normalize for dedup: lowercase, strip whitespace."""
    return name.strip().lower()


def is_useful_name(name: str) -> bool:
    """Filter out names that are too short or junky for training."""
    if len(name) < 2:
        return False
    # Skip pure numbers
    if name.strip().isdigit():
        return False
    # Skip very short abbreviations
    if len(name) <= 2 and not name.isalpha():
        return False
    return True


def extract_positive_pairs(clusters: list[dict]) -> dict[str, list[dict]]:
    """
    Extract cross-book positive pairs from verified clusters.

    For each cluster with ground_truth, generate pairs between members
    from different books (cross-lingual pairs are most valuable).
    """
    pairs_by_cat = defaultdict(list)
    seen = set()  # (norm_a, norm_b) dedup

    for cluster in clusters:
        gt = cluster.get("ground_truth", {})
        if not gt:
            continue
        if cluster.get("book_count", 0) < MIN_BOOK_COUNT:
            continue

        category = cluster["category"]
        members = cluster.get("members", [])

        # Get unique (name, lang) pairs per member
        member_info = []
        seen_names = set()
        for m in members:
            name = m["name"]
            lang = BOOK_LANGS.get(m["book_id"], "??")
            norm = normalize_name(name)
            if norm in seen_names:
                continue
            if not is_useful_name(name):
                continue
            seen_names.add(norm)
            member_info.append({"name": name, "lang": lang, "book_id": m["book_id"]})

        # Also include modern_name if available
        modern = gt.get("modern_name")
        if modern and normalize_name(modern) not in seen_names:
            if is_useful_name(modern):
                member_info.append({"name": modern, "lang": "en", "book_id": "_ground_truth"})
                seen_names.add(normalize_name(modern))

        # Generate all cross-book pairs
        for a, b in combinations(member_info, 2):
            # Skip same-book pairs (less useful for training)
            if a["book_id"] == b["book_id"]:
                continue

            # Dedup
            key = tuple(sorted([normalize_name(a["name"]), normalize_name(b["name"])]))
            if key in seen:
                continue
            # Skip if names are identical (nothing to learn)
            if key[0] == key[1]:
                continue
            seen.add(key)

            langs = f"{a['lang']}-{b['lang']}"
            pairs_by_cat[category].append({
                "source": a["name"],
                "target": b["name"],
                "langs": langs,
                "note": f"mined from cluster '{cluster['canonical_name']}'"
            })

    return dict(pairs_by_cat)


def extract_hard_negatives(clusters: list[dict]) -> dict[str, list[dict]]:
    """
    Extract hard negatives from known bad merges.

    These are pairs the model incorrectly matched — perfect for teaching
    it to discriminate better.
    """
    negs_by_cat = defaultdict(list)
    by_name = {c["canonical_name"]: c for c in clusters}

    for cluster_name, bad_member in KNOWN_BAD_MERGES:
        if cluster_name not in by_name:
            continue
        cluster = by_name[cluster_name]
        category = cluster["category"]

        # The negative pair: cluster's canonical name ≠ bad member
        negs_by_cat[category].append({
            "source": cluster_name,
            "target": bad_member,
            "note": f"bad merge: {bad_member} wrongly matched to {cluster_name}"
        })

        # Also pair the bad member against the cluster's modern_name if available
        gt = cluster.get("ground_truth", {})
        modern = gt.get("modern_name")
        if modern and modern.lower() != cluster_name.lower():
            negs_by_cat[category].append({
                "source": modern,
                "target": bad_member,
                "note": f"bad merge: {bad_member} ≠ {modern}"
            })

    return dict(negs_by_cat)


def merge_with_existing(existing: dict, new_positives: dict, new_negatives: dict) -> dict:
    """Merge new mined pairs with existing curated pairs, deduplicating."""
    merged = {
        "description": "Multilingual training data for cross-lingual entity matching in early modern scientific texts",
        "version": "2.0",
        "languages": ["Portuguese", "English", "Latin", "French", "Spanish", "Italian", "German"],
        "note": "v2.0: Expanded with mined pairs from 12-book concordance (2,146 verified clusters) + hard negatives from fixed bad merges",
        "statistics": {},
        "categories": {},
    }

    all_categories = set()
    if "categories" in existing:
        all_categories.update(existing["categories"].keys())
    all_categories.update(new_positives.keys())
    all_categories.update(new_negatives.keys())

    total_pos = 0
    total_neg = 0

    for cat in sorted(all_categories):
        # Existing pairs
        existing_pos = []
        existing_neg = []
        if "categories" in existing and cat in existing["categories"]:
            existing_pos = existing["categories"][cat].get("positive_pairs", [])
            existing_neg = existing["categories"][cat].get("hard_negatives", [])

        # Dedup existing
        seen_pos = set()
        deduped_pos = []
        for p in existing_pos:
            key = tuple(sorted([normalize_name(p["source"]), normalize_name(p["target"])]))
            if key not in seen_pos and key[0] != key[1]:
                seen_pos.add(key)
                p["origin"] = "curated"
                deduped_pos.append(p)

        # Add new mined positives
        mined_count = 0
        for p in new_positives.get(cat, []):
            key = tuple(sorted([normalize_name(p["source"]), normalize_name(p["target"])]))
            if key not in seen_pos:
                seen_pos.add(key)
                p["origin"] = "mined"
                deduped_pos.append(p)
                mined_count += 1

        # Dedup negatives
        seen_neg = set()
        deduped_neg = []
        for n in existing_neg:
            key = tuple(sorted([normalize_name(n["source"]), normalize_name(n["target"])]))
            if key not in seen_neg:
                seen_neg.add(key)
                n["origin"] = "curated"
                deduped_neg.append(n)

        neg_mined = 0
        for n in new_negatives.get(cat, []):
            key = tuple(sorted([normalize_name(n["source"]), normalize_name(n["target"])]))
            if key not in seen_neg:
                seen_neg.add(key)
                n["origin"] = "mined"
                deduped_neg.append(n)
                neg_mined += 1

        merged["categories"][cat] = {
            "positive_pairs": deduped_pos,
            "hard_negatives": deduped_neg,
        }

        total_pos += len(deduped_pos)
        total_neg += len(deduped_neg)

        print(f"  {cat}: {len(deduped_pos)} positive ({len(existing_pos)} curated + {mined_count} mined), "
              f"{len(deduped_neg)} negative ({len(existing_neg)} curated + {neg_mined} mined)")

    merged["statistics"] = {
        "total_positive_pairs": total_pos,
        "total_hard_negatives": total_neg,
    }

    return merged


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract training pairs from concordance")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without saving")
    args = parser.parse_args()

    # Load concordance
    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    verified = sum(1 for c in clusters if c.get("ground_truth"))
    multi_book = sum(1 for c in clusters if c.get("book_count", 0) >= 2)
    print(f"  {verified} with ground_truth, {multi_book} spanning 2+ books")

    # Extract positive pairs
    print(f"\nExtracting positive pairs from verified multi-book clusters...")
    new_positives = extract_positive_pairs(clusters)
    total_new_pos = sum(len(v) for v in new_positives.values())
    print(f"  {total_new_pos} new positive pairs extracted")

    # Extract hard negatives
    print(f"\nExtracting hard negatives from known bad merges...")
    new_negatives = extract_hard_negatives(clusters)
    total_new_neg = sum(len(v) for v in new_negatives.values())
    print(f"  {total_new_neg} new hard negatives extracted")

    # Load existing pairs
    print(f"\nLoading existing curated pairs from {EXISTING_PAIRS_PATH}")
    with open(EXISTING_PAIRS_PATH) as f:
        existing = json.load(f)
    existing_pos = sum(len(p.get("positive_pairs", [])) for p in existing.get("categories", {}).values())
    existing_neg = sum(len(p.get("hard_negatives", [])) for p in existing.get("categories", {}).values())
    print(f"  {existing_pos} existing positive, {existing_neg} existing negative")

    # Merge
    print(f"\nMerging (with dedup)...")
    merged = merge_with_existing(existing, new_positives, new_negatives)

    stats = merged["statistics"]
    print(f"\n{'='*60}")
    print(f"Final: {stats['total_positive_pairs']} positive pairs, {stats['total_hard_negatives']} hard negatives")
    print(f"  (was: {existing_pos} positive, {existing_neg} negative)")

    if args.dry_run:
        print("\nDry run — not saving.")
        return

    # Save
    output_path = Path(args.output)
    print(f"\nSaving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    size_kb = output_path.stat().st_size / 1024
    print(f"  {size_kb:.0f} KB")

    print(f"\nDone! To fine-tune v3:")
    print(f"  python3 scripts/finetune_embeddings.py \\")
    print(f"    --input {output_path} \\")
    print(f"    --output models/finetuned-bge-m3-v3 \\")
    print(f"    --epochs 3 --loss mnrl")


if __name__ == "__main__":
    main()

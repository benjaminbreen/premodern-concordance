#!/usr/bin/env python3
"""
Clean up bad variants in entity files and concordance using normalized edit distance.

Removes false variant matches like "Ga" for "Galen" and "San Antonio" for "Antilles".
Also removes mentions that were only found via the bad variants.

Usage:
    python3 scripts/clean_variants.py --dry-run     # preview changes
    python3 scripts/clean_variants.py               # apply changes
"""

import argparse
import json
import shutil
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"

# --- Metrics ---

MIN_SUBSTR_LEN = 4        # Minimum length of shorter string for substring matches
EDIT_SIM_THRESHOLD = 0.45  # Normalized edit distance threshold for non-substring variants


def edit_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def norm_edit_sim(s1: str, s2: str) -> float:
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    mx = max(len(s1), len(s2))
    if mx == 0:
        return 0.0
    return 1.0 - edit_distance(s1, s2) / mx


def is_valid_variant(name: str, variant: str) -> bool:
    """Check if a variant should be kept for a given entity name."""
    n, v = name.lower().strip(), variant.lower().strip()

    # Identical (case-insensitive) → always keep
    if n == v:
        return True

    # Substring check with minimum length guard
    is_substr = n in v or v in n
    if is_substr:
        return min(len(n), len(v)) >= MIN_SUBSTR_LEN

    # Non-substring: use normalized edit distance
    return norm_edit_sim(name, variant) >= EDIT_SIM_THRESHOLD


def clean_entity_file(fpath: Path, dry_run: bool) -> tuple[dict, dict]:
    """Clean variants and mentions in a single entity file.
    Returns (stats, entity_lookup) where entity_lookup maps (book_id, entity_id) → cleaned variants."""
    data = json.load(open(fpath))
    book_id = data["book"]["id"]
    stats = {
        "book_id": book_id,
        "file": fpath.name,
        "entities_checked": 0,
        "entities_modified": 0,
        "variants_removed": 0,
        "mentions_removed": 0,
        "examples": [],  # (entity_name, dropped_variants)
    }

    for entity in data["entities"]:
        name = entity["name"]
        old_variants = entity.get("variants", [])
        if len(old_variants) <= 1:
            stats["entities_checked"] += 1
            continue

        # Filter variants
        new_variants = [v for v in old_variants if is_valid_variant(name, v)]
        dropped_set = set(v.lower() for v in old_variants) - set(v.lower() for v in new_variants)
        n_dropped = len(old_variants) - len(new_variants)

        if n_dropped > 0:
            entity["variants"] = new_variants
            stats["variants_removed"] += n_dropped
            stats["entities_modified"] += 1

            # Track examples (first 10)
            if len(stats["examples"]) < 10:
                dropped_display = sorted(set(old_variants) - set(new_variants))[:5]
                stats["examples"].append((name, dropped_display))

            # Filter mentions matched by dropped variants
            if "mentions" in entity and dropped_set:
                old_count = len(entity["mentions"])
                entity["mentions"] = [
                    m for m in entity["mentions"]
                    if m.get("matched_term", "").lower() not in dropped_set
                ]
                stats["mentions_removed"] += old_count - len(entity["mentions"])

        stats["entities_checked"] += 1

    if not dry_run and stats["variants_removed"] > 0:
        # Backup
        backup = fpath.with_suffix(".pre-cleanup.json")
        if not backup.exists():
            shutil.copy2(fpath, backup)
        # Save cleaned file
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Build entity lookup from in-memory (cleaned) data
    entity_lookup = {}
    for e in data["entities"]:
        entity_lookup[(book_id, e["id"])] = e.get("variants", [])

    return stats, entity_lookup


def update_concordance(entity_lookup: dict, dry_run: bool) -> dict:
    """Update concordance.json member variants to match cleaned entity files."""
    conc_path = DATA_DIR / "concordance.json"
    conc = json.load(open(conc_path))

    stats = {"members_updated": 0, "variants_removed": 0}

    for cluster in conc["clusters"]:
        for member in cluster["members"]:
            key = (member["book_id"], member["entity_id"])
            if key not in entity_lookup:
                continue

            clean_variants = entity_lookup[key]
            old_variants = member.get("variants", [])

            # Filter member variants to only include those in the cleaned set
            clean_set = set(v.lower() for v in clean_variants)
            new_variants = [v for v in old_variants if v.lower() in clean_set]

            n_removed = len(old_variants) - len(new_variants)
            if n_removed > 0:
                member["variants"] = new_variants
                stats["members_updated"] += 1
                stats["variants_removed"] += n_removed

    if not dry_run and stats["variants_removed"] > 0:
        backup = conc_path.with_suffix(".pre-cleanup.json")
        if not backup.exists():
            shutil.copy2(conc_path, backup)
        with open(conc_path, "w", encoding="utf-8") as f:
            json.dump(conc, f, ensure_ascii=False, indent=2)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Clean up bad variants in entity files")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    entity_files = sorted(DATA_DIR.glob("*_entities.json"))
    print(f"Found {len(entity_files)} entity files")
    print(f"Settings: MIN_SUBSTR_LEN={MIN_SUBSTR_LEN}, EDIT_SIM_THRESHOLD={EDIT_SIM_THRESHOLD}")
    if args.dry_run:
        print("DRY RUN — no files will be modified\n")
    print()

    # Phase 1: Clean entity files
    entity_lookup = {}  # (book_id, entity_id) → cleaned variants
    total_stats = defaultdict(int)

    for fpath in entity_files:
        stats, file_lookup = clean_entity_file(fpath, args.dry_run)
        entity_lookup.update(file_lookup)

        print(f"  {stats['file']:35s}  "
              f"variants removed: {stats['variants_removed']:5d}  "
              f"mentions removed: {stats['mentions_removed']:5d}  "
              f"entities modified: {stats['entities_modified']:4d}/{stats['entities_checked']}")

        if stats["examples"]:
            for name, dropped in stats["examples"][:3]:
                print(f"    e.g. {name} dropped: {dropped}")

        total_stats["variants_removed"] += stats["variants_removed"]
        total_stats["mentions_removed"] += stats["mentions_removed"]
        total_stats["entities_modified"] += stats["entities_modified"]

    print(f"\n  Total variants removed:  {total_stats['variants_removed']}")
    print(f"  Total mentions removed:  {total_stats['mentions_removed']}")
    print(f"  Total entities modified: {total_stats['entities_modified']}")

    # Phase 2: Update concordance
    print(f"\nUpdating concordance.json...")
    conc_stats = update_concordance(entity_lookup, args.dry_run)
    print(f"  Members updated: {conc_stats['members_updated']}")
    print(f"  Variants removed from concordance: {conc_stats['variants_removed']}")

    if args.dry_run:
        print("\nDry run complete. Run without --dry-run to apply changes.")
    else:
        print(f"\nDone. Backups saved as *.pre-cleanup.json")
        print("Next step: rebuild search index with:")
        print("  python3 scripts/build_search_index.py")


if __name__ == "__main__":
    main()

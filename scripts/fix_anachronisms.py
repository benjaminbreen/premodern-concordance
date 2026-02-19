#!/usr/bin/env python3
"""
Remove anachronistic person citations from clusters.

If a person's birth year is after the book's publication year,
that citation must be from a modern editor, not the original author.
Remove these members from clusters.

Usage:
    python3 scripts/fix_anachronisms.py [--dry-run]
"""

import json
import sys
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    book_years = {b["id"]: b["year"] for b in data["books"]}
    print(f"  {len(clusters)} clusters, {len(book_years)} books\n")

    total_removed = 0
    clusters_affected = 0

    for c in clusters:
        if c["category"] != "PERSON":
            continue
        gt = c.get("ground_truth") or {}
        birth = gt.get("birth_year")
        if not birth or birth < 0:
            continue

        name = gt.get("modern_name", c["canonical_name"])
        original_count = len(c["members"])
        kept = []
        removed = []

        for m in c["members"]:
            book_year = book_years.get(m["book_id"], 9999)
            if birth > book_year:
                removed.append(m)
            else:
                kept.append(m)

        if removed:
            clusters_affected += 1
            total_removed += len(removed)
            for m in removed:
                by = book_years.get(m["book_id"], "?")
                print(f"  [{c['id']:4d}] {name:30s} (b.{birth}): remove '{m['name']}' x{m['count']} from {m['book_id'].split('_')[0]} ({by})")

            if not dry_run:
                c["members"] = kept
                # Recompute book_count and total_mentions
                c["book_count"] = len(set(m["book_id"] for m in kept))
                c["total_mentions"] = sum(m["count"] for m in kept)
                # Recompute edges: remove edges involving removed books
                removed_books = {m["book_id"] for m in removed}
                if c.get("edges"):
                    c["edges"] = [
                        e for e in c["edges"]
                        if e["source_book"] not in removed_books
                        and e["target_book"] not in removed_books
                    ]

    print(f"\n  Members removed:    {total_removed}")
    print(f"  Clusters affected:  {clusters_affected}")

    # Remove clusters that now have 0 members
    if not dry_run:
        before = len(clusters)
        clusters = [c for c in clusters if len(c["members"]) > 0]
        empty = before - len(clusters)
        if empty:
            print(f"  Empty clusters removed: {empty}")
            # Renumber
            for i, c in enumerate(clusters):
                c["id"] = i
            data["clusters"] = clusters

        # Recompute stats
        from collections import Counter
        cat_counts = Counter(c["category"] for c in clusters)
        data["stats"]["total_clusters"] = len(clusters)
        data["stats"]["by_category"] = dict(sorted(cat_counts.items()))
        data["stats"]["entities_matched"] = sum(len(c["members"]) for c in clusters)

    if not dry_run and total_removed > 0:
        print(f"\nSaving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB, {len(clusters)} clusters")
    elif dry_run:
        print("\nNo changes written (dry run).")


if __name__ == "__main__":
    main()

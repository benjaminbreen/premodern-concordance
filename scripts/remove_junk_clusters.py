#!/usr/bin/env python3
"""
Remove low-quality junk clusters from concordance.json.

Removes clusters that meet ALL of these criteria:
  - No ground_truth.description
  - No ground_truth.wikipedia_extract
  - No ground_truth.modern_name
  - total_mentions <= 5

These are OCR artifacts, abbreviations, and fragments that add noise
without providing useful information.

Also removes specific known-junk entries regardless of mentions
(chapter references, section headers, etc.).

Usage:
    python3 scripts/remove_junk_clusters.py [--dry-run]
"""

import json
import re
import sys
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak6")

# Entries to always remove regardless of mentions (structural junk)
ALWAYS_REMOVE = {
    "cap.",
    "CHAPTER III",
    "PARTE PRIMA",
    "PI. 17",
    "Occull.",
    "Therapeut.",
    "Herb, Amb.",
    "Mom.",
    "loc",
    "sal",
    "lib.",
    "fol.",
    "Secon",
    "Comment",
}


def is_junk(cluster: dict) -> tuple[bool, str]:
    """Determine if a cluster is junk. Returns (is_junk, reason)."""
    name = cluster["canonical_name"]
    gt = cluster.get("ground_truth", {})
    mentions = cluster.get("total_mentions", 0)
    members = cluster.get("members", [])

    # Always-remove list
    if name in ALWAYS_REMOVE:
        return True, "known_junk"

    # Has useful content — keep
    if gt.get("description") or gt.get("wikipedia_extract"):
        return False, "has_content"

    # Has a modern name mapping — keep (someone enriched it)
    if gt.get("modern_name"):
        return False, "has_modern_name"

    # No content at all — check mentions threshold
    if mentions <= 5:
        return True, "empty_low_mentions"

    return False, "enough_mentions"


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    if not dry_run:
        print(f"Backing up to {BACKUP_PATH}")
        with open(BACKUP_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)

    # Classify all clusters
    keep = []
    remove = []
    for c in clusters:
        is_j, reason = is_junk(c)
        if is_j:
            remove.append((c, reason))
        else:
            keep.append(c)

    # Report
    print(f"\nResults:")
    print(f"  Keep:   {len(keep)}")
    print(f"  Remove: {len(remove)}")

    # Breakdown of removals
    from collections import Counter
    reasons = Counter(r for _, r in remove)
    for reason, count in reasons.most_common():
        print(f"    {reason}: {count}")

    cats = Counter(c["category"] for c, _ in remove)
    print(f"\n  Removed by category:")
    for cat, count in cats.most_common():
        print(f"    {cat}: {count}")

    total_removed_mentions = sum(c.get("total_mentions", 0) for c, _ in remove)
    print(f"\n  Total mentions removed: {total_removed_mentions}")
    print(f"  Avg mentions per removed: {total_removed_mentions / len(remove):.1f}" if remove else "")

    # Show some examples
    print(f"\n  Sample removals:")
    for c, reason in remove[:20]:
        print(f"    {c['canonical_name']:35s}  {c.get('total_mentions',0):3d} mentions  ({reason})")

    if dry_run:
        print(f"\n  DRY RUN — no changes written.")
        return

    # Update clusters and stats
    data["clusters"] = keep

    # Update stats
    if "stats" in data:
        data["stats"]["total_clusters"] = len(keep)
        data["stats"]["total_mentions"] = sum(c.get("total_mentions", 0) for c in keep)

    # Save
    print(f"\nSaving to {CONCORDANCE_PATH}...")
    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB")
    print(f"\nDone! {len(keep)} clusters remain.")
    print("Now rebuild the search index:")
    print("  python3 scripts/build_search_index.py")


if __name__ == "__main__":
    main()

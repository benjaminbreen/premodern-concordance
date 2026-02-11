#!/usr/bin/env python3
"""
Fix 85 problematic clusters in the concordance:
  - 25 deletions (OCR artifacts, abbreviations, non-entities)
  - ~16 bad merges (remove wrongly-matched members)
  - ~10 reclassifications (wrong category)

Usage:
    python3 scripts/fix_problematic_clusters.py [--dry-run]
"""

import json
import sys
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak6")

DRY_RUN = "--dry-run" in sys.argv


def main():
    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Build lookup by canonical_name
    by_name = {c["canonical_name"]: c for c in clusters}

    # ===== 1. DELETIONS =====
    # OCR artifacts, abbreviations, chapter headers, non-entities
    delete_names = [
        "Chapter X.", "Comment", "orientaL", "materias", "Occull.",
        "Chapter XII", "l'AJmirante", "rcaux", "fputofanguinis", "Path",
        "Springs", "baf^azo", "Mom.", "scenes", "inverted dome",
        "Journal", "Falattouaroc", "Impiaftro di formento", "Anatricela",
        "aurinetra", "Oper.Med.", "ties the Tongue", "slow-breeders",
        "ruym", "region caliente",
    ]

    delete_ids = set()
    for name in delete_names:
        if name in by_name:
            delete_ids.add(by_name[name]["id"])
            print(f"  DELETE: id={by_name[name]['id']} \"{name}\"")
        else:
            print(f"  WARNING: delete target not found: \"{name}\"")

    print(f"\n  Total to delete: {len(delete_ids)}")

    # ===== 2. BAD MERGES =====
    # Remove specific wrongly-matched members from clusters.
    # Format: (cluster_canonical_name, member_name_to_remove)
    # Some clusters have multiple bad members.
    bad_merge_removals = [
        # Cassiquiare river ≠ Cassiopeia constellation
        ("Cassiquiare", "Cassiopeia"),
        # Lion ≠ Leech
        ("Leaõ", "Leech"),
        # Vespucci ≠ Vespasian
        ("Vespucci", "Vespasian"),
        # Sparrow ≠ Apteryx (kiwi bird)
        ("sparrow", "spteryx"),
        # Retentive (memory) ≠ retentissement (French: resonance)
        ("Retentive", "retentissement"),
        # Horn-Church (Essex) ≠ Cape Horn
        ("Horn-Church", "Horn"),
        # Upton ≠ Upminster
        ("Upton", "Upminster"),
        # House of Commons ≠ generic "house"
        ("House of Communs", "house"),
        # Hayhay ≠ Haify
        ("Hayhay", "Haify"),
        # plumbea (lead-colored) ≠ plumbago (graphite)
        ("plumbea", "plumbago"),
        # Mosses ≠ mo' (OCR), Mochi (food)
        ("mosses", "mo'"),
        ("mosses", "Mochi"),
        # Jorullo volcano (Mexico) ≠ Jaurù (Brazil)
        ("Jorullo", "Jaurù"),
        # Siara/Ceará (Brazil) ≠ Syra (Greek island)
        ("Siara", "Syra"),
        # poetry ≠ Poefia (OCR artifact)
        ("poetry", "Poefia"),
        # vernucolo (grape) ≠ vernenos (venomous)
        ("vernucolo", "vernenos"),
    ]

    merge_fixes = 0
    for cluster_name, member_name in bad_merge_removals:
        if cluster_name not in by_name:
            print(f"  WARNING: merge target cluster not found: \"{cluster_name}\"")
            continue

        c = by_name[cluster_name]
        original_count = len(c["members"])
        c["members"] = [m for m in c["members"] if m["name"] != member_name]
        removed = original_count - len(c["members"])

        if removed > 0:
            merge_fixes += 1
            # Update aggregate stats
            c["book_count"] = len(set(m["book_id"] for m in c["members"]))
            c["total_mentions"] = sum(m["count"] for m in c["members"])
            print(f"  MERGE FIX: \"{cluster_name}\" (id={c['id']}): removed \"{member_name}\" ({removed} member(s)), {len(c['members'])} remaining")
        else:
            print(f"  WARNING: member \"{member_name}\" not found in \"{cluster_name}\"")

    print(f"\n  Total merge fixes: {merge_fixes}")

    # ===== 3. RECLASSIFICATIONS =====
    # Correct wrong categories
    reclassifications = {
        # Astronomical objects wrongly categorized as ANIMAL
        "Orion": "OBJECT",
        "Aldebaran": "OBJECT",
        "Sirius": "OBJECT",
        "ζ Herculis": "OBJECT",
        # Astronomical objects with other wrong categories
        "Pisces": "OBJECT",
        "Cygnus": "OBJECT",
        "nebula": "OBJECT",
        # Substance wrongly categorized
        "blood": "SUBSTANCE",
        # Wrong category
        "storms": "CONCEPT",
        "celestial body": "OBJECT",
    }

    reclass_count = 0
    for name, new_cat in reclassifications.items():
        if name not in by_name:
            print(f"  WARNING: reclassify target not found: \"{name}\"")
            continue

        c = by_name[name]
        old_cat = c["category"]
        if old_cat == new_cat:
            print(f"  SKIP: \"{name}\" already {new_cat}")
            continue

        c["category"] = new_cat
        # Also update ground_truth if present
        if "ground_truth" in c and "category" in c.get("ground_truth", {}):
            c["ground_truth"]["category"] = new_cat
        reclass_count += 1
        print(f"  RECLASSIFY: \"{name}\" (id={c['id']}): {old_cat} → {new_cat}")

    print(f"\n  Total reclassifications: {reclass_count}")

    # ===== 4. APPLY DELETIONS =====
    original_len = len(clusters)
    clusters = [c for c in clusters if c["id"] not in delete_ids]
    deleted = original_len - len(clusters)
    data["clusters"] = clusters

    # Update stats
    data["stats"]["cluster_count"] = len(clusters)

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Deleted: {deleted} clusters")
    print(f"  Merge fixes: {merge_fixes}")
    print(f"  Reclassifications: {reclass_count}")
    print(f"  Clusters: {original_len} → {len(clusters)}")

    if DRY_RUN:
        print("\n  DRY RUN — no changes saved")
        return

    # Backup
    print(f"\nBacking up to {BACKUP_PATH}")
    with open(BACKUP_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    # Save
    print(f"Saving to {CONCORDANCE_PATH}...")
    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB")
    print("\nDone! Now rebuild the search index:")
    print("  python3 scripts/build_search_index.py")


if __name__ == "__main__":
    main()

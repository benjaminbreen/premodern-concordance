#!/usr/bin/env python3
"""
Comprehensive data quality cleanup:
  1. Remove wrong members from contaminated clusters
  2. Fix ANIMAL miscategorization (67 clusters)
  3. Merge language-split duplicates (agua/Water, febre/fever, etc.)
  4. Clear 218 "family name" Wikidata IDs
  5. Fix specific wrong modern_names

Usage:
    python3 scripts/cleanup_quality.py [--dry-run]
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak10")

# ─── 1. Members to REMOVE from specific clusters ────────────────────────
# {cluster_id: [member_names_to_remove]}
REMOVE_MEMBERS = {
    # Canela: remove cardamomo (different spice)
    44: ["cardamomo"],
    # Apoplexia: remove Aphasia
    1495: ["Aphasia"],
    # purga: remove Purgatorio
    1494: ["Purgatorio"],
    # Helmholtz: remove Hermanno (from 1563, impossible)
    627: ["Hermanno"],
    # porco: remove Porpoces (porpoises)
    1875: ["Porpoces"],
    # Halley's comet: remove Faye's Comet
    1729: ["Faye's Comet"],
    # Loadstone: remove magnesia
    596: ["magnesia"],
    # Hydropesia: remove hydroforbia (hydrophobia/rabies)
    527: ["hydroforbia"],
    # Ciatica: remove catarros/Catarros (catarrh)
    1506: ["catarros", "Catarros"],
}

# ─── 2. ANIMAL → correct category reassignments ─────────────────────────
# {cluster_id: new_category}
CATEGORY_FIXES = {
    # Celestial bodies → CONCEPT (no CELESTIAL_BODY category exists)
    197: "CONCEPT",    # sun
    1507: "CONCEPT",   # moon
    556: "CONCEPT",    # Jupiter
    1565: "CONCEPT",   # Saturn
    1644: "CONCEPT",   # satellites
    1650: "CONCEPT",   # comets
    1705: "CONCEPT",   # Sirius
    1750: "CONCEPT",   # 61 Cygni
    754: "CONCEPT",    # stars
    1050: "CONCEPT",   # Orion
    2457: "CONCEPT",   # Lyra
    2499: "CONCEPT",   # Centaures
    2842: "CONCEPT",   # Leo
    1313: "CONCEPT",   # star
    3032: "CONCEPT",   # Aldebaran
    3232: "CONCEPT",   # celestial body
    3236: "CONCEPT",   # Hercules
    4342: "CONCEPT",   # Cephei

    # Animal products → SUBSTANCE
    220: "SUBSTANCE",   # carne (meat)
    561: "SUBSTANCE",   # ovo (egg)
    1542: "SUBSTANCE",  # gemas de ovos
    640: "SUBSTANCE",   # Milk
    403: "SUBSTANCE",   # Eggs
    809: "SUBSTANCE",   # Hair
    400: "SUBSTANCE",   # Butter
    883: "SUBSTANCE",   # leite
    2082: "SUBSTANCE",  # Algalia (civet)
    1154: "SUBSTANCE",  # feathers
    2154: "SUBSTANCE",  # carabe (ambergris)
    2237: "SUBSTANCE",  # seda (silk)
    487: "SUBSTANCE",   # musc
    2978: "SUBSTANCE",  # fur
    3192: "SUBSTANCE",  # leite azedo
    3203: "SUBSTANCE",  # claradeovo
    3284: "SUBSTANCE",  # Horse dung
    3313: "SUBSTANCE",  # Skins
    3664: "SUBSTANCE",  # animal matter
    3711: "SUBSTANCE",  # fel (bile)
    3851: "SUBSTANCE",  # blood
    3858: "SUBSTANCE",  # Egg-shells
    3938: "SUBSTANCE",  # Dogs-turd

    # Abstract/collective → CONCEPT
    258: "CONCEPT",     # organic beings
    1682: "CONCEPT",    # organism
    1674: "CONCEPT",    # hybrids
    774: "CONCEPT",     # domestic animals
    813: "CONCEPT",     # fauna
    1122: "CONCEPT",    # prey
    2378: "CONCEPT",    # animal kingdom
    2723: "CONCEPT",    # domesticated animals
    1144: "CONCEPT",    # creatures
    1157: "CONCEPT",    # fossils
    2531: "CONCEPT",    # offspring
    2728: "CONCEPT",    # parent-species
    1341: "CONCEPT",    # waters (aquatic animals)
    1345: "CONCEPT",    # Marine animals
    2979: "CONCEPT",    # domestic breeds
    3353: "CONCEPT",    # land animals
    3365: "CONCEPT",    # extinct species
    3382: "CONCEPT",    # young
    3968: "CONCEPT",    # wild species
    4003: "CONCEPT",    # marine fauna
    4005: "CONCEPT",    # marine inhabitants
    4164: "CONCEPT",    # human embryos
    4191: "CONCEPT",    # brutes

    # Other fixes
    2067: "CONCEPT",    # thunder
    1779: "CONCEPT",    # Man (was "Manatee")
    3204: "ANIMAL",     # boy → actually ox (boi), keep ANIMAL but fix modern_name
}

# ─── 3. Modern name fixes ────────────────────────────────────────────────
MODERN_NAME_FIXES = {
    1779: "Humanity",       # was "Manatee" — members are Darwin/Humboldt "Man"
    3258: "Leech",          # was "lion" — members are Leeches
    3748: "Sheep",          # was "egg" — members are ovelha (sheep)
    3204: "Ox",             # was "Ox" — keep, but was listed as "boy"
}

# ─── 4. Language-split merges ────────────────────────────────────────────
# (primary_id, [secondary_ids]) — merge secondaries into primary
LANGUAGE_MERGES = [
    (0, [525]),         # Water + agua → Water
    (1491, [1103]),     # febre + fever → febre
    (1493, [46, 3851]),  # sangue + Blood + blood(ANIMAL) → sangue
    (528, [736]),       # veas + Vein → veas
    (561, [403]),       # ovo + Eggs → ovo
]

# ─── 5. "Family name" Wikidata IDs to clear ─────────────────────────────
FAMILY_NAME_IDS = [50, 197, 1499, 558, 211, 556, 3, 5, 224, 1533, 1526, 240, 633, 239, 71, 7, 1558, 70, 250, 90, 1580, 81, 699, 284, 22, 629, 1609, 1664, 637, 1633, 643, 92, 678, 1771, 1662, 329, 105, 106, 107, 1680, 675, 676, 683, 723, 309, 693, 696, 725, 122, 714, 1749, 721, 1767, 130, 327, 752, 824, 998, 148, 776, 1066, 1843, 1853, 2386, 152, 1883, 375, 377, 828, 163, 847, 862, 995, 1987, 489, 881, 899, 1282, 2049, 422, 921, 929, 2091, 2148, 2151, 2394, 434, 992, 1193, 2174, 2186, 2194, 2201, 2203, 2220, 439, 455, 459, 519, 1056, 2325, 2337, 466, 475, 1071, 1087, 1101, 1362, 2416, 496, 1125, 1132, 1136, 1187, 2522, 2627, 500, 509, 1211, 1217, 1228, 1249, 2673, 2675, 2692, 2704, 2757, 2811, 2835, 2851, 2877, 3755, 1303, 1313, 1320, 1326, 1374, 1376, 1397, 2907, 3074, 3083, 3092, 3094, 3096, 3126, 3128, 3130, 3206, 3213, 3240, 1409, 1427, 1430, 3252, 3254, 3262, 3308, 3312, 3314, 3344, 3358, 3449, 3450, 3494, 3502, 3522, 3524, 3543, 3568, 3578, 3631, 3634, 3684, 3692, 3694, 3714, 3720, 3722, 3725, 3770, 3780, 3788, 3792, 3794, 3816, 3817, 3854, 3901, 3907, 3915, 3919, 3933, 3942, 3952, 3957, 3958, 3992, 4033, 4093, 4117, 4146, 4191, 4277, 4280, 4290, 4302, 4343, 4388, 4390, 4413, 4433, 4443, 4448, 4508, 4516, 4529, 4551]


def merge_ground_truth(clusters):
    best_gt = {}
    best_score = -1
    for c in clusters:
        gt = c.get("ground_truth") or {}
        score = sum([
            3 if gt.get("wikidata_id") else 0,
            2 if gt.get("wikipedia_url") else 0,
            2 if gt.get("wikipedia_extract") else 0,
            1 if gt.get("modern_name") else 0,
            1 if gt.get("description") else 0,
        ])
        if score > best_score:
            best_score = score
            best_gt = dict(gt)
    for c in clusters:
        gt = c.get("ground_truth") or {}
        for key, val in gt.items():
            if val and not best_gt.get(key):
                best_gt[key] = val
    return best_gt


def merge_clusters(primary, others):
    all_members = list(primary.get("members", []))
    seen = set()
    for m in all_members:
        seen.add((m.get("entity_id", ""), m.get("book_id", ""), m.get("name", "")))
    for c in others:
        for m in c.get("members", []):
            key = (m.get("entity_id", ""), m.get("book_id", ""), m.get("name", ""))
            if key not in seen:
                all_members.append(m)
                seen.add(key)
    primary["members"] = all_members
    books = set(m.get("book_id", "") for m in all_members)
    primary["book_count"] = len(books)
    primary["total_mentions"] = sum(m.get("count", 0) for m in all_members)
    primary["member_count"] = len(all_members)
    primary["ground_truth"] = merge_ground_truth([primary] + list(others))
    return primary


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    id_to_idx = {c["id"]: i for i, c in enumerate(clusters)}
    stats = defaultdict(int)

    # ─── Phase 1: Remove wrong members ───────────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 1: Removing wrong members from contaminated clusters")
    print(f"{'='*60}")

    for cid, bad_names in REMOVE_MEMBERS.items():
        if cid not in id_to_idx:
            print(f"  [WARN] Cluster {cid} not found")
            continue
        c = clusters[id_to_idx[cid]]
        name = c.get("canonical_name", "?")
        bad_set = set(n.lower() for n in bad_names)
        old_count = len(c.get("members", []))

        if not dry_run:
            c["members"] = [m for m in c["members"]
                           if m.get("name", "").lower() not in bad_set]
            new_count = len(c["members"])
            # Recalc stats
            c["member_count"] = new_count
            c["total_mentions"] = sum(m.get("count", 0) for m in c["members"])
            c["book_count"] = len(set(m.get("book_id") for m in c["members"]))
        else:
            new_count = sum(1 for m in c["members"]
                          if m.get("name", "").lower() not in bad_set)

        removed = old_count - new_count
        if removed > 0:
            print(f"  [{name}] removed {removed} members: {bad_names}")
            stats["members_removed"] += removed

    # ─── Phase 2: Fix ANIMAL miscategorization ───────────────────────
    print(f"\n{'='*60}")
    print("PHASE 2: Fixing ANIMAL miscategorization (67 clusters)")
    print(f"{'='*60}")

    for cid, new_cat in CATEGORY_FIXES.items():
        if cid not in id_to_idx:
            continue
        c = clusters[id_to_idx[cid]]
        old_cat = c.get("category", "?")
        if old_cat == new_cat:
            continue
        name = c.get("canonical_name", "?")
        print(f"  [{name}] {old_cat} -> {new_cat}")
        if not dry_run:
            c["category"] = new_cat
        stats["categories_fixed"] += 1

    # ─── Phase 2b: Fix wrong modern names ────────────────────────────
    print(f"\n  Modern name fixes:")
    for cid, new_modern in MODERN_NAME_FIXES.items():
        if cid not in id_to_idx:
            continue
        c = clusters[id_to_idx[cid]]
        gt = c.get("ground_truth") or {}
        old_modern = gt.get("modern_name", "?")
        name = c.get("canonical_name", "?")
        if old_modern != new_modern:
            print(f"  [{name}] modern: {old_modern} -> {new_modern}")
            if not dry_run:
                gt["modern_name"] = new_modern
                c["ground_truth"] = gt
            stats["modern_names_fixed"] += 1

    # ─── Phase 3: Merge language-split duplicates ────────────────────
    print(f"\n{'='*60}")
    print("PHASE 3: Merging language-split duplicates")
    print(f"{'='*60}")

    absorbed_ids = set()
    for primary_id, secondary_ids in LANGUAGE_MERGES:
        if primary_id not in id_to_idx:
            print(f"  [WARN] Primary {primary_id} not found")
            continue
        primary = clusters[id_to_idx[primary_id]]
        others = []
        for sid in secondary_ids:
            if sid not in id_to_idx:
                print(f"  [WARN] Secondary {sid} not found")
                continue
            others.append(clusters[id_to_idx[sid]])
            absorbed_ids.add(sid)

        if not others:
            continue

        names = [primary.get("canonical_name", "?")] + [c.get("canonical_name", "?") for c in others]
        old_mentions = primary.get("total_mentions", 0)

        if not dry_run:
            merge_clusters(primary, others)

        new_mentions = primary.get("total_mentions", 0) if not dry_run else "?"
        print(f"  {' + '.join(names)} -> {names[0]} ({old_mentions} -> {new_mentions} mentions)")
        stats["language_merges"] += 1

    # ─── Phase 4: Clear "family name" Wikidata IDs ───────────────────
    print(f"\n{'='*60}")
    print(f"PHASE 4: Clearing {len(FAMILY_NAME_IDS)} 'family name' Wikidata IDs")
    print(f"{'='*60}")

    for cid in FAMILY_NAME_IDS:
        if cid not in id_to_idx:
            continue
        c = clusters[id_to_idx[cid]]
        gt = c.get("ground_truth") or {}
        if not gt.get("wikidata_id"):
            continue
        if not dry_run:
            gt["wikidata_id"] = ""
            # Keep wikipedia_url and extract if they look valid
            # (some may have been manually fixed to correct articles)
            c["ground_truth"] = gt
        stats["family_name_cleared"] += 1

    print(f"  Cleared: {stats['family_name_cleared']}")

    # ─── Phase 5: Remove absorbed clusters, renumber ─────────────────
    if not dry_run:
        new_clusters = [c for c in clusters if c["id"] not in absorbed_ids]
        for i, c in enumerate(new_clusters):
            c["id"] = i
        data["clusters"] = new_clusters

        # Update stats
        total = len(new_clusters)
        from collections import Counter
        cats = Counter(c.get("category", "?") for c in new_clusters)
        has_qid = sum(1 for c in new_clusters if (c.get("ground_truth") or {}).get("wikidata_id"))
        has_wiki = sum(1 for c in new_clusters if (c.get("ground_truth") or {}).get("wikipedia_url"))

        data["stats"] = {
            "total_clusters": total,
            "entities_matched": sum(len(c.get("members", [])) for c in new_clusters),
            "by_category": dict(cats.most_common()),
            "enriched_clusters": total,
            "with_wikidata": has_qid,
            "with_wikipedia": has_wiki,
            "with_linnaean": 0,
            "cluster_count": total,
        }
    else:
        new_clusters = [c for c in clusters if c["id"] not in absorbed_ids]

    # ─── Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Wrong members removed:     {stats['members_removed']}")
    print(f"  Categories fixed:          {stats['categories_fixed']}")
    print(f"  Modern names fixed:        {stats['modern_names_fixed']}")
    print(f"  Language merges:           {stats['language_merges']}")
    print(f"  Family-name QIDs cleared:  {stats['family_name_cleared']}")
    print(f"  Clusters absorbed:         {len(absorbed_ids)}")
    print(f"  Clusters before:           {len(clusters)}")
    print(f"  Clusters after:            {len(new_clusters)}")

    if not dry_run:
        print(f"\nBacking up to {BACKUP_PATH}")
        with open(CONCORDANCE_PATH) as f:
            original = f.read()
        with open(BACKUP_PATH, "w") as f:
            f.write(original)

        print(f"Saving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB")

        print(f"\nUpdated stats:")
        print(json.dumps(data["stats"], indent=2))
    else:
        print("\nNo changes written (dry run).")


if __name__ == "__main__":
    main()

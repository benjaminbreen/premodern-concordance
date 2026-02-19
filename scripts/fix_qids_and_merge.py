#!/usr/bin/env python3
"""
Fix bad Wikidata QIDs and apply approved merge proposals.

Phase 1: Fix 46 clusters with wrong QIDs (remove or replace)
Phase 2: Apply approved merges from merge_proposals.json
  - Auto-approve clean HIGH proposals
  - Auto-approve clean MEDIUM proposals
  - Promote obvious LOW proposals (Avicenna, France, London, Rome, etc.)
  - Skip flagged wrong proposals

Usage:
    python3 scripts/fix_qids_and_merge.py [--dry-run]
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
PROPOSALS_PATH = Path(__file__).parent.parent / "data" / "merge_proposals.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak8")

# ─── Phase 1: QID corrections ───────────────────────────────────────────────
# {cluster_id: "remove_qid" | "Q-new-id"}
QID_CORRECTIONS = {
    120: "Q43513",       # esmeralda -> emerald (was Seattle Q5083)
    172: "remove_qid",   # flower (was cannabis Q2845)
    180: "remove_qid",   # land (was Japan Q17)
    202: "Q336",         # sciences -> science (was Q1298668)
    236: "remove_qid",   # Flowers (was cannabis Q2845)
    250: "Q336",         # Science -> science (was Q1298668)
    531: "remove_qid",   # Grass (was cannabis Q2845)
    544: "Q177413",      # demonio -> demon (was demonstration Q175331)
    673: "remove_qid",   # cap. (was cathedral chapter Q216285)
    713: "Q1090",        # Argento -> silver (was graphite Q5309)
    714: "Q1090",        # prata -> silver (was graphite Q5309)
    748: "remove_qid",   # flores (was cannabis Q2845)
    752: "Q1090",        # Silver -> silver (was graphite Q5309)
    837: "Q165",         # Sea -> sea (was Seattle Q5083)
    1009: "remove_qid",  # Amat. mixed abbrevs (was Aristotle Q868)
    1029: "remove_qid",  # grasses (was cannabis Q2845)
    1036: "Q165",        # mer -> sea (was Seattle Q5083)
    1141: "Q140",        # Lion -> lion (was Singapore Q334)
    1209: "remove_qid",  # agua do mar mixed cluster (was horse Q726)
    1288: "remove_qid",  # work (was Q1298668)
    1370: "Q7354",       # Southern Ocean (was Arctic Q25322)
    1380: "remove_qid",  # City (was Paris Q90)
    1430: "remove_qid",  # study (was Q1298668)
    1463: "remove_qid",  # Mineral generic (was graphite Q5309)
    1757: "remove_qid",  # rame/copper (was ruby Q43088)
    1917: "remove_qid",  # herbe (was cannabis Q2845)
    2059: "remove_qid",  # Cidade (was Paris Q90)
    2181: "remove_qid",  # Lange (was Humboldt Q6694)
    2351: "remove_qid",  # Langius (was Riolan Q3174344)
    2355: "Q43513",      # Esmeraldas -> emerald (was Seattle Q5083)
    2378: "Q3436681",    # Lamanon -> Robert de Lamanon (was La Perouse Q294478)
    2566: "Q1286",       # Alpes maritimes -> Alps (was Q1151300)
    2570: "Q5955",       # ALTAI -> Altai Mountains (was Q1151300)
    3011: "Q6674",       # Devil -> devil (was Aconitum Q155904)
    3200: "remove_qid",  # minerio generic (was graphite Q5309)
    3311: "Q3174345",    # Riolanus -> Riolan Younger (was Q3174344)
    3401: "remove_qid",  # Harris (was Hamilton Q11887)
    3421: "Q6674",       # diable -> devil (was Aconitum Q155904)
    3440: "remove_qid",  # black (was graphite Q5309)
    3659: "Q43012",      # Leeches -> leech (was Singapore Q334)
    4035: "remove_qid",  # Chapter X. (was Q216285)
    4307: "remove_qid",  # Mineral bodies (was graphite Q5309)
    4383: "remove_qid",  # CHAPTER IV (was Q216285)
    4824: "remove_qid",  # Fig. 41 (was shape Q207961)
    4825: "remove_qid",  # Fig. 42 (was shape Q207961)
    4900: "remove_qid",  # dry land (was Japan Q17)
}

# ─── Phase 2: Merge rejection list ──────────────────────────────────────────
# Proposals to REJECT, identified by the set of cluster IDs involved.
# These are the ~45 flagged wrong proposals from analysis.
REJECT_MERGES = [
    # HIGH confidence rejects
    {1, 599, 1004, 1455},          # Water + fluid + agua azerada (too generic)
    {172, 236, 531, 748, 1029, 1917},  # flower + Grass + herbe (different plants, bad QID)
    {46, 2181, 2692, 3504},        # Humboldt + Lange (Lange is not Humboldt)
    {713, 714, 752, 1463, 3200, 3394, 3440, 4307},  # Silver + graphite + mineral + black (bad QID)
    {202, 250, 1288, 1430},        # sciences + work + study (too generic)
    {147, 180, 4900},              # Japan + land + dry land (bad QID)
    {268, 335},                     # coal + Charcoal (historically distinct)
    {4035, 4383},                   # Chapter X + Chapter IV
    {4824, 4825},                   # Fig. 41 + Fig. 42

    # MEDIUM confidence rejects
    {229, 458, 1184},              # purga + Purgatorio + Purges (Purgatory != purging)
    {277, 1159, 3074},             # Ciatica + Sciatica + catarros (catarrh != sciatica)
    {69, 1009},                    # Aristotle + Amat. (mixed abbreviations)
    {65, 133, 1052},               # Space + existence + existents (unrelated)
    {1373, 1480, 1757},            # rubies + rubino + rame (copper != rubies)
    {145, 4581},                   # Madrid + New Madrid (different places)
    {2351, 3311},                  # Langius + Riolanus (different people)
    {2378, 2694},                  # Lamanon + La Perouse (different people)
    {2578, 3401},                  # Hamilton + Harris (different people)
    {837, 1036},                   # Sea + mer (had bad QID Q5083=Seattle)
    {2566, 2570},                  # Alps + Altai (different mountains)
    {998, 1370},                   # Polar Sea + Southern Ocean (different oceans)
    {544, 1584},                   # demonio + Demonstrations (demon != demo)
    {1141, 3659},                  # Lion + Leeches (bad QID)
    {1209, 3800, 4283},            # agua do mar + horses (bad QID)
    {3162, 4387},                  # lune + Astrea (Moon != asteroid)
    {638, 2156, 4614},             # Capricorn + Scorpion + Tropick of Capricorn
    {1380, 2059},                  # City + Cidade (too generic, bad QID=Paris)
    {427, 1046, 3063},             # Bees + Bee + beetle (different insects)
    {1261, 3143},                  # Peony + Bettony (different plants)
    {3665, 4171, 3011, 3421},      # Aconite + Devil (bad QID confusion)
    {2488, 3530},                  # Roxburgh + Rhod. (likely different)
    {2207, 1539},                  # Caucase + Cauca (Caucasus != Cauca)
    {778, 4213, 2553, 3850},       # Cocks + pollo + Chicken + Heron
    {1555, 3106, 1662},            # Sapa + Sabao + sap (soap vs grape must vs sap)
    {1847, 3024},                  # Rainha + Kings (queen vs kings)
    {3649, 4073},                  # Fig. 2 + Fig. 19
    {229, 1184},                   # purga + Purges subset
    {843, 1696},                   # ano + 1870 (year concept + specific year)
]

# LOW confidence proposals to PROMOTE (accept)
# Identified by canonical names as a shortcut since LOW proposals are by modern_name
PROMOTE_LOW_NAMES = {
    "avicenna", "france", "london", "rome", "opium",
    "alexandria", "naples", "lisbon", "granada",
    "portugal", "china", "peru", "chile", "venezuela",
    "cuba", "brazil", "turkey", "arabia", "ethiopia",
    "scotland", "ireland", "japan", "norway", "sweden",
    "denmark", "holland", "switzerland", "austria",
    "belgium", "russia", "greece", "persia",
}


def merge_ground_truth(clusters):
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


def merge_clusters(primary, others):
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

    # Pick canonical name from cluster with most mentions
    best_name = primary.get("canonical_name", "")
    best_mentions = primary.get("total_mentions", 0)
    for c in others:
        if c.get("total_mentions", 0) > best_mentions:
            best_mentions = c["total_mentions"]
            best_name = c.get("canonical_name", best_name)
    # Actually prefer the primary's name if it's in English/Latin
    # (keep the existing canonical name unless the merged one is much bigger)

    return primary


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Build ID -> cluster index map
    id_to_idx = {}
    for idx, c in enumerate(clusters):
        id_to_idx[c["id"]] = idx

    # ─── Phase 1: Fix QIDs ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"PHASE 1: Fixing {len(QID_CORRECTIONS)} bad QIDs")
    print(f"{'='*60}")

    qid_fixed = 0
    qid_removed = 0
    for cid, action in QID_CORRECTIONS.items():
        if cid not in id_to_idx:
            print(f"  [WARN] Cluster {cid} not found, skipping")
            continue
        c = clusters[id_to_idx[cid]]
        gt = c.get("ground_truth") or {}
        old_qid = gt.get("wikidata_id", "")
        name = c.get("canonical_name", "?")

        if action == "remove_qid":
            if old_qid and not dry_run:
                gt["wikidata_id"] = ""
                c["ground_truth"] = gt
            print(f"  [remove] {name} (id={cid}): {old_qid} -> (removed)")
            qid_removed += 1
        else:
            if not dry_run:
                gt["wikidata_id"] = action
                c["ground_truth"] = gt
            print(f"  [fix]    {name} (id={cid}): {old_qid} -> {action}")
            qid_fixed += 1

    print(f"\n  QIDs removed: {qid_removed}")
    print(f"  QIDs replaced: {qid_fixed}")

    # ─── Phase 2: Apply merges ───────────────────────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 2: Applying approved merges")
    print(f"{'='*60}")

    with open(PROPOSALS_PATH) as f:
        proposals_data = json.load(f)
    proposals = proposals_data["proposals"]
    print(f"  {len(proposals)} proposals loaded")

    # Build rejection set (frozensets of cluster IDs)
    reject_sets = [frozenset(s) for s in REJECT_MERGES]

    accepted = 0
    rejected = 0
    skipped = 0
    promoted = 0
    clusters_absorbed = 0  # clusters that got merged into others
    absorbed_ids = set()   # track which cluster IDs have been absorbed

    for p_idx, proposal in enumerate(proposals):
        cluster_ids = frozenset(c["id"] for c in proposal["clusters"])
        confidence = proposal["confidence"]

        # Check if this proposal is in the reject list
        is_rejected = any(cluster_ids == rs or cluster_ids.issubset(rs) or rs.issubset(cluster_ids)
                         for rs in reject_sets)

        if is_rejected:
            rejected += 1
            continue

        # For LOW confidence, only accept promoted ones
        if confidence == "LOW":
            modern_name = ""
            for c_info in proposal["clusters"]:
                mn = c_info.get("modern_name", "").lower()
                if mn:
                    modern_name = mn
                    break
            if modern_name not in PROMOTE_LOW_NAMES:
                skipped += 1
                continue
            promoted += 1

        # Skip if any cluster in this proposal has already been absorbed
        if any(cid in absorbed_ids for cid in cluster_ids):
            skipped += 1
            continue

        # Find the primary cluster (highest total_mentions, or first valid)
        valid_clusters = []
        for c_info in proposal["clusters"]:
            cid = c_info["id"]
            if cid in id_to_idx and cid not in absorbed_ids:
                valid_clusters.append(clusters[id_to_idx[cid]])

        if len(valid_clusters) < 2:
            skipped += 1
            continue

        # Sort by total mentions descending - primary is the biggest
        valid_clusters.sort(key=lambda c: c.get("total_mentions", 0), reverse=True)
        primary = valid_clusters[0]
        others = valid_clusters[1:]

        names = " + ".join(c.get("canonical_name", "?") for c in valid_clusters)
        cat = primary.get("category", "?")

        if not dry_run:
            merge_clusters(primary, others)

        # Mark absorbed clusters
        for c in others:
            absorbed_ids.add(c["id"])
            clusters_absorbed += 1

        accepted += 1
        if confidence == "LOW":
            print(f"  [PROMOTED] [{cat}] {names}")
        elif accepted <= 50 or accepted % 20 == 0:
            print(f"  [{confidence}] [{cat}] {names}")

    print(f"\n  Proposals accepted: {accepted}")
    print(f"  Proposals rejected: {rejected}")
    print(f"  Proposals skipped (LOW not promoted / already absorbed): {skipped}")
    print(f"  LOW proposals promoted: {promoted}")
    print(f"  Clusters absorbed: {clusters_absorbed}")

    # Remove absorbed clusters
    if not dry_run:
        new_clusters = [c for c in clusters if c["id"] not in absorbed_ids]
        print(f"\n  Clusters before: {len(clusters)}")
        print(f"  Clusters after:  {len(new_clusters)}")
        print(f"  Net reduction:   {len(clusters) - len(new_clusters)}")
        data["clusters"] = new_clusters

        # Re-number cluster IDs sequentially
        for i, c in enumerate(data["clusters"]):
            c["id"] = i

        # Update stats
        data["stats"]["cluster_count"] = len(data["clusters"])
    else:
        remaining = len(clusters) - len(absorbed_ids)
        print(f"\n  Would reduce from {len(clusters)} to {remaining} clusters")

    # ─── Save ────────────────────────────────────────────────────────────
    if not dry_run:
        print(f"\nBacking up to {BACKUP_PATH}")
        # Read original for backup
        with open(CONCORDANCE_PATH) as f:
            original = f.read()
        with open(BACKUP_PATH, "w") as f:
            f.write(original)

        print(f"Saving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB")
        print("\nNext: rebuild search index")
        print("  python3 scripts/build_search_index.py")
    else:
        print("\nNo changes written (dry run).")


if __name__ == "__main__":
    main()

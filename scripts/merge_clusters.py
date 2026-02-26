#!/usr/bin/env python3
"""
Merge fragmented clusters in concordance.json.

Reads a merge plan (JSON file mapping merge groups), consolidates members,
cross-references, and edges, updates all pointers, and saves the result.

Usage:
    python scripts/merge_clusters.py [--plan merge_plan.json] [--dry-run]
"""

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
DEFAULT_PLAN_PATH = Path(__file__).parent.parent / "data" / "merge_plan.json"


def load_concordance():
    print(f"Loading {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    print(f"  {len(data['clusters'])} clusters")
    return data


def save_concordance(data):
    # Backup
    backup = CONCORDANCE_PATH.with_suffix(".pre_merge.json")
    if backup.exists():
        # Rotate backups
        backup2 = CONCORDANCE_PATH.with_suffix(".pre_merge2.json")
        shutil.copy2(backup, backup2)
    shutil.copy2(CONCORDANCE_PATH, backup)
    print(f"  Backup saved to {backup}")

    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f)
    size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"  Saved {CONCORDANCE_PATH} ({size_mb:.1f} MB)")


def auto_generate_merge_plan(data):
    """Generate merge plan from same-category, same-modern_name clusters."""
    clusters = data["clusters"]
    by_key = defaultdict(list)

    for c in clusters:
        gt = c.get("ground_truth", {})
        if not isinstance(gt, dict):
            continue
        mn = (gt.get("modern_name") or "").strip()
        if not mn:
            continue
        # Case-insensitive grouping
        key = (mn.lower(), c["category"])
        by_key[key].append(c)

    groups = []
    for (mn_lower, cat), group in sorted(by_key.items()):
        if len(group) < 2:
            continue
        # Sort by total_mentions descending — primary gets the most mentions
        group.sort(key=lambda c: -c.get("total_mentions", 0))
        ids = [c["id"] for c in group]
        groups.append({
            "ids": ids,
            "modern_name": group[0].get("ground_truth", {}).get("modern_name", mn_lower),
            "category": cat,
            "reason": f"same modern_name '{mn_lower}' + category '{cat}'"
        })

    return groups


def merge_group(clusters_by_id, group_ids):
    """Merge a group of cluster IDs into one. Returns (primary, removed_ids)."""
    group = [clusters_by_id[cid] for cid in group_ids if cid in clusters_by_id]
    if len(group) < 2:
        return None, []

    # Primary = most mentions
    group.sort(key=lambda c: -c.get("total_mentions", 0))
    primary = group[0]
    others = group[1:]

    # Merge members — deduplicate by (entity_id, book_id)
    seen_members = set()
    merged_members = []
    for m in primary.get("members", []):
        key = (m["entity_id"], m["book_id"])
        if key not in seen_members:
            seen_members.add(key)
            merged_members.append(m)

    for other in others:
        for m in other.get("members", []):
            key = (m["entity_id"], m["book_id"])
            if key not in seen_members:
                seen_members.add(key)
                merged_members.append(m)

    primary["members"] = merged_members

    # Merge cross-references — deduplicate by (target_cluster_id, link_type)
    seen_xrefs = set()
    merged_xrefs = []
    removed_ids = set(c["id"] for c in others)

    for xref in primary.get("cross_references", []):
        # Skip self-referential xrefs
        if xref.get("target_cluster_id") in removed_ids or xref.get("target_cluster_id") == primary["id"]:
            continue
        key = (xref.get("target_cluster_id"), xref.get("link_type", ""))
        if key not in seen_xrefs:
            seen_xrefs.add(key)
            merged_xrefs.append(xref)

    for other in others:
        for xref in other.get("cross_references", []):
            if xref.get("target_cluster_id") in removed_ids or xref.get("target_cluster_id") == primary["id"]:
                continue
            key = (xref.get("target_cluster_id"), xref.get("link_type", ""))
            if key not in seen_xrefs:
                seen_xrefs.add(key)
                merged_xrefs.append(xref)

    primary["cross_references"] = merged_xrefs

    # Merge edges — edges are dicts with source_book, source_name, target_book, target_name, similarity
    seen_edges = set()
    merged_edges = []
    removed_names = set()
    for other in others:
        for m in other.get("members", []):
            removed_names.add(m["name"])

    for edge_list_owner in [primary] + list(others):
        for edge in edge_list_owner.get("edges", []):
            key = (edge.get("source_book", ""), edge.get("source_name", ""),
                   edge.get("target_book", ""), edge.get("target_name", ""))
            if key not in seen_edges:
                seen_edges.add(key)
                merged_edges.append(edge)
    primary["edges"] = merged_edges

    # Pick best ground_truth — prefer one with most fields, or wikidata_id
    best_gt = primary.get("ground_truth", {})
    if not isinstance(best_gt, dict):
        best_gt = {}
    for other in others:
        other_gt = other.get("ground_truth", {})
        if not isinstance(other_gt, dict):
            continue
        # Score: count of non-empty fields
        def gt_score(gt):
            return sum(1 for v in gt.values() if v) + (10 if gt.get("wikidata_id") else 0) + (5 if gt.get("wikipedia_extract") else 0)
        if gt_score(other_gt) > gt_score(best_gt):
            best_gt = other_gt
    primary["ground_truth"] = best_gt

    # Recalculate stats
    primary["member_count"] = len(merged_members)
    primary["total_mentions"] = sum(m.get("count", 0) for m in merged_members)
    primary["book_count"] = len(set(m["book_id"] for m in merged_members))

    return primary, [c["id"] for c in others]


def apply_merge_plan(data, plan, dry_run=False):
    """Apply merge plan to concordance data."""
    clusters = data["clusters"]
    clusters_by_id = {c["id"]: c for c in clusters}

    total_removed = 0
    id_remap = {}  # old_id -> new_primary_id

    print(f"\nApplying {len(plan)} merge groups...")

    for i, group in enumerate(plan):
        ids = group["ids"]
        modern_name = group.get("modern_name", "?")
        category = group.get("category", "?")

        # Verify all IDs exist
        valid_ids = [cid for cid in ids if cid in clusters_by_id]
        if len(valid_ids) < 2:
            print(f"  Skip: {modern_name} ({category}) — only {len(valid_ids)} valid IDs")
            continue

        primary, removed = merge_group(clusters_by_id, valid_ids)
        if not primary:
            continue

        for rid in removed:
            id_remap[rid] = primary["id"]
            del clusters_by_id[rid]
            total_removed += 1

        mentions = primary["total_mentions"]
        books = primary["book_count"]
        members = primary["member_count"]
        print(f"  [{i+1}/{len(plan)}] {modern_name} ({category}): merged {len(removed)+1} → 1 "
              f"({mentions} mentions, {books} books, {members} members)")

    if dry_run:
        print(f"\n[DRY RUN] Would remove {total_removed} clusters, {len(plan)} merges")
        return data

    # Update cross-references everywhere — remap target_cluster_id
    print(f"\nRemapping cross-references...")
    remap_count = 0
    remaining = list(clusters_by_id.values())
    for c in remaining:
        updated_xrefs = []
        for xref in c.get("cross_references", []):
            tid = xref.get("target_cluster_id")
            if tid in id_remap:
                new_tid = id_remap[tid]
                # Skip if it would become self-referential
                if new_tid == c["id"]:
                    continue
                xref["target_cluster_id"] = new_tid
                # Update target name if we have it
                if new_tid in clusters_by_id:
                    xref["target_cluster_name"] = clusters_by_id[new_tid]["canonical_name"]
                remap_count += 1
            updated_xrefs.append(xref)

        # Deduplicate after remapping
        seen = set()
        deduped = []
        for xref in updated_xrefs:
            key = (xref.get("target_cluster_id"), xref.get("link_type", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(xref)
        c["cross_references"] = deduped

    print(f"  Remapped {remap_count} cross-reference targets")

    # Edges are dicts (not IDs), no remapping needed — they reference book/name pairs

    # Rebuild cluster list (preserve order, remove deleted)
    new_clusters = [c for c in clusters if c["id"] in clusters_by_id]

    # Re-number IDs sequentially
    print("Re-numbering cluster IDs...")
    old_to_new = {}
    for i, c in enumerate(new_clusters):
        old_to_new[c["id"]] = i
        c["id"] = i

    # Update all cross-reference target IDs to use new numbering
    for c in new_clusters:
        for xref in c.get("cross_references", []):
            tid = xref.get("target_cluster_id")
            if tid in old_to_new:
                xref["target_cluster_id"] = old_to_new[tid]

    data["clusters"] = new_clusters

    # Update stats
    data["stats"]["total_clusters"] = len(new_clusters)
    data["stats"]["total_entities"] = sum(c.get("member_count", len(c.get("members", []))) for c in new_clusters)
    data["metadata"]["last_merge"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    print(f"\nDone: {len(clusters)} → {len(new_clusters)} clusters ({total_removed} removed)")
    return data


def main():
    parser = argparse.ArgumentParser(description="Merge fragmented concordance clusters")
    parser.add_argument("--plan", type=Path, default=None,
                        help="JSON file with merge plan (default: auto-generate from same modern_name + category)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview merges without saving")
    parser.add_argument("--save-plan", type=Path, default=None,
                        help="Save auto-generated plan to file instead of applying")
    args = parser.parse_args()

    data = load_concordance()

    if args.plan:
        print(f"Loading merge plan from {args.plan}")
        with open(args.plan) as f:
            plan = json.load(f)
        print(f"  {len(plan)} merge groups")
    else:
        print("Auto-generating merge plan (same modern_name + category)...")
        plan = auto_generate_merge_plan(data)
        print(f"  Found {len(plan)} merge groups")

    if args.save_plan:
        args.save_plan.parent.mkdir(parents=True, exist_ok=True)
        with open(args.save_plan, "w") as f:
            json.dump(plan, f, indent=2)
        print(f"  Saved plan to {args.save_plan}")
        return

    if not plan:
        print("No merges needed!")
        return

    data = apply_merge_plan(data, plan, dry_run=args.dry_run)

    if not args.dry_run:
        save_concordance(data)
        print("\nRemember to rebuild downstream artifacts:")
        print("  python scripts/build_search_index.py")
        print("  python scripts/build_neighbor_graph.py")


if __name__ == "__main__":
    main()

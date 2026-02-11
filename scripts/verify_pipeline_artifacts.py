#!/usr/bin/env python3
"""
Verify concordance pipeline artifacts are internally consistent.

Checks:
1) concordance.json has unique cluster IDs (and stable keys if required)
2) search_index.json count matches concordance cluster count
3) search index metadata IDs map to concordance IDs
4) cluster_neighbors.json count and IDs match the search index
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify concordance artifacts")
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent.parent / "web" / "public" / "data"),
        help="Directory containing concordance/search/neighbor JSON files",
    )
    parser.add_argument(
        "--allow-missing-stable-keys",
        action="store_true",
        help="Do not fail if clusters/search metadata are missing stable_key",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    concordance_path = data_dir / "concordance.json"
    search_path = data_dir / "search_index.json"
    neighbors_path = data_dir / "cluster_neighbors.json"

    errors: list[str] = []
    warnings: list[str] = []

    for p in [concordance_path, search_path, neighbors_path]:
        if not p.exists():
            errors.append(f"Missing file: {p}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        return 1

    concordance = load_json(concordance_path)
    clusters = concordance.get("clusters", [])
    if not isinstance(clusters, list) or not clusters:
        errors.append("concordance.json has no clusters array")

    cluster_ids = []
    stable_keys = []
    for c in clusters:
        cid = c.get("id")
        if cid is None:
            errors.append("Cluster without id in concordance.json")
            continue
        cluster_ids.append(str(cid))
        sk = c.get("stable_key")
        if sk:
            stable_keys.append(str(sk))
        elif not args.allow_missing_stable_keys:
            errors.append(f"Cluster {cid} missing stable_key")

    if len(set(cluster_ids)) != len(cluster_ids):
        errors.append("Duplicate cluster IDs in concordance.json")
    if stable_keys and len(set(stable_keys)) != len(stable_keys):
        errors.append("Duplicate stable_key values in concordance.json")

    search_index = load_json(search_path)
    entries = search_index.get("entries", [])
    if not isinstance(entries, list):
        errors.append("search_index.json entries is not a list")
        entries = []

    if len(entries) != len(clusters):
        errors.append(
            f"Count mismatch: search_index entries={len(entries)} vs concordance clusters={len(clusters)}"
        )

    entry_ids = []
    entry_stable_keys = []
    for i, entry in enumerate(entries):
        meta = entry.get("metadata", {})
        eid = meta.get("id")
        if eid is None:
            errors.append(f"Search entry {i} missing metadata.id")
            continue
        entry_ids.append(str(eid))
        sk = meta.get("stable_key")
        if sk:
            entry_stable_keys.append(str(sk))
        elif not args.allow_missing_stable_keys:
            errors.append(f"Search entry id={eid} missing metadata.stable_key")
        if not meta.get("display_name"):
            warnings.append(f"Search entry id={eid} missing metadata.display_name")

    if set(entry_ids) != set(cluster_ids):
        errors.append("search_index metadata.id set does not match concordance cluster id set")

    neighbors = load_json(neighbors_path)
    neighbor_map = neighbors.get("neighbors", {})
    neighbor_count = neighbors.get("count")
    if not isinstance(neighbor_map, dict):
        errors.append("cluster_neighbors.json neighbors is not an object")
        neighbor_map = {}

    if neighbor_count != len(entries):
        errors.append(
            f"Count mismatch: cluster_neighbors count={neighbor_count} vs search_index entries={len(entries)}"
        )

    if set(neighbor_map.keys()) != set(entry_ids):
        errors.append("cluster_neighbors neighbor IDs do not match search_index metadata.id set")

    for cid, nlist in neighbor_map.items():
        if not isinstance(nlist, list):
            errors.append(f"Neighbors for cluster {cid} is not a list")
            continue
        for n in nlist:
            nid = n.get("id")
            if nid is None:
                errors.append(f"Neighbor entry for cluster {cid} missing id")
                continue
            if str(nid) not in set(entry_ids):
                errors.append(f"Neighbor id {nid} for cluster {cid} not in search index IDs")

    if warnings:
        for w in warnings[:20]:
            print(f"WARN: {w}")
        if len(warnings) > 20:
            print(f"WARN: ... {len(warnings) - 20} more warnings")

    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"\nFAILED: {len(errors)} errors, {len(warnings)} warnings")
        return 1

    print(
        "OK: "
        f"{len(clusters)} clusters, {len(entries)} indexed entries, "
        f"{len(neighbor_map)} neighbor rows verified"
    )
    if warnings:
        print(f"Completed with {len(warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())


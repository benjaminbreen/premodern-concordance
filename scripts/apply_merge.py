#!/usr/bin/env python3
"""
Apply near-duplicate merge to the existing concordance.json.

Standalone script that doesn't need the embedding model — just reads
the current concordance, merges near-duplicate clusters, and writes
the result back.

Usage:
    python apply_merge.py              # apply merges in-place
    python apply_merge.py --dry-run    # preview only
"""

import argparse
import json
import copy
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
CONCORDANCE_PATH = DATA_DIR / "concordance.json"


def normalized_levenshtein(a: str, b: str) -> float:
    """Normalized Levenshtein similarity (1.0 = identical)."""
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0.0
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(dp[j], dp[j - 1], prev)
            prev = temp
    return 1 - dp[n] / max(m, n)


def merge_near_duplicates(
    clusters: list[dict],
    lev_threshold: float = 0.83,
) -> tuple[list[dict], int]:
    """Merge cluster pairs that are near-duplicates split by subcategory noise."""
    merged_into: dict[int, int] = {}
    merge_count = 0

    by_category: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(clusters):
        by_category[c["category"]].append(i)

    for cat, indices in by_category.items():
        for ii in range(len(indices)):
            idx_a = indices[ii]
            if idx_a in merged_into:
                continue
            a = clusters[idx_a]

            for jj in range(ii + 1, len(indices)):
                idx_b = indices[jj]
                if idx_b in merged_into:
                    continue
                b = clusters[idx_b]

                t = lev_threshold + 0.02 if cat == "PLACE" else lev_threshold
                lev = normalized_levenshtein(a["canonical_name"], b["canonical_name"])
                if lev < t:
                    continue

                books_a = set(m["book_id"] for m in a["members"])
                books_b = set(m["book_id"] for m in b["members"])
                shared_books = books_a & books_b

                if not shared_books:
                    if lev < 1.0:
                        continue
                    names_a = set(m["name"].lower() for m in a["members"])
                    names_b = set(m["name"].lower() for m in b["members"])
                    if not (names_a & names_b):
                        continue

                if a["total_mentions"] >= b["total_mentions"]:
                    keeper, absorbed = idx_a, idx_b
                else:
                    keeper, absorbed = idx_b, idx_a

                k, ab = clusters[keeper], clusters[absorbed]

                existing = {(m["book_id"], m["entity_id"]) for m in k["members"]}
                for m in ab["members"]:
                    if (m["book_id"], m["entity_id"]) not in existing:
                        k["members"].append(m)

                existing_edges = {
                    (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
                    for e in k["edges"]
                }
                for e in ab["edges"]:
                    key = (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
                    if key not in existing_edges:
                        k["edges"].append(e)

                k["total_mentions"] = sum(m["count"] for m in k["members"])
                k["book_count"] = len(set(m["book_id"] for m in k["members"]))

                merged_into[absorbed] = keeper
                merge_count += 1

                print(f"    {ab['canonical_name']} -> {k['canonical_name']} "
                      f"(lev={lev:.2f}, shared_books={len(shared_books)})")

    result = [c for i, c in enumerate(clusters) if i not in merged_into]
    result.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))
    for i, c in enumerate(result):
        c["id"] = i + 1

    return result, merge_count


def main():
    parser = argparse.ArgumentParser(description="Apply near-duplicate merge to concordance")
    parser.add_argument("--dry-run", action="store_true", help="Preview merges without writing")
    parser.add_argument("--input", type=str, default=str(CONCORDANCE_PATH))
    args = parser.parse_args()

    path = Path(args.input)
    print(f"Loading {path}...")
    with open(path) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters loaded")

    print("\nMerging near-duplicates...")
    merged, count = merge_near_duplicates(copy.deepcopy(clusters))
    print(f"\n  {count} merges -> {len(merged)} clusters (was {len(clusters)})")

    if args.dry_run:
        print("\n[DRY RUN] No file written.")
        return

    data["clusters"] = merged
    data["metadata"]["merge_applied"] = True
    data["metadata"]["pre_merge_count"] = len(clusters)

    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    main()

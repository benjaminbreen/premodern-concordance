#!/usr/bin/env python3
"""
Pre-compute nearest neighbors in embedding space for all concordance clusters.
Reads search_index.json, computes cosine similarities, outputs cluster_neighbors.json.

Output format:
{
  "neighbors": {
    "<cluster_id>": [
      { "id": <int>, "similarity": <float> },
      ...  (top K neighbors)
    ]
  }
}

~300KB for 1283 clusters × 15 neighbors.
"""

import json
import math
import sys
from pathlib import Path

K = 15  # number of neighbors per cluster

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def main():
    base = Path(__file__).parent.parent / "web" / "public" / "data"
    index_path = base / "search_index.json"
    out_path = base / "cluster_neighbors.json"

    print(f"Loading {index_path}...")
    with open(index_path) as f:
        data = json.load(f)

    entries = data["entries"]
    n = len(entries)
    print(f"  {n} entries, {data['dimensions']} dims")

    # Extract IDs and embeddings
    ids = [e["metadata"]["id"] for e in entries]
    names = [e["metadata"]["canonical_name"] for e in entries]
    embeddings = [e["embedding"] for e in entries]

    # Pre-compute norms for efficiency
    norms = [math.sqrt(sum(x * x for x in emb)) for emb in embeddings]

    print(f"Computing {n}×{n} pairwise similarities...")
    neighbors: dict[int, list[dict]] = {}

    for i in range(n):
        if i % 100 == 0:
            print(f"  {i}/{n}...")

        sims = []
        for j in range(n):
            if i == j:
                continue
            if norms[i] == 0 or norms[j] == 0:
                continue
            dot = sum(a * b for a, b in zip(embeddings[i], embeddings[j]))
            sim = dot / (norms[i] * norms[j])
            sims.append((ids[j], round(sim, 4)))

        # Top K by similarity
        sims.sort(key=lambda x: -x[1])
        neighbors[ids[i]] = [
            {"id": s[0], "sim": s[1]}
            for s in sims[:K]
        ]

    output = {"k": K, "count": n, "neighbors": neighbors}

    print(f"Writing {out_path}...")
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_kb = out_path.stat().st_size / 1024
    print(f"  {size_kb:.0f} KB written")
    print("Done.")

if __name__ == "__main__":
    main()

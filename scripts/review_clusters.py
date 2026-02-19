#!/usr/bin/env python3
"""
Multi-angle cluster quality review and additional merge candidate detection.

Checks:
  1. Embedding similarity — cluster pairs with cosine > threshold
  2. Same Wikipedia URL — clusters pointing to same article
  3. Member overlap — clusters sharing entity members
  4. Quality spot-check — verify merged clusters look coherent
  5. Singleton review — small clusters that may be fragments
  6. Category anomalies — entities that seem miscategorized

Usage:
    python3 scripts/review_clusters.py
    python3 scripts/review_clusters.py --output data/review_report.json
"""

import json
import re
import unicodedata
import numpy as np
from collections import defaultdict
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
SEARCH_INDEX_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "search_index.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "review_report.json"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_data():
    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    print("Loading search index...")
    with open(SEARCH_INDEX_PATH) as f:
        index = json.load(f)
    embeddings = np.array([e["embedding"] for e in index["entries"]], dtype=np.float32)
    print(f"  {embeddings.shape[0]} embeddings, {embeddings.shape[1]} dims")

    return clusters, embeddings, index


def cluster_summary(c):
    gt = c.get("ground_truth") or {}
    members = c.get("members", [])
    names = sorted(set(m["name"] for m in members))[:6]
    return {
        "id": c["id"],
        "canonical_name": c.get("canonical_name", ""),
        "category": c.get("category", ""),
        "modern_name": gt.get("modern_name", ""),
        "wikidata_id": gt.get("wikidata_id", ""),
        "wikipedia_url": gt.get("wikipedia_url", ""),
        "book_count": c.get("book_count", 0),
        "total_mentions": c.get("total_mentions", 0),
        "member_count": len(members),
        "sample_names": names,
    }


def check_embedding_similarity(clusters, embeddings, threshold=0.92):
    """Find cluster pairs with high embedding cosine similarity."""
    print(f"\n{'='*60}")
    print(f"CHECK 1: Embedding similarity (threshold={threshold})")
    print(f"{'='*60}")

    n = len(clusters)
    assert n == embeddings.shape[0], f"Mismatch: {n} clusters vs {embeddings.shape[0]} embeddings"

    # Normalize embeddings for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = embeddings / norms

    # Process in chunks to avoid memory issues
    proposals = []
    chunk_size = 500
    for i_start in range(0, n, chunk_size):
        i_end = min(i_start + chunk_size, n)
        # Compute similarity of chunk against all clusters after it
        chunk = normed[i_start:i_end]
        sims = chunk @ normed[i_end:].T  # only upper triangle

        rows, cols = np.where(sims >= threshold)
        for r, c_local in zip(rows, cols):
            i = i_start + r
            j = i_end + c_local
            sim = float(sims[r, c_local])

            ci = clusters[i]
            cj = clusters[j]

            # Skip if same category requirement not met
            if ci.get("category") != cj.get("category"):
                continue

            # Skip if they already share a QID (already proposed)
            qi = (ci.get("ground_truth") or {}).get("wikidata_id", "")
            qj = (cj.get("ground_truth") or {}).get("wikidata_id", "")
            if qi and qj and qi == qj:
                continue

            # Skip if they share modern_name (already proposed)
            mi = (ci.get("ground_truth") or {}).get("modern_name", "").lower().strip()
            mj = (cj.get("ground_truth") or {}).get("modern_name", "").lower().strip()
            if mi and mj and mi == mj:
                continue

            proposals.append({
                "similarity": round(sim, 4),
                "cluster_a": cluster_summary(ci),
                "cluster_b": cluster_summary(cj),
            })

        if i_start % 1000 == 0 and i_start > 0:
            print(f"  Processed {i_start}/{n}...")

    # Also check within chunks (upper triangle)
    for i_start in range(0, n, chunk_size):
        i_end = min(i_start + chunk_size, n)
        chunk = normed[i_start:i_end]
        sims = chunk @ chunk.T
        for r in range(sims.shape[0]):
            for c_local in range(r + 1, sims.shape[1]):
                if sims[r, c_local] >= threshold:
                    i = i_start + r
                    j = i_start + c_local
                    ci = clusters[i]
                    cj = clusters[j]
                    if ci.get("category") != cj.get("category"):
                        continue
                    qi = (ci.get("ground_truth") or {}).get("wikidata_id", "")
                    qj = (cj.get("ground_truth") or {}).get("wikidata_id", "")
                    if qi and qj and qi == qj:
                        continue
                    mi = (ci.get("ground_truth") or {}).get("modern_name", "").lower().strip()
                    mj = (cj.get("ground_truth") or {}).get("modern_name", "").lower().strip()
                    if mi and mj and mi == mj:
                        continue
                    proposals.append({
                        "similarity": round(float(sims[r, c_local]), 4),
                        "cluster_a": cluster_summary(ci),
                        "cluster_b": cluster_summary(cj),
                    })

    proposals.sort(key=lambda p: -p["similarity"])
    print(f"  Found {len(proposals)} new high-similarity pairs")
    if proposals:
        print(f"\n  Top 30:")
        for p in proposals[:30]:
            a = p["cluster_a"]
            b = p["cluster_b"]
            print(f"    {p['similarity']:.3f}  [{a['category']}] {a['canonical_name']} ({a['modern_name']}) <-> {b['canonical_name']} ({b['modern_name']})")
            print(f"           names: {a['sample_names'][:3]} vs {b['sample_names'][:3]}")
    return proposals


def check_same_wikipedia(clusters):
    """Find clusters pointing to the same Wikipedia article."""
    print(f"\n{'='*60}")
    print("CHECK 2: Same Wikipedia URL")
    print(f"{'='*60}")

    by_url = defaultdict(list)
    for c in clusters:
        gt = c.get("ground_truth") or {}
        url = gt.get("wikipedia_url", "").strip()
        if url:
            # Normalize URL
            url_norm = url.lower().replace("https://", "").replace("http://", "")
            by_url[url_norm].append(c)

    duplicates = []
    for url, group in by_url.items():
        if len(group) >= 2:
            # Check if same category
            cats = set(c.get("category") for c in group)
            duplicates.append({
                "wikipedia_url": group[0].get("ground_truth", {}).get("wikipedia_url", ""),
                "same_category": len(cats) == 1,
                "categories": sorted(cats),
                "clusters": [cluster_summary(c) for c in group],
            })

    duplicates.sort(key=lambda d: -sum(c["total_mentions"] for c in d["clusters"]))
    print(f"  Found {len(duplicates)} groups sharing a Wikipedia URL")
    for d in duplicates[:20]:
        names = " + ".join(c["canonical_name"] for c in d["clusters"])
        cats = "/".join(d["categories"])
        mentions = sum(c["total_mentions"] for c in d["clusters"])
        print(f"    [{cats}] {names}  ({mentions} mentions)")
        print(f"      URL: {d['wikipedia_url']}")
    return duplicates


def check_member_overlap(clusters):
    """Find clusters that share entity members."""
    print(f"\n{'='*60}")
    print("CHECK 3: Member overlap")
    print(f"{'='*60}")

    # Build entity_id -> cluster map
    entity_to_clusters = defaultdict(set)
    for idx, c in enumerate(clusters):
        for m in c.get("members", []):
            eid = m.get("entity_id", "")
            if eid:
                entity_to_clusters[eid].add(idx)

    # Find overlapping pairs
    overlap_pairs = defaultdict(int)
    for eid, cidxs in entity_to_clusters.items():
        if len(cidxs) >= 2:
            cidx_list = sorted(cidxs)
            for i in range(len(cidx_list)):
                for j in range(i + 1, len(cidx_list)):
                    overlap_pairs[(cidx_list[i], cidx_list[j])] += 1

    overlaps = []
    for (i, j), count in sorted(overlap_pairs.items(), key=lambda x: -x[1]):
        ci = clusters[i]
        cj = clusters[j]
        overlaps.append({
            "shared_members": count,
            "cluster_a": cluster_summary(ci),
            "cluster_b": cluster_summary(cj),
        })

    print(f"  Found {len(overlaps)} cluster pairs with shared members")
    for o in overlaps[:15]:
        a = o["cluster_a"]
        b = o["cluster_b"]
        print(f"    {o['shared_members']} shared: [{a['category']}] {a['canonical_name']} <-> [{b['category']}] {b['canonical_name']}")
    return overlaps


def quality_spotcheck(clusters):
    """Check for incoherent clusters (members from very different semantic domains)."""
    print(f"\n{'='*60}")
    print("CHECK 4: Quality spot-check (large clusters)")
    print(f"{'='*60}")

    large = [c for c in clusters if len(c.get("members", [])) >= 8]
    large.sort(key=lambda c: -len(c.get("members", [])))
    print(f"  {len(large)} clusters with 8+ members")

    suspicious = []
    for c in large:
        members = c.get("members", [])
        names = [m["name"] for m in members]
        norm_names = [normalize(n) for n in names]

        # Check: do member names have any common words?
        word_counts = defaultdict(int)
        for nn in norm_names:
            for w in nn.split():
                if len(w) >= 3:
                    word_counts[w] += 1

        # If no word appears in more than 20% of members, it might be incoherent
        max_freq = max(word_counts.values()) if word_counts else 0
        coherence = max_freq / len(members) if members else 0

        books = set(m.get("book_id") for m in members)

        suspicious.append({
            "cluster": cluster_summary(c),
            "coherence_score": round(coherence, 3),
            "all_names": sorted(set(names)),
            "book_count": len(books),
        })

    # Sort by coherence (least coherent first)
    suspicious.sort(key=lambda s: s["coherence_score"])
    print(f"\n  Least coherent large clusters:")
    for s in suspicious[:20]:
        c = s["cluster"]
        print(f"    coherence={s['coherence_score']:.2f} [{c['category']}] {c['canonical_name']} "
              f"({c['member_count']} members, {c['book_count']} books)")
        print(f"      names: {s['all_names'][:8]}")
    return suspicious


def check_singletons(clusters):
    """Review singleton clusters that might be fragments."""
    print(f"\n{'='*60}")
    print("CHECK 5: Singleton clusters (1 member)")
    print(f"{'='*60}")

    singletons = [c for c in clusters if len(c.get("members", [])) == 1]
    print(f"  {len(singletons)} singleton clusters out of {len(clusters)} total ({100*len(singletons)/len(clusters):.1f}%)")

    # Group by category
    by_cat = defaultdict(int)
    for c in singletons:
        by_cat[c.get("category", "?")] += 1
    for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    # High-mention singletons are interesting — they might need merging
    high_mention_singletons = [c for c in singletons if c.get("total_mentions", 0) >= 5]
    high_mention_singletons.sort(key=lambda c: -c.get("total_mentions", 0))
    print(f"\n  High-mention singletons (>=5 mentions): {len(high_mention_singletons)}")
    for c in high_mention_singletons[:20]:
        gt = c.get("ground_truth") or {}
        m = c["members"][0]
        print(f"    [{c['category']}] {c['canonical_name']} ({m['count']} mentions, {m['book_id']})")
        print(f"      modern: {gt.get('modern_name', '?')}, qid: {gt.get('wikidata_id', '?')}")

    return high_mention_singletons


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--sim-threshold", type=float, default=0.92)
    args = parser.parse_args()

    clusters, embeddings, index = load_data()

    # Run all checks
    sim_proposals = check_embedding_similarity(clusters, embeddings, args.sim_threshold)
    wiki_dupes = check_same_wikipedia(clusters)
    member_overlaps = check_member_overlap(clusters)
    quality = quality_spotcheck(clusters)
    singletons = check_singletons(clusters)

    # Save report
    report = {
        "summary": {
            "total_clusters": len(clusters),
            "embedding_similarity_pairs": len(sim_proposals),
            "same_wikipedia_groups": len(wiki_dupes),
            "member_overlap_pairs": len(member_overlaps),
            "large_clusters_checked": len(quality),
            "singleton_clusters": len([c for c in clusters if len(c.get("members", [])) == 1]),
        },
        "embedding_similarity": sim_proposals[:100],  # top 100
        "same_wikipedia": wiki_dupes,
        "member_overlap": member_overlaps[:50],
        "quality_spotcheck": quality[:30],
        "singletons_high_mention": [cluster_summary(c) for c in (singletons or [])[:50]],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to {output_path}")


if __name__ == "__main__":
    main()

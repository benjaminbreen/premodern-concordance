#!/usr/bin/env python3
"""
Build the cross-book concordance using fine-tuned embeddings.

Loads entities from all books, embeds them, finds cross-book matches,
and clusters them into concordance groups (entities that refer to the
same real-world thing across different books and languages).

Usage:
    python build_concordance.py
    python build_concordance.py --threshold 0.82 --min-count 2
"""

import argparse
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from collections import defaultdict

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_PATH = Path(__file__).parent.parent / "models" / "finetuned-bge-m3-v2"
DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
OUTPUT_PATH = DATA_DIR / "concordance.json"

# Cross-book matching thresholds (slightly lower than within-book dedup
# because cross-lingual matches are the whole point)
MATCH_THRESHOLD = 0.84
PERSON_THRESHOLD = 0.80   # Lower for persons across languages (Galen/Galeno)
MIN_ENTITY_COUNT = 1      # Minimum occurrence count to include


def normalize_for_key(text: str) -> str:
    """Normalize a name for stable-key signature generation."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def build_cluster_stable_key(cluster: dict) -> str:
    """Build a deterministic key from category + normalized member names."""
    names = set()
    for member in cluster.get("members", []):
        n = normalize_for_key(member.get("name", ""))
        if n:
            names.add(n)
        normalized_variants = sorted(
            {normalize_for_key(variant) for variant in member.get("variants", []) if variant}
        )
        for v in normalized_variants[:5]:
            if v:
                names.add(v)

    # Keep signature bounded while remaining deterministic.
    signature_names = sorted(names)[:16]
    signature = f"{cluster.get('category', '').lower()}|{'|'.join(signature_names)}"
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
    return f"clu_{digest}"


def assign_stable_keys(clusters: list[dict]) -> None:
    """Assign unique stable keys to all clusters in-place."""
    seen = defaultdict(int)
    for cluster in clusters:
        base = build_cluster_stable_key(cluster)
        seen[base] += 1
        if seen[base] == 1:
            cluster["stable_key"] = base
        else:
            cluster["stable_key"] = f"{base}-{seen[base]}"


def load_book_entities(filepath: Path) -> dict:
    """Load a book's entity file and return book metadata + entities."""
    with open(filepath) as f:
        data = json.load(f)
    return data


def embed_entities(entities: list[dict], model: SentenceTransformer) -> np.ndarray:
    """Embed entity names with category context."""
    texts = [
        f"{e['name']} ({e.get('subcategory', e['category']).lower()})"
        for e in entities
    ]
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=True, batch_size=256)


def string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity based on shared characters and prefix."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    min_len = min(len(s1), len(s2))
    if min_len == 0:
        return 0.0
    common_prefix = 0
    for i in range(min_len):
        if s1[i] == s2[i]:
            common_prefix += 1
        else:
            break
    set1, set2 = set(s1), set(s2)
    shared = len(set1 & set2)
    total = len(set1 | set2)
    char_ratio = shared / total if total > 0 else 0
    len_ratio = min_len / max(len(s1), len(s2))
    prefix_score = common_prefix / min_len
    return 0.5 * prefix_score + 0.3 * char_ratio + 0.2 * len_ratio


def find_cross_book_matches(
    book_a_entities: list[dict],
    book_a_embeddings: np.ndarray,
    book_a_id: str,
    book_b_entities: list[dict],
    book_b_embeddings: np.ndarray,
    book_b_id: str,
    threshold: float,
) -> list[dict]:
    """Find matching entities between two books."""
    matches = []
    # Compute similarity matrix
    sims = book_a_embeddings @ book_b_embeddings.T  # (n_a, n_b)

    for i in range(len(book_a_entities)):
        cat_i = book_a_entities[i]["category"]
        for j in range(len(book_b_entities)):
            cat_j = book_b_entities[j]["category"]
            if cat_i != cat_j:
                continue

            sim = float(sims[i, j])
            t = PERSON_THRESHOLD if cat_i == "PERSON" else threshold

            # Boost threshold if string similarity is high
            str_sim = string_similarity(
                book_a_entities[i]["name"],
                book_b_entities[j]["name"]
            )
            if str_sim > 0.5:
                t -= 0.03

            if sim >= t:
                matches.append({
                    "a_idx": i,
                    "b_idx": j,
                    "a_book": book_a_id,
                    "b_book": book_b_id,
                    "similarity": sim,
                    "str_sim": str_sim,
                    "category": cat_i,
                })

    return matches


def build_clusters(
    all_matches: list[dict],
    book_entities: dict[str, list[dict]],
) -> list[dict]:
    """Build concordance clusters from pairwise matches.

    Each cluster is a group of entities across books that refer to
    the same real-world thing.
    """
    # Create a unified index: (book_id, entity_idx) -> global_id
    global_id_map = {}
    reverse_map = {}
    gid = 0
    for book_id, entities in book_entities.items():
        for idx in range(len(entities)):
            key = (book_id, idx)
            global_id_map[key] = gid
            reverse_map[gid] = key
            gid += 1

    # Build adjacency graph from matches
    neighbors = defaultdict(set)
    edge_data = {}  # (gid_a, gid_b) -> match info

    for match in all_matches:
        gid_a = global_id_map[(match["a_book"], match["a_idx"])]
        gid_b = global_id_map[(match["b_book"], match["b_idx"])]
        neighbors[gid_a].add(gid_b)
        neighbors[gid_b].add(gid_a)
        edge_key = (min(gid_a, gid_b), max(gid_a, gid_b))
        edge_data[edge_key] = match

    # Find connected components via BFS
    visited = set()
    raw_groups = []

    for node in neighbors:
        if node in visited:
            continue
        group = []
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            group.append(current)
            for neighbor in neighbors[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(group) > 1:
            raw_groups.append(sorted(group))

    # Post-process: validate groups — prune entities that are too dissimilar
    # to the primary (highest count) member
    clusters = []
    for group in raw_groups:
        # Find primary member (highest total count)
        primary_gid = max(group, key=lambda g: book_entities[reverse_map[g][0]][reverse_map[g][1]]["count"])
        primary_book, primary_idx = reverse_map[primary_gid]
        primary_entity = book_entities[primary_book][primary_idx]

        # Validate each member: must have a direct high-similarity edge
        # to the PRIMARY entity (not to any other validated member, to prevent chaining)
        validated = [primary_gid]
        for gid in group:
            if gid == primary_gid:
                continue
            book_id, idx = reverse_map[gid]
            entity = book_entities[book_id][idx]
            ss = string_similarity(primary_entity["name"], entity["name"])
            is_substr = (primary_entity["name"].lower() in entity["name"].lower() or
                         entity["name"].lower() in primary_entity["name"].lower())
            # Check for direct edge to the PRIMARY member only
            has_direct_edge = False
            edge_key = (min(gid, primary_gid), max(gid, primary_gid))
            if edge_key in edge_data:
                has_direct_edge = edge_data[edge_key]["similarity"] >= 0.84
            if (ss >= 0.35 and has_direct_edge) or is_substr:
                validated.append(gid)
            elif has_direct_edge and ss >= 0.2:
                # Allow if direct edge is very strong (>= 0.90)
                if edge_data[edge_key]["similarity"] >= 0.90:
                    validated.append(gid)

        if len(validated) < 2:
            continue

        # Check this cluster spans multiple books
        books_in_cluster = set()
        for gid in validated:
            book_id, _ = reverse_map[gid]
            books_in_cluster.add(book_id)

        if len(books_in_cluster) < 2:
            continue  # Skip within-book matches (already handled by dedup)

        # Build cluster object
        members = []
        total_mentions = 0
        for gid in validated:
            book_id, idx = reverse_map[gid]
            entity = book_entities[book_id][idx]
            total_mentions += entity["count"]
            members.append({
                "entity_id": entity["id"],
                "book_id": book_id,
                "name": entity["name"],
                "category": entity["category"],
                "subcategory": entity.get("subcategory", ""),
                "count": entity["count"],
                "variants": entity.get("variants", [entity["name"]]),
                "contexts": entity.get("contexts", [])[:2],
            })

        # Collect edges within this cluster
        edges = []
        for i, gid_a in enumerate(validated):
            for gid_b in validated[i+1:]:
                edge_key = (min(gid_a, gid_b), max(gid_a, gid_b))
                if edge_key in edge_data:
                    match = edge_data[edge_key]
                    book_a, idx_a = reverse_map[gid_a]
                    book_b, idx_b = reverse_map[gid_b]
                    edges.append({
                        "source_book": book_a,
                        "source_name": book_entities[book_a][idx_a]["name"],
                        "target_book": book_b,
                        "target_name": book_entities[book_b][idx_b]["name"],
                        "similarity": round(match["similarity"], 3),
                    })

        cluster = {
            "canonical_name": primary_entity["name"],
            "category": primary_entity["category"],
            "subcategory": primary_entity.get("subcategory", ""),
            "book_count": len(books_in_cluster),
            "total_mentions": total_mentions,
            "members": members,
            "edges": edges,
        }
        clusters.append(cluster)

    # Sort by book_count (desc), then total_mentions (desc)
    clusters.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))

    # Assign IDs
    for i, cluster in enumerate(clusters):
        cluster["id"] = i + 1

    return clusters


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
    """Merge cluster pairs that are near-duplicates split by subcategory noise.

    Criteria (all must hold):
      1. Same category
      2. High normalized Levenshtein between canonical names (>= lev_threshold)
      3. Share at least one book (both have members from the same source text)
         — OR identical canonical names with variant-level name overlap (exact dupes)

    This catches orthographic splits (cheiro/cheyro, estomago/eſtomago) without
    merging genuinely different concepts (Africa/Arica, cabras/cobras).
    """
    merged_into: dict[int, int] = {}  # cluster index -> absorbing cluster index
    merge_count = 0

    # Index clusters by category for efficient lookup
    by_category: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(clusters):
        by_category[c["category"]].append(i)

    for cat, indices in by_category.items():
        for ii in range(len(indices)):
            idx_a = indices[ii]
            # Skip if already absorbed
            if idx_a in merged_into:
                continue
            a = clusters[idx_a]

            for jj in range(ii + 1, len(indices)):
                idx_b = indices[jj]
                if idx_b in merged_into:
                    continue
                b = clusters[idx_b]

                # Check Levenshtein similarity
                # Places need a higher bar — short place names are easily confused
                # (Africa/Arica, Goa/Gao)
                t = lev_threshold + 0.02 if cat == "PLACE" else lev_threshold
                lev = normalized_levenshtein(a["canonical_name"], b["canonical_name"])
                if lev < t:
                    continue

                # Check shared books (primary safeguard)
                books_a = set(m["book_id"] for m in a["members"])
                books_b = set(m["book_id"] for m in b["members"])
                shared_books = books_a & books_b

                # For identical names (lev=1.0), also allow name overlap without shared books
                # (catches exact dupes split only by subcategory)
                if not shared_books:
                    if lev < 1.0:
                        continue
                    # Identical names: require variant-level overlap as confirmation
                    names_a = set(m["name"].lower() for m in a["members"])
                    names_b = set(m["name"].lower() for m in b["members"])
                    if not (names_a & names_b):
                        continue

                # Merge: absorb smaller into larger
                if a["total_mentions"] >= b["total_mentions"]:
                    keeper, absorbed = idx_a, idx_b
                else:
                    keeper, absorbed = idx_b, idx_a

                k, ab = clusters[keeper], clusters[absorbed]

                # Merge members (avoid duplicating same book+entity_id)
                existing = {(m["book_id"], m["entity_id"]) for m in k["members"]}
                for m in ab["members"]:
                    if (m["book_id"], m["entity_id"]) not in existing:
                        k["members"].append(m)

                # Merge edges
                existing_edges = {
                    (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
                    for e in k["edges"]
                }
                for e in ab["edges"]:
                    key = (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
                    if key not in existing_edges:
                        k["edges"].append(e)

                # Update stats
                k["total_mentions"] = sum(m["count"] for m in k["members"])
                k["book_count"] = len(set(m["book_id"] for m in k["members"]))

                merged_into[absorbed] = keeper
                merge_count += 1

                print(f"    {ab['canonical_name']} -> {k['canonical_name']} "
                      f"(lev={lev:.2f}, shared_books={len(shared_books)})")

    # Remove absorbed clusters
    result = [c for i, c in enumerate(clusters) if i not in merged_into]

    # Re-sort and re-assign IDs
    result.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))
    for i, c in enumerate(result):
        c["id"] = i + 1

    return result, merge_count


def main():
    parser = argparse.ArgumentParser(description="Build cross-book concordance")
    parser.add_argument("--threshold", type=float, default=MATCH_THRESHOLD,
                        help=f"Match threshold (default: {MATCH_THRESHOLD})")
    parser.add_argument("--min-count", type=int, default=MIN_ENTITY_COUNT,
                        help=f"Min entity count to include (default: {MIN_ENTITY_COUNT})")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH),
                        help=f"Output file (default: {OUTPUT_PATH})")
    args = parser.parse_args()

    # Discover all entity files
    entity_files = sorted(DATA_DIR.glob("*_entities.json"))
    if not entity_files:
        print("No entity files found in", DATA_DIR)
        return

    print(f"Found {len(entity_files)} books:")

    # Load all books
    books_meta = []
    book_entities = {}  # book_id -> list of entities
    for filepath in entity_files:
        data = load_book_entities(filepath)
        book_id = data["book"]["id"]
        entities = [e for e in data["entities"] if e["count"] >= args.min_count]
        book_entities[book_id] = entities
        books_meta.append(data["book"])
        print(f"  {data['book']['title']} ({data['book'].get('language', '?')}): {len(entities)} entities")

    if len(books_meta) < 2:
        print("Need at least 2 books for concordance.")
        return

    # Load embedding model
    print(f"\nLoading model from {MODEL_PATH}...")
    model = SentenceTransformer(str(MODEL_PATH))

    # Embed all books
    book_embeddings = {}
    for book_id, entities in book_entities.items():
        book_title = next(b["title"] for b in books_meta if b["id"] == book_id)
        print(f"\nEmbedding {book_title} ({len(entities)} entities)...")
        book_embeddings[book_id] = embed_entities(entities, model)

    # Find cross-book matches for each pair
    book_ids = list(book_entities.keys())
    all_matches = []

    print(f"\nFinding cross-book matches (threshold={args.threshold})...")
    for i in range(len(book_ids)):
        for j in range(i + 1, len(book_ids)):
            bid_a, bid_b = book_ids[i], book_ids[j]
            title_a = next(b["title"] for b in books_meta if b["id"] == bid_a)
            title_b = next(b["title"] for b in books_meta if b["id"] == bid_b)
            print(f"  {title_a} <-> {title_b}...", end=" ", flush=True)

            t0 = time.time()
            matches = find_cross_book_matches(
                book_entities[bid_a], book_embeddings[bid_a], bid_a,
                book_entities[bid_b], book_embeddings[bid_b], bid_b,
                args.threshold,
            )
            elapsed = time.time() - t0
            print(f"{len(matches)} matches ({elapsed:.1f}s)")
            all_matches.extend(matches)

    print(f"\nTotal pairwise matches: {len(all_matches)}")

    # Build clusters
    print("Building concordance clusters...")
    clusters = build_clusters(all_matches, book_entities)

    # Post-processing: merge near-duplicate clusters split by subcategory noise
    print("Merging near-duplicate clusters...")
    clusters, merge_count = merge_near_duplicates(clusters)
    if merge_count:
        print(f"  Merged {merge_count} cluster pairs")

    # Assign deterministic cluster keys for stable references across rebuilds.
    assign_stable_keys(clusters)

    # Stats
    entities_in_clusters = sum(len(c["members"]) for c in clusters)
    three_book_clusters = sum(1 for c in clusters if c["book_count"] >= 3)
    by_category = defaultdict(int)
    for c in clusters:
        by_category[c["category"]] += 1

    print(f"\nConcordance Results:")
    print(f"  Clusters: {len(clusters)}")
    print(f"  Entities matched: {entities_in_clusters}")
    print(f"  Clusters spanning all {len(book_ids)} books: {three_book_clusters}")
    print(f"  By category:")
    for cat in sorted(by_category, key=lambda c: -by_category[c]):
        print(f"    {cat}: {by_category[cat]}")

    # Build output
    output = {
        "metadata": {
            "created": time.strftime("%Y-%m-%d %H:%M"),
            "threshold": args.threshold,
            "person_threshold": PERSON_THRESHOLD,
            "min_count": args.min_count,
        },
        "books": books_meta,
        "stats": {
            "total_clusters": len(clusters),
            "entities_matched": entities_in_clusters,
            "clusters_all_books": three_book_clusters,
            "by_category": dict(by_category),
        },
        "clusters": clusters,
    }

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nSaved to: {output_path} ({size_mb:.1f} MB)")

    # Show top clusters
    print(f"\nTop 20 clusters:")
    for c in clusters[:20]:
        books = ", ".join(sorted(set(m["book_id"].split("_")[0] for m in c["members"])))
        names = " / ".join(m["name"] for m in c["members"][:4])
        suffix = f" +{len(c['members'])-4} more" if len(c["members"]) > 4 else ""
        print(f"  [{c['category']}] {c['canonical_name']} ({c['total_mentions']}x, {c['book_count']} books): {names}{suffix}")


if __name__ == "__main__":
    main()

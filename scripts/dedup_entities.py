#!/usr/bin/env python3
"""
Deduplicate entities within a single book using fine-tuned embeddings.

Finds entities that refer to the same thing (Galen/Galeno/Galenus) and merges
them into a single entity with combined counts, unioned variants, and merged
contexts. Produces a cleaner, smaller entity file.

Usage:
    python dedup_entities.py --input web/public/data/semedo_entities.json
    python dedup_entities.py --input web/public/data/semedo_entities.json --output deduped.json --dry-run
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_PATH = Path(__file__).parent.parent / "models" / "finetuned-bge-m3-v2"

# Similarity thresholds for merging within a book
MERGE_THRESHOLD = 0.88       # High — conservative to avoid false merges
PERSON_MERGE_THRESHOLD = 0.85  # Slightly lower for persons (Galen/Galeno are clearly the same)
STRING_SIM_BOOST = 0.05      # Lower threshold if string similarity is also high


def edit_distance(s1: str, s2: str) -> int:
    """Levenshtein edit distance."""
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def is_plausible_merge(name1: str, name2: str, category: str = "") -> bool:
    """Check if two entity names are plausibly the same thing.
    Blocks merges of clearly different short words (June/July, Body/Bones)
    and persons with shared first names but different surnames."""
    n1, n2 = name1.lower().strip(), name2.lower().strip()

    # If one contains the other, always plausible (Root/Roots, Stone/Stone in the Kidneys)
    if n1 in n2 or n2 in n1:
        return True

    # For PERSON entities with multi-word names, check that surnames are compatible.
    # Blocks: "Duarte Barbosa" + "Duarte Pacheco", "Gaspar Corrêa" + "Gaspar da Cruz"
    if category == "PERSON":
        words1 = n1.split()
        words2 = n2.split()
        if len(words1) >= 2 and len(words2) >= 2:
            # Both have first + last name — check if last words are similar
            last1, last2 = words1[-1], words2[-1]
            # Skip common particles (da, de, do, di, van, von, etc.)
            particles = {"da", "de", "do", "di", "das", "dos", "del", "van", "von"}
            if last1 in particles and len(words1) >= 3:
                last1 = words1[-2]
            if last2 in particles and len(words2) >= 3:
                last2 = words2[-2]
            # If first words match but last words are very different, block
            if words1[0] == words2[0] and edit_distance(last1, last2) > max(2, len(min(last1, last2, key=len)) // 2):
                return False

    # For short names (< 8 chars), require low edit distance relative to length
    shorter = min(len(n1), len(n2))
    if shorter < 8:
        ed = edit_distance(n1, n2)
        max_ed = max(1, shorter // 3)  # allow ~1 edit per 3 chars
        if ed > max_ed:
            return False

    return True


def string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity based on shared characters and prefix."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0

    min_len = min(len(s1), len(s2))
    if min_len == 0:
        return 0.0

    # Common prefix
    common_prefix = 0
    for i in range(min_len):
        if s1[i] == s2[i]:
            common_prefix += 1
        else:
            break

    # Shared character ratio
    set1, set2 = set(s1), set(s2)
    shared = len(set1 & set2)
    total = len(set1 | set2)
    char_ratio = shared / total if total > 0 else 0

    # Length similarity
    len_ratio = min_len / max(len(s1), len(s2))

    prefix_score = common_prefix / min_len
    return 0.5 * prefix_score + 0.3 * char_ratio + 0.2 * len_ratio


def embed_entities(entities: list[dict], model: SentenceTransformer) -> np.ndarray:
    """Embed entity names with category context."""
    texts = [
        f"{e['name']} ({e.get('subcategory', e['category']).lower()})"
        for e in entities
    ]
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=True, batch_size=256)


def find_merge_groups(
    entities: list[dict],
    embeddings: np.ndarray,
) -> list[list[int]]:
    """Find groups of entities that should be merged using graph-based clustering."""
    n = len(entities)

    # Build adjacency list: connect entities above merge threshold within same category
    neighbors = defaultdict(set)

    # Compute similarity matrix in chunks to manage memory
    chunk_size = 1000
    for i_start in range(0, n, chunk_size):
        i_end = min(i_start + chunk_size, n)
        chunk_emb = embeddings[i_start:i_end]
        # Compare this chunk against all entities
        sims = chunk_emb @ embeddings.T  # (chunk_size, n)

        for local_i in range(i_end - i_start):
            global_i = i_start + local_i
            cat_i = entities[global_i]["category"]

            for j in range(global_i + 1, n):
                cat_j = entities[j]["category"]
                if cat_i != cat_j:
                    continue

                sim = float(sims[local_i, j])
                base_threshold = PERSON_MERGE_THRESHOLD if cat_i == "PERSON" else MERGE_THRESHOLD
                threshold = base_threshold

                # Boost: lower threshold if names are also string-similar
                str_sim = string_similarity(entities[global_i]["name"], entities[j]["name"])
                if str_sim > 0.5:
                    threshold -= STRING_SIM_BOOST

                if sim >= threshold:
                    # Safety check: require minimum string similarity to prevent
                    # merging semantically similar but distinct entities
                    # (e.g., "June" and "July", "Body" and "Bones")
                    if str_sim < 0.3:
                        continue

                    # Edit-distance guard for short words + person surname check
                    if not is_plausible_merge(entities[global_i]["name"], entities[j]["name"], cat_i):
                        continue

                    neighbors[global_i].add(global_i)
                    neighbors[global_i].add(j)
                    neighbors[j].add(j)
                    neighbors[j].add(global_i)

        if i_end % 2000 == 0 or i_end == n:
            print(f"  Compared {i_end}/{n} entities...")

    # Find connected components via BFS
    visited = set()
    raw_groups = []

    for node in neighbors:
        if node in visited:
            continue
        # BFS
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

    # Post-process: validate groups to prevent chaining artifacts.
    # Every member must be plausibly related to the primary (highest-count) entity.
    groups = []
    pruned_count = 0
    for group in raw_groups:
        primary_idx = max(group, key=lambda i: entities[i]["count"])
        primary_name = entities[primary_idx]["name"]

        validated = [primary_idx]
        for idx in group:
            if idx == primary_idx:
                continue
            member_name = entities[idx]["name"]
            # Must pass string similarity OR substring check against primary
            ss = string_similarity(primary_name, member_name)
            is_substr = primary_name.lower() in member_name.lower() or member_name.lower() in primary_name.lower()
            if ss >= 0.3 or is_substr:
                validated.append(idx)
            else:
                pruned_count += 1

        if len(validated) > 1:
            groups.append(sorted(validated))

    if pruned_count > 0:
        print(f"  Pruned {pruned_count} false chain links from groups")

    return groups


def merge_entities(entities: list[dict], group: list[int]) -> dict:
    """Merge a group of entity indices into a single entity."""
    members = [entities[i] for i in group]

    # Primary entity: the one with the highest count
    primary = max(members, key=lambda e: e["count"])

    # Combine counts
    total_count = sum(e["count"] for e in members)

    # Union all variants + all names
    all_variants = set()
    for e in members:
        all_variants.add(e["name"])
        for v in e.get("variants", []):
            all_variants.add(v)
    # Put primary name first
    variant_list = [primary["name"]] + sorted(all_variants - {primary["name"]})

    # Merge contexts (deduplicate, keep up to 5)
    seen_contexts = set()
    merged_contexts = []
    for e in members:
        for ctx in e.get("contexts", []):
            ctx_lower = ctx.lower().strip()
            if ctx_lower not in seen_contexts:
                seen_contexts.add(ctx_lower)
                merged_contexts.append(ctx)
    merged_contexts = merged_contexts[:5]

    # Merge mentions (combine all, sort by offset, cap at 100)
    all_mentions = []
    for e in members:
        all_mentions.extend(e.get("mentions", []))
    all_mentions.sort(key=lambda m: m.get("offset", 0))
    all_mentions = all_mentions[:100]

    # Build merged entity
    merged = {
        "id": primary["id"],
        "name": primary["name"],
        "category": primary["category"],
        "subcategory": primary.get("subcategory", ""),
        "count": total_count,
        "contexts": merged_contexts,
        "variants": variant_list,
    }
    if all_mentions:
        merged["mentions"] = all_mentions

    return merged


def main():
    parser = argparse.ArgumentParser(description="Deduplicate entities within a book")
    parser.add_argument("--input", required=True, help="Entity JSON file")
    parser.add_argument("--output", help="Output file (default: overwrites input)")
    parser.add_argument("--dry-run", action="store_true", help="Show merges without writing")
    parser.add_argument("--threshold", type=float, default=MERGE_THRESHOLD,
                        help=f"Merge threshold (default: {MERGE_THRESHOLD})")
    args = parser.parse_args()

    # Load
    input_path = Path(args.input)
    with open(input_path) as f:
        data = json.load(f)

    entities = data["entities"]
    book_title = data["book"].get("title", input_path.stem)
    print(f"Loaded {len(entities)} entities from {book_title}")

    # Embed
    print(f"Loading model from {MODEL_PATH}...")
    model = SentenceTransformer(str(MODEL_PATH))
    print("Embedding entities...")
    embeddings = embed_entities(entities, model)

    # Find merge groups
    print("Finding duplicate groups...")
    groups = find_merge_groups(entities, embeddings)

    # Report
    total_merged = sum(len(g) for g in groups)
    print(f"\nFound {len(groups)} merge groups covering {total_merged} entities")

    if args.dry_run or len(groups) == 0:
        # Show what would be merged
        for i, group in enumerate(groups[:30]):
            members = [entities[idx] for idx in group]
            names = [f"{e['name']} ({e['count']}x)" for e in members]
            cat = members[0]["category"]
            print(f"  Group {i+1} [{cat}]: {' + '.join(names)}")
        if len(groups) > 30:
            print(f"  ... and {len(groups) - 30} more groups")
        if args.dry_run:
            print("\nDry run — no changes written.")
            return

    # Build merged entity list
    merged_indices = set()
    merged_entities = []

    for group in groups:
        merged = merge_entities(entities, group)
        merged_entities.append(merged)
        merged_indices.update(group)

    # Keep unmerged entities as-is
    for i, entity in enumerate(entities):
        if i not in merged_indices:
            merged_entities.append(entity)

    # Sort by count descending
    merged_entities.sort(key=lambda e: -e["count"])

    # Reassign IDs to avoid conflicts
    seen_ids = set()
    for e in merged_entities:
        base_id = e["id"]
        if base_id in seen_ids:
            # Generate unique ID
            counter = 2
            while f"{base_id}_{counter}" in seen_ids:
                counter += 1
            e["id"] = f"{base_id}_{counter}"
        seen_ids.add(e["id"])

    # Update stats
    category_counts = defaultdict(int)
    for e in merged_entities:
        category_counts[e["category"]] += 1

    data["entities"] = merged_entities
    data["stats"]["total_entities"] = len(merged_entities)
    data["stats"]["by_category"] = dict(category_counts)
    data["stats"]["dedup_merges"] = len(groups)
    data["stats"]["dedup_entities_merged"] = total_merged

    print(f"\nResults:")
    print(f"  Before: {len(entities)} entities")
    print(f"  After:  {len(merged_entities)} entities")
    print(f"  Merged: {total_merged} entities into {len(groups)} groups")
    print(f"  Reduction: {len(entities) - len(merged_entities)} fewer entities ({(1 - len(merged_entities)/len(entities))*100:.1f}%)")

    # Save
    output_path = Path(args.output) if args.output else input_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Saved to: {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

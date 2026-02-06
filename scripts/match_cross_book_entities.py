#!/usr/bin/env python3
"""
Match entities across books using the fine-tuned embedding model.
Creates a unified concordance with link types.

Usage:
    python match_cross_book_entities.py \
        --book1 web/public/data/semedo_entities.json \
        --book2 web/public/data/culpeper_entities.json \
        --output web/public/data/concordance.json
"""

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

# Model path
MODEL_PATH = Path(__file__).parent.parent / "models" / "finetuned-bge-m3-v2"

# Link type classification thresholds
THRESHOLDS = {
    "auto_accept": 0.85,     # High confidence match
    "candidate": 0.65,       # Consider as candidate
    "same_language_ortho": 0.90,  # Same language = likely orthographic variant
    "diff_language_same": 0.80,   # Different language = likely same referent
    "other_concept": 0.92,   # Higher threshold for OTHER_CONCEPT matches
    "preparation": 0.90,     # Higher threshold for PREPARATION (too broad otherwise)
    "person_string_sim": 0.35,  # Minimum string similarity for PERSON matches
}


def string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity based on shared characters and length."""
    s1, s2 = s1.lower(), s2.lower()

    # Exact match
    if s1 == s2:
        return 1.0

    # Check for common prefix (handles Medicina/Medicine, Dioscorides/Diofcorides)
    min_len = min(len(s1), len(s2))
    common_prefix = 0
    for i in range(min_len):
        if s1[i] == s2[i]:
            common_prefix += 1
        else:
            break

    # Check for shared character ratio
    set1, set2 = set(s1), set(s2)
    shared = len(set1 & set2)
    total = len(set1 | set2)
    char_ratio = shared / total if total > 0 else 0

    # Length similarity
    len_ratio = min_len / max(len(s1), len(s2))

    # Combined score: weight prefix heavily, then char overlap, then length
    prefix_score = common_prefix / min_len if min_len > 0 else 0
    return 0.5 * prefix_score + 0.3 * char_ratio + 0.2 * len_ratio

# Link types
LINK_TYPES = [
    "orthographic_variant",   # Spelling variants (Galen/Galeno)
    "same_referent",          # Same thing, different languages (sangue/blood)
    "conceptual_overlap",     # Related concepts (fever/ague)
    "derivation",             # One derived from other (opium/laudanum)
    "contested_identity",     # Disputed whether same (cassia/cinnamon)
]


def load_book_entities(filepath: Path) -> dict:
    """Load entities from a book JSON file."""
    with open(filepath) as f:
        return json.load(f)


def embed_entities(entities: list[dict], model: SentenceTransformer) -> np.ndarray:
    """Embed entity names using the fine-tuned model."""
    names = [e["name"] for e in entities]
    # Add context for better embeddings
    texts = [f"{e['name']} ({e.get('subcategory', e['category']).lower()})" for e in entities]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return embeddings


def classify_link_type(
    entity1: dict, entity2: dict,
    similarity: float,
    lang1: str, lang2: str
) -> str:
    """Classify the type of link between two entities."""
    same_lang = lang1.lower() == lang2.lower()
    cat1 = entity1.get("category", "")
    cat2 = entity2.get("category", "")
    subcat1 = entity1.get("subcategory", "")
    subcat2 = entity2.get("subcategory", "")

    # Same language, high similarity = orthographic variant
    if same_lang and similarity > THRESHOLDS["same_language_ortho"]:
        return "orthographic_variant"

    # Different language, high similarity = same referent (translation)
    if not same_lang and similarity > THRESHOLDS["diff_language_same"]:
        return "same_referent"

    # Same category, medium-high similarity = same referent or overlap
    if cat1 == cat2:
        if similarity > 0.75:
            return "same_referent"
        elif similarity > 0.65:
            return "conceptual_overlap"

    # Substance → Preparation relationship
    if (subcat1 == "PREPARATION" and subcat2 in ["PLANT", "ANIMAL", "MINERAL"]) or \
       (subcat2 == "PREPARATION" and subcat1 in ["PLANT", "ANIMAL", "MINERAL"]):
        if similarity > 0.6:
            return "derivation"

    # Default to conceptual overlap for moderate similarity
    if similarity > THRESHOLDS["candidate"]:
        return "conceptual_overlap"

    return "conceptual_overlap"


def find_matches(
    entities1: list[dict], embeddings1: np.ndarray, lang1: str,
    entities2: list[dict], embeddings2: np.ndarray, lang2: str,
    top_k: int = 5
) -> list[dict]:
    """Find cross-book entity matches."""
    matches = []

    # Compute similarity matrix
    similarity_matrix = embeddings1 @ embeddings2.T

    for i, ent1 in enumerate(entities1):
        cat1 = ent1.get("category", "")

        # Get top-k matches for this entity
        sims = similarity_matrix[i]
        top_indices = np.argsort(sims)[::-1][:top_k * 2]  # Get more, filter by category

        subcat1 = ent1.get("subcategory", "")

        for j in top_indices:
            ent2 = entities2[j]
            cat2 = ent2.get("category", "")
            subcat2 = ent2.get("subcategory", "")
            sim = float(sims[j])

            # Only match within same category
            if cat1 != cat2:
                continue

            # Require subcategory match when both have valid subcategories
            # This prevents CONCEPT/PRACTICE matching CONCEPT/QUALITY etc.
            if subcat1 and subcat2 and not subcat1.startswith("OTHER_") and not subcat2.startswith("OTHER_"):
                if subcat1 != subcat2:
                    continue

            # Apply threshold
            if sim < THRESHOLDS["candidate"]:
                continue

            # For PERSON category, require string similarity (names should share features)
            # This prevents matching completely different scholars together
            if cat1 == "PERSON":
                str_sim = string_similarity(ent1["name"], ent2["name"])
                if str_sim < THRESHOLDS["person_string_sim"]:
                    continue

            # For PREPARATION subcategory, require higher threshold (too heterogeneous)
            if subcat1 == "PREPARATION" and subcat2 == "PREPARATION":
                if sim < THRESHOLDS["preparation"]:
                    continue

            # For OTHER_CONCEPT specifically, require higher similarity threshold
            if subcat1 == "OTHER_CONCEPT" and subcat2 == "OTHER_CONCEPT":
                if sim < THRESHOLDS["other_concept"]:
                    continue
                # Also require some string similarity for OTHER_* matches
                str_sim = string_similarity(ent1["name"], ent2["name"])
                if str_sim < 0.3:  # Names must share some linguistic features
                    continue

            # For any OTHER_* subcategory match, apply string similarity filter
            elif subcat1.startswith("OTHER_") and subcat2.startswith("OTHER_"):
                str_sim = string_similarity(ent1["name"], ent2["name"])
                if str_sim < 0.25:
                    continue

            # Classify link type
            link_type = classify_link_type(ent1, ent2, sim, lang1, lang2)

            matches.append({
                "source": ent1["name"],
                "source_id": ent1["id"],
                "source_book": lang1,
                "target": ent2["name"],
                "target_id": ent2["id"],
                "target_book": lang2,
                "category": cat1,
                "subcategory": ent1.get("subcategory", ""),
                "similarity": round(sim, 4),
                "link_type": link_type,
                "auto_accepted": sim >= THRESHOLDS["auto_accept"]
            })

    # Sort by similarity
    matches.sort(key=lambda x: x["similarity"], reverse=True)

    # Deduplicate (keep highest similarity for each pair)
    seen_pairs = set()
    unique_matches = []
    for m in matches:
        key = (m["source_id"], m["target_id"])
        if key not in seen_pairs:
            seen_pairs.add(key)
            unique_matches.append(m)

    # One-to-one matching: each source and target can only appear once
    # This prevents "attractor" entities from matching everything
    matched_sources = set()
    matched_targets = set()
    one_to_one_matches = []
    for m in unique_matches:
        if m["source_id"] not in matched_sources and m["target_id"] not in matched_targets:
            one_to_one_matches.append(m)
            matched_sources.add(m["source_id"])
            matched_targets.add(m["target_id"])

    return one_to_one_matches


def build_canonical_entities(
    book1_data: dict, book2_data: dict, matches: list[dict]
) -> list[dict]:
    """Build unified canonical entity list from matched entities."""
    # Group matches by source entity
    from collections import defaultdict

    entity_groups = defaultdict(lambda: {
        "canonical_name": "",
        "variants": [],
        "category": "",
        "subcategory": "",
        "books": {},
        "total_count": 0
    })

    # Add all book1 entities
    for ent in book1_data["entities"]:
        key = ent["id"]
        entity_groups[key]["canonical_name"] = ent["name"]
        entity_groups[key]["category"] = ent["category"]
        entity_groups[key]["subcategory"] = ent.get("subcategory", "")
        entity_groups[key]["variants"].extend(ent.get("variants", [ent["name"]]))
        entity_groups[key]["books"][book1_data["book"]["id"]] = ent["count"]
        entity_groups[key]["total_count"] += ent["count"]

    # Merge matched book2 entities
    merged = set()
    for match in matches:
        if match["auto_accepted"] or match["similarity"] > 0.80:
            source_key = match["source_id"]
            target_key = match["target_id"]

            # Find target entity
            target_ent = None
            for ent in book2_data["entities"]:
                if ent["id"] == target_key:
                    target_ent = ent
                    break

            if target_ent and target_key not in merged:
                entity_groups[source_key]["variants"].append(target_ent["name"])
                entity_groups[source_key]["variants"].extend(
                    v for v in target_ent.get("variants", [])
                    if v != target_ent["name"]
                )
                entity_groups[source_key]["books"][book2_data["book"]["id"]] = target_ent["count"]
                entity_groups[source_key]["total_count"] += target_ent["count"]
                merged.add(target_key)

    # Add unmatched book2 entities
    for ent in book2_data["entities"]:
        if ent["id"] not in merged:
            key = f"book2_{ent['id']}"
            entity_groups[key]["canonical_name"] = ent["name"]
            entity_groups[key]["category"] = ent["category"]
            entity_groups[key]["subcategory"] = ent.get("subcategory", "")
            entity_groups[key]["variants"].extend(ent.get("variants", [ent["name"]]))
            entity_groups[key]["books"][book2_data["book"]["id"]] = ent["count"]
            entity_groups[key]["total_count"] += ent["count"]

    # Convert to list
    result = []
    for key, data in entity_groups.items():
        result.append({
            "id": key,
            "canonical_name": data["canonical_name"],
            "category": data["category"],
            "subcategory": data["subcategory"],
            "variants": list(set(data["variants"])),
            "books": data["books"],
            "book_count": len(data["books"]),
            "total_count": data["total_count"]
        })

    # Sort by book count then total count
    result.sort(key=lambda x: (x["book_count"], x["total_count"]), reverse=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="Match entities across books")
    parser.add_argument("--book1", required=True, help="First book entities JSON")
    parser.add_argument("--book2", required=True, help="Second book entities JSON")
    parser.add_argument("--output", required=True, help="Output concordance JSON")
    parser.add_argument("--top-k", type=int, default=5, help="Top-k matches per entity")
    args = parser.parse_args()

    # Load books
    print("Loading books...")
    book1 = load_book_entities(Path(args.book1))
    book2 = load_book_entities(Path(args.book2))

    print(f"  Book 1: {book1['book']['title']} - {len(book1['entities'])} entities")
    print(f"  Book 2: {book2['book']['title']} - {len(book2['entities'])} entities")

    # Load embedding model
    print(f"\nLoading embedding model from {MODEL_PATH}...")
    model = SentenceTransformer(str(MODEL_PATH))

    # Embed entities
    print("\nEmbedding Book 1 entities...")
    emb1 = embed_entities(book1["entities"], model)

    print("Embedding Book 2 entities...")
    emb2 = embed_entities(book2["entities"], model)

    # Find matches
    print("\nFinding cross-book matches...")
    matches = find_matches(
        book1["entities"], emb1, book1["book"]["language"],
        book2["entities"], emb2, book2["book"]["language"],
        top_k=args.top_k
    )

    # Also find reverse matches
    reverse_matches = find_matches(
        book2["entities"], emb2, book2["book"]["language"],
        book1["entities"], emb1, book1["book"]["language"],
        top_k=args.top_k
    )

    # Combine and deduplicate
    all_matches = matches + reverse_matches
    seen = set()
    unique_matches = []
    for m in sorted(all_matches, key=lambda x: x["similarity"], reverse=True):
        key = tuple(sorted([m["source_id"], m["target_id"]]))
        if key not in seen:
            seen.add(key)
            unique_matches.append(m)

    print(f"  Found {len(unique_matches)} unique cross-book matches")

    # Count by link type
    by_link_type = {}
    auto_accepted = 0
    for m in unique_matches:
        lt = m["link_type"]
        by_link_type[lt] = by_link_type.get(lt, 0) + 1
        if m["auto_accepted"]:
            auto_accepted += 1

    print(f"  Auto-accepted (sim > {THRESHOLDS['auto_accept']}): {auto_accepted}")
    print(f"  By link type:")
    for lt, count in sorted(by_link_type.items(), key=lambda x: -x[1]):
        print(f"    {lt}: {count}")

    # Build canonical entities
    print("\nBuilding unified concordance...")
    canonical = build_canonical_entities(book1, book2, unique_matches)

    # Stats
    shared = sum(1 for c in canonical if c["book_count"] > 1)
    print(f"  Total canonical entities: {len(canonical)}")
    print(f"  Shared across books: {shared}")

    # Build output
    output = {
        "books": [book1["book"], book2["book"]],
        "matches": unique_matches[:500],  # Top 500 matches
        "canonical_entities": canonical,
        "stats": {
            "total_matches": len(unique_matches),
            "auto_accepted": auto_accepted,
            "by_link_type": by_link_type,
            "canonical_entities": len(canonical),
            "shared_entities": shared,
            "thresholds": THRESHOLDS
        }
    }

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")

    # Show top matches
    print(f"\nTop 20 cross-book matches:")
    for m in unique_matches[:20]:
        flag = "✓" if m["auto_accepted"] else " "
        print(f"  {flag} {m['similarity']:.3f}  {m['source']:<25} ↔ {m['target']:<25} [{m['link_type']}]")


if __name__ == "__main__":
    main()

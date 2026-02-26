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
from collections import Counter, defaultdict

import networkx as nx
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_PATH = Path(__file__).parent.parent / "models" / "finetuned-bge-m3-v3"
DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
OUTPUT_PATH = DATA_DIR / "concordance.json"

# Cross-book matching thresholds (slightly lower than within-book dedup
# because cross-lingual matches are the whole point)
MATCH_THRESHOLD = 0.88
PERSON_THRESHOLD = 0.84   # Person names can be lower than global threshold with lexical gate
CONCEPT_THRESHOLD = 0.88  # Higher for concepts to prevent mega-cluster chaining
MIN_ENTITY_COUNT = 1      # Minimum occurrence count to include
VALIDATION_EDGE_THRESHOLD = 0.84
CONCEPT_VALIDATION_THRESHOLD = 0.88
CONCEPT_FAMILY_MIN_SIM = 0.82
MAX_CLUSTER_SIZE = 150    # Safety cap — clusters above this get split
GRAPH_TOP_K = 4           # Mutual top-k pruning to reduce hub chaining
COMMUNITY_METHOD = "louvain"
LOUVAIN_RESOLUTION = 1.5
LOUVAIN_SEED = 42
DUPLICATE_MERGE_MODE = "strict"

# Category-specific minimum thresholds to suppress broad semantic attractors.
CATEGORY_MIN_THRESHOLD = {
    "SUBSTANCE": 0.88,
    "PLANT": 0.88,
    "ANIMAL": 0.89,
    "PLACE": 0.88,
    "OBJECT": 0.88,
    "DISEASE": 0.87,
}

PERSON_LEXICAL_MIN_SIM = 0.35
PERSON_TOKEN_SIM_MIN = 0.84

CONCEPT_FAMILY_SUFFIXES = {
    "s", "es", "ed", "ing", "al", "ally", "ual", "ually",
    "ation", "ations", "ative", "ively", "ly", "ment", "ments",
}

VALID_TOP_CATEGORIES = {"PERSON", "PLANT", "ANIMAL", "SUBSTANCE", "PLACE", "DISEASE", "CONCEPT", "OBJECT"}

DEFAULT_SUBCATEGORY = {
    "PERSON": "OTHER_PERSON",
    "PLANT": "OTHER_PLANT",
    "ANIMAL": "OTHER_ANIMAL",
    "SUBSTANCE": "OTHER_SUBSTANCE",
    "PLACE": "OTHER_PLACE",
    "DISEASE": "OTHER_DISEASE",
    "CONCEPT": "OTHER_CONCEPT",
    "OBJECT": "OTHER_OBJECT",
}

SUBCATEGORY_TO_CATEGORY = {
    "AUTHORITY": "PERSON",
    "SCHOLAR": "PERSON",
    "PRACTITIONER": "PERSON",
    "PATRON": "PERSON",
    "PATIENT": "PERSON",
    "OTHER_PERSON": "PERSON",
    "HERB": "PLANT",
    "TREE": "PLANT",
    "ROOT": "PLANT",
    "SEED": "PLANT",
    "RESIN": "PLANT",
    "OTHER_PLANT": "PLANT",
    "MAMMAL": "ANIMAL",
    "BIRD": "ANIMAL",
    "FISH": "ANIMAL",
    "INSECT": "ANIMAL",
    "REPTILE": "ANIMAL",
    "PRODUCT": "ANIMAL",
    "OTHER_ANIMAL": "ANIMAL",
    "MINERAL": "SUBSTANCE",
    "PREPARATION": "SUBSTANCE",
    "ANATOMY": "SUBSTANCE",
    "OTHER_SUBSTANCE": "SUBSTANCE",
    "COUNTRY": "PLACE",
    "CITY": "PLACE",
    "REGION": "PLACE",
    "OTHER_PLACE": "PLACE",
    "ACUTE": "DISEASE",
    "CHRONIC": "DISEASE",
    "SYMPTOM": "DISEASE",
    "OTHER_DISEASE": "DISEASE",
    "THEORY": "CONCEPT",
    "PRACTICE": "CONCEPT",
    "QUALITY": "CONCEPT",
    "OTHER_CONCEPT": "CONCEPT",
    "INSTRUMENT": "OBJECT",
    "VESSEL": "OBJECT",
    "TOOL": "OBJECT",
    "OTHER_OBJECT": "OBJECT",
}

CATEGORY_TO_TOPLEVEL = {
    "ANATOMY": ("SUBSTANCE", "ANATOMY"),
    "MINERAL": ("SUBSTANCE", "MINERAL"),
    "PREPARATION": ("SUBSTANCE", "PREPARATION"),
    "OTHER_SUBSTANCE": ("SUBSTANCE", "OTHER_SUBSTANCE"),
    "SYMPTOM": ("DISEASE", "SYMPTOM"),
    "ACUTE": ("DISEASE", "ACUTE"),
    "CHRONIC": ("DISEASE", "CHRONIC"),
    "OTHER_DISEASE": ("DISEASE", "OTHER_DISEASE"),
    "THEORY": ("CONCEPT", "THEORY"),
    "PRACTICE": ("CONCEPT", "PRACTICE"),
    "QUALITY": ("CONCEPT", "QUALITY"),
    "COGNITIVE_PROCESS": ("CONCEPT", "OTHER_CONCEPT"),
    "MENTAL_FACULTY": ("CONCEPT", "OTHER_CONCEPT"),
    "SCHOOL_OF_THOUGHT": ("CONCEPT", "OTHER_CONCEPT"),
    "PHENOMENON": ("CONCEPT", "OTHER_CONCEPT"),
    "ANOMALY": ("CONCEPT", "OTHER_CONCEPT"),
    "OTHER_CONCEPT": ("CONCEPT", "OTHER_CONCEPT"),
    "COUNTRY": ("PLACE", "COUNTRY"),
    "CITY": ("PLACE", "CITY"),
    "REGION": ("PLACE", "REGION"),
    "OTHER_PLACE": ("PLACE", "OTHER_PLACE"),
    "INSTRUMENT": ("OBJECT", "INSTRUMENT"),
    "VESSEL": ("OBJECT", "VESSEL"),
    "TOOL": ("OBJECT", "TOOL"),
    "OTHER_OBJECT": ("OBJECT", "OTHER_OBJECT"),
    "AUTHORITY": ("PERSON", "AUTHORITY"),
    "SCHOLAR": ("PERSON", "SCHOLAR"),
    "PRACTITIONER": ("PERSON", "PRACTITIONER"),
    "PATRON": ("PERSON", "PATRON"),
    "PATIENT": ("PERSON", "PATIENT"),
    "OTHER_PERSON": ("PERSON", "OTHER_PERSON"),
    "HERB": ("PLANT", "HERB"),
    "TREE": ("PLANT", "TREE"),
    "ROOT": ("PLANT", "ROOT"),
    "SEED": ("PLANT", "SEED"),
    "RESIN": ("PLANT", "RESIN"),
    "OTHER_PLANT": ("PLANT", "OTHER_PLANT"),
    "MAMMAL": ("ANIMAL", "MAMMAL"),
    "BIRD": ("ANIMAL", "BIRD"),
    "FISH": ("ANIMAL", "FISH"),
    "INSECT": ("ANIMAL", "INSECT"),
    "REPTILE": ("ANIMAL", "REPTILE"),
    "PRODUCT": ("ANIMAL", "PRODUCT"),
    "OTHER_ANIMAL": ("ANIMAL", "OTHER_ANIMAL"),
    "ORGANIZATION": ("CONCEPT", "OTHER_CONCEPT"),
    "OTHER_ORGANIZATION": ("CONCEPT", "OTHER_CONCEPT"),
    "OTHER": ("CONCEPT", "OTHER_CONCEPT"),
}

SUBCATEGORY_NORMALIZATION = {
    "OTHER_ANATOMY": "ANATOMY",
    "ORGAN": "ANATOMY",
    "BODY_PART": "ANATOMY",
    "MEDICINE": "PREPARATION",
    "DRUG": "PREPARATION",
    "AUTHOR": "SCHOLAR",
    "WRITER": "SCHOLAR",
    "PHYSICIAN": "PRACTITIONER",
    "APOTHECARY": "PRACTITIONER",
    "TOWN": "CITY",
    "EMPIRE": "COUNTRY",
}


def normalize_for_key(text: str) -> str:
    """Normalize a name for stable-key signature generation."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def normalize_match_text(text: str) -> str:
    """Normalize text for lexical matching (case/diacritics/punctuation-insensitive)."""
    return normalize_for_key(text).replace("-", "")


def is_exact_lexical_match(a: str, b: str) -> bool:
    """True when two terms are effectively identical across orthographic noise."""
    na = normalize_match_text(a)
    nb = normalize_match_text(b)
    return len(na) >= 4 and na == nb


def is_concept_family_variant(a: str, b: str) -> bool:
    """Conservative lexical family check for concept variants (habit/habits/habitual)."""
    na = normalize_match_text(a)
    nb = normalize_match_text(b)
    if not na or not nb or na == nb:
        return False
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) < 4 or not longer.startswith(shorter):
        return False
    suffix = longer[len(shorter):]
    return suffix in CONCEPT_FAMILY_SUFFIXES


def slugify_canonical_name(name: str) -> str:
    """Generate a human-readable URL slug from a canonical name."""
    text = unicodedata.normalize("NFD", (name or "").lower().strip())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "unnamed"


def assign_stable_keys(clusters: list[dict], previous_concordance: Path | None = None) -> None:
    """Assign human-readable stable keys, preserving keys from previous concordance.

    Key preservation uses member overlap matching: if >=50% of a new cluster's
    members match an old cluster, the new cluster inherits the old key.
    """
    inherited = {}  # new cluster index -> inherited key

    # Phase 1: Inherit keys from previous concordance via member overlap
    if previous_concordance and previous_concordance.exists():
        try:
            old_data = json.loads(previous_concordance.read_text(encoding="utf-8"))
            old_clusters = old_data.get("clusters", [])

            # Build old member signatures
            old_sigs = []
            for oc in old_clusters:
                sig = frozenset(
                    (m.get("entity_id", ""), m.get("book_id", ""))
                    for m in oc.get("members", [])
                )
                old_sigs.append((sig, oc.get("stable_key", "")))

            used_old = set()
            for ni, nc in enumerate(clusters):
                new_sig = frozenset(
                    (m.get("entity_id", ""), m.get("book_id", ""))
                    for m in nc.get("members", [])
                )
                if not new_sig:
                    continue

                best_overlap = 0
                best_oi = None
                for oi, (old_sig, _old_key) in enumerate(old_sigs):
                    if oi in used_old or not old_sig:
                        continue
                    overlap = len(new_sig & old_sig)
                    min_size = min(len(new_sig), len(old_sig))
                    if overlap > best_overlap and overlap >= max(1, min_size * 0.5):
                        best_overlap = overlap
                        best_oi = oi

                if best_oi is not None:
                    old_key = old_sigs[best_oi][1]
                    # Only inherit human-readable keys (not old hash-based clu_* keys)
                    if old_key and not old_key.startswith("clu_"):
                        inherited[ni] = old_key
                    used_old.add(best_oi)

            print(f"  Inherited {len(inherited)} stable keys from previous concordance")
        except Exception as e:
            print(f"  Warning: could not load previous concordance: {e}")

    # Phase 2: Assign human-readable slugs
    used_keys = set(inherited.values())

    for ni, cluster in enumerate(clusters):
        if ni in inherited:
            cluster["stable_key"] = inherited[ni]
            continue

        base = slugify_canonical_name(cluster.get("canonical_name", ""))

        if base not in used_keys:
            cluster["stable_key"] = base
            used_keys.add(base)
        else:
            # Disambiguate with category
            cat = cluster.get("category", "").lower()
            cat_slug = f"{base}-{cat}" if cat else base
            if cat_slug not in used_keys:
                cluster["stable_key"] = cat_slug
                used_keys.add(cat_slug)
            else:
                n = 2
                while f"{cat_slug}-{n}" in used_keys:
                    n += 1
                cluster["stable_key"] = f"{cat_slug}-{n}"
                used_keys.add(cluster["stable_key"])


def normalize_entity_schema(entity: dict) -> bool:
    """Normalize category/subcategory to the 8-category schema in-place."""
    before_cat = (entity.get("category") or "").strip()
    before_sub = (entity.get("subcategory") or "").strip()

    cat = before_cat.upper().replace(" ", "_")
    sub = before_sub.upper().replace(" ", "_")

    if sub in SUBCATEGORY_NORMALIZATION:
        sub = SUBCATEGORY_NORMALIZATION[sub]

    if cat in CATEGORY_TO_TOPLEVEL:
        top_cat, default_sub = CATEGORY_TO_TOPLEVEL[cat]
        cat = top_cat
        if not sub:
            sub = default_sub

    if sub in SUBCATEGORY_TO_CATEGORY:
        cat = SUBCATEGORY_TO_CATEGORY[sub]

    if cat not in VALID_TOP_CATEGORIES:
        cat = SUBCATEGORY_TO_CATEGORY.get(sub, "CONCEPT")

    if sub not in SUBCATEGORY_TO_CATEGORY or SUBCATEGORY_TO_CATEGORY[sub] != cat:
        sub = DEFAULT_SUBCATEGORY[cat]

    entity["category"] = cat
    entity["subcategory"] = sub
    return entity["category"] != before_cat or entity["subcategory"] != before_sub


def normalize_book_schema(data: dict) -> dict:
    """Normalize all entities in a book payload and return normalization stats."""
    stats = Counter()
    entities = data.get("entities", [])
    for entity in entities:
        before_cat = entity.get("category")
        changed = normalize_entity_schema(entity)
        if changed:
            stats["changed"] += 1
        if before_cat != entity.get("category"):
            stats[f"cat_to_{entity['category']}"] += 1
    return {
        "entity_count": len(entities),
        "changed": stats["changed"],
        "top_changes": stats.most_common(10),
    }


def load_book_entities(filepath: Path) -> dict:
    """Load a book's entity file and return book metadata + entities."""
    with open(filepath) as f:
        data = json.load(f)
    data["_schema_normalization"] = normalize_book_schema(data)
    return data


def embed_entities(entities: list[dict], model: SentenceTransformer) -> np.ndarray:
    """Embed entity names with category context.

    CONCEPT entities are embedded without subcategory suffix to prevent
    the shared '(other_concept)' token from inflating pairwise similarities
    and creating mega-clusters via transitive chaining.
    """
    texts = []
    for e in entities:
        if e["category"] == "CONCEPT":
            # Bare name — avoids artificial similarity from shared suffix
            texts.append(e["name"])
        else:
            texts.append(f"{e['name']} ({e.get('subcategory', e['category']).lower()})")
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


def normalized_name_tokens(name: str) -> list[str]:
    """Tokenize a name using the same normalization as matching."""
    return [tok for tok in normalize_for_key(name).split("-") if tok]


def person_name_compatible(name_a: str, name_b: str, str_sim: float) -> bool:
    """Guardrail against PERSON attractor matches (Paracelsus<->Borda style)."""
    if is_exact_lexical_match(name_a, name_b):
        return True
    if str_sim >= PERSON_LEXICAL_MIN_SIM:
        return True

    toks_a = normalized_name_tokens(name_a)
    toks_b = normalized_name_tokens(name_b)
    if not toks_a or not toks_b:
        return False

    shared = set(toks_a) & set(toks_b)
    if any(len(tok) >= 4 for tok in shared):
        return True

    # Conservative fallback for near-orthographic surname variants.
    best = 0.0
    for ta in toks_a:
        for tb in toks_b:
            if min(len(ta), len(tb)) < 4:
                continue
            best = max(best, string_similarity(ta, tb))
            if best >= PERSON_TOKEN_SIM_MIN:
                return True
    return False


def category_base_threshold(category: str, threshold: float) -> float:
    """Precision-first thresholds by category."""
    if category == "PERSON":
        # Keep PERSON slightly below global threshold, but require lexical compatibility.
        return max(PERSON_THRESHOLD, threshold - 0.03)
    if category == "CONCEPT":
        return max(CONCEPT_THRESHOLD, threshold)
    return max(threshold, CATEGORY_MIN_THRESHOLD.get(category, threshold))


def find_cross_book_matches(
    book_a_entities: list[dict],
    book_a_embeddings: np.ndarray,
    book_a_id: str,
    book_b_entities: list[dict],
    book_b_embeddings: np.ndarray,
    book_b_id: str,
    threshold: float,
) -> list[dict]:
    """Find matching entities between two books.

    Vectorized: groups by category, uses numpy to find above-threshold
    pairs, and dictionary lookup for exact lexical matches — avoids
    the O(n*m) Python double-loop that thermal-throttles on large pairs.
    """
    matches = []

    # Pre-compute per-entity data
    a_cats = [e["category"] for e in book_a_entities]
    b_cats = [e["category"] for e in book_b_entities]
    a_names = [e["name"] for e in book_a_entities]
    b_names = [e["name"] for e in book_b_entities]
    a_norm = [normalize_match_text(e["name"]) for e in book_a_entities]
    b_norm = [normalize_match_text(e["name"]) for e in book_b_entities]

    # Group indices by category
    a_by_cat: dict[str, list[int]] = defaultdict(list)
    b_by_cat: dict[str, list[int]] = defaultdict(list)
    for i, cat in enumerate(a_cats):
        a_by_cat[cat].append(i)
    for j, cat in enumerate(b_cats):
        b_by_cat[cat].append(j)

    # Full similarity matrix (BLAS — fast)
    sims = book_a_embeddings @ book_b_embeddings.T

    # Build norm-name index for B (for exact lexical matching via dict lookup)
    b_norm_to_indices: dict[str, list[int]] = defaultdict(list)
    for j, nn in enumerate(b_norm):
        if len(nn) >= 4:
            b_norm_to_indices[nn].append(j)

    # Process each category that exists in both books
    for cat in set(a_by_cat.keys()) & set(b_by_cat.keys()):
        a_idx = np.array(a_by_cat[cat])
        b_idx = np.array(b_by_cat[cat])

        if len(a_idx) == 0 or len(b_idx) == 0:
            continue

        # Category-specific precision-first thresholding
        base_t = category_base_threshold(cat, threshold)

        # Extract sub-similarity-matrix for this category pair
        sub_sims = sims[np.ix_(a_idx, b_idx)]

        # Minimum embedding threshold for candidate enumeration.
        # Only PERSON gets a small lexical boost at decision time.
        min_t = base_t - (0.02 if cat == "PERSON" else 0.0)
        if cat == "CONCEPT":
            min_t = min(min_t, CONCEPT_FAMILY_MIN_SIM)

        # Find above-threshold pairs using numpy (replaces O(n*m) Python loop)
        local_rows, local_cols = np.where(sub_sims >= min_t)

        # Build candidate set using original indices
        candidate_pairs: set[tuple[int, int]] = set()
        for k in range(len(local_rows)):
            candidate_pairs.add((int(a_idx[local_rows[k]]), int(b_idx[local_cols[k]])))

        # Add exact lexical matches via dict lookup (bypasses embedding threshold)
        b_idx_set = set(b_idx.tolist())
        for ai in a_idx:
            nn_a = a_norm[ai]
            if len(nn_a) >= 4 and nn_a in b_norm_to_indices:
                for bj in b_norm_to_indices[nn_a]:
                    if bj in b_idx_set:
                        candidate_pairs.add((int(ai), bj))

        # Process only the candidates (typically <<1% of all pairs)
        for i, j in candidate_pairs:
            name_i = a_names[i]
            name_j = b_names[j]
            sim = float(sims[i, j])

            str_sim = string_similarity(name_i, name_j)
            effective_t = base_t - (0.02 if cat == "PERSON" and str_sim >= 0.65 else 0.0)

            exact_seed = (a_norm[i] == b_norm[j] and len(a_norm[i]) >= 4)

            # For CONCEPT entities, disable exact lexical seeding for
            # generic/short words that cause mega-cluster chaining.
            if exact_seed and cat == "CONCEPT":
                norm_len = len(a_norm[i])
                if norm_len < 8:
                    exact_seed = False
                elif sim < 0.70:
                    exact_seed = False

            concept_family = (
                cat == "CONCEPT"
                and is_concept_family_variant(name_i, name_j)
            )

            if cat == "PERSON" and not exact_seed:
                if not person_name_compatible(name_i, name_j, str_sim):
                    continue

            # Keep if similarity exceeds threshold or exact lexical seed
            keep = exact_seed or sim >= effective_t

            # Conservative concept-family bridge
            if not keep and concept_family and sim >= CONCEPT_FAMILY_MIN_SIM:
                keep = True

            if keep:
                matches.append({
                    "a_idx": i,
                    "b_idx": j,
                    "a_book": book_a_id,
                    "b_book": book_b_id,
                    "similarity": sim,
                    "str_sim": str_sim,
                    "category": cat,
                    "exact_seed": exact_seed,
                    "concept_family": concept_family,
                })

    return matches


def graph_edge_weight(match: dict) -> float:
    """Weighted edge score used by community detection and top-k pruning."""
    weight = float(match["similarity"])
    if match.get("exact_seed"):
        weight += 0.03
    if match.get("concept_family"):
        weight += 0.02
    return weight


def build_raw_neighbors(edge_data: dict[tuple[int, int], dict]) -> dict[int, set[int]]:
    """Build undirected adjacency from edge_data."""
    neighbors: dict[int, set[int]] = defaultdict(set)
    for gid_a, gid_b in edge_data:
        neighbors[gid_a].add(gid_b)
        neighbors[gid_b].add(gid_a)
    return neighbors


def prune_edges_mutual_topk(
    edge_data: dict[tuple[int, int], dict],
    top_k: int,
) -> tuple[dict[int, set[int]], dict[tuple[int, int], dict]]:
    """Prune graph edges to mutual top-k neighbors to suppress hub chaining."""
    if top_k <= 0:
        neighbors = build_raw_neighbors(edge_data)
        return neighbors, edge_data

    ranked_neighbors: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for (gid_a, gid_b), match in edge_data.items():
        score = graph_edge_weight(match)
        ranked_neighbors[gid_a].append((score, gid_b))
        ranked_neighbors[gid_b].append((score, gid_a))

    top_neighbors: dict[int, set[int]] = {}
    for gid, items in ranked_neighbors.items():
        items.sort(key=lambda x: (-x[0], x[1]))
        top_neighbors[gid] = {neighbor for _, neighbor in items[:top_k]}

    pruned: dict[tuple[int, int], dict] = {}
    neighbors: dict[int, set[int]] = defaultdict(set)
    for (gid_a, gid_b), match in edge_data.items():
        if gid_b in top_neighbors.get(gid_a, set()) and gid_a in top_neighbors.get(gid_b, set()):
            pruned[(gid_a, gid_b)] = match
            neighbors[gid_a].add(gid_b)
            neighbors[gid_b].add(gid_a)

    # Safety fallback: if mutual-k removes everything, keep the original graph.
    if not pruned:
        return build_raw_neighbors(edge_data), edge_data
    return neighbors, pruned


def detect_candidate_groups(
    neighbors: dict[int, set[int]],
    edge_data: dict[tuple[int, int], dict],
    community_method: str,
    louvain_resolution: float,
) -> list[list[int]]:
    """Detect candidate groups using Louvain communities over connected components."""
    if not neighbors:
        return []

    graph = nx.Graph()
    graph.add_nodes_from(neighbors.keys())
    for (gid_a, gid_b), match in edge_data.items():
        if gid_b in neighbors.get(gid_a, set()):
            graph.add_edge(gid_a, gid_b, weight=graph_edge_weight(match))

    raw_groups: list[list[int]] = []
    for component_nodes in nx.connected_components(graph):
        if len(component_nodes) <= 1:
            continue
        component = graph.subgraph(component_nodes).copy()

        if community_method != "louvain" or component.number_of_nodes() < 6 or component.number_of_edges() < 5:
            raw_groups.append(sorted(component_nodes))
            continue

        try:
            communities = nx.community.louvain_communities(
                component,
                weight="weight",
                resolution=louvain_resolution,
                seed=LOUVAIN_SEED,
            )
        except Exception:
            communities = [set(component_nodes)]

        non_singletons = [sorted(group) for group in communities if len(group) > 1]
        if non_singletons:
            raw_groups.extend(non_singletons)
        else:
            raw_groups.append(sorted(component_nodes))

    raw_groups.sort(key=lambda g: (g[0], len(g)))
    return raw_groups


def build_clusters(
    all_matches: list[dict],
    book_entities: dict[str, list[dict]],
    community_method: str = COMMUNITY_METHOD,
    graph_top_k: int = GRAPH_TOP_K,
    louvain_resolution: float = LOUVAIN_RESOLUTION,
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

    # Build edge graph from matches
    edge_data = {}  # (gid_a, gid_b) -> match info

    for match in all_matches:
        gid_a = global_id_map[(match["a_book"], match["a_idx"])]
        gid_b = global_id_map[(match["b_book"], match["b_idx"])]
        edge_key = (min(gid_a, gid_b), max(gid_a, gid_b))
        edge_data[edge_key] = match

    if not edge_data:
        return []

    raw_edge_count = len(edge_data)
    raw_neighbors = build_raw_neighbors(edge_data)
    neighbors, edge_data = prune_edges_mutual_topk(edge_data, graph_top_k)
    raw_groups = detect_candidate_groups(neighbors, edge_data, community_method, louvain_resolution)

    print(
        f"  Graph edges: {len(edge_data)}/{raw_edge_count}, nodes={len(raw_neighbors)}, "
        f"mutual-top{graph_top_k} pruning, groups={len(raw_groups)} ({community_method})"
    )

    # Post-process: validate groups.
    # Keep robust subgroups via lexical seeds + multi-neighbor evidence,
    # not only direct linkage to the highest-count primary.
    clusters = []
    for group in raw_groups:
        # Find primary member (highest total count)
        primary_gid = max(group, key=lambda g: book_entities[reverse_map[g][0]][reverse_map[g][1]]["count"])
        primary_book, primary_idx = reverse_map[primary_gid]
        primary_entity = book_entities[primary_book][primary_idx]

        group_set = set(group)
        entity_by_gid = {}
        for gid in group:
            b, i = reverse_map[gid]
            entity_by_gid[gid] = book_entities[b][i]

        def get_edge(a: int, b: int) -> dict | None:
            return edge_data.get((min(a, b), max(a, b)))

        # Seed validation with primary + exact lexical matches (and conservative
        # concept-family links) anywhere in the component.
        validated_set = {primary_gid}
        for gid_a in group:
            for gid_b in neighbors.get(gid_a, set()):
                if gid_b not in group_set or gid_a >= gid_b:
                    continue
                edge = get_edge(gid_a, gid_b)
                if not edge:
                    continue
                if edge.get("exact_seed"):
                    validated_set.add(gid_a)
                    validated_set.add(gid_b)
                elif edge.get("concept_family") and edge["similarity"] >= CONCEPT_FAMILY_MIN_SIM:
                    validated_set.add(gid_a)
                    validated_set.add(gid_b)

        # Iterative expansion with anti-chaining guards.
        is_concept = primary_entity["category"] == "CONCEPT"
        # CONCEPT clusters need stricter validation to prevent mega-cluster chaining
        val_threshold = CONCEPT_VALIDATION_THRESHOLD if is_concept else VALIDATION_EDGE_THRESHOLD
        min_strong_links = 3 if is_concept else 2

        changed = True
        while changed:
            changed = False
            for gid in group:
                if gid in validated_set:
                    continue

                entity = entity_by_gid[gid]
                strong_links = 0
                near_exact_link = False
                seed_link = False

                for vgid in validated_set:
                    edge = get_edge(gid, vgid)
                    if not edge:
                        continue
                    if edge.get("exact_seed"):
                        seed_link = True
                        break
                    if edge.get("concept_family") and edge["similarity"] >= CONCEPT_FAMILY_MIN_SIM:
                        seed_link = True
                        break

                    sim = edge["similarity"]
                    if sim >= val_threshold:
                        strong_links += 1
                        ss_v = string_similarity(entity["name"], entity_by_gid[vgid]["name"])
                        if ss_v >= 0.92:
                            near_exact_link = True

                if seed_link:
                    validated_set.add(gid)
                    changed = True
                    continue

                # Allow nodes with robust support from multiple validated members.
                if strong_links >= min_strong_links or near_exact_link:
                    validated_set.add(gid)
                    changed = True
                    continue

                # Keep original strong-primary fallback as a final safety valve.
                edge_to_primary = get_edge(gid, primary_gid)
                if not edge_to_primary:
                    continue
                has_direct_edge = edge_to_primary["similarity"] >= val_threshold
                if not has_direct_edge:
                    continue
                ss = string_similarity(primary_entity["name"], entity["name"])
                is_substr = (
                    primary_entity["name"].lower() in entity["name"].lower()
                    or entity["name"].lower() in primary_entity["name"].lower()
                )
                if ss >= 0.35 or is_substr:
                    validated_set.add(gid)
                    changed = True
                elif ss >= 0.2 and edge_to_primary["similarity"] >= 0.90:
                    validated_set.add(gid)
                    changed = True

        validated = sorted(validated_set)

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
    mode: str = DUPLICATE_MERGE_MODE,
) -> tuple[list[dict], int]:
    """Merge cluster pairs that are near-duplicates split by subcategory noise.

    Modes:
      - off: disabled
      - strict: merge only exact lexical canonical duplicates
      - legacy: previous fuzzy Levenshtein merge behavior

    Criteria (all must hold):
      1. Same category
      2. High normalized Levenshtein between canonical names (>= lev_threshold)
      3. Share at least one book (both have members from the same source text)
         — OR identical canonical names with variant-level name overlap (exact dupes)

    This catches orthographic splits (cheiro/cheyro, estomago/eſtomago) without
    merging genuinely different concepts (Africa/Arica, cabras/cobras).
    """
    if mode == "off":
        return clusters, 0

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

                lev = normalized_levenshtein(a["canonical_name"], b["canonical_name"])
                if mode == "strict":
                    if not is_exact_lexical_match(a["canonical_name"], b["canonical_name"]):
                        continue
                else:
                    # Legacy behavior: fuzzy Levenshtein + shared-book safeguard.
                    # Places need a higher bar — short place names are easily confused
                    # (Africa/Arica, Goa/Gao)
                    t = lev_threshold + 0.02 if cat == "PLACE" else lev_threshold
                    if lev < t:
                        continue

                # Check shared books (primary safeguard)
                books_a = set(m["book_id"] for m in a["members"])
                books_b = set(m["book_id"] for m in b["members"])
                shared_books = books_a & books_b

                # For identical names, also allow name overlap without shared books.
                if not shared_books:
                    if mode != "strict" and lev < 1.0:
                        continue
                    # Identical names: require variant-level overlap as confirmation
                    names_a = {normalize_match_text(m["name"]) for m in a["members"]}
                    names_b = {normalize_match_text(m["name"]) for m in b["members"]}
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
                      f"(mode={mode}, lev={lev:.2f}, shared_books={len(shared_books)})")

    # Remove absorbed clusters
    result = [c for i, c in enumerate(clusters) if i not in merged_into]

    # Re-sort and re-assign IDs
    result.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))
    for i, c in enumerate(result):
        c["id"] = i + 1

    return result, merge_count


def merge_by_ground_truth(clusters: list[dict]) -> tuple[list[dict], int]:
    """Merge clusters that share the same ground_truth.modern_name and category.

    This catches fragmentation from the embedding similarity step — e.g. five
    separate "Moon" clusters that all resolved to modern_name="Moon" after
    Wikidata enrichment.  Runs after migrate_ground_truth.py has populated
    ground_truth fields.  Safe to call even if no ground_truth exists (no-op).
    """
    # Group by (modern_name_lower, category)
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, c in enumerate(clusters):
        gt = c.get("ground_truth", {})
        if not isinstance(gt, dict):
            continue
        mn = (gt.get("modern_name") or "").strip()
        if not mn:
            continue
        by_key[(mn.lower(), c["category"])].append(i)

    merged_into: dict[int, int] = {}
    merge_count = 0

    for (mn_lower, cat), indices in by_key.items():
        if len(indices) < 2:
            continue

        # Pick primary = most mentions
        indices.sort(key=lambda i: -clusters[i].get("total_mentions", 0))
        primary_idx = indices[0]
        primary = clusters[primary_idx]

        for absorbed_idx in indices[1:]:
            if absorbed_idx in merged_into:
                continue
            ab = clusters[absorbed_idx]

            # Merge members
            existing = {(m["book_id"], m["entity_id"]) for m in primary["members"]}
            for m in ab["members"]:
                if (m["book_id"], m["entity_id"]) not in existing:
                    primary["members"].append(m)
                    existing.add((m["book_id"], m["entity_id"]))

            # Merge edges
            existing_edges = {
                (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
                for e in primary.get("edges", [])
            }
            for e in ab.get("edges", []):
                key = (e["source_book"], e["source_name"], e["target_book"], e["target_name"])
                if key not in existing_edges:
                    primary["edges"].append(e)

            # Merge cross-references
            if ab.get("cross_references"):
                existing_xrefs = {
                    (x.get("target_cluster_id"), x.get("link_type", ""))
                    for x in primary.get("cross_references", [])
                }
                if "cross_references" not in primary:
                    primary["cross_references"] = []
                for x in ab["cross_references"]:
                    xkey = (x.get("target_cluster_id"), x.get("link_type", ""))
                    if xkey not in existing_xrefs:
                        primary["cross_references"].append(x)
                        existing_xrefs.add(xkey)

            # Pick best ground_truth
            def gt_score(gt):
                if not isinstance(gt, dict):
                    return 0
                return (sum(1 for v in gt.values() if v)
                        + (10 if gt.get("wikidata_id") else 0)
                        + (5 if gt.get("wikipedia_extract") else 0))

            ab_gt = ab.get("ground_truth", {})
            if isinstance(ab_gt, dict) and gt_score(ab_gt) > gt_score(primary.get("ground_truth", {})):
                primary["ground_truth"] = ab_gt

            # Update stats
            primary["total_mentions"] = sum(m["count"] for m in primary["members"])
            primary["book_count"] = len(set(m["book_id"] for m in primary["members"]))
            primary["member_count"] = len(primary["members"])

            merged_into[absorbed_idx] = primary_idx
            merge_count += 1

            print(f"    ground_truth merge: {ab['canonical_name']} -> {primary['canonical_name']} "
                  f"(modern_name='{mn_lower}', {cat})")

    if not merge_count:
        return clusters, 0

    # Remove absorbed clusters, re-sort, re-assign IDs
    result = [c for i, c in enumerate(clusters) if i not in merged_into]
    result.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))
    for i, c in enumerate(result):
        c["id"] = i + 1

    return result, merge_count


def split_oversized_clusters(
    clusters: list[dict],
    max_size: int = MAX_CLUSTER_SIZE,
) -> list[dict]:
    """Split clusters that exceed max_size by keeping only members with
    strong connections to the primary entity.

    For oversized clusters, we keep only members that have high string
    similarity to the primary or appear in the cluster's edge list with
    high similarity. This breaks mega-clusters back into manageable pieces.
    """
    result = []
    split_count = 0

    for cluster in clusters:
        members = cluster.get("members", [])
        if len(members) <= max_size:
            result.append(cluster)
            continue

        # This cluster is too big — keep only the most relevant members
        primary_name = cluster["canonical_name"].lower()
        edges = cluster.get("edges", [])

        # Build edge-based relevance scores for each member
        member_scores: dict[tuple[str, str], float] = {}
        for m in members:
            key = (m["book_id"], m["entity_id"])
            name = m["name"].lower()
            # String similarity to primary
            ss = string_similarity(primary_name, name)
            # Is it a substring match?
            if primary_name in name or name in primary_name:
                ss = max(ss, 0.6)
            # Exact match to primary
            if normalize_match_text(name) == normalize_match_text(primary_name):
                ss = 1.0
            member_scores[key] = ss

        # Boost scores based on edge connections to the primary
        primary_variants = {primary_name, normalize_match_text(primary_name)}
        for edge in edges:
            src_name = edge["source_name"].lower()
            tgt_name = edge["target_name"].lower()
            sim = edge["similarity"]

            # If one side is the primary, boost the other side
            if normalize_match_text(src_name) in primary_variants:
                for m in members:
                    if m["name"].lower() == tgt_name and m["book_id"] == edge["target_book"]:
                        key = (m["book_id"], m["entity_id"])
                        member_scores[key] = max(member_scores.get(key, 0), sim)
            elif normalize_match_text(tgt_name) in primary_variants:
                for m in members:
                    if m["name"].lower() == src_name and m["book_id"] == edge["source_book"]:
                        key = (m["book_id"], m["entity_id"])
                        member_scores[key] = max(member_scores.get(key, 0), sim)

        # Keep top max_size members by relevance score
        scored_members = []
        for m in members:
            key = (m["book_id"], m["entity_id"])
            scored_members.append((member_scores.get(key, 0), m))
        scored_members.sort(key=lambda x: -x[0])

        kept = [m for _, m in scored_members[:max_size]]
        dropped = len(members) - len(kept)

        # Rebuild cluster
        cluster["members"] = kept
        cluster["total_mentions"] = sum(m["count"] for m in kept)
        cluster["book_count"] = len(set(m["book_id"] for m in kept))

        # Filter edges to only reference kept members
        kept_keys = {(m["book_id"], m["entity_id"]) for m in kept}
        kept_names_by_book = defaultdict(set)
        for m in kept:
            kept_names_by_book[m["book_id"]].add(m["name"])
        cluster["edges"] = [
            e for e in edges
            if e["source_name"] in kept_names_by_book.get(e["source_book"], set())
            and e["target_name"] in kept_names_by_book.get(e["target_book"], set())
        ]

        if cluster["book_count"] >= 2:
            result.append(cluster)
            split_count += 1
            print(f"    Split {cluster['canonical_name']}: {len(members)} -> {len(kept)} members (dropped {dropped})")

    # Re-sort and re-assign IDs
    result.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))
    for i, c in enumerate(result):
        c["id"] = i + 1

    return result, split_count


def main():
    parser = argparse.ArgumentParser(description="Build cross-book concordance")
    parser.add_argument("--threshold", type=float, default=MATCH_THRESHOLD,
                        help=f"Match threshold (default: {MATCH_THRESHOLD})")
    parser.add_argument("--min-count", type=int, default=MIN_ENTITY_COUNT,
                        help=f"Min entity count to include (default: {MIN_ENTITY_COUNT})")
    parser.add_argument(
        "--community-method",
        choices=["louvain", "components"],
        default=COMMUNITY_METHOD,
        help=f"Community partition method (default: {COMMUNITY_METHOD})",
    )
    parser.add_argument(
        "--graph-top-k",
        type=int,
        default=GRAPH_TOP_K,
        help=f"Mutual top-k pruning for graph edges (default: {GRAPH_TOP_K})",
    )
    parser.add_argument(
        "--louvain-resolution",
        type=float,
        default=LOUVAIN_RESOLUTION,
        help=f"Louvain resolution (default: {LOUVAIN_RESOLUTION})",
    )
    parser.add_argument(
        "--duplicate-merge-mode",
        choices=["off", "strict", "legacy"],
        default=DUPLICATE_MERGE_MODE,
        help=f"Near-duplicate post-merge mode (default: {DUPLICATE_MERGE_MODE})",
    )
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
    schema_changed_total = 0
    for filepath in entity_files:
        data = load_book_entities(filepath)
        book_id = data["book"]["id"]
        entities = [e for e in data["entities"] if e["count"] >= args.min_count]
        book_entities[book_id] = entities
        books_meta.append(data["book"])
        norm = data.get("_schema_normalization", {})
        changed = norm.get("changed", 0)
        schema_changed_total += changed
        print(
            f"  {data['book']['title']} ({data['book'].get('language', '?')}): "
            f"{len(entities)} entities"
            + (f", schema-normalized={changed}" if changed else "")
        )

    if schema_changed_total:
        print(f"  Total schema-normalized entities: {schema_changed_total}")

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
    print(
        "Building concordance clusters "
        f"(method={args.community_method}, top_k={args.graph_top_k}, "
        f"resolution={args.louvain_resolution})..."
    )
    clusters = build_clusters(
        all_matches,
        book_entities,
        community_method=args.community_method,
        graph_top_k=args.graph_top_k,
        louvain_resolution=args.louvain_resolution,
    )

    # Post-processing: merge near-duplicate clusters split by subcategory noise
    print(f"Merging near-duplicate clusters (mode={args.duplicate_merge_mode})...")
    clusters, merge_count = merge_near_duplicates(
        clusters,
        mode=args.duplicate_merge_mode,
    )
    if merge_count:
        print(f"  Merged {merge_count} cluster pairs")

    # Post-processing: merge clusters sharing same ground_truth.modern_name + category.
    # This catches fragmentation from embedding similarity (e.g. 5 separate Moon clusters).
    # Only effective after migrate_ground_truth.py has populated ground_truth fields.
    print("Merging clusters with matching ground_truth.modern_name...")
    clusters, gt_merge_count = merge_by_ground_truth(clusters)
    if gt_merge_count:
        print(f"  Merged {gt_merge_count} cluster pairs by ground_truth")

    # Safety valve: split oversized clusters
    oversized = [c for c in clusters if len(c.get("members", [])) > MAX_CLUSTER_SIZE]
    if oversized:
        print(f"\nSplitting {len(oversized)} oversized clusters (max={MAX_CLUSTER_SIZE})...")
        clusters, split_count = split_oversized_clusters(clusters, MAX_CLUSTER_SIZE)
        print(f"  Split {split_count} clusters")

    # Assign human-readable stable keys, preserving from previous concordance.
    output_path = Path(args.output)
    assign_stable_keys(clusters, previous_concordance=output_path)

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
            "community_method": args.community_method,
            "graph_top_k": args.graph_top_k,
            "louvain_resolution": args.louvain_resolution,
            "duplicate_merge_mode": args.duplicate_merge_mode,
            "schema_normalized_entities": schema_changed_total,
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

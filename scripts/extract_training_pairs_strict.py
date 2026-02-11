#!/usr/bin/env python3
"""
Extract HIGH-QUALITY training pairs for embedding fine-tuning.

Unlike extract_training_pairs.py (which mines all cross-book pairs),
this script is highly selective:

  1. POSITIVE PAIRS (~800): Prioritizes conceptually non-obvious matches
     where surface forms look very different but a domain expert verified
     they're the same entity. Scored by normalized Levenshtein distance ×
     cross-lingual bonus. Capped per cluster.

  2. HARD NEGATIVES (~200): Surface-similar strings from DIFFERENT clusters
     that the model might confuse. Mined automatically by comparing member
     names across clusters with high string similarity but different meaning.

The goal: teach the model domain-specific conceptual links like
  engenho ↔ machine, aromata ↔ drogue, terça ↔ tertian fever
rather than trivial cognates it already handles (agua ↔ water).

Usage:
    python3 scripts/extract_training_pairs_strict.py [--dry-run]
    python3 scripts/extract_training_pairs_strict.py --output data/training_pairs_v3.json
"""

import json
import random
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
EXISTING_PAIRS_PATH = Path(__file__).parent.parent / "data" / "training_pairs.json"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "data" / "training_pairs_v3.json"

# Book ID → 2-letter language code
BOOK_LANGS = {
    "coloquios_da_orta_1563": "pt",
    "historia_medicinal_monardes_1574": "es",
    "ricettario_fiorentino_1597": "it",
    "english_physician_1652": "en",
    "pseudodoxia_epidemica_browne_1646": "en",
    "polyanthea_medicinal": "pt",
    "relation_historique_humboldt_vol3_1825": "fr",
    "kosmos_humboldt_1845": "en",
    "connexion_physical_sciences_somerville_1858": "en",
    "origin_of_species_darwin_1859": "en",
    "first_principles_spencer_1862": "en",
    "principles_of_psychology_james_1890": "en",
}

# ── Configuration ──
TARGET_POSITIVES = 800
TARGET_NEGATIVES = 200
MAX_PAIRS_PER_CLUSTER = 5          # Prevent mega-cluster dominance
MIN_NAME_LENGTH = 3                 # Skip very short names
MIN_LEVENSHTEIN_RATIO = 0.25       # Minimum normalized distance (0=identical, 1=totally different)
CROSS_LINGUAL_BONUS = 1.5          # Multiplier for cross-language pairs
DIFFERENT_SCRIPT_BONUS = 1.3       # Bonus when first 3 chars differ entirely

# Clusters to skip entirely (known bad clusters from review)
SKIP_CLUSTERS = {
    "consciousness",  # 185 monolingual en-en pairs, all James's Psychology
    "crusados",       # Conflates currency, crucibles, crosses, stars
    "Chapter X",      # Chapter numbers, meaningless
    "Man",            # Conflates human, manatee, mana
    "Sapa",           # Conflates sapa (grape must), soap, sap, toads
    "round",          # Matched to fitness magazine
}

# ── String distance ──

def levenshtein_distance(s1: str, s2: str) -> int:
    """Standard Levenshtein edit distance."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,      # deletion
                curr[j] + 1,           # insertion
                prev[j] + (c1 != c2),  # substitution
            ))
        prev = curr
    return prev[-1]


def normalized_distance(a: str, b: str) -> float:
    """Normalized Levenshtein distance: 0 = identical, 1 = completely different."""
    a_lower, b_lower = a.lower().strip(), b.lower().strip()
    if a_lower == b_lower:
        return 0.0
    max_len = max(len(a_lower), len(b_lower))
    if max_len == 0:
        return 0.0
    return levenshtein_distance(a_lower, b_lower) / max_len


def pair_score(name_a: str, name_b: str, lang_a: str, lang_b: str) -> float:
    """
    Score a pair's training value. Higher = more useful for fine-tuning.

    High scores: cross-lingual pairs with very different surface forms
    Low scores: same-language cognates, near-identical strings
    """
    dist = normalized_distance(name_a, name_b)

    # Below minimum distance threshold → worthless
    if dist < MIN_LEVENSHTEIN_RATIO:
        return 0.0

    score = dist

    # Cross-lingual bonus
    if lang_a != lang_b:
        score *= CROSS_LINGUAL_BONUS

    # Extra bonus if the first 3 chars are entirely different (truly non-obvious)
    a3 = name_a[:3].lower()
    b3 = name_b[:3].lower()
    if a3 != b3 and not any(c in b3 for c in a3):
        score *= DIFFERENT_SCRIPT_BONUS

    # Penalize very short names (less informative)
    min_len = min(len(name_a.strip()), len(name_b.strip()))
    if min_len < 4:
        score *= 0.5

    # Penalize if either name looks like an OCR artifact or garbage
    for name in [name_a, name_b]:
        if sum(1 for c in name if not c.isalpha() and c not in " '-.,") > len(name) * 0.3:
            score *= 0.3

    return score


def is_useful_name(name: str) -> bool:
    """Filter out names that are too short or junky."""
    name = name.strip()
    if len(name) < MIN_NAME_LENGTH:
        return False
    if name.isdigit():
        return False
    # Skip chapter/section references
    if name.lower().startswith("chapter") or name.lower().startswith("cap."):
        return False
    # Skip overly generic terms
    if name.lower() in {"the", "and", "for", "with", "from", "that", "this"}:
        return False
    return True


def normalize_name(name: str) -> str:
    return name.strip().lower()


# ── Positive pair extraction ──

def extract_scored_positives(clusters: list[dict]) -> list[dict]:
    """
    Extract and score all candidate positive pairs, return sorted by score.
    """
    all_pairs = []
    seen = set()

    for cluster in clusters:
        gt = cluster.get("ground_truth", {})
        if not gt:
            continue
        if cluster.get("book_count", 0) < 2:
            continue

        cname = cluster.get("canonical_name", "")
        if cname in SKIP_CLUSTERS:
            continue

        category = cluster["category"]
        members = cluster.get("members", [])

        # Collect unique (name, lang) per member
        member_info = []
        seen_names = set()
        for m in members:
            name = m["name"]
            lang = BOOK_LANGS.get(m["book_id"], "??")
            norm = normalize_name(name)
            if norm in seen_names or not is_useful_name(name):
                continue
            seen_names.add(norm)
            member_info.append({"name": name, "lang": lang, "book_id": m["book_id"]})

        # Include modern_name as an anchor
        modern = gt.get("modern_name")
        if modern and normalize_name(modern) not in seen_names and is_useful_name(modern):
            member_info.append({"name": modern, "lang": "en", "book_id": "_ground_truth"})
            seen_names.add(normalize_name(modern))

        # Score all cross-book pairs
        cluster_pairs = []
        for a, b in combinations(member_info, 2):
            if a["book_id"] == b["book_id"]:
                continue

            key = tuple(sorted([normalize_name(a["name"]), normalize_name(b["name"])]))
            if key in seen or key[0] == key[1]:
                continue
            seen.add(key)

            sc = pair_score(a["name"], b["name"], a["lang"], b["lang"])
            if sc <= 0:
                continue

            langs = f"{a['lang']}-{b['lang']}"
            cluster_pairs.append({
                "source": a["name"],
                "target": b["name"],
                "category": category,
                "langs": langs,
                "score": round(sc, 3),
                "cluster": cname,
                "note": f"from '{cname}' (score={sc:.2f})"
            })

        # Cap per cluster: take the highest-scoring pairs
        cluster_pairs.sort(key=lambda p: p["score"], reverse=True)
        all_pairs.extend(cluster_pairs[:MAX_PAIRS_PER_CLUSTER])

    # Sort all pairs by score descending
    all_pairs.sort(key=lambda p: p["score"], reverse=True)
    return all_pairs


# ── Hard negative mining ──

def mine_hard_negatives(clusters: list[dict]) -> list[dict]:
    """
    Mine hard negatives: surface-similar names from DIFFERENT clusters.

    These are pairs the model might confuse because the strings look alike,
    but they refer to completely different entities.
    """
    # Build name → (cluster_id, category) index
    name_index = {}  # normalized_name → (cluster_canonical, category, original_name)
    for cluster in clusters:
        cname = cluster.get("canonical_name", "")
        if cname in SKIP_CLUSTERS:
            continue
        category = cluster["category"]
        for m in cluster.get("members", []):
            name = m["name"]
            if is_useful_name(name):
                norm = normalize_name(name)
                if norm not in name_index:
                    name_index[norm] = (cname, category, name)
        # Also index canonical name and modern name
        if is_useful_name(cname):
            norm = normalize_name(cname)
            if norm not in name_index:
                name_index[norm] = (cname, category, cname)
        gt = cluster.get("ground_truth", {})
        modern = gt.get("modern_name", "")
        if modern and is_useful_name(modern):
            norm = normalize_name(modern)
            if norm not in name_index:
                name_index[norm] = (cname, category, modern)

    names = list(name_index.keys())
    print(f"  Hard negative mining: {len(names)} unique names indexed")

    # Find surface-similar pairs from different clusters
    # For efficiency, group by first 3 chars and compare within groups
    by_prefix = defaultdict(list)
    for norm in names:
        prefix = norm[:3] if len(norm) >= 3 else norm
        by_prefix[prefix].append(norm)

    # Also check similar prefixes (edit distance 1 on prefix)
    candidates = []
    seen = set()

    for prefix, group_names in by_prefix.items():
        # Compare all pairs within same prefix group
        for i, n1 in enumerate(group_names):
            for n2 in group_names[i+1:]:
                c1_cluster, c1_cat, c1_orig = name_index[n1]
                c2_cluster, c2_cat, c2_orig = name_index[n2]

                # Must be from DIFFERENT clusters
                if c1_cluster == c2_cluster:
                    continue

                key = tuple(sorted([n1, n2]))
                if key in seen:
                    continue
                seen.add(key)

                # Surface similarity (low distance = high similarity = good hard negative)
                dist = normalized_distance(c1_orig, c2_orig)
                if dist > 0.45:  # Too different to be a useful hard negative
                    continue
                if dist < 0.12:  # Too similar — likely just spelling variants / duplicate clusters
                    continue

                # Skip if one name is a substring of the other (likely same entity, split cluster)
                n1_low, n2_low = c1_orig.lower().strip(), c2_orig.lower().strip()
                if n1_low in n2_low or n2_low in n1_low:
                    continue

                # Higher similarity = better hard negative (inverted score)
                neg_score = 1.0 - dist

                # Bonus if same category (harder to discriminate)
                if c1_cat == c2_cat:
                    neg_score *= 1.2

                candidates.append({
                    "source": c1_orig,
                    "target": c2_orig,
                    "category": f"{c1_cat}/{c2_cat}" if c1_cat != c2_cat else c1_cat,
                    "score": round(neg_score, 3),
                    "note": f"hard neg: '{c1_orig}' ({c1_cluster}) ≠ '{c2_orig}' ({c2_cluster})",
                    "source_cluster": c1_cluster,
                    "target_cluster": c2_cluster,
                })

    candidates.sort(key=lambda p: p["score"], reverse=True)
    print(f"  Found {len(candidates)} hard negative candidates")
    return candidates


# ── Merge with curated ──

def load_curated_pairs(path: Path) -> tuple[list[dict], list[dict]]:
    """Load existing curated pairs, score them, return (positives, negatives)."""
    with open(path) as f:
        data = json.load(f)

    positives = []
    negatives = []

    for cat, cat_data in data.get("categories", {}).items():
        for p in cat_data.get("positive_pairs", []):
            sc = pair_score(p["source"], p["target"],
                          p.get("langs", "en-en").split("-")[0],
                          p.get("langs", "en-en").split("-")[1] if "-" in p.get("langs", "") else "en")
            positives.append({
                "source": p["source"],
                "target": p["target"],
                "category": cat,
                "langs": p.get("langs", "??"),
                "score": max(round(sc, 3), 0.5),  # Curated pairs get minimum 0.5
                "cluster": "curated",
                "note": p.get("note", "curated pair"),
                "origin": "curated",
            })
        for n in cat_data.get("hard_negatives", []):
            negatives.append({
                "source": n["source"],
                "target": n["target"],
                "category": cat,
                "score": 0.8,  # Curated negatives are high quality
                "note": n.get("note", "curated hard negative"),
                "origin": "curated",
            })

    return positives, negatives


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract strict training pairs")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    # Load concordance
    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    verified = sum(1 for c in clusters if c.get("ground_truth"))
    multi = sum(1 for c in clusters if c.get("book_count", 0) >= 2)
    print(f"  {len(clusters)} clusters ({verified} verified, {multi} multi-book)")

    # ── 1. Extract and score positive pairs ──
    print(f"\nExtracting scored positive pairs...")
    mined_positives = extract_scored_positives(clusters)
    print(f"  {len(mined_positives)} scored pairs (after per-cluster cap of {MAX_PAIRS_PER_CLUSTER})")

    # Load curated pairs
    print(f"\nLoading curated pairs...")
    curated_pos, curated_neg = load_curated_pairs(EXISTING_PAIRS_PATH)
    print(f"  {len(curated_pos)} curated positives, {len(curated_neg)} curated negatives")

    # Merge and deduplicate positives
    seen_pos = set()
    all_positives = []

    # Curated first (they get priority)
    for p in curated_pos:
        key = tuple(sorted([normalize_name(p["source"]), normalize_name(p["target"])]))
        if key not in seen_pos and key[0] != key[1]:
            seen_pos.add(key)
            all_positives.append(p)

    # Then mined
    for p in mined_positives:
        key = tuple(sorted([normalize_name(p["source"]), normalize_name(p["target"])]))
        if key not in seen_pos:
            seen_pos.add(key)
            p["origin"] = "mined"
            all_positives.append(p)

    # Sort by score and take top N
    all_positives.sort(key=lambda p: p["score"], reverse=True)

    print(f"\n  Total unique positives: {len(all_positives)}")
    print(f"  Score distribution:")
    for threshold in [2.0, 1.5, 1.0, 0.75, 0.5, 0.25]:
        count = sum(1 for p in all_positives if p["score"] >= threshold)
        print(f"    score >= {threshold}: {count}")

    selected_pos = all_positives[:TARGET_POSITIVES]

    # Show category breakdown of selected
    cat_counts = defaultdict(int)
    for p in selected_pos:
        cat_counts[p["category"]] += 1
    print(f"\n  Selected {len(selected_pos)} positives:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    # ── 2. Mine hard negatives ──
    print(f"\nMining hard negatives...")
    mined_negatives = mine_hard_negatives(clusters)

    # Merge with curated negatives
    seen_neg = set()
    all_negatives = []
    for n in curated_neg:
        key = tuple(sorted([normalize_name(n["source"]), normalize_name(n["target"])]))
        if key not in seen_neg:
            seen_neg.add(key)
            all_negatives.append(n)
    for n in mined_negatives:
        key = tuple(sorted([normalize_name(n["source"]), normalize_name(n["target"])]))
        if key not in seen_neg:
            seen_neg.add(key)
            n["origin"] = "mined"
            all_negatives.append(n)

    all_negatives.sort(key=lambda p: p["score"], reverse=True)
    selected_neg = all_negatives[:TARGET_NEGATIVES]

    print(f"  Selected {len(selected_neg)} hard negatives (from {len(all_negatives)} candidates)")

    # ── 3. Build output ──
    # Group by category
    output_categories = defaultdict(lambda: {"positive_pairs": [], "hard_negatives": []})
    for p in selected_pos:
        cat = p["category"]
        output_categories[cat]["positive_pairs"].append({
            "source": p["source"],
            "target": p["target"],
            "langs": p.get("langs", "??"),
            "score": p["score"],
            "origin": p.get("origin", "mined"),
            "note": p["note"],
        })
    for n in selected_neg:
        # For negatives, use first category if it's a combo
        cat = n["category"].split("/")[0] if "/" in n["category"] else n["category"]
        output_categories[cat]["hard_negatives"].append({
            "source": n["source"],
            "target": n["target"],
            "score": n["score"],
            "origin": n.get("origin", "mined"),
            "note": n["note"],
        })

    total_pos = sum(len(v["positive_pairs"]) for v in output_categories.values())
    total_neg = sum(len(v["hard_negatives"]) for v in output_categories.values())

    # Calculate language pair stats
    lang_pairs = defaultdict(int)
    for p in selected_pos:
        langs = p.get("langs", "??")
        lang_pairs[langs] += 1

    output = {
        "description": "High-quality training data for cross-lingual entity matching in early modern texts",
        "version": "3.0",
        "note": "v3.0: Strict selection — high string distance, cross-lingual priority, per-cluster cap, mined hard negatives",
        "statistics": {
            "total_positive_pairs": total_pos,
            "total_hard_negatives": total_neg,
            "language_pair_distribution": dict(sorted(lang_pairs.items(), key=lambda x: -x[1])),
            "selection_criteria": {
                "min_levenshtein_ratio": MIN_LEVENSHTEIN_RATIO,
                "max_pairs_per_cluster": MAX_PAIRS_PER_CLUSTER,
                "cross_lingual_bonus": CROSS_LINGUAL_BONUS,
                "target_positives": TARGET_POSITIVES,
                "target_negatives": TARGET_NEGATIVES,
            }
        },
        "categories": dict(output_categories),
    }

    print(f"\n{'='*60}")
    print(f"Final: {total_pos} positive pairs, {total_neg} hard negatives")
    print(f"\nLanguage pair distribution:")
    for lp, count in sorted(lang_pairs.items(), key=lambda x: -x[1])[:10]:
        print(f"  {lp}: {count}")

    # Show some top-scored examples
    print(f"\nTop 10 highest-scored positive pairs:")
    for p in selected_pos[:10]:
        print(f"  [{p['score']:.2f}] {p['source']} ↔ {p['target']} ({p.get('langs','??')}) — {p['cluster']}")

    print(f"\nTop 10 hard negatives:")
    for n in selected_neg[:10]:
        print(f"  [{n['score']:.2f}] {n['source']} ≠ {n['target']} — {n['note'][:60]}")

    if args.dry_run:
        print("\nDry run — not saving.")
        return

    output_path = Path(args.output)
    print(f"\nSaving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    size_kb = output_path.stat().st_size / 1024
    print(f"  {size_kb:.0f} KB")


if __name__ == "__main__":
    main()

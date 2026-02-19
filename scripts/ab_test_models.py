#!/usr/bin/env python3
"""
A/B test v2 vs v3 fine-tuned embedding models.

Tests on:
  1. Curated training pairs (sanity check — v3 should do well)
  2. HELD-OUT concordance pairs NOT in training data (generalization test)
  3. Hard negative discrimination
  4. Random cross-book entity pairs from concordance
  5. Edge cases: OCR-degraded names, very short names, Latin terms

Reports cosine similarities for both models side by side.
"""

import json
import random
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

# Paths
BASE = Path(__file__).parent.parent
CONCORDANCE_PATH = BASE / "web" / "public" / "data" / "concordance.json"
TRAINING_PATH = BASE / "data" / "curated_training_pairs.json"
MODEL_V2 = BASE / "models" / "finetuned-bge-m3-v2"
MODEL_V3 = BASE / "models" / "finetuned-bge-m3-v3"

BOOK_LANGS = {
    "coloquios_da_orta_1563": "PT",
    "historia_medicinal_monardes_1574": "ES",
    "ricettario_fiorentino_1597": "IT",
    "english_physician_1652": "EN",
    "pseudodoxia_epidemica_browne_1646": "EN",
    "polyanthea_medicinal": "PT",
    "relation_historique_humboldt_vol3_1825": "FR",
    "kosmos_humboldt_1845": "EN",
    "connexion_physical_sciences_somerville_1858": "EN",
    "origin_of_species_darwin_1859": "EN",
    "first_principles_spencer_1862": "EN",
    "principles_of_psychology_james_1890": "EN",
}


def load_models():
    """Load both models."""
    from sentence_transformers import SentenceTransformer
    print("Loading v2 model...")
    v2 = SentenceTransformer(str(MODEL_V2))
    print("Loading v3 model...")
    v3 = SentenceTransformer(str(MODEL_V3))
    return v2, v3


def cosine_sim(model, a: str, b: str) -> float:
    """Compute cosine similarity between two strings."""
    emb_a = model.encode(a, normalize_embeddings=True)
    emb_b = model.encode(b, normalize_embeddings=True)
    return float(emb_a @ emb_b)


def get_training_pair_keys(training_data: dict) -> set:
    """Get set of all (source, target) pairs in training data (lowercased)."""
    keys = set()
    for batch in training_data["batches"]:
        for p in batch["positive_pairs"]:
            k = tuple(sorted([p["source"].lower().strip(), p["target"].lower().strip()]))
            keys.add(k)
    return keys


def extract_held_out_pairs(clusters: list, training_keys: set, n: int = 100) -> list:
    """
    Extract cross-book member pairs from verified clusters
    that are NOT in the training data.
    """
    held_out = []
    seen = set()

    random.shuffle(clusters)
    for cluster in clusters:
        gt = cluster.get("ground_truth", {})
        if not gt:
            continue
        if cluster.get("book_count", 0) < 2:
            continue

        members = cluster.get("members", [])
        # Get unique (name, book_id) per member
        member_info = []
        seen_names = set()
        for m in members:
            name = m["name"]
            norm = name.lower().strip()
            if norm in seen_names or len(name) < 2:
                continue
            seen_names.add(norm)
            lang = BOOK_LANGS.get(m["book_id"], "??")
            member_info.append({"name": name, "lang": lang, "book_id": m["book_id"]})

        # Generate cross-book pairs not in training
        from itertools import combinations
        for a, b in combinations(member_info, 2):
            if a["book_id"] == b["book_id"]:
                continue
            key = tuple(sorted([a["name"].lower().strip(), b["name"].lower().strip()]))
            if key[0] == key[1]:
                continue
            if key in training_keys:
                continue
            if key in seen:
                continue
            seen.add(key)

            held_out.append({
                "source": a["name"],
                "target": b["name"],
                "langs": f"{a['lang']}-{b['lang']}",
                "cluster": cluster["canonical_name"],
                "category": cluster["category"],
            })

        if len(held_out) >= n * 3:  # collect extra, then sample
            break

    random.shuffle(held_out)
    return held_out[:n]


def extract_negative_pairs(clusters: list, n: int = 50) -> list:
    """
    Create plausible-looking negative pairs: names from DIFFERENT clusters
    that share a category (e.g., two different plants with similar names).
    """
    by_cat = defaultdict(list)
    for c in clusters:
        for m in c.get("members", []):
            name = m["name"]
            if len(name) >= 3:
                by_cat[c["category"]].append({
                    "name": name,
                    "cluster": c["canonical_name"],
                })

    negatives = []
    seen = set()
    for cat, entities in by_cat.items():
        random.shuffle(entities)
        for i in range(min(len(entities) - 1, n)):
            a = entities[i]
            # Find a different-cluster entity
            for j in range(i + 1, len(entities)):
                b = entities[j]
                if a["cluster"] != b["cluster"]:
                    key = tuple(sorted([a["name"].lower(), b["name"].lower()]))
                    if key not in seen and key[0] != key[1]:
                        seen.add(key)
                        negatives.append({
                            "source": a["name"],
                            "target": b["name"],
                            "category": cat,
                            "note": f"{a['cluster']} ≠ {b['cluster']}",
                        })
                        break
            if len(negatives) >= n:
                break
        if len(negatives) >= n:
            break

    return negatives[:n]


def run_test(v2, v3, pairs: list, label: str, should_match: bool):
    """Run a test suite and print results."""
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"  {'(should match)' if should_match else '(should NOT match)'}  —  {len(pairs)} pairs")
    print(f"{'='*80}")

    v2_sims = []
    v3_sims = []
    v3_wins = 0
    v2_wins = 0

    details = []
    for p in pairs:
        s2 = cosine_sim(v2, p["source"], p["target"])
        s3 = cosine_sim(v3, p["source"], p["target"])
        v2_sims.append(s2)
        v3_sims.append(s3)

        if should_match:
            if s3 > s2:
                v3_wins += 1
            elif s2 > s3:
                v2_wins += 1
        else:
            if s3 < s2:
                v3_wins += 1  # Lower is better for negatives
            elif s2 < s3:
                v2_wins += 1

        details.append((p, s2, s3))

    # Sort by biggest v3 improvement
    if should_match:
        details.sort(key=lambda x: x[2] - x[1], reverse=True)
    else:
        details.sort(key=lambda x: x[1] - x[2], reverse=True)

    # Show top 10 biggest improvements and 5 biggest regressions
    print(f"\n  Top improvements (v3 better):")
    for p, s2, s3 in details[:10]:
        delta = s3 - s2 if should_match else s2 - s3
        langs = p.get("langs", p.get("category", ""))
        print(f"    {p['source']:25} ↔ {p['target']:25} v2={s2:.3f}  v3={s3:.3f}  Δ{delta:+.3f}  [{langs}]")

    print(f"\n  Biggest regressions (v2 better):")
    for p, s2, s3 in details[-5:]:
        delta = s3 - s2 if should_match else s2 - s3
        langs = p.get("langs", p.get("category", ""))
        print(f"    {p['source']:25} ↔ {p['target']:25} v2={s2:.3f}  v3={s3:.3f}  Δ{delta:+.3f}  [{langs}]")

    # Summary stats
    avg_v2 = np.mean(v2_sims)
    avg_v3 = np.mean(v3_sims)
    med_v2 = np.median(v2_sims)
    med_v3 = np.median(v3_sims)

    print(f"\n  Summary:")
    print(f"    {'Metric':<20} {'v2':>8} {'v3':>8} {'Delta':>8}")
    print(f"    {'─'*48}")
    print(f"    {'Mean similarity':<20} {avg_v2:>8.4f} {avg_v3:>8.4f} {avg_v3-avg_v2:>+8.4f}")
    print(f"    {'Median similarity':<20} {med_v2:>8.4f} {med_v3:>8.4f} {med_v3-med_v2:>+8.4f}")
    print(f"    {'v3 wins':<20} {v3_wins:>8d}")
    print(f"    {'v2 wins':<20} {v2_wins:>8d}")
    print(f"    {'Ties':<20} {len(pairs)-v3_wins-v2_wins:>8d}")

    # Threshold analysis (how many exceed typical merge thresholds)
    for thresh in [0.80, 0.84, 0.75, 0.70]:
        v2_above = sum(1 for s in v2_sims if s >= thresh)
        v3_above = sum(1 for s in v3_sims if s >= thresh)
        print(f"    {'Above ' + str(thresh):<20} {v2_above:>8d} {v3_above:>8d} {v3_above-v2_above:>+8d}")

    return avg_v2, avg_v3, v2_sims, v3_sims


def main():
    random.seed(42)
    np.random.seed(42)

    # Load data
    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        concordance = json.load(f)
    clusters = concordance["clusters"]
    print(f"  {len(clusters)} clusters")

    print("Loading training data...")
    with open(TRAINING_PATH) as f:
        training = json.load(f)
    training_keys = get_training_pair_keys(training)
    print(f"  {len(training_keys)} training pair keys")

    # Load models
    v2, v3 = load_models()

    # ── TEST 1: Held-out positive pairs ──────────────────────────────────────
    print("\nExtracting held-out cross-book pairs (NOT in training data)...")
    held_out = extract_held_out_pairs(clusters, training_keys, n=100)
    print(f"  {len(held_out)} held-out pairs")

    # Count cross-lingual
    cross_lingual = sum(1 for p in held_out if p["langs"].split("-")[0] != p["langs"].split("-")[1])
    print(f"  {cross_lingual} cross-lingual, {len(held_out)-cross_lingual} same-language")

    avg_v2_pos, avg_v3_pos, _, _ = run_test(v2, v3, held_out, "HELD-OUT POSITIVES (generalization)", True)

    # ── TEST 2: Random same-category negatives ───────────────────────────────
    print("\nExtracting random same-category negative pairs...")
    negatives = extract_negative_pairs(clusters, n=80)
    print(f"  {len(negatives)} negative pairs")

    avg_v2_neg, avg_v3_neg, _, _ = run_test(v2, v3, negatives, "SAME-CATEGORY NEGATIVES (discrimination)", False)

    # ── TEST 3: Curated training pairs (sanity check) ────────────────────────
    all_pos = []
    for batch in training["batches"]:
        all_pos.extend(batch["positive_pairs"])
    sample_training = random.sample(all_pos, min(60, len(all_pos)))
    run_test(v2, v3, sample_training, "TRAINING DATA SAMPLE (sanity check — v3 should excel)", True)

    # ── TEST 4: Curated hard negatives (sanity check) ────────────────────────
    all_neg = []
    for batch in training["batches"]:
        all_neg.extend(batch["hard_negatives"])
    sample_neg = random.sample(all_neg, min(60, len(all_neg)))
    run_test(v2, v3, sample_neg, "CURATED HARD NEGATIVES (v3 should push these apart)", False)

    # ── TEST 5: Specific edge cases ──────────────────────────────────────────
    edge_cases_pos = [
        {"source": "sangue", "target": "blood", "langs": "PT-EN"},
        {"source": "pietra", "target": "stone", "langs": "IT-EN"},
        {"source": "fièvre", "target": "fever", "langs": "FR-EN"},
        {"source": "Quecksilber", "target": "mercury", "langs": "DE-EN"},
        {"source": "azogue", "target": "mercury", "langs": "ES-EN"},
        {"source": "pimenta", "target": "pepper", "langs": "PT-EN"},
        {"source": "opio", "target": "opium", "langs": "ES-EN"},
        {"source": "veneno", "target": "poison", "langs": "ES-EN"},
        {"source": "Magnetismus", "target": "magnetism", "langs": "DE-EN"},
        {"source": "Naturphilosophie", "target": "natural philosophy", "langs": "DE-EN"},
        {"source": "acqua", "target": "water", "langs": "IT-EN"},
        {"source": "pedra", "target": "stone", "langs": "PT-EN"},
        {"source": "zucchero", "target": "sugar", "langs": "IT-EN"},
        {"source": "estrellas", "target": "stars", "langs": "ES-EN"},
        {"source": "Pflanze", "target": "plant", "langs": "DE-EN"},
        {"source": "erva", "target": "herb", "langs": "PT-EN"},
        {"source": "remedio", "target": "remedy", "langs": "PT-EN"},
        {"source": "cerveau", "target": "brain", "langs": "FR-EN"},
        {"source": "Seelenlehre", "target": "psychology", "langs": "DE-EN"},
        {"source": "Krankheit", "target": "disease", "langs": "DE-EN"},
    ]
    run_test(v2, v3, edge_cases_pos, "EDGE CASES: Cross-lingual (not in training)", True)

    edge_cases_neg = [
        {"source": "sangue", "target": "sangria", "category": "SUBSTANCE"},
        {"source": "pedra", "target": "Pedro", "category": "PLACE/PERSON"},
        {"source": "opio", "target": "opal", "category": "SUBSTANCE"},
        {"source": "fièvre", "target": "fièvre jaune", "category": "DISEASE"},
        {"source": "erva", "target": "Erivan", "category": "PLACE"},
        {"source": "mercury", "target": "Mercury", "category": "PLANET/ELEMENT"},
        {"source": "cerveau", "target": "cerveja", "category": "SUBSTANCE"},
        {"source": "remedio", "target": "remora", "category": "ANIMAL"},
        {"source": "estrellas", "target": "Estrella", "category": "PERSON"},
        {"source": "acqua", "target": "acquavite", "category": "SUBSTANCE"},
    ]
    run_test(v2, v3, edge_cases_neg, "EDGE CASES: Confusable negatives (not in training)", False)

    # ── FINAL SUMMARY ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  FINAL VERDICT")
    print(f"{'='*80}")

    sep_v2 = avg_v2_pos - avg_v2_neg
    sep_v3 = avg_v3_pos - avg_v3_neg

    print(f"\n  On HELD-OUT data (not in training):")
    print(f"    v2 separation (pos - neg): {sep_v2:.4f}")
    print(f"    v3 separation (pos - neg): {sep_v3:.4f}")
    print(f"    Improvement:               {sep_v3 - sep_v2:+.4f}")

    if sep_v3 > sep_v2 + 0.02:
        print(f"\n    → v3 GENERALIZES WELL. Safe to use in production.")
    elif sep_v3 > sep_v2 - 0.02:
        print(f"\n    → v3 roughly TIES with v2 on held-out data. Marginal improvement.")
    else:
        print(f"\n    → v3 may be OVERFITTING. v2 generalizes better on unseen data.")


if __name__ == "__main__":
    main()

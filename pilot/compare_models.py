#!/usr/bin/env python3
"""
Compare embedding models on the test pairs.
Outputs a comparison table showing performance by model.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics import precision_recall_fscore_support


MODELS = [
    ("BAAI/bge-m3", "BGE-M3 (baseline)"),
    ("intfloat/multilingual-e5-large-instruct", "mE5-Large-Instruct"),
    ("Snowflake/snowflake-arctic-embed-l-v2.0", "Arctic-Embed-L-v2"),
    ("sentence-transformers/paraphrase-multilingual-mpnet-base-v2", "Paraphrase-mMPNet"),
]


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def evaluate_model(model_name, df, threshold=0.7):
    """Evaluate a single model on the test pairs."""
    print(f"\nLoading {model_name}...")
    model = SentenceTransformer(model_name, trust_remote_code=True)

    # Encode unique terms
    terms = sorted(set(df["term_a"]).union(set(df["term_b"])))
    print(f"  Encoding {len(terms)} terms...")
    embeddings = {term: model.encode(term) for term in terms}

    # Compute similarities
    results = []
    for _, row in df.iterrows():
        sim = cosine(embeddings[row["term_a"]], embeddings[row["term_b"]])
        is_match = row["link_type"] != "hard_negative"
        pred_match = sim >= threshold
        results.append({
            "link_type": row["link_type"],
            "similarity": sim,
            "is_match": is_match,
            "pred_match": pred_match,
        })

    results_df = pd.DataFrame(results)

    # Overall metrics
    y_true = results_df["is_match"].to_numpy()
    y_pred = results_df["pred_match"].to_numpy()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )

    # Per-link-type recall
    link_type_stats = {}
    for link_type in results_df["link_type"].unique():
        subset = results_df[results_df["link_type"] == link_type]
        avg_sim = subset["similarity"].mean()
        recall_70 = (subset["similarity"] >= 0.7).mean()
        link_type_stats[link_type] = {"avg_sim": avg_sim, "recall_70": recall_70}

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "same_referent_recall": link_type_stats.get("same_referent", {}).get("recall_70", 0),
        "same_referent_avg_sim": link_type_stats.get("same_referent", {}).get("avg_sim", 0),
        "hard_negative_avg_sim": link_type_stats.get("hard_negative", {}).get("avg_sim", 0),
        "link_type_stats": link_type_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare embedding models")
    parser.add_argument("--pairs", default="pilot/test_pairs.csv", help="Test pairs CSV")
    parser.add_argument("--out", default="pilot/model_comparison.txt", help="Output file")
    parser.add_argument("--threshold", type=float, default=0.7, help="Match threshold")
    args = parser.parse_args()

    df = pd.read_csv(args.pairs)

    results = {}
    for model_id, model_name in MODELS:
        try:
            results[model_name] = evaluate_model(model_id, df, args.threshold)
        except Exception as e:
            print(f"  Error loading {model_id}: {e}")
            continue

    # Output comparison
    lines = []
    lines.append("=" * 70)
    lines.append("EMBEDDING MODEL COMPARISON")
    lines.append(f"Test pairs: {len(df)}, Threshold: {args.threshold}")
    lines.append("=" * 70)
    lines.append("")

    # Summary table
    lines.append("OVERALL METRICS:")
    lines.append("-" * 70)
    lines.append(f"{'Model':<25} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    lines.append("-" * 70)
    for model_name, r in results.items():
        lines.append(f"{model_name:<25} {r['precision']:>10.3f} {r['recall']:>10.3f} {r['f1']:>10.3f}")
    lines.append("")

    # Cross-lingual performance (the hard case)
    lines.append("CROSS-LINGUAL SAME_REFERENT (the critical metric):")
    lines.append("-" * 70)
    lines.append(f"{'Model':<25} {'Avg Similarity':>15} {'Recall@0.7':>12}")
    lines.append("-" * 70)
    for model_name, r in results.items():
        lines.append(f"{model_name:<25} {r['same_referent_avg_sim']:>15.3f} {r['same_referent_recall']:>11.1%}")
    lines.append("")

    # Hard negative separation
    lines.append("HARD NEGATIVE SEPARATION (lower is better):")
    lines.append("-" * 70)
    lines.append(f"{'Model':<25} {'Hard Neg Avg Sim':>18} {'Gap from Same Ref':>18}")
    lines.append("-" * 70)
    for model_name, r in results.items():
        gap = r['same_referent_avg_sim'] - r['hard_negative_avg_sim']
        lines.append(f"{model_name:<25} {r['hard_negative_avg_sim']:>18.3f} {gap:>18.3f}")
    lines.append("")

    # Detailed by link type for best model
    best_model = max(results.items(), key=lambda x: x[1]['same_referent_recall'])
    lines.append(f"DETAILED RESULTS FOR BEST MODEL: {best_model[0]}")
    lines.append("-" * 70)
    for link_type, stats in best_model[1]['link_type_stats'].items():
        lines.append(f"  {link_type:<25} Avg: {stats['avg_sim']:.3f}  Recall@0.7: {stats['recall_70']:.1%}")

    output = "\n".join(lines)
    print(output)
    Path(args.out).write_text(output)
    print(f"\nResults saved to {args.out}")


if __name__ == "__main__":
    main()

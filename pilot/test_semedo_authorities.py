#!/usr/bin/env python3
"""
Test embedding similarity on Semedo's cited authorities.
Compares base BGE-M3 vs fine-tuned model on person name variants.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def evaluate_model(model_path, df, model_name):
    """Evaluate a model on the name pairs and return results."""
    print(f"\nLoading {model_name}...")
    model = SentenceTransformer(model_path)

    # Get unique terms
    terms = sorted(set(df["term_a"]).union(set(df["term_b"])))
    print(f"Encoding {len(terms)} unique name variants...")
    embeddings = {term: model.encode(term) for term in terms}

    # Calculate similarities
    results = []
    for _, row in df.iterrows():
        sim = cosine(embeddings[row["term_a"]], embeddings[row["term_b"]])
        results.append({
            "term_a": row["term_a"],
            "term_b": row["term_b"],
            "lang_a": row["lang_a"],
            "lang_b": row["lang_b"],
            "link_type": row["link_type"],
            "modern_id": row["modern_id"],
            "similarity": sim,
        })

    return pd.DataFrame(results)


def print_summary(df, model_name):
    """Print summary statistics."""
    print(f"\n{'='*60}")
    print(f"Results for: {model_name}")
    print(f"{'='*60}")

    avg_sim = df["similarity"].mean()
    print(f"Average similarity: {avg_sim:.3f}")
    print(f"Pairs above 0.7: {(df['similarity'] >= 0.7).sum()}/{len(df)} ({(df['similarity'] >= 0.7).mean():.1%})")
    print(f"Pairs above 0.8: {(df['similarity'] >= 0.8).sum()}/{len(df)} ({(df['similarity'] >= 0.8).mean():.1%})")
    print(f"Pairs above 0.9: {(df['similarity'] >= 0.9).sum()}/{len(df)} ({(df['similarity'] >= 0.9).mean():.1%})")

    # By link type
    print("\nBy link type:")
    for link_type in sorted(df["link_type"].unique()):
        subset = df[df["link_type"] == link_type]
        print(f"  {link_type}: avg={subset['similarity'].mean():.3f} (n={len(subset)})")

    # Lowest similarities (potential problem cases)
    print("\nLowest similarity pairs:")
    for _, row in df.nsmallest(5, "similarity").iterrows():
        print(f"  {row['similarity']:.3f}: {row['term_a']} <-> {row['term_b']}")

    # Highest similarities
    print("\nHighest similarity pairs:")
    for _, row in df.nlargest(5, "similarity").iterrows():
        print(f"  {row['similarity']:.3f}: {row['term_a']} <-> {row['term_b']}")


def main():
    parser = argparse.ArgumentParser(description="Test embeddings on Semedo authorities")
    parser.add_argument("--pairs", default="pilot/semedo_authorities.csv", help="CSV with name pairs")
    parser.add_argument("--base-model", default="BAAI/bge-m3", help="Base model for comparison")
    parser.add_argument("--finetuned", default="models/finetuned-bge-m3-premodern", help="Fine-tuned model path")
    parser.add_argument("--out", default="pilot/semedo_embedding_comparison.csv", help="Output CSV")
    args = parser.parse_args()

    # Load pairs
    df = pd.read_csv(args.pairs)
    print(f"Loaded {len(df)} name variant pairs for {df['modern_id'].nunique()} historical figures")

    # Evaluate both models
    base_results = evaluate_model(args.base_model, df, "Base BGE-M3")
    finetuned_results = evaluate_model(args.finetuned, df, "Fine-tuned BGE-M3")

    # Print summaries
    print_summary(base_results, "Base BGE-M3")
    print_summary(finetuned_results, "Fine-tuned BGE-M3 (premodern)")

    # Merge results for comparison
    comparison = base_results.copy()
    comparison = comparison.rename(columns={"similarity": "sim_base"})
    comparison["sim_finetuned"] = finetuned_results["similarity"]
    comparison["improvement"] = comparison["sim_finetuned"] - comparison["sim_base"]

    # Save comparison
    comparison.to_csv(args.out, index=False)
    print(f"\nComparison saved to {args.out}")

    # Summary of improvements
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    avg_improvement = comparison["improvement"].mean()
    improved_count = (comparison["improvement"] > 0).sum()
    print(f"Average improvement: {avg_improvement:+.3f}")
    print(f"Pairs improved: {improved_count}/{len(comparison)} ({improved_count/len(comparison):.1%})")

    # Biggest improvements
    print("\nBiggest improvements from fine-tuning:")
    for _, row in comparison.nlargest(5, "improvement").iterrows():
        print(f"  {row['improvement']:+.3f}: {row['term_a']} <-> {row['term_b']}")
        print(f"          base={row['sim_base']:.3f} -> finetuned={row['sim_finetuned']:.3f}")


if __name__ == "__main__":
    main()

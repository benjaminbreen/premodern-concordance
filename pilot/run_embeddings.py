#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics import precision_recall_fscore_support


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    parser = argparse.ArgumentParser(description="Embedding baseline for entity-pair test set.")
    parser.add_argument("--pairs", default="pilot/test_pairs.csv", help="CSV with term pairs")
    parser.add_argument("--model", default="BAAI/bge-m3", help="SentenceTransformer model")
    parser.add_argument("--threshold", type=float, default=0.7, help="match threshold")
    parser.add_argument("--out", default="pilot/embedding_results.csv", help="output CSV")
    parser.add_argument("--summary", default="pilot/summary.txt", help="summary text")
    args = parser.parse_args()

    pairs_path = Path(args.pairs)
    df = pd.read_csv(pairs_path)

    # Encode unique terms
    terms = sorted(set(df["term_a"]).union(set(df["term_b"])))
    model = SentenceTransformer(args.model)
    embeddings = {term: model.encode(term) for term in terms}

    rows = []
    for _, row in df.iterrows():
        emb_a = embeddings[row["term_a"]]
        emb_b = embeddings[row["term_b"]]
        sim = cosine(emb_a, emb_b)
        is_match = row["link_type"] != "hard_negative"
        pred_match = sim >= args.threshold
        rows.append({
            **row.to_dict(),
            "similarity": sim,
            "is_match": is_match,
            "pred_match": pred_match,
        })

    out_df = pd.DataFrame(rows)
    out_df.to_csv(args.out, index=False)

    # Overall metrics
    y_true = out_df["is_match"].astype(bool).to_numpy()
    y_pred = out_df["pred_match"].astype(bool).to_numpy()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )

    # Per-link-type stats
    lines = []
    lines.append(f"Model: {args.model}")
    lines.append(f"Pairs: {len(out_df)}")
    lines.append(f"Threshold: {args.threshold:.2f}")
    lines.append("")
    lines.append(f"Overall precision: {precision:.3f}")
    lines.append(f"Overall recall: {recall:.3f}")
    lines.append(f"Overall F1: {f1:.3f}")
    lines.append("")
    lines.append("By link_type:")

    for link_type in sorted(out_df["link_type"].unique()):
        subset = out_df[out_df["link_type"] == link_type]
        avg_sim = subset["similarity"].mean()
        recall_70 = (subset["similarity"] >= 0.7).mean()
        recall_50 = (subset["similarity"] >= 0.5).mean()
        lines.append(f"- {link_type}")
        lines.append(f"  Avg similarity: {avg_sim:.3f}")
        lines.append(f"  Recall@0.7: {recall_70:.2%}")
        lines.append(f"  Recall@0.5: {recall_50:.2%}")

    Path(args.summary).write_text("\n".join(lines))


if __name__ == "__main__":
    main()

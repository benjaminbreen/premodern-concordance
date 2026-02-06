#!/usr/bin/env python3
"""
Fine-tune BGE-M3 (or other embedding models) on typed entity pairs.

This uses contrastive learning: positive pairs are pulled together,
negative pairs are pushed apart in embedding space.

IMPORTANT: Uses train/test split to avoid overfitting. Test pairs are
held out and never seen during training.

Usage:
    python pilot/finetune_embeddings.py --pairs pilot/combined_pairs.csv --epochs 10

Requirements:
    - sentence-transformers >= 2.2.0
    - torch (with MPS support on Apple Silicon, or CUDA on NVIDIA)
"""
import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer, InputExample, losses
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader


# Link types that count as positive matches
POSITIVE_LINK_TYPES = {
    "same_referent",
    "orthographic_variant",
    "derivation",
}

# Link types that count as negative (non-matches)
NEGATIVE_LINK_TYPES = {
    "hard_negative",
}

# Uncertain types - can be used for evaluation but not training
UNCERTAIN_LINK_TYPES = {
    "conceptual_overlap",
    "contested_identity",
}


def prepare_training_data(df, test_size=0.25, random_state=42):
    """
    Convert DataFrame to training examples with proper train/test split.

    Returns:
        train_examples: InputExamples for training
        test_df: DataFrame of held-out pairs for evaluation (NEVER seen during training)
    """
    # Split BEFORE creating examples to avoid data leakage
    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=random_state, stratify=df["link_type"]
    )

    print(f"  Train/test split: {len(train_df)} train, {len(test_df)} test (held out)")

    train_examples = []

    # Only use training data for examples
    for _, row in train_df.iterrows():
        if row["link_type"] in POSITIVE_LINK_TYPES:
            train_examples.append(InputExample(
                texts=[row["term_a"], row["term_b"]],
                label=1.0
            ))
        elif row["link_type"] in NEGATIVE_LINK_TYPES:
            train_examples.append(InputExample(
                texts=[row["term_a"], row["term_b"]],
                label=0.0
            ))
        elif row["link_type"] in UNCERTAIN_LINK_TYPES:
            # Include uncertain types in training with intermediate labels
            label = 0.5 if row["link_type"] == "conceptual_overlap" else 0.3
            train_examples.append(InputExample(
                texts=[row["term_a"], row["term_b"]],
                label=label
            ))

    return train_examples, test_df


def evaluate_on_test_set(model, test_df, threshold=0.7):
    """Evaluate model on held-out test set."""
    from sklearn.metrics import precision_recall_fscore_support

    def cosine(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    results = []
    for _, row in test_df.iterrows():
        emb_a = model.encode(row["term_a"])
        emb_b = model.encode(row["term_b"])
        sim = cosine(emb_a, emb_b)
        is_match = row["link_type"] != "hard_negative"
        pred_match = sim >= threshold
        results.append({
            "term_a": row["term_a"],
            "term_b": row["term_b"],
            "link_type": row["link_type"],
            "similarity": sim,
            "is_match": is_match,
            "pred_match": pred_match,
        })

    results_df = pd.DataFrame(results)

    y_true = results_df["is_match"].to_numpy()
    y_pred = results_df["pred_match"].to_numpy()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )

    # Per-link-type stats
    print("\n  Results on HELD-OUT test set:")
    print(f"  Precision: {precision:.3f}, Recall: {recall:.3f}, F1: {f1:.3f}")
    print("\n  By link type:")
    for link_type in sorted(results_df["link_type"].unique()):
        subset = results_df[results_df["link_type"] == link_type]
        avg_sim = subset["similarity"].mean()
        recall_70 = (subset["similarity"] >= 0.7).mean()
        print(f"    {link_type}: avg_sim={avg_sim:.3f}, recall@0.7={recall_70:.1%}")

    return results_df


def main():
    parser = argparse.ArgumentParser(description="Fine-tune embedding model on entity pairs")
    parser.add_argument("--pairs", default="pilot/test_pairs.csv", help="Training pairs CSV")
    parser.add_argument("--model", default="BAAI/bge-m3", help="Base model to fine-tune")
    parser.add_argument("--output", default="pilot/finetuned-model", help="Output directory")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--warmup-steps", type=int, default=10, help="Warmup steps")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--augment", action="store_true", help="Augment data with swapped pairs")
    parser.add_argument("--test-size", type=float, default=0.25, help="Fraction held out for testing")
    args = parser.parse_args()

    # Check for GPU/MPS availability
    if torch.cuda.is_available():
        device = "cuda"
        print(f"Using CUDA GPU: {torch.cuda.get_device_name()}")
    elif torch.backends.mps.is_available():
        device = "mps"
        print("Using Apple Silicon MPS acceleration")
    else:
        device = "cpu"
        print("Using CPU (this will be slow)")

    # Load data
    print(f"\nLoading pairs from {args.pairs}...")
    df = pd.read_csv(args.pairs)
    print(f"  Total pairs: {len(df)}")
    print(f"  Positive (same_referent, orthographic_variant, derivation): {len(df[df['link_type'].isin(POSITIVE_LINK_TYPES)])}")
    print(f"  Negative (hard_negative): {len(df[df['link_type'].isin(NEGATIVE_LINK_TYPES)])}")
    print(f"  Uncertain (conceptual_overlap, contested_identity): {len(df[df['link_type'].isin(UNCERTAIN_LINK_TYPES)])}")

    # CRITICAL: Split data BEFORE training to avoid overfitting
    train_examples, test_df = prepare_training_data(df, test_size=args.test_size)

    # Save test set for reproducibility
    test_df.to_csv(Path(args.output).parent / "test_set_held_out.csv", index=False)
    print(f"  Saved held-out test set to test_set_held_out.csv")

    # Data augmentation: add swapped pairs (term_b, term_a)
    if args.augment:
        augmented = []
        for ex in train_examples:
            augmented.append(InputExample(
                texts=[ex.texts[1], ex.texts[0]],
                label=ex.label
            ))
        train_examples.extend(augmented)
        print(f"  Augmented to {len(train_examples)} training examples")

    # Shuffle training data
    random.shuffle(train_examples)

    # Load model
    print(f"\nLoading base model: {args.model}...")
    model = SentenceTransformer(args.model, device=device)

    # Create data loader
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=args.batch_size)

    # Use CosineSimilarityLoss for regression-style training
    # This works well when you have explicit similarity labels
    train_loss = losses.CosineSimilarityLoss(model)

    # No in-training evaluator - we evaluate on held-out test set after training
    evaluator = None

    # Calculate training steps
    steps_per_epoch = len(train_dataloader)
    total_steps = steps_per_epoch * args.epochs

    print(f"\nTraining configuration:")
    print(f"  Training examples: {len(train_examples)}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Steps per epoch: {steps_per_epoch}")
    print(f"  Total epochs: {args.epochs}")
    print(f"  Total steps: {total_steps}")
    print(f"  Learning rate: {args.lr}")
    print(f"  Warmup steps: {args.warmup_steps}")
    print(f"  Device: {device}")

    # Train
    print(f"\nStarting training...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        evaluator=evaluator,
        evaluation_steps=steps_per_epoch,  # Evaluate once per epoch
        output_path=args.output,
        optimizer_params={"lr": args.lr},
        show_progress_bar=True,
    )

    print(f"\nTraining complete!")
    print(f"Fine-tuned model saved to: {args.output}")

    # Evaluate on held-out test set
    print("\n" + "=" * 60)
    print("EVALUATION ON HELD-OUT TEST SET")
    print("(These pairs were NEVER seen during training)")
    print("=" * 60)

    # Load the saved model for evaluation
    finetuned_model = SentenceTransformer(args.output)
    test_results = evaluate_on_test_set(finetuned_model, test_df)

    # Save test results
    test_results.to_csv(Path(args.output).parent / "test_results.csv", index=False)

    print(f"\nTo use the fine-tuned model:")
    print(f"  model = SentenceTransformer('{args.output}')")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fine-tune BGE-M3 embedding model for cross-lingual entity matching.

Uses the training pairs from data/training_pairs.json to create triplets
for contrastive learning.

Usage:
    python finetune_embeddings.py --epochs 3 --output models/finetuned-bge-m3-v2
"""

import argparse
import json
import random
from pathlib import Path

from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader


def load_training_data(filepath: Path) -> dict:
    """Load training pairs from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def create_triplets(data: dict) -> list[InputExample]:
    """
    Convert training pairs to triplets for contrastive learning.

    For each positive pair (anchor, positive), we sample a hard negative
    from the same category to create (anchor, positive, negative).
    """
    triplets = []

    for category, pairs in data["categories"].items():
        positives = pairs["positive_pairs"]
        negatives = pairs["hard_negatives"]

        # Create positive pairs
        for pair in positives:
            anchor = pair["source"]
            positive = pair["target"]

            # Sample a hard negative from the same category
            if negatives:
                neg_pair = random.choice(negatives)
                negative = neg_pair["target"]
            else:
                # If no hard negatives, use a random positive's target from different anchor
                other_positives = [p for p in positives if p["source"] != anchor]
                if other_positives:
                    negative = random.choice(other_positives)["target"]
                else:
                    continue

            triplets.append(InputExample(texts=[anchor, positive, negative]))

            # Also add reverse direction (target as anchor)
            triplets.append(InputExample(texts=[positive, anchor, negative]))

    return triplets


def create_pairs(data: dict) -> list[InputExample]:
    """
    Create positive and negative pairs for MultipleNegativesRankingLoss.
    This loss works better with fewer examples.
    """
    examples = []

    for category, pairs in data["categories"].items():
        positives = pairs["positive_pairs"]

        for pair in positives:
            # Positive pair
            examples.append(InputExample(texts=[pair["source"], pair["target"]]))
            # Reverse direction
            examples.append(InputExample(texts=[pair["target"], pair["source"]]))

    return examples


def main():
    parser = argparse.ArgumentParser(description="Fine-tune embedding model")
    parser.add_argument("--input", default="data/training_pairs.json", help="Training data JSON")
    parser.add_argument("--base-model", default="BAAI/bge-m3", help="Base model to fine-tune")
    parser.add_argument("--output", default="models/finetuned-bge-m3-v2", help="Output directory")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps")
    parser.add_argument("--loss", choices=["triplet", "mnrl"], default="mnrl",
                        help="Loss function: triplet or mnrl (MultipleNegativesRankingLoss)")
    args = parser.parse_args()

    # Paths
    input_path = Path(__file__).parent.parent / args.input
    output_path = Path(__file__).parent.parent / args.output

    # Load training data
    print(f"Loading training data from {input_path}...")
    data = load_training_data(input_path)

    print(f"  Categories: {list(data['categories'].keys())}")
    total_pos = sum(len(pairs["positive_pairs"]) for pairs in data["categories"].values())
    total_neg = sum(len(pairs["hard_negatives"]) for pairs in data["categories"].values())
    print(f"  Total positive pairs: {total_pos}")
    print(f"  Total hard negatives: {total_neg}")

    # Load base model
    print(f"\nLoading base model: {args.base_model}...")

    # Check if we have a previous fine-tuned version to start from
    prev_model_path = Path(__file__).parent.parent / "models" / "finetuned-bge-m3-premodern"
    if prev_model_path.exists():
        print(f"  Found previous fine-tuned model at {prev_model_path}")
        print(f"  Starting from previous fine-tuned weights...")
        model = SentenceTransformer(str(prev_model_path))
    else:
        print(f"  Starting from base model...")
        model = SentenceTransformer(args.base_model)

    # Create training examples
    print("\nCreating training examples...")
    if args.loss == "triplet":
        examples = create_triplets(data)
        train_loss = losses.TripletLoss(model)
        print(f"  Created {len(examples)} triplets for TripletLoss")
    else:
        examples = create_pairs(data)
        train_loss = losses.MultipleNegativesRankingLoss(model)
        print(f"  Created {len(examples)} pairs for MultipleNegativesRankingLoss")

    # Shuffle examples
    random.shuffle(examples)

    # Create data loader
    train_dataloader = DataLoader(examples, shuffle=True, batch_size=args.batch_size)

    # Calculate training steps
    total_steps = len(train_dataloader) * args.epochs
    print(f"\nTraining configuration:")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Total training steps: {total_steps}")
    print(f"  Warmup steps: {args.warmup_steps}")
    print(f"  Loss function: {args.loss}")

    # Train
    print(f"\nStarting training...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        output_path=str(output_path),
        show_progress_bar=True,
        save_best_model=True,
    )

    print(f"\nTraining complete!")
    print(f"Model saved to: {output_path}")

    # Quick evaluation on a few examples
    print("\n--- Quick Evaluation ---")
    test_pairs = [
        ("Galeno", "Galen"),
        ("Medicina", "Medicine"),
        ("água", "water"),
        ("febre", "fever"),
        ("Lisboa", "Lisbon"),
        ("Galeno", "Avicenna"),  # Should be dissimilar
        ("água", "wine"),  # Should be dissimilar
    ]

    model = SentenceTransformer(str(output_path))
    for source, target in test_pairs:
        emb1 = model.encode(source, normalize_embeddings=True)
        emb2 = model.encode(target, normalize_embeddings=True)
        sim = float(emb1 @ emb2)
        expected = "similar" if target not in ["Avicenna", "wine"] else "dissimilar"
        print(f"  {source:15} ↔ {target:15}: {sim:.3f} (expected: {expected})")


if __name__ == "__main__":
    main()

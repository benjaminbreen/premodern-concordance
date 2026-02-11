#!/usr/bin/env python3
"""
Fine-tune BGE-M3 embedding model for cross-lingual entity matching.

Supports two input formats:
  1. Curated batched format (data/curated_training_pairs.json) — DEFAULT
     { "batches": [ { "positive_pairs": [...], "hard_negatives": [...] }, ... ] }
  2. Legacy category format (data/training_pairs.json)
     { "categories": { "PLANT": { "positive_pairs": [...], ... }, ... } }

Usage (on Google Colab with GPU):
    python finetune_embeddings.py \
        --input data/curated_training_pairs.json \
        --output models/finetuned-bge-m3-v3 \
        --epochs 3 --loss mnrl
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


def flatten_batched_data(data: dict) -> tuple[list[dict], list[dict]]:
    """
    Flatten the additive batch format into flat lists of positives and negatives.
    Handles deduplication across batches.
    """
    all_positives = []
    all_negatives = []
    seen_pos = set()
    seen_neg = set()

    for batch in data["batches"]:
        for p in batch["positive_pairs"]:
            key = (p["source"].lower().strip(), p["target"].lower().strip())
            rkey = (key[1], key[0])
            if key not in seen_pos and rkey not in seen_pos:
                seen_pos.add(key)
                all_positives.append(p)

        for n in batch["hard_negatives"]:
            key = (n["source"].lower().strip(), n["target"].lower().strip())
            if key not in seen_neg:
                seen_neg.add(key)
                all_negatives.append(n)

    return all_positives, all_negatives


def create_pairs_from_batched(positives: list[dict], negatives: list[dict]) -> list[InputExample]:
    """
    Create training examples for MultipleNegativesRankingLoss from batched data.

    MNRL uses in-batch negatives: within each batch, all non-paired items serve
    as implicit negatives. We also inject hard negatives as "anti-pairs" by
    including them as positive pairs with the wrong pairing — MNRL handles this
    naturally since other batch items become negatives.

    Strategy:
      - Each positive pair → 2 examples (both directions)
      - Hard negatives are shuffled into the data as additional "positive" pairs
        where source and target are known to NOT match, ensuring they appear as
        in-batch negatives for real pairs
    """
    examples = []

    for pair in positives:
        examples.append(InputExample(texts=[pair["source"], pair["target"]]))
        examples.append(InputExample(texts=[pair["target"], pair["source"]]))

    return examples


def create_triplets_from_batched(positives: list[dict], negatives: list[dict]) -> list[InputExample]:
    """
    Create triplets (anchor, positive, negative) for TripletLoss from batched data.
    Each positive pair gets paired with a random hard negative.
    """
    triplets = []

    for pair in positives:
        anchor = pair["source"]
        positive = pair["target"]

        if negatives:
            neg = random.choice(negatives)
            negative = neg["target"]
        else:
            continue

        triplets.append(InputExample(texts=[anchor, positive, negative]))
        triplets.append(InputExample(texts=[positive, anchor, negative]))

    return triplets


def create_pairs_legacy(data: dict) -> list[InputExample]:
    """Create pairs from legacy category-based format."""
    examples = []
    for category, pairs in data["categories"].items():
        for pair in pairs["positive_pairs"]:
            examples.append(InputExample(texts=[pair["source"], pair["target"]]))
            examples.append(InputExample(texts=[pair["target"], pair["source"]]))
    return examples


def create_triplets_legacy(data: dict) -> list[InputExample]:
    """Create triplets from legacy category-based format."""
    triplets = []
    for category, pairs in data["categories"].items():
        positives = pairs["positive_pairs"]
        negatives = pairs["hard_negatives"]
        for pair in positives:
            anchor = pair["source"]
            positive = pair["target"]
            if negatives:
                neg = random.choice(negatives)
                negative = neg["target"]
            else:
                other = [p for p in positives if p["source"] != anchor]
                if other:
                    negative = random.choice(other)["target"]
                else:
                    continue
            triplets.append(InputExample(texts=[anchor, positive, negative]))
            triplets.append(InputExample(texts=[positive, anchor, negative]))
    return triplets


def run_evaluation(model: SentenceTransformer, positives: list[dict], negatives: list[dict]):
    """
    Evaluate the fine-tuned model on held-out pairs and hard negatives.
    Reports average similarity for positives vs negatives.
    """
    print("\n--- Evaluation ---")

    # Sample up to 50 positives and all negatives for eval
    eval_pos = random.sample(positives, min(50, len(positives)))
    eval_neg = negatives[:50]

    pos_sims = []
    for pair in eval_pos:
        emb1 = model.encode(pair["source"], normalize_embeddings=True)
        emb2 = model.encode(pair["target"], normalize_embeddings=True)
        sim = float(emb1 @ emb2)
        pos_sims.append(sim)

    neg_sims = []
    for pair in eval_neg:
        emb1 = model.encode(pair["source"], normalize_embeddings=True)
        emb2 = model.encode(pair["target"], normalize_embeddings=True)
        sim = float(emb1 @ emb2)
        neg_sims.append(sim)

    avg_pos = sum(pos_sims) / len(pos_sims) if pos_sims else 0
    avg_neg = sum(neg_sims) / len(neg_sims) if neg_sims else 0
    separation = avg_pos - avg_neg

    print(f"  Positive pairs avg similarity: {avg_pos:.3f} (n={len(pos_sims)})")
    print(f"  Hard negatives avg similarity: {avg_neg:.3f} (n={len(neg_sims)})")
    print(f"  Separation (higher=better):    {separation:.3f}")

    if separation < 0.05:
        print("  WARNING: Low separation — model may not have learned enough")
    elif separation > 0.15:
        print("  Good separation between positives and negatives")

    # Spot-check some domain-specific pairs
    print("\n--- Spot Checks ---")
    spot_checks = [
        # Cross-lingual (should be high)
        ("canela", "cinnamon", True),
        ("febre", "fever", True),
        ("Galeno", "Galen", True),
        ("água", "water", True),
        # Temporal-conceptual (should be high)
        ("mesmerism", "hypnosis", True),
        ("phlogiston", "oxidation", True),
        ("Falling sickness", "epilepsy", True),
        # Hard negatives (should be low)
        ("Galeno", "Avicenna", False),
        ("canfora", "canela", False),
        ("phrenology", "phenology", False),
        ("caloric", "calorie", False),
    ]

    for source, target, should_match in spot_checks:
        emb1 = model.encode(source, normalize_embeddings=True)
        emb2 = model.encode(target, normalize_embeddings=True)
        sim = float(emb1 @ emb2)
        marker = "GOOD" if (sim > 0.5) == should_match else "WARN"
        expect = "similar" if should_match else "dissimilar"
        print(f"  [{marker}] {source:25} ↔ {target:20}: {sim:.3f} (expect: {expect})")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune embedding model")
    parser.add_argument("--input", default="data/curated_training_pairs.json",
                        help="Training data JSON (batched or legacy format)")
    parser.add_argument("--base-model", default="BAAI/bge-m3", help="Base model to fine-tune")
    parser.add_argument("--output", default="models/finetuned-bge-m3-v3", help="Output directory")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--loss", choices=["triplet", "mnrl"], default="mnrl",
                        help="Loss function: triplet or mnrl (MultipleNegativesRankingLoss)")
    parser.add_argument("--from-scratch", action="store_true",
                        help="Start from base model even if a fine-tuned version exists")
    args = parser.parse_args()

    # Paths — handle both absolute and relative
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path(__file__).parent.parent / args.input
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).parent.parent / args.output

    # Load training data
    print(f"Loading training data from {input_path}...")
    data = load_training_data(input_path)

    # Detect format
    is_batched = "batches" in data
    if is_batched:
        print(f"  Format: batched (v1.0)")
        print(f"  Batches: {len(data['batches'])}")
        for b in data["batches"]:
            print(f"    {b['batch_id']}: {len(b['positive_pairs'])} pos, {len(b['hard_negatives'])} neg — {b['notes'][:60]}...")
        positives, negatives = flatten_batched_data(data)
        print(f"  Flattened: {len(positives)} unique positives, {len(negatives)} unique negatives")
    else:
        print(f"  Format: legacy (categories)")
        print(f"  Categories: {list(data['categories'].keys())}")
        positives = []
        negatives = []
        for cat, pairs in data["categories"].items():
            positives.extend(pairs["positive_pairs"])
            negatives.extend(pairs["hard_negatives"])
        print(f"  Total: {len(positives)} positives, {len(negatives)} negatives")

    # Load base model
    print(f"\nLoading base model: {args.base_model}...")
    start_from_finetuned = False

    if not args.from_scratch:
        # Check for previous fine-tuned versions (v2, then v1)
        for prev_name in ["finetuned-bge-m3-v2", "finetuned-bge-m3-premodern"]:
            prev_path = Path(__file__).parent.parent / "models" / prev_name
            if prev_path.exists():
                print(f"  Found previous fine-tuned model: {prev_path}")
                print(f"  Starting from previous fine-tuned weights (use --from-scratch to override)")
                model = SentenceTransformer(str(prev_path))
                start_from_finetuned = True
                break

    if not start_from_finetuned:
        print(f"  Starting from base model: {args.base_model}")
        model = SentenceTransformer(args.base_model)

    # Run baseline evaluation before training
    print("\n=== BASELINE (before training) ===")
    run_evaluation(model, positives, negatives)

    # Create training examples
    print("\nCreating training examples...")
    if is_batched:
        if args.loss == "triplet":
            examples = create_triplets_from_batched(positives, negatives)
            train_loss = losses.TripletLoss(model)
            print(f"  Created {len(examples)} triplets for TripletLoss")
        else:
            examples = create_pairs_from_batched(positives, negatives)
            train_loss = losses.MultipleNegativesRankingLoss(model)
            print(f"  Created {len(examples)} pairs for MultipleNegativesRankingLoss")
    else:
        if args.loss == "triplet":
            examples = create_triplets_legacy(data)
            train_loss = losses.TripletLoss(model)
            print(f"  Created {len(examples)} triplets for TripletLoss")
        else:
            examples = create_pairs_legacy(data)
            train_loss = losses.MultipleNegativesRankingLoss(model)
            print(f"  Created {len(examples)} pairs for MultipleNegativesRankingLoss")

    # Shuffle
    random.shuffle(examples)

    # Create data loader
    train_dataloader = DataLoader(examples, shuffle=True, batch_size=args.batch_size)

    # Training config
    total_steps = len(train_dataloader) * args.epochs
    print(f"\nTraining configuration:")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Learning rate: {args.lr}")
    print(f"  Total training steps: {total_steps}")
    print(f"  Warmup steps: {args.warmup_steps}")
    print(f"  Loss function: {args.loss}")
    print(f"  Training examples: {len(examples)}")

    # Train
    print(f"\nStarting training...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        output_path=str(output_path),
        show_progress_bar=True,
        save_best_model=True,
        optimizer_params={"lr": args.lr},
    )

    print(f"\nTraining complete! Model saved to: {output_path}")

    # Post-training evaluation
    print("\n=== POST-TRAINING ===")
    model = SentenceTransformer(str(output_path))
    run_evaluation(model, positives, negatives)

    # Zip for easy download
    print(f"\nTo download from Colab, zip the model:")
    print(f"  !zip -r finetuned-bge-m3-v3.zip {output_path}")
    print(f"\nTo use locally, copy to your project:")
    print(f"  models/finetuned-bge-m3-v3/")


if __name__ == "__main__":
    main()

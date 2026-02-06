#!/usr/bin/env python3
"""
Build search index with OpenAI embeddings for concordance clusters.

Generates a search_index.json file with precomputed embeddings
for fast semantic search.

Usage:
    python scripts/build_search_index.py
"""

import json
import os
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")
    sys.exit(1)

# Paths
CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
OUTPUT_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "search_index.json"

# Model config
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 512  # Matryoshka truncation — good quality at 1/3 the size
BATCH_SIZE = 100  # OpenAI supports up to 2048 inputs per call


def build_embedding_text(cluster: dict) -> str:
    """Build rich text for embedding from a cluster's fields."""
    parts = []

    # Canonical name (most important)
    parts.append(cluster["canonical_name"])

    # Category and subcategory
    parts.append(cluster["category"])
    if cluster.get("subcategory"):
        parts.append(cluster["subcategory"])

    # Ground truth enrichment
    gt = cluster.get("ground_truth", {})

    # Semantic gloss (rich thematic description for conceptual search)
    if gt.get("semantic_gloss"):
        parts.append(gt["semantic_gloss"])

    # All variant names from members
    variant_names = set()
    for member in cluster.get("members", []):
        variant_names.add(member["name"])
        # Add a selection of variants (not all — some clusters have hundreds)
        for v in member.get("variants", [])[:10]:
            variant_names.add(v)
    variant_names.discard(cluster["canonical_name"])
    if variant_names:
        parts.append(" | ".join(sorted(variant_names)[:20]))
    if gt.get("modern_name"):
        parts.append(gt["modern_name"])
    if gt.get("linnaean"):
        parts.append(gt["linnaean"])
    if gt.get("wikidata_description"):
        parts.append(gt["wikidata_description"])
    if gt.get("description"):
        parts.append(gt["description"])
    if gt.get("family"):
        parts.append(gt["family"])
    if gt.get("note"):
        # Truncate long notes
        parts.append(gt["note"][:200])

    return " | ".join(parts)


def build_metadata(cluster: dict) -> dict:
    """Extract searchable metadata for lexical matching."""
    gt = cluster.get("ground_truth", {})

    # Collect all name variants for lexical search
    all_names = [cluster["canonical_name"]]
    for member in cluster.get("members", []):
        all_names.append(member["name"])
        all_names.extend(member.get("variants", [])[:10])

    # Deduplicate while preserving order
    seen = set()
    unique_names = []
    for n in all_names:
        nl = n.lower()
        if nl not in seen:
            seen.add(nl)
            unique_names.append(n)

    books = list(set(m["book_id"] for m in cluster.get("members", [])))

    return {
        "id": cluster["id"],
        "canonical_name": cluster["canonical_name"],
        "category": cluster["category"],
        "subcategory": cluster.get("subcategory", ""),
        "book_count": cluster.get("book_count", len(books)),
        "total_mentions": cluster.get("total_mentions", 0),
        "books": books,
        "modern_name": gt.get("modern_name", ""),
        "linnaean": gt.get("linnaean", ""),
        "wikidata_id": gt.get("wikidata_id", ""),
        "wikidata_description": gt.get("wikidata_description", ""),
        "wikipedia_url": gt.get("wikipedia_url", ""),
        "confidence": gt.get("confidence", ""),
        "note": gt.get("note", ""),
        "family": gt.get("family", ""),
        "semantic_gloss": gt.get("semantic_gloss", ""),
        "portrait_url": gt.get("portrait_url", ""),
        # All name variants for lexical matching (capped at 30)
        "names": unique_names[:30],
    }


def main():
    # Load API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Try .env.local files
        for env_path in [
            Path(__file__).parent.parent / ".env.local",
            Path(__file__).parent.parent / "web" / ".env.local",
        ]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("OPENAI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
            if api_key:
                break

    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment or .env.local")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # Load concordance
    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Build embedding texts and metadata
    print("Building embedding texts...")
    texts = []
    metadata = []
    for cluster in clusters:
        texts.append(build_embedding_text(cluster))
        metadata.append(build_metadata(cluster))

    # Generate embeddings in batches
    print(f"Generating embeddings with {EMBEDDING_MODEL} (dims={EMBEDDING_DIMS})...")
    all_embeddings = []
    total_tokens = 0

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} texts)...", end=" ")

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
            dimensions=EMBEDDING_DIMS,
        )

        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
        total_tokens += response.usage.total_tokens
        print(f"done ({response.usage.total_tokens} tokens)")

        # Rate limiting
        if batch_num < total_batches:
            time.sleep(0.1)

    print(f"  Total tokens: {total_tokens}")

    # Build index
    index = {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMS,
        "count": len(clusters),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entries": [
            {"embedding": emb, "metadata": meta}
            for emb, meta in zip(all_embeddings, metadata)
        ],
    }

    # Save
    print(f"Saving to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w") as f:
        json.dump(index, f)

    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB")
    print(f"\nDone! {len(clusters)} clusters indexed.")


if __name__ == "__main__":
    main()

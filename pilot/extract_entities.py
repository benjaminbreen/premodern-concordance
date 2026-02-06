#!/usr/bin/env python3
"""
Entity extraction pipeline for early modern texts.

Workflow:
1. Chunk text into manageable pieces
2. Extract entities from each chunk via local LLM (ollama)
3. Aggregate raw extractions
4. Deduplicate using fine-tuned embedding model (cluster similar names)
5. Output ranked CSV of canonical entities with variants

Usage:
    python pilot/extract_entities.py --input books/polyanthea_medicinal.txt
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering


# --- Configuration ---

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.1:8b"
CHUNK_SIZE = 3000  # characters per chunk
CHUNK_OVERLAP = 200  # overlap to avoid splitting entities
EMBEDDING_MODEL = "models/finetuned-bge-m3-premodern"
SIMILARITY_THRESHOLD = 0.97  # High threshold - only very close variants (lower = more aggressive merging)

EXTRACTION_PROMPT_TEMPLATE = """You are an expert in early modern European medicine, natural philosophy, and pharmacy.
You are reading a passage from an 18th-century Portuguese medical text.

Extract ALL named entities from this passage. Include:
- PERSONS: physicians, natural philosophers, ancient authorities, contemporary authors
- SUBSTANCES: drugs, plants, minerals, animal products, preparations, chemicals
- CONCEPTS: diseases, medical theories, procedures, anatomical terms

For each entity, provide:
- name: exactly as it appears in the text (preserve original spelling)
- category: PERSON, SUBSTANCE, or CONCEPT
- context: one brief phrase explaining what it is or how it's used (max 10 words)

Return ONLY a JSON array. No other text. Example format:
[
  {{"name": "Galeno", "category": "PERSON", "context": "ancient medical authority cited"}},
  {{"name": "ruybarbo", "category": "SUBSTANCE", "context": "purgative drug"}},
  {{"name": "Hydropesia", "category": "CONCEPT", "context": "disease involving fluid accumulation"}}
]

If no entities are found, return an empty array: []

PASSAGE:
{text}

JSON ARRAY:"""


# --- Text Chunking ---

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks, trying to break at paragraph boundaries.
    """
    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to break at paragraph boundary
        break_point = text.rfind('\n\n', start + chunk_size // 2, end)
        if break_point == -1:
            # Try sentence boundary
            break_point = text.rfind('. ', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = end
        else:
            break_point += 2  # Include the delimiter

        chunks.append(text[start:break_point])
        start = break_point - overlap

    return chunks


# --- LLM Extraction ---

def extract_from_chunk(chunk: str, model: str = DEFAULT_MODEL) -> list[dict]:
    """
    Send a chunk to ollama and extract entities.
    """
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(text=chunk)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temp for consistent extraction
                    "num_predict": 2000,
                }
            },
            timeout=120
        )
        response.raise_for_status()

        result = response.json()
        text = result.get("response", "")

        # Try to parse JSON from response
        # Sometimes model adds extra text, so find the array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            entities = json.loads(match.group())
            return entities
        return []

    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"  Warning: extraction failed: {e}", file=sys.stderr)
        return []


def extract_all_entities(chunks: list[str], model: str = DEFAULT_MODEL) -> list[dict]:
    """
    Extract entities from all chunks.
    """
    all_entities = []

    for i, chunk in enumerate(chunks):
        print(f"  Processing chunk {i+1}/{len(chunks)}...", end=" ", flush=True)
        entities = extract_from_chunk(chunk, model)
        print(f"found {len(entities)} entities")

        # Add chunk index for tracking
        for e in entities:
            e["chunk"] = i

        all_entities.extend(entities)

    return all_entities


# --- Embedding-based Deduplication ---

def deduplicate_entities(entities: list[dict], model_path: str = EMBEDDING_MODEL,
                         threshold: float = SIMILARITY_THRESHOLD) -> pd.DataFrame:
    """
    Cluster entity names using embeddings to find variants of the same entity.
    Only clusters within the same category to avoid merging persons with substances.
    Returns DataFrame with canonical names and their variants.
    """
    if not entities:
        return pd.DataFrame()

    print(f"\nDeduplicating {len(entities)} raw extractions...")

    # Group by raw name first (exact matches)
    name_to_entities = defaultdict(list)
    for e in entities:
        name = e.get("name", "").strip()
        if name:
            name_to_entities[name].append(e)

    # Determine primary category for each name (majority vote)
    name_to_category = {}
    for name, ents in name_to_entities.items():
        categories = [e.get("category", "UNKNOWN") for e in ents]
        name_to_category[name] = max(set(categories), key=categories.count)

    unique_names = list(name_to_entities.keys())
    print(f"  {len(unique_names)} unique surface forms")

    if len(unique_names) < 2:
        return _entities_to_dataframe(name_to_entities, {n: 0 for n in unique_names})

    # Load embedding model
    print(f"  Loading embedding model...")
    model = SentenceTransformer(model_path)

    print(f"  Encoding {len(unique_names)} names...")
    embeddings = model.encode(unique_names, show_progress_bar=True)

    # Build name -> embedding mapping
    name_to_embedding = {name: emb for name, emb in zip(unique_names, embeddings)}

    # Cluster WITHIN each category separately
    print(f"  Clustering within categories...")
    categories = set(name_to_category.values())

    global_cluster_id = 0
    name_to_cluster = {}

    for category in sorted(categories):
        cat_names = [n for n in unique_names if name_to_category[n] == category]

        if len(cat_names) < 2:
            for name in cat_names:
                name_to_cluster[name] = global_cluster_id
                global_cluster_id += 1
            continue

        # Get embeddings for this category
        cat_embeddings = np.array([name_to_embedding[n] for n in cat_names])

        # Compute cosine similarity matrix
        norms = np.linalg.norm(cat_embeddings, axis=1, keepdims=True)
        normalized = cat_embeddings / norms
        similarity_matrix = np.dot(normalized, normalized.T)
        distance_matrix = 1 - similarity_matrix

        # Cluster
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - threshold,
            metric="precomputed",
            linkage="average"
        )
        labels = clustering.fit_predict(distance_matrix)

        # Assign global cluster IDs
        for name, label in zip(cat_names, labels):
            name_to_cluster[name] = global_cluster_id + label

        global_cluster_id += len(set(labels))

    n_clusters = len(set(name_to_cluster.values()))
    print(f"  Found {n_clusters} distinct entities from {len(unique_names)} surface forms")

    return _entities_to_dataframe(name_to_entities, name_to_cluster)


def _entities_to_dataframe(name_to_entities: dict, name_to_cluster: dict) -> pd.DataFrame:
    """
    Convert clustered entities to a DataFrame with canonical names.
    """
    # Group by cluster
    cluster_to_names = defaultdict(list)
    for name, cluster in name_to_cluster.items():
        cluster_to_names[cluster].append(name)

    rows = []
    for cluster_id, names in cluster_to_names.items():
        # Collect all entity instances for this cluster
        all_instances = []
        for name in names:
            all_instances.extend(name_to_entities[name])

        # Pick canonical name (most frequent, or longest if tie)
        name_counts = defaultdict(int)
        for name in names:
            name_counts[name] = len(name_to_entities[name])
        canonical = max(names, key=lambda n: (name_counts[n], len(n)))

        # Collect variants (excluding canonical)
        variants = [n for n in names if n != canonical]

        # Determine category (majority vote)
        categories = [e.get("category", "UNKNOWN") for e in all_instances]
        category = max(set(categories), key=categories.count) if categories else "UNKNOWN"

        # Collect contexts
        contexts = list(set(e.get("context", "") for e in all_instances if e.get("context")))

        # Count occurrences (total mentions across all chunks)
        total_count = len(all_instances)

        # Unique chunks where this entity appears
        chunks = sorted(set(e.get("chunk", 0) for e in all_instances))

        rows.append({
            "canonical_name": canonical,
            "category": category,
            "variants": "; ".join(variants) if variants else "",
            "count": total_count,
            "chunk_count": len(chunks),
            "contexts": " | ".join(contexts[:3]),  # Top 3 contexts
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["count", "chunk_count"], ascending=False)
    return df


# --- Main Pipeline ---

def run_pipeline(input_path: str, output_path: str, model: str = DEFAULT_MODEL,
                 embedding_model: str = EMBEDDING_MODEL, threshold: float = SIMILARITY_THRESHOLD):
    """
    Run the full extraction pipeline.
    """
    print(f"=" * 60)
    print(f"Entity Extraction Pipeline")
    print(f"=" * 60)
    print(f"Input: {input_path}")
    print(f"LLM: {model}")
    print(f"Embedding model: {embedding_model}")
    print(f"Similarity threshold: {threshold}")
    print()

    # Load text
    print("Loading text...")
    text = Path(input_path).read_text(encoding="utf-8", errors="ignore")
    print(f"  {len(text):,} characters")

    # Chunk
    print("\nChunking text...")
    chunks = chunk_text(text)
    print(f"  {len(chunks)} chunks")

    # Extract
    print("\nExtracting entities...")
    raw_entities = extract_all_entities(chunks, model)
    print(f"\n  Total raw extractions: {len(raw_entities)}")

    # Deduplicate
    df = deduplicate_entities(raw_entities, embedding_model, threshold)

    # Save
    print(f"\nSaving to {output_path}...")
    df.to_csv(output_path, index=False)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"Total distinct entities: {len(df)}")
    print(f"\nBy category:")
    print(df["category"].value_counts().to_string())
    print(f"\nTop 20 entities by frequency:")
    print(df.head(20)[["canonical_name", "category", "count", "variants"]].to_string())

    return df


def main():
    parser = argparse.ArgumentParser(description="Extract entities from early modern texts")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output", default=None, help="Output CSV (default: input_entities.csv)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--embedding-model", default=EMBEDDING_MODEL, help="Embedding model for deduplication")
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD, help="Similarity threshold for clustering")
    args = parser.parse_args()

    if args.output is None:
        input_stem = Path(args.input).stem
        args.output = f"pilot/{input_stem}_entities.csv"

    run_pipeline(args.input, args.output, args.model, args.embedding_model, args.threshold)


if __name__ == "__main__":
    main()

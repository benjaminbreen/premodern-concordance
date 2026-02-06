#!/usr/bin/env python3
"""
Entity extraction with multiple provider support for comparison testing.

Providers:
- ollama: Local models (llama3.1, qwen, etc.)
- openai: GPT-5 Nano, etc.
- google: Gemini 2.5 Flash Lite, etc.

Usage:
    # Test all three on same sample
    python extract_entities_multi.py --input sample.txt --provider ollama --model qwen2.5:1.5b
    python extract_entities_multi.py --input sample.txt --provider google --model gemini-2.5-flash-lite
    python extract_entities_multi.py --input sample.txt --provider openai --model gpt-5-nano

Requires:
    - GOOGLE_API_KEY env var for Google
    - OPENAI_API_KEY env var for OpenAI
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering


# --- Configuration ---

CHUNK_SIZE = 3000
CHUNK_OVERLAP = 200
EMBEDDING_MODEL = "models/finetuned-bge-m3-premodern"
SIMILARITY_THRESHOLD = 0.97

EXTRACTION_PROMPT = """You are an expert in early modern European medicine, natural philosophy, and pharmacy.
You are reading a passage from an 18th-century Portuguese medical text.

Extract ALL named entities from this passage. Include:
- PERSONS: physicians, natural philosophers, ancient authorities, contemporary authors
- SUBSTANCES: drugs, plants, minerals, animal products, preparations, chemicals
- CONCEPTS: diseases, medical theories, procedures, anatomical terms

For each entity, provide:
- name: exactly as it appears in the text (preserve original spelling)
- category: PERSON, SUBSTANCE, or CONCEPT
- context: one brief phrase explaining what it is or how it's used (max 10 words)

Return ONLY a JSON array. No other text. Example:
[
  {"name": "Galeno", "category": "PERSON", "context": "ancient medical authority cited"},
  {"name": "ruybarbo", "category": "SUBSTANCE", "context": "purgative drug"}
]

If no entities found, return: []

PASSAGE:
"""


# --- Provider Implementations ---

class OllamaProvider:
    def __init__(self, model="llama3.1:8b"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    def extract(self, text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT + text + "\n\nJSON ARRAY:"
        try:
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 2000}
                },
                timeout=120
            )
            response.raise_for_status()
            result = response.json().get("response", "")
            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"  Warning: ollama extraction failed: {e}", file=sys.stderr)
        return []


class GoogleProvider:
    def __init__(self, model="gemini-2.5-flash-lite"):
        self.model = model
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable required")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def extract(self, text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT + text + "\n\nJSON ARRAY:"
        try:
            response = requests.post(
                f"{self.url}?key={self.api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2000}
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            text_out = result["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r'\[.*\]', text_out, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"  Warning: google extraction failed: {e}", file=sys.stderr)
        return []


class OpenAIProvider:
    def __init__(self, model="gpt-5-nano"):
        self.model = model
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
        self.url = "https://api.openai.com/v1/chat/completions"

    def extract(self, text: str) -> list[dict]:
        prompt = EXTRACTION_PROMPT + text
        try:
            response = requests.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You extract entities from historical texts. Return only JSON arrays."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2000
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            text_out = result["choices"][0]["message"]["content"]
            match = re.search(r'\[.*\]', text_out, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"  Warning: openai extraction failed: {e}", file=sys.stderr)
        return []


def get_provider(provider_name: str, model: str):
    providers = {
        "ollama": OllamaProvider,
        "google": GoogleProvider,
        "openai": OpenAIProvider,
    }
    if provider_name not in providers:
        raise ValueError(f"Unknown provider: {provider_name}. Choose from: {list(providers.keys())}")
    return providers[provider_name](model)


# --- Text Processing ---

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r'\n{3,}', '\n\n', text)
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        break_point = text.rfind('\n\n', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = text.rfind('. ', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = end
        else:
            break_point += 2
        chunks.append(text[start:break_point])
        start = break_point - overlap
    return chunks


def extract_all(chunks: list[str], provider) -> tuple[list[dict], dict]:
    """Extract entities and return timing stats."""
    all_entities = []
    total_time = 0

    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}/{len(chunks)}...", end=" ", flush=True)
        start = time.time()
        entities = provider.extract(chunk)
        elapsed = time.time() - start
        total_time += elapsed
        print(f"{len(entities)} entities ({elapsed:.1f}s)")

        for e in entities:
            e["chunk"] = i
        all_entities.extend(entities)

    stats = {
        "total_time": total_time,
        "avg_time_per_chunk": total_time / len(chunks) if chunks else 0,
        "total_entities": len(all_entities),
    }
    return all_entities, stats


# --- Deduplication (same as before) ---

def deduplicate_entities(entities: list[dict], model_path: str = EMBEDDING_MODEL,
                         threshold: float = SIMILARITY_THRESHOLD) -> pd.DataFrame:
    if not entities:
        return pd.DataFrame()

    print(f"\nDeduplicating {len(entities)} raw extractions...")

    name_to_entities = defaultdict(list)
    for e in entities:
        name = e.get("name", "").strip()
        if name:
            name_to_entities[name].append(e)

    name_to_category = {}
    for name, ents in name_to_entities.items():
        categories = [e.get("category", "UNKNOWN") for e in ents]
        name_to_category[name] = max(set(categories), key=categories.count)

    unique_names = list(name_to_entities.keys())
    print(f"  {len(unique_names)} unique surface forms")

    if len(unique_names) < 2:
        return _entities_to_dataframe(name_to_entities, {n: 0 for n in unique_names})

    print(f"  Loading embedding model...")
    model = SentenceTransformer(model_path)

    print(f"  Encoding names...")
    embeddings = model.encode(unique_names, show_progress_bar=False)
    name_to_embedding = {name: emb for name, emb in zip(unique_names, embeddings)}

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

        cat_embeddings = np.array([name_to_embedding[n] for n in cat_names])
        norms = np.linalg.norm(cat_embeddings, axis=1, keepdims=True)
        normalized = cat_embeddings / norms
        similarity_matrix = np.dot(normalized, normalized.T)
        distance_matrix = 1 - similarity_matrix

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - threshold,
            metric="precomputed",
            linkage="average"
        )
        labels = clustering.fit_predict(distance_matrix)

        for name, label in zip(cat_names, labels):
            name_to_cluster[name] = global_cluster_id + label
        global_cluster_id += len(set(labels))

    n_clusters = len(set(name_to_cluster.values()))
    print(f"  Found {n_clusters} distinct entities")

    return _entities_to_dataframe(name_to_entities, name_to_cluster)


def _entities_to_dataframe(name_to_entities: dict, name_to_cluster: dict) -> pd.DataFrame:
    cluster_to_names = defaultdict(list)
    for name, cluster in name_to_cluster.items():
        cluster_to_names[cluster].append(name)

    rows = []
    for cluster_id, names in cluster_to_names.items():
        all_instances = []
        for name in names:
            all_instances.extend(name_to_entities[name])

        name_counts = defaultdict(int)
        for name in names:
            name_counts[name] = len(name_to_entities[name])
        canonical = max(names, key=lambda n: (name_counts[n], len(n)))
        variants = [n for n in names if n != canonical]

        categories = [e.get("category", "UNKNOWN") for e in all_instances]
        category = max(set(categories), key=categories.count) if categories else "UNKNOWN"

        contexts = list(set(e.get("context", "") for e in all_instances if e.get("context")))
        total_count = len(all_instances)
        chunks = sorted(set(e.get("chunk", 0) for e in all_instances))

        rows.append({
            "canonical_name": canonical,
            "category": category,
            "variants": "; ".join(variants) if variants else "",
            "count": total_count,
            "chunk_count": len(chunks),
            "contexts": " | ".join(contexts[:3]),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["count", "chunk_count"], ascending=False)
    return df


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Extract entities with multiple providers")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output", default=None, help="Output CSV")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "google", "openai"])
    parser.add_argument("--model", default=None, help="Model name (provider-specific)")
    parser.add_argument("--embedding-model", default=EMBEDDING_MODEL)
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument("--max-chunks", type=int, default=None, help="Limit chunks for testing")
    args = parser.parse_args()

    # Default models per provider
    default_models = {
        "ollama": "llama3.1:8b",
        "google": "gemini-2.5-flash-lite",
        "openai": "gpt-5-nano",
    }
    model = args.model or default_models[args.provider]

    if args.output is None:
        input_stem = Path(args.input).stem
        args.output = f"pilot/{input_stem}_{args.provider}_{model.replace(':', '-')}_entities.csv"

    print(f"=" * 60)
    print(f"Entity Extraction - Provider Comparison")
    print(f"=" * 60)
    print(f"Provider: {args.provider}")
    print(f"Model: {model}")
    print(f"Input: {args.input}")
    print()

    # Load and chunk
    text = Path(args.input).read_text(encoding="utf-8", errors="ignore")
    chunks = chunk_text(text)
    if args.max_chunks:
        chunks = chunks[:args.max_chunks]
    print(f"Processing {len(chunks)} chunks\n")

    # Extract
    provider = get_provider(args.provider, model)
    raw_entities, stats = extract_all(chunks, provider)

    print(f"\n--- Extraction Stats ---")
    print(f"Total time: {stats['total_time']:.1f}s")
    print(f"Avg per chunk: {stats['avg_time_per_chunk']:.2f}s")
    print(f"Raw entities: {stats['total_entities']}")

    # Deduplicate
    df = deduplicate_entities(raw_entities, args.embedding_model, args.threshold)
    df.to_csv(args.output, index=False)

    print(f"\n--- Results ---")
    print(f"Distinct entities: {len(df)}")
    print(f"Output: {args.output}")
    print(f"\nTop 15:")
    print(df.head(15)[["canonical_name", "category", "count"]].to_string())


if __name__ == "__main__":
    main()

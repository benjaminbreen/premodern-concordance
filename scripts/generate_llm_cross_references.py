#!/usr/bin/env python3
"""
Generate cross-references between concordance clusters using Gemini.

For each cluster, asks Gemini to identify synonyms, closely related entities,
and contested identities from the list of other same-category clusters.

Results are stored in data/llm_cross_references.json keyed by STABLE identifiers
(wikidata_id or modern_name+category), so they persist across concordance rebuilds.
After a rebuild, just re-run integrate_cross_references.py to re-map to new IDs.
Only genuinely new clusters (not in the cache) need LLM calls.

Usage:
    python3 scripts/generate_llm_cross_references.py
    python3 scripts/generate_llm_cross_references.py --dry-run
    python3 scripts/generate_llm_cross_references.py --category PERSON
    python3 scripts/generate_llm_cross_references.py --limit 50
"""

import argparse
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).parent.parent / ".env.local")

BASE_DIR = Path(__file__).resolve().parent.parent
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"
OUTPUT_PATH = BASE_DIR / "data" / "llm_cross_references.json"

CHECKPOINT_EVERY = 50

# Prompt template
SYSTEM_PROMPT = """You are a historian of science and medicine analyzing a concordance of premodern texts (1500s-1890s).
Given an entity and a list of other entities from the same category, identify semantic relationships.

CRITICAL: Be EXTREMELY selective. Aim for 0-5 total entries across all categories. Most entities will have 0-3 relationships. NEVER list more than 8 total.

Categories:
- SYNONYM: Same referent, different name (e.g., "Society of Jesus" = "Jesuits", "quicksilver" = "mercury", "phthisis" = "consumption"). Must truly refer to the SAME thing.
- CROSS_LINGUISTIC: Same entity in different languages (e.g., "canela" (Spanish) = "cinnamon" (English), "acqua" (Italian) = "water" (English)). Must be a direct translation, not just a related term.
- CONTESTED: Historical sources ACTIVELY DEBATED whether these are the same thing (e.g., "cassia" vs "cinnamon", "silphium" vs "asafoetida"). This is rare — only for genuine identity disputes in historical texts.
- RELATED: A SPECIFIC, notable relationship — NOT generic category membership. Good: "Galen" → "Hippocrates" (intellectual tradition), "nutmeg" → "mace" (same fruit). BAD: listing every insect species as "related" to "Insects", listing every person from Rome as "related" to "Rome".

Do NOT list:
- Things that merely belong to the same category (NOT every insect is "related" to another insect, NOT every mineral is "related" to "Sand")
- Hypernym/hyponym relationships (do NOT list specific species under a broad genus or class name)
- Entities that just appear in the same text or book
- Generic associations (disease → medicine, plant → botany)
- Broad/vague connections. If the reason is "X is a type of Y" or "X and Y are both Z", do NOT list it.

Return ONLY valid JSON, no markdown. Format:
{"synonyms": [{"name": "...", "reason": "..."}], "cross_linguistic": [{"name": "...", "reason": "..."}], "contested": [{"name": "...", "reason": "..."}], "related": [{"name": "...", "reason": "..."}]}

If no relationships exist for a category, use an empty array. It is perfectly fine to return all empty arrays."""


def normalize_name(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_key(cluster: dict) -> str:
    """Generate a stable key for a cluster that survives concordance rebuilds."""
    gt = cluster.get("ground_truth") or {}
    wikidata_id = (gt.get("wikidata_id") or "").strip()
    if wikidata_id:
        return f"wd:{wikidata_id}"
    modern = gt.get("modern_name", "")
    if modern:
        return f"mn:{normalize_name(modern)}:{cluster['category']}"
    return f"cn:{normalize_name(cluster['canonical_name'])}:{cluster['category']}"


MAX_CANDIDATES = 250  # Cap candidate list to avoid overwhelming prompts


def get_cluster_books(cluster: dict) -> set[str]:
    """Get set of book_ids for a cluster's members."""
    return {m.get("book_id", "").split("_")[0] for m in cluster.get("members", [])} - {""}


def build_candidate_list(clusters: list[dict], category: str,
                         exclude_id: int, source_books: set[str] | None = None) -> str:
    """Build a concise candidate list for the prompt.

    If source_books is provided and there are too many candidates,
    prioritize entities that share books with the source.
    """
    all_candidates = []
    shared_book_candidates = []
    for c in clusters:
        if c["category"] != category or c["id"] == exclude_id:
            continue
        gt = c.get("ground_truth") or {}
        modern = gt.get("modern_name", "")
        canonical = c["canonical_name"]
        name = modern if modern else canonical
        if modern and canonical != modern and normalize_name(canonical) != normalize_name(modern):
            name = f"{modern} (aka {canonical})"
        all_candidates.append(name)
        if source_books and get_cluster_books(c) & source_books:
            shared_book_candidates.append(name)

    # Use shared-book candidates if we have too many, but always include all
    # if under the cap
    if len(all_candidates) > MAX_CANDIDATES and shared_book_candidates:
        candidates = shared_book_candidates
    else:
        candidates = all_candidates

    # Final cap
    candidates = sorted(set(candidates))[:MAX_CANDIDATES]
    return "\n".join(f"- {c}" for c in candidates)


def build_prompt(cluster: dict, candidate_list: str) -> str:
    """Build the prompt for a single cluster."""
    gt = cluster.get("ground_truth") or {}
    modern = gt.get("modern_name", "")
    canonical = cluster["canonical_name"]
    category = cluster["category"]
    wiki = (gt.get("wikipedia_extract") or "")[:300]

    entity_desc = f"Entity: {modern or canonical}"
    if modern and canonical != modern:
        entity_desc += f" (historical name: {canonical})"
    entity_desc += f"\nCategory: {category}"
    if wiki:
        entity_desc += f"\nDescription: {wiki}"

    # For large categories, include a note about selectivity
    return f"""{entity_desc}

From the following list of other {category} entities in the concordance, identify any that are SYNONYMS, CROSS-LINGUISTIC equivalents, CONTESTED identities, or strongly RELATED to this entity.

Candidates:
{candidate_list}"""


def call_gemini(prompt: str, client, model: str, retries: int = 2) -> dict | None:
    """Call Gemini and parse JSON response. Retries on JSON parse errors."""
    for attempt in range(retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.1,
                    "max_output_tokens": 2048,
                },
            )
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"    JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"    Gemini error: {e}")
            return None


def load_cache() -> dict:
    """Load existing LLM cross-reference cache."""
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    return {"version": 2, "entries": {}}


def save_cache(cache: dict):
    """Save cache to disk."""
    with open(OUTPUT_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Generate cross-references between concordance clusters using Gemini")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompts without calling Gemini")
    parser.add_argument("--category", type=str, default=None,
                        help="Only process clusters in this category (e.g., PERSON)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max clusters to process (0 = all)")
    parser.add_argument("--model", default="gemini-2.5-flash-lite",
                        help="Gemini model")
    parser.add_argument("--force", action="store_true",
                        help="Re-generate even for cached clusters")
    args = parser.parse_args()

    # Load concordance
    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Load cache
    cache = load_cache()
    entries = cache["entries"]
    print(f"  {len(entries)} cached entries")

    # Filter clusters
    to_process = []
    for c in clusters:
        if args.category and c["category"] != args.category:
            continue
        key = stable_key(c)
        if key in entries and not args.force:
            continue
        # Skip clusters without ground_truth (can't identify them reliably)
        gt = c.get("ground_truth") or {}
        if not gt.get("modern_name") and not gt.get("wikidata_id"):
            continue
        to_process.append(c)

    if args.limit > 0:
        to_process = to_process[:args.limit]

    print(f"  {len(to_process)} clusters to process"
          f" (skipping {len(clusters) - len(to_process)} cached/filtered)")

    if not to_process:
        print("Nothing to do.")
        return

    # Report category sizes
    from collections import Counter as _Counter
    cat_counts = _Counter(c["category"] for c in clusters)
    print("\nCategory sizes (total clusters):")
    for cat in sorted(set(c["category"] for c in to_process)):
        print(f"  {cat}: {cat_counts[cat]} clusters (max {MAX_CANDIDATES} candidates per prompt)")

    if args.dry_run:
        # Show sample prompts
        for c in to_process[:3]:
            cat = c["category"]
            source_books = get_cluster_books(c)
            candidate_list = build_candidate_list(clusters, cat, c["id"], source_books)
            prompt = build_prompt(c, candidate_list)
            n_cands = candidate_list.count("\n") + 1
            print(f"\n{'='*60}")
            print(f"Cluster #{c['id']} {c['canonical_name']} ({cat}) — {n_cands} candidates")
            print(f"{'='*60}")
            print(prompt[:500])
            if len(prompt) > 500:
                print(f"... ({len(prompt)} chars total)")
        print(f"\n[DRY RUN] Would process {len(to_process)} clusters")
        return

    # Set up Gemini client
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: set GEMINI_API_KEY or GOOGLE_API_KEY in .env.local")
        return
    client = genai.Client(api_key=api_key)

    # Process clusters
    print(f"\nProcessing {len(to_process)} clusters with {args.model}...")
    processed = 0
    errors = 0
    total_refs = 0

    for i, c in enumerate(to_process):
        cat = c["category"]
        gt = c.get("ground_truth") or {}
        modern = gt.get("modern_name", c["canonical_name"])
        key = stable_key(c)

        # Build per-cluster candidate list (capped, prioritizes shared books)
        source_books = get_cluster_books(c)
        candidate_list = build_candidate_list(clusters, cat, c["id"], source_books)
        prompt = build_prompt(c, candidate_list)

        print(f"  [{i+1}/{len(to_process)}] {modern} ({cat})...", end=" ", flush=True)

        result = call_gemini(prompt, client, args.model)
        if result is None:
            errors += 1
            print("ERROR")
            time.sleep(2)
            continue

        # Cap total refs at 8 (prioritize synonyms/cross_linguistic > contested > related)
        MAX_REFS = 8
        synonyms = result.get("synonyms", [])[:MAX_REFS]
        cross_ling = result.get("cross_linguistic", [])[:MAX_REFS]
        contested = result.get("contested", [])[:MAX_REFS]
        related = result.get("related", [])[:MAX_REFS]
        n_total = len(synonyms) + len(cross_ling) + len(contested) + len(related)
        if n_total > MAX_REFS:
            # Trim related first, then contested
            budget = MAX_REFS - len(synonyms) - len(cross_ling)
            contested = contested[:max(0, budget)]
            budget -= len(contested)
            related = related[:max(0, budget)]

        n_refs = len(synonyms) + len(cross_ling) + len(contested) + len(related)
        total_refs += n_refs
        print(f"{n_refs} refs")

        # Store with stable key
        entries[key] = {
            "modern_name": modern,
            "canonical_name": c["canonical_name"],
            "category": cat,
            "wikidata_id": (gt.get("wikidata_id") or "").strip(),
            "synonyms": synonyms,
            "cross_linguistic": cross_ling,
            "contested": contested,
            "related": related,
        }
        processed += 1

        # Checkpoint save
        if processed % CHECKPOINT_EVERY == 0:
            print(f"  [checkpoint] saving {len(entries)} entries...")
            save_cache(cache)

        # Rate limiting
        time.sleep(0.3)

    # Final save
    save_cache(cache)

    print(f"\nDone!")
    print(f"  Processed: {processed}")
    print(f"  Errors: {errors}")
    print(f"  Total refs generated: {total_refs}")
    print(f"  Cache now has {len(entries)} entries")
    print(f"  Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

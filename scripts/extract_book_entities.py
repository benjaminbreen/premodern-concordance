#!/usr/bin/env python3
"""
Extract entities from a book using Gemini 2.5 Flash Lite.
Uses the new 6-category schema with subcategories.

Usage:
    python extract_book_entities.py --input books/english_physician_1652.txt --output web/public/data/culpeper_entities.json
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).parent.parent / ".env.local")

# Chunking parameters
CHUNK_SIZE = 2500
CHUNK_OVERLAP = 200

# 8-category schema with PLANT and ANIMAL as top-level
EXTRACTION_PROMPT = """You are an expert in early modern European science, medicine, and natural philosophy.
Extract ALL named entities from this passage from an early modern text (16th-18th century).

CATEGORIES AND SUBCATEGORIES:

PERSON - Human agents
  Subcategories: AUTHORITY (ancient/medieval sources like Galen, Dioscorides),
                 SCHOLAR (early modern authors), PRACTITIONER (physicians, apothecaries),
                 PATRON (rulers, sponsors), OTHER_PERSON

PLANT - Botanical species, herbs, trees, roots, seeds, plant products
  Subcategories: HERB, TREE, ROOT, SEED, RESIN, OTHER_PLANT

ANIMAL - Animal species and animal-derived products
  Subcategories: MAMMAL, BIRD, FISH, INSECT, REPTILE, PRODUCT (honey, milk, musk), OTHER_ANIMAL

SUBSTANCE - Non-living materials and compound preparations
  Subcategories: MINERAL (metals, earths, stones), PREPARATION (compound medicines, distillates),
                 ANATOMY (body parts, organs, fluids, humors), OTHER_SUBSTANCE

PLACE - Geographic locations
  Subcategories: COUNTRY, CITY, REGION, OTHER_PLACE

DISEASE - Medical conditions
  Subcategories: ACUTE (fever, pleurisy), CHRONIC (dropsy, consumption),
                 SYMPTOM (pain, swelling), OTHER_DISEASE

CONCEPT - Abstract ideas
  Subcategories: THEORY (humoral theory, astrological medicine),
                 PRACTICE (bloodletting, distillation), QUALITY (hot, cold, moist, dry),
                 OTHER_CONCEPT

OBJECT - Artifacts and instruments
  Subcategories: INSTRUMENT (alembic, furnace), VESSEL (flask, jar),
                 TOOL (knife, scale), OTHER_OBJECT

For each entity provide:
- name: exactly as it appears (preserve original spelling)
- category: one of PERSON, PLANT, ANIMAL, SUBSTANCE, PLACE, DISEASE, CONCEPT, OBJECT
- subcategory: the appropriate subcategory from above
- context: brief description (max 10 words)

Return ONLY a JSON array. Example:
[{"name": "Galen", "category": "PERSON", "subcategory": "AUTHORITY", "context": "ancient medical authority"},
 {"name": "Maidenhair", "category": "PLANT", "subcategory": "HERB", "context": "herb for coughs and jaundice"},
 {"name": "yellow Jaundice", "category": "DISEASE", "subcategory": "CHRONIC", "context": "disease of liver obstruction"},
 {"name": "Bezoar stone", "category": "SUBSTANCE", "subcategory": "MINERAL", "context": "antidote stone from animal stomachs"}]

PASSAGE:
"""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks for processing."""
    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    # Remove common EEBO artifacts
    text = re.sub(r'description\nPAGE \d+', '', text)
    text = re.sub(r'description\nPAGE \[UNNUMBERED\]', '', text)
    text = re.sub(r'keyboard_return\nBack to content', '', text)
    text = re.sub(r'\* \d+\.\d+', '', text)  # Remove reference markers

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunk = text[start:].strip()
            if len(chunk) > 200:
                chunks.append(chunk)
            break

        # Try to break at paragraph
        break_point = text.rfind('\n\n', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = text.rfind('. ', start + chunk_size // 2, end)
        if break_point == -1:
            break_point = end
        else:
            break_point += 2

        chunk = text[start:break_point].strip()
        if len(chunk) > 200:
            chunks.append(chunk)
        start = break_point - CHUNK_OVERLAP

    return chunks


def extract_entities(chunk: str, client, model: str) -> list[dict] | None:
    """Extract entities from a single chunk."""
    prompt = EXTRACTION_PROMPT + chunk + "\n\nJSON:"

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": 0.1, "max_output_tokens": 4000}
        )

        text_out = response.text

        # Strip markdown code fences if present
        if '```' in text_out:
            fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text_out)
            if fence_match:
                text_out = fence_match.group(1)

        # Parse JSON from response
        match = re.search(r'\[.*\]', text_out, re.DOTALL)
        if match:
            entities = json.loads(match.group())
            # Validate structure
            valid = []
            for e in entities:
                if all(k in e for k in ["name", "category", "context"]):
                    # Ensure subcategory exists
                    if "subcategory" not in e:
                        e["subcategory"] = f"OTHER_{e['category']}"
                    valid.append(e)
            return valid if valid else None
    except Exception as e:
        print(f"  Warning: {e}")
    return None


def aggregate_entities(all_entities: list[dict]) -> list[dict]:
    """Aggregate entities by name, counting occurrences."""
    from collections import defaultdict

    aggregated = defaultdict(lambda: {
        "name": "",
        "category": "",
        "subcategory": "",
        "contexts": [],
        "count": 0,
        "variants": set()
    })

    for ent in all_entities:
        name = ent.get("name", "").strip()
        if not name or len(name) < 2:
            continue

        key = name.lower()
        aggregated[key]["name"] = name
        aggregated[key]["category"] = ent.get("category", "CONCEPT")
        aggregated[key]["subcategory"] = ent.get("subcategory", f"OTHER_{ent.get('category', 'CONCEPT')}")
        aggregated[key]["count"] += 1
        aggregated[key]["variants"].add(name)

        context = ent.get("context", "")
        if context and context not in aggregated[key]["contexts"]:
            aggregated[key]["contexts"].append(context)

    # Convert to list
    result = []
    for key, data in aggregated.items():
        result.append({
            "id": key.replace(" ", "_").replace(".", "_"),
            "name": data["name"],
            "category": data["category"],
            "subcategory": data["subcategory"],
            "count": data["count"],
            "contexts": data["contexts"][:5],
            "variants": list(data["variants"])
        })

    # Sort by count
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


def load_progress(progress_path: Path) -> tuple[list[dict], int]:
    """Load raw entities from a progress file if it exists."""
    if progress_path.exists():
        with open(progress_path) as f:
            data = json.load(f)
        return data.get("raw_entities", []), data.get("last_chunk", 0)
    return [], 0


def save_progress(progress_path: Path, raw_entities: list[dict], last_chunk: int):
    """Save raw entities and progress to a checkpoint file."""
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump({
            "raw_entities": raw_entities,
            "last_chunk": last_chunk
        }, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Extract entities from a book")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--title", default="", help="Book title")
    parser.add_argument("--author", default="", help="Book author")
    parser.add_argument("--year", type=int, default=0, help="Publication year")
    parser.add_argument("--language", default="English", help="Book language")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model")
    parser.add_argument("--limit", type=int, default=0, help="Limit chunks (0 = all)")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh, ignore progress file")
    args = parser.parse_args()

    # Load text
    input_path = Path(args.input)
    text = input_path.read_text(encoding="utf-8", errors="ignore")
    print(f"Loaded {len(text):,} characters from {input_path.name}")

    # Try to extract metadata from text if not provided
    title = args.title
    author = args.author
    year = args.year

    if not title:
        # Try to find title in first 500 chars
        title_match = re.search(r'Title\n(.+?)(?:\n|Author)', text[:1000])
        if title_match:
            title = title_match.group(1).strip()[:100]

    if not author:
        author_match = re.search(r'Author\n(.+?)(?:\n|Publication)', text[:1000])
        if author_match:
            author = author_match.group(1).strip()

    if not year:
        year_match = re.search(r'\b(1[5-7]\d{2})\b', text[:2000])
        if year_match:
            year = int(year_match.group(1))

    # Chunk text
    chunks = chunk_text(text)
    print(f"Created {len(chunks)} chunks")

    if args.limit > 0:
        chunks = chunks[:args.limit]
        print(f"Limited to {len(chunks)} chunks")

    # Check for existing progress
    output_path = Path(args.output)
    progress_path = output_path.with_suffix(".progress.json")
    start_chunk = 0
    all_entities = []

    if not args.no_resume:
        all_entities, start_chunk = load_progress(progress_path)
        if start_chunk > 0:
            print(f"Resuming from chunk {start_chunk + 1}/{len(chunks)} ({len(all_entities)} entities so far)")

    # Initialize Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found")

    client = genai.Client(api_key=api_key)
    print(f"Using model: {args.model}\n")

    # Extract entities
    failed = 0

    for i in range(start_chunk, len(chunks)):
        chunk = chunks[i]
        print(f"Processing chunk {i+1}/{len(chunks)}...", end=" ", flush=True)

        entities = extract_entities(chunk, client, args.model)

        if entities:
            all_entities.extend(entities)
            print(f"✓ {len(entities)} entities")
        else:
            failed += 1
            print("✗ skipped")

        # Save progress every 25 chunks
        if (i + 1) % 25 == 0:
            save_progress(progress_path, all_entities, i + 1)
            print(f"  [checkpoint saved: {len(all_entities)} entities through chunk {i+1}]")

        time.sleep(0.3)  # Rate limiting

    # Aggregate
    aggregated = aggregate_entities(all_entities)

    # Calculate stats
    by_category = {}
    by_subcategory = {}
    for e in aggregated:
        cat = e["category"]
        subcat = e["subcategory"]
        by_category[cat] = by_category.get(cat, 0) + 1
        by_subcategory[subcat] = by_subcategory.get(subcat, 0) + 1

    # Build output
    book_id = input_path.stem.replace(" ", "-").lower()
    output_data = {
        "book": {
            "id": book_id,
            "title": title or input_path.stem,
            "author": author or "Unknown",
            "year": year or 0,
            "language": args.language,
            "description": f"Entities extracted from {input_path.name}"
        },
        "entities": aggregated,
        "stats": {
            "total_entities": len(aggregated),
            "by_category": by_category,
            "by_subcategory": by_subcategory,
            "extraction_method": args.model,
            "chunks_processed": len(chunks) - failed,
            "chunks_failed": failed
        }
    }

    # Save final output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Clean up progress file
    if progress_path.exists():
        progress_path.unlink()
        print("  [progress file cleaned up]")

    print(f"\n{'='*50}")
    print(f"Extracted {len(all_entities)} raw mentions")
    print(f"Aggregated to {len(aggregated)} unique entities")
    print(f"Failed chunks: {failed}")
    print(f"\nBy category:")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()

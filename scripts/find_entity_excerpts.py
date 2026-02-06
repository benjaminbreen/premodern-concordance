#!/usr/bin/env python3
"""
Find text excerpts for each entity by searching the source text.
No LLM needed — just fast string matching against the book text.

Adds a 'mentions' array to each entity with surrounding context and offsets.

Usage:
    python find_entity_excerpts.py \
        --entities web/public/data/culpeper_entities.json \
        --text books/english_physician_1652.txt
"""

import argparse
import json
import re
from pathlib import Path


CONTEXT_WINDOW = 150  # chars on each side of the match
MAX_MENTIONS = 100    # cap per entity (detail page shows all, table shows first few)


def find_mentions(text: str, text_lower: str, entity: dict) -> list[dict]:
    """Find all occurrences of an entity (and its variants) in the source text."""
    mentions = []
    seen_offsets = set()

    # Collect all search terms: name + variants
    search_terms = set()
    search_terms.add(entity["name"])
    for v in entity.get("variants", []):
        search_terms.add(v)

    for term in search_terms:
        if len(term) < 2:
            continue

        # Use word-boundary matching to avoid partial matches
        # Escape special regex chars in the term
        pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)

        for match in pattern.finditer(text):
            offset = match.start()

            # Skip if we already found a mention very close to this offset
            # (prevents duplicates from overlapping variants)
            if any(abs(offset - s) < 50 for s in seen_offsets):
                continue
            seen_offsets.add(offset)

            # Extract surrounding context
            start = max(0, offset - CONTEXT_WINDOW)
            end = min(len(text), offset + len(term) + CONTEXT_WINDOW)

            # Try to extend to word boundaries
            if start > 0:
                space = text.rfind(' ', max(0, start - 20), start)
                if space != -1:
                    start = space + 1
            if end < len(text):
                space = text.find(' ', end, min(len(text), end + 20))
                if space != -1:
                    end = space

            excerpt = text[start:end].strip()
            # Clean up whitespace
            excerpt = re.sub(r'\s+', ' ', excerpt)

            mentions.append({
                "offset": offset,
                "matched_term": match.group(),
                "excerpt": excerpt,
            })

            if len(mentions) >= MAX_MENTIONS:
                break

        if len(mentions) >= MAX_MENTIONS:
            break

    # Sort by offset (order of appearance in text)
    mentions.sort(key=lambda m: m["offset"])
    return mentions[:MAX_MENTIONS]


def main():
    parser = argparse.ArgumentParser(description="Find text excerpts for entities")
    parser.add_argument("--entities", required=True, help="Entity JSON file")
    parser.add_argument("--text", required=True, help="Source text file")
    parser.add_argument("--output", help="Output file (default: overwrites entities file)")
    args = parser.parse_args()

    # Load entities
    entities_path = Path(args.entities)
    with open(entities_path) as f:
        data = json.load(f)

    # Load source text
    text_path = Path(args.text)
    text = text_path.read_text(encoding="utf-8", errors="ignore")
    text_lower = text.lower()

    print(f"Loaded {len(data['entities'])} entities from {entities_path.name}")
    print(f"Source text: {len(text):,} characters from {text_path.name}")

    # Find mentions for each entity
    total_mentions = 0
    entities_with_mentions = 0

    for i, entity in enumerate(data["entities"]):
        if (i + 1) % 500 == 0:
            print(f"  Processing entity {i+1}/{len(data['entities'])}...")

        mentions = find_mentions(text, text_lower, entity)
        entity["mentions"] = mentions

        if mentions:
            entities_with_mentions += 1
            total_mentions += len(mentions)

    print(f"\nResults:")
    print(f"  Entities with mentions found: {entities_with_mentions}/{len(data['entities'])}")
    print(f"  Total mentions: {total_mentions}")
    print(f"  Avg mentions per entity: {total_mentions / max(entities_with_mentions, 1):.1f}")

    # Save
    output_path = Path(args.output) if args.output else entities_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Report file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nSaved to: {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

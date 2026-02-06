#!/usr/bin/env python3
"""
Extract and aggregate all entities from the Semedo training data.
Creates a JSON file suitable for the web frontend.
"""

import json
from collections import defaultdict
from pathlib import Path

def extract_entities():
    """Extract all entities from training data."""
    training_file = Path(__file__).parent.parent / "pilot" / "entity_training_data.jsonl"

    # Aggregate entities
    entities = defaultdict(lambda: {
        "name": "",
        "category": "",
        "contexts": [],
        "count": 0,
        "variants": set()
    })

    with open(training_file, "r", encoding="utf-8") as f:
        for line in f:
            example = json.loads(line)
            # Get the assistant response (JSON array of entities)
            assistant_msg = example["messages"][2]["content"]
            try:
                extracted = json.loads(assistant_msg)
                for ent in extracted:
                    name = ent.get("name", "").strip()
                    if not name:
                        continue

                    # Use lowercase for deduplication key
                    key = name.lower()

                    entities[key]["name"] = name  # Keep original casing
                    entities[key]["category"] = ent.get("category", "UNKNOWN")
                    entities[key]["count"] += 1

                    context = ent.get("context", "")
                    if context and context not in entities[key]["contexts"]:
                        entities[key]["contexts"].append(context)

                    # Track variant spellings
                    entities[key]["variants"].add(name)
            except json.JSONDecodeError:
                continue

    # Convert to list and sort by frequency
    entity_list = []
    for key, data in entities.items():
        entity_list.append({
            "id": key.replace(" ", "_").replace(".", "_"),
            "name": data["name"],
            "category": data["category"],
            "count": data["count"],
            "contexts": data["contexts"][:5],  # Keep top 5 contexts
            "variants": list(data["variants"])
        })

    # Sort by count descending
    entity_list.sort(key=lambda x: x["count"], reverse=True)

    return entity_list

def main():
    entities = extract_entities()

    # Summary stats
    by_category = defaultdict(int)
    for e in entities:
        by_category[e["category"]] += 1

    print(f"Total unique entities: {len(entities)}")
    print(f"\nBy category:")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print(f"\nTop 20 most frequent:")
    for e in entities[:20]:
        print(f"  {e['count']:3d}x  {e['name']:<30} [{e['category']}]")

    # Save to JSON
    output_file = Path(__file__).parent.parent / "web" / "data" / "semedo_entities.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Create book metadata
    book_data = {
        "book": {
            "id": "semedo-polyanthea-1741",
            "title": "Polyanthea Medicinal",
            "author": "João Curvo Semedo",
            "year": 1741,
            "language": "Portuguese",
            "description": "A comprehensive medical treatise covering diseases, remedies, and pharmaceutical preparations in early 18th century Portugal."
        },
        "entities": entities,
        "stats": {
            "total_entities": len(entities),
            "by_category": dict(by_category),
            "extraction_method": "gemini-2.5-flash-lite",
            "chunks_processed": 461
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(book_data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_file}")

if __name__ == "__main__":
    main()

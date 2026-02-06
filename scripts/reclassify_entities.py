#!/usr/bin/env python3
"""
Reclassify existing entities into the new 6-category schema.
Batches entities for efficiency (~50 per API call).
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).parent.parent / ".env.local")

SCHEMA = """
PERSON - Human agents
  Subcategories: AUTHORITY (ancient/medieval sources), SCHOLAR (early modern authors),
                 PRACTITIONER (physicians, craftsmen), PATRON (rulers), OTHER_PERSON

PLACE - Geographic locations
  Subcategories: COUNTRY, CITY, REGION, OTHER_PLACE

SUBSTANCE - Natural materials and preparations
  Subcategories: PLANT, ANIMAL, MINERAL, PREPARATION (compound medicines),
                 ANATOMY (body parts, organs, fluids, humors)

OBJECT - Artifacts and instruments
  Subcategories: INSTRUMENT (alembic, furnace), VESSEL (flask, jar),
                 TOOL (knife, scale), OTHER_OBJECT

DISEASE - Medical conditions
  Subcategories: ACUTE (fever, pleurisy), CHRONIC (dropsy, consumption),
                 SYMPTOM (pain, swelling), OTHER_DISEASE

CONCEPT - Abstract ideas
  Subcategories: THEORY (humoral theory, mechanics), PRACTICE (bloodletting, distillation),
                 QUALITY (hot, cold, purgative), OTHER_CONCEPT
"""

PROMPT_TEMPLATE = """Reclassify these entities from an early modern medical text into the schema below.

SCHEMA:
{schema}

For each entity, return ONLY a JSON array with the format:
{{"name": "original name", "category": "TOP_LEVEL", "subcategory": "SUBCATEGORY"}}

ENTITIES TO CLASSIFY:
{entities}

Return ONLY the JSON array, no other text:"""


def batch_reclassify(entities: list[dict], client, model: str) -> list[dict]:
    """Reclassify a batch of entities."""
    # Format entities for the prompt
    entity_list = "\n".join(
        f"- {e['name']} (old category: {e['category']}, context: {e['contexts'][0] if e['contexts'] else 'none'})"
        for e in entities
    )

    prompt = PROMPT_TEMPLATE.format(schema=SCHEMA, entities=entity_list)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": 0.1, "max_output_tokens": 4000}
        )

        # Parse response
        text = response.text
        # Find JSON array in response
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end > start:
            results = json.loads(text[start:end])
            return results
    except Exception as e:
        print(f"  Error: {e}")

    return []


def main():
    # Load existing entities
    input_file = Path(__file__).parent.parent / "web" / "public" / "data" / "semedo_entities.json"
    with open(input_file) as f:
        data = json.load(f)

    entities = data["entities"]
    print(f"Loaded {len(entities)} entities to reclassify")

    # Initialize Gemini client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found")

    client = genai.Client(api_key=api_key)
    model = "gemini-2.5-flash-lite"

    # Process in batches
    batch_size = 50
    reclassified = {}

    for i in range(0, len(entities), batch_size):
        batch = entities[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1}/{(len(entities) + batch_size - 1) // batch_size}...", end=" ", flush=True)

        results = batch_reclassify(batch, client, model)

        # Map results back by name
        for r in results:
            name_lower = r.get("name", "").lower()
            reclassified[name_lower] = {
                "category": r.get("category", "CONCEPT"),
                "subcategory": r.get("subcategory", "OTHER_CONCEPT")
            }

        print(f"✓ {len(results)} classified")
        time.sleep(0.5)  # Rate limiting

    # Apply reclassifications to original data
    updated_count = 0
    for entity in entities:
        key = entity["name"].lower()
        if key in reclassified:
            entity["category"] = reclassified[key]["category"]
            entity["subcategory"] = reclassified[key]["subcategory"]
            updated_count += 1
        else:
            # Keep old category, add generic subcategory
            entity["subcategory"] = f"OTHER_{entity['category']}"

    # Update stats
    by_category = {}
    by_subcategory = {}
    for e in entities:
        cat = e["category"]
        subcat = e.get("subcategory", "UNKNOWN")
        by_category[cat] = by_category.get(cat, 0) + 1
        by_subcategory[subcat] = by_subcategory.get(subcat, 0) + 1

    data["stats"]["by_category"] = by_category
    data["stats"]["by_subcategory"] = by_subcategory

    # Save updated data
    output_file = input_file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"Reclassified {updated_count} of {len(entities)} entities")
    print(f"\nBy category:")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print(f"\nBy subcategory:")
    for subcat, count in sorted(by_subcategory.items(), key=lambda x: -x[1])[:15]:
        print(f"  {subcat}: {count}")
    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()

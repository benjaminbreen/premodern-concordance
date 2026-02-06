#!/usr/bin/env python3
"""Fix category normalization - ensure subcategories map to correct top-level."""

import json
from pathlib import Path

# Valid subcategories in our 8-category schema (PLANT and ANIMAL are top-level)
VALID_SUBCATEGORIES = {
    "AUTHORITY", "SCHOLAR", "PRACTITIONER", "PATRON", "PATIENT", "OTHER_PERSON",
    "COUNTRY", "CITY", "REGION", "OTHER_PLACE",
    "HERB", "TREE", "ROOT", "SEED", "RESIN", "OTHER_PLANT",
    "MAMMAL", "BIRD", "FISH", "INSECT", "REPTILE", "PRODUCT", "OTHER_ANIMAL",
    "MINERAL", "PREPARATION", "ANATOMY", "OTHER_SUBSTANCE",
    "INSTRUMENT", "VESSEL", "TOOL", "OTHER_OBJECT",
    "ACUTE", "CHRONIC", "SYMPTOM", "OTHER_DISEASE",
    "THEORY", "PRACTICE", "QUALITY", "OTHER_CONCEPT"
}

# Map non-standard subcategories to valid ones
SUBCATEGORY_FIXES = {
    # Variations of valid subcategories
    "SUBSTANCE": "OTHER_SUBSTANCE",
    "OTHER_PRACTICE": "PRACTICE",
    "OTHER_ANATOMY": "ANATOMY",
    "OTHER_QUALITY": "QUALITY",
    "OTHER_SYMPTOM": "SYMPTOM",
    "OTHER_ANIMAL": "OTHER_ANIMAL",
    # Domain-specific terms to subcategories
    "HUMOR": "ANATOMY",
    "HUMORS": "ANATOMY",
    "FLUID": "ANATOMY",
    "BLOODLETTING": "PRACTICE",
    "DISTILLATION": "PRACTICE",
    "DECOCTION": "PREPARATION",
    # Common Gemini outputs that need mapping
    "HERB": "OTHER_PLANT",
    "MEDICINE": "PREPARATION",
    "DRUG": "PREPARATION",
    "ORGAN": "ANATOMY",
    "BODY_PART": "ANATOMY",
    "AUTHOR": "SCHOLAR",
    "WRITER": "SCHOLAR",
    "PHYSICIAN": "PRACTITIONER",
    "APOTHECARY": "PRACTITIONER",
    "KING": "PATRON",
    "RULER": "PATRON",
    "BIBLICAL FIGURE": "AUTHORITY",
    "BIBLICAL_FIGURE": "AUTHORITY",
    "TOWN": "CITY",
    "EMPIRE": "COUNTRY",
    "FEVER": "ACUTE",
    "CONDITION": "CHRONIC",
    "SIGN": "SYMPTOM",
    "ASTROLOGY": "THEORY",
    "PHYSIOLOGY": "THEORY",
}

# Map subcategories to their correct top-level category (8-category schema)
SUBCATEGORY_TO_CATEGORY = {
    # PERSON subcategories
    "AUTHORITY": "PERSON",
    "SCHOLAR": "PERSON",
    "PRACTITIONER": "PERSON",
    "PATRON": "PERSON",
    "PATIENT": "PERSON",
    "OTHER_PERSON": "PERSON",

    # PLANT subcategories
    "HERB": "PLANT",
    "TREE": "PLANT",
    "ROOT": "PLANT",
    "SEED": "PLANT",
    "RESIN": "PLANT",
    "OTHER_PLANT": "PLANT",

    # ANIMAL subcategories
    "MAMMAL": "ANIMAL",
    "BIRD": "ANIMAL",
    "FISH": "ANIMAL",
    "INSECT": "ANIMAL",
    "REPTILE": "ANIMAL",
    "PRODUCT": "ANIMAL",
    "OTHER_ANIMAL": "ANIMAL",

    # SUBSTANCE subcategories
    "MINERAL": "SUBSTANCE",
    "PREPARATION": "SUBSTANCE",
    "ANATOMY": "SUBSTANCE",
    "OTHER_SUBSTANCE": "SUBSTANCE",

    # PLACE subcategories
    "COUNTRY": "PLACE",
    "CITY": "PLACE",
    "REGION": "PLACE",
    "OTHER_PLACE": "PLACE",

    # OBJECT subcategories
    "INSTRUMENT": "OBJECT",
    "VESSEL": "OBJECT",
    "TOOL": "OBJECT",
    "OTHER_OBJECT": "OBJECT",

    # DISEASE subcategories
    "ACUTE": "DISEASE",
    "CHRONIC": "DISEASE",
    "SYMPTOM": "DISEASE",
    "OTHER_DISEASE": "DISEASE",

    # CONCEPT subcategories
    "THEORY": "CONCEPT",
    "PRACTICE": "CONCEPT",
    "QUALITY": "CONCEPT",
    "OTHER_CONCEPT": "CONCEPT",
}

# Valid top-level categories
VALID_CATEGORIES = {"PERSON", "PLANT", "ANIMAL", "SUBSTANCE", "PLACE", "DISEASE", "CONCEPT", "OBJECT"}

# Map misplaced top-level uses (subcategory used as category)
CATEGORY_FIXES = {
    "ANATOMY": ("SUBSTANCE", "ANATOMY"),
    "MINERAL": ("SUBSTANCE", "MINERAL"),
    "PREPARATION": ("SUBSTANCE", "PREPARATION"),
    "PRACTICE": ("CONCEPT", "PRACTICE"),
    "THEORY": ("CONCEPT", "THEORY"),
    "QUALITY": ("CONCEPT", "QUALITY"),
    "SYMPTOM": ("DISEASE", "SYMPTOM"),
    "ACUTE": ("DISEASE", "ACUTE"),
    "CHRONIC": ("DISEASE", "CHRONIC"),
    "AUTHORITY": ("PERSON", "AUTHORITY"),
    "SCHOLAR": ("PERSON", "SCHOLAR"),
    "PRACTITIONER": ("PERSON", "PRACTITIONER"),
    "PATRON": ("PERSON", "PATRON"),
    "PATIENT": ("PERSON", "PATIENT"),
    "COUNTRY": ("PLACE", "COUNTRY"),
    "REGION": ("PLACE", "REGION"),
    "CITY": ("PLACE", "CITY"),
    "OTHER_PLACE": ("PLACE", "OTHER_PLACE"),
    "INSTRUMENT": ("OBJECT", "INSTRUMENT"),
    "VESSEL": ("OBJECT", "VESSEL"),
    "TOOL": ("OBJECT", "TOOL"),
    "OTHER_OBJECT": ("OBJECT", "OTHER_OBJECT"),
    "HERB": ("PLANT", "HERB"),
    "TREE": ("PLANT", "TREE"),
    "ROOT": ("PLANT", "ROOT"),
    "SEED": ("PLANT", "SEED"),
    "RESIN": ("PLANT", "RESIN"),
    "MAMMAL": ("ANIMAL", "MAMMAL"),
    "BIRD": ("ANIMAL", "BIRD"),
    "FISH": ("ANIMAL", "FISH"),
    "INSECT": ("ANIMAL", "INSECT"),
    "REPTILE": ("ANIMAL", "REPTILE"),
    "PRODUCT": ("ANIMAL", "PRODUCT"),
    "ORGAN": ("SUBSTANCE", "ANATOMY"),
}

def fix_file(input_file: Path) -> dict:
    """Fix categories in a single file and return stats."""
    with open(input_file) as f:
        data = json.load(f)

    fixed_count = 0
    subcat_fixed = 0
    for entity in data["entities"]:
        cat = entity.get("category", "")
        subcat = entity.get("subcategory", "")

        # Normalize subcategory first (case-insensitive lookup)
        subcat_upper = subcat.upper().replace(" ", "_") if subcat else ""
        if subcat_upper in SUBCATEGORY_FIXES:
            entity["subcategory"] = SUBCATEGORY_FIXES[subcat_upper]
            subcat = entity["subcategory"]
            subcat_fixed += 1
        elif subcat and subcat not in VALID_SUBCATEGORIES:
            # Try to infer from category if subcategory is non-standard
            if cat in VALID_CATEGORIES:
                entity["subcategory"] = f"OTHER_{cat}"
                subcat = entity["subcategory"]
                subcat_fixed += 1

        # If category is actually a subcategory, fix it
        if cat in CATEGORY_FIXES:
            correct_cat, correct_subcat = CATEGORY_FIXES[cat]
            entity["category"] = correct_cat
            if not subcat or subcat == cat:
                entity["subcategory"] = correct_subcat
            fixed_count += 1

        # Validate subcategory maps to correct category
        if subcat in SUBCATEGORY_TO_CATEGORY:
            expected_cat = SUBCATEGORY_TO_CATEGORY[subcat]
            if entity["category"] != expected_cat:
                entity["category"] = expected_cat
                fixed_count += 1

    # Recalculate stats
    by_category = {}
    by_subcategory = {}
    for e in data["entities"]:
        cat = e["category"]
        subcat = e.get("subcategory", "UNKNOWN")
        by_category[cat] = by_category.get(cat, 0) + 1
        by_subcategory[subcat] = by_subcategory.get(subcat, 0) + 1

    data["stats"]["by_category"] = by_category
    data["stats"]["by_subcategory"] = by_subcategory

    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"fixed": fixed_count, "subcat_fixed": subcat_fixed, "by_category": by_category, "by_subcategory": by_subcategory}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fix category normalization in entity files")
    parser.add_argument("--file", help="Specific file to fix (otherwise fixes all in data/)")
    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent / "web" / "public" / "data"

    if args.file:
        files = [Path(args.file)]
    else:
        files = list(data_dir.glob("*_entities.json"))

    for input_file in files:
        print(f"\nProcessing: {input_file.name}")
        result = fix_file(input_file)

        print(f"  Fixed {result['fixed']} category assignments")
        print(f"  Fixed {result['subcat_fixed']} subcategory normalizations")
        print(f"  By category:")
        for cat, count in sorted(result['by_category'].items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")
        print(f"  By subcategory (top 10):")
        for subcat, count in sorted(result['by_subcategory'].items(), key=lambda x: -x[1])[:10]:
            print(f"    {subcat}: {count}")


if __name__ == "__main__":
    main()

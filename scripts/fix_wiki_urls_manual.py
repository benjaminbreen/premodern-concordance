#!/usr/bin/env python3
"""
Manually fix wrong Wikipedia URLs found by review_clusters.py.
Matches clusters by their current (wrong) URL, not by ID.

Usage:
    python3 scripts/fix_wiki_urls_manual.py [--dry-run]
"""

import json
import sys
import urllib.parse
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"

# Map: wrong_url_substring -> {canonical_name_pattern: correct_url}
# Using URL title substring for matching since full URLs have encoding variations
# "CLEAR" means remove the URL entirely

FIXES = [
    # Europe PubMed Central -> Europe
    {"wrong_url_contains": "Europe%20PubMed%20Central",
     "fixes": {"default": "https://en.wikipedia.org/wiki/Europe"}},

    # Mindat.org -> Mind
    {"wrong_url_contains": "Mindat.org",
     "fixes": {"default": "https://en.wikipedia.org/wiki/Mind"}},

    # Cannabis (drug) -> correct plant articles
    # Only fix specific modern names; leave Hemp and other Cannabis clusters alone
    {"wrong_url_contains": "Cannabis",
     "fixes_by_modern": {
         "Flower": "https://en.wikipedia.org/wiki/Flower",
         "Flowers": "https://en.wikipedia.org/wiki/Flower",
         "Grass": "https://en.wikipedia.org/wiki/Poaceae",
         "Poaceae": "https://en.wikipedia.org/wiki/Poaceae",
         "Herb": "https://en.wikipedia.org/wiki/Herb",
         "default": None,  # keep for Hemp, Cannabis, etc.
     }},

    # Florence -> Fire
    {"wrong_url_contains": "Florence",
     "skip_modern": ["Florence"],  # don't fix if it's actually about Florence
     "fixes": {"default": "https://en.wikipedia.org/wiki/Fire"}},

    # Science project -> Science (but clear "work" and "study")
    {"wrong_url_contains": "Science%20project",
     "fixes_by_modern": {
         "Sciences": "https://en.wikipedia.org/wiki/Science",
         "Science": "https://en.wikipedia.org/wiki/Science",
         "Work": "CLEAR",
         "Study": "CLEAR",
         "default": "https://en.wikipedia.org/wiki/Science",
     }},

    # Glass (surname) -> Glass
    {"wrong_url_contains": "Glass%20%28surname%29",
     "fixes": {"default": "https://en.wikipedia.org/wiki/Glass"}},

    # Graphite -> Silver (for silver clusters that got graphite URL)
    {"wrong_url_contains": "Graphite",
     "fixes_by_modern": {
         "Silver": "https://en.wikipedia.org/wiki/Silver",
         "Graphite": None,  # keep if actually graphite
         "default": "CLEAR",
     }},

    # Ruby -> correct (rubino=ruby fine, rame=copper)
    {"wrong_url_contains": "/Ruby",
     "fixes_by_modern": {
         "ruby": None,      # keep
         "Ruby": None,      # keep
         "Copper": "https://en.wikipedia.org/wiki/Copper",
         "default": None,
     }},

    # Chapter (religion) -> clear
    {"wrong_url_contains": "Chapter%20%28religion%29",
     "fixes": {"default": "CLEAR"}},

    # Ethics -> correct (consumption=TB, Ethicks=ethics)
    {"wrong_url_contains": "/Ethics",
     "fixes_by_modern": {
         "Phthisis": "https://en.wikipedia.org/wiki/Tuberculosis",
         "Ethics": None,  # keep
         "default": None,
     }},

    # MRI -> Magnet
    {"wrong_url_contains": "Magnetic%20resonance%20imaging",
     "fixes": {"default": "https://en.wikipedia.org/wiki/Magnet"}},

    # Congenital diaphragmatic hernia -> correct
    {"wrong_url_contains": "Congenital%20diaphragmatic%20hernia",
     "fixes_by_modern": {
         "Hernia": "https://en.wikipedia.org/wiki/Hernia",
         "Diaphragm": "https://en.wikipedia.org/wiki/Thoracic_diaphragm",
         "default": "CLEAR",
     }},

    # Skink -> Skin
    {"wrong_url_contains": "/Skink",
     "fixes_by_modern": {
         "Skin": "https://en.wikipedia.org/wiki/Skin",
         "default": "https://en.wikipedia.org/wiki/Skin",
     }},

    # Seattle -> correct
    {"wrong_url_contains": "/Seattle",
     "fixes_by_modern": {
         "Emerald": "https://en.wikipedia.org/wiki/Emerald",
         "sea": "https://en.wikipedia.org/wiki/Sea",
         "Sea": "https://en.wikipedia.org/wiki/Sea",
         "default": "CLEAR",
     }},

    # Colorado -> Color
    {"wrong_url_contains": "/Colorado",
     "skip_modern": ["Colorado"],
     "fixes": {"default": "https://en.wikipedia.org/wiki/Color"}},

    # Cementum -> correct body parts
    {"wrong_url_contains": "/Cementum",
     "fixes_by_modern": {
         "Ligaments": "https://en.wikipedia.org/wiki/Ligament",
         "Limbs": "https://en.wikipedia.org/wiki/Limb_(anatomy)",
         "default": "CLEAR",
     }},

    # Autoimmune lymphoproliferative syndrome -> mountains
    # Both have modern_name "Alps" so match by canonical_name
    {"wrong_url_contains": "Autoimmune%20lymphoproliferative",
     "fixes_by_canonical": {
         "Alpes maritimes": "https://en.wikipedia.org/wiki/Maritime_Alps",
         "ALTAÏ": "https://en.wikipedia.org/wiki/Altai_Mountains",
         "default": "CLEAR",
     }},

    # Northern Germany -> Dolomite
    {"wrong_url_contains": "Northern_Germany",
     "fixes_by_modern": {
         "dolomite": "https://en.wikipedia.org/wiki/Dolomite_(mineral)",
         "Dolomite": "https://en.wikipedia.org/wiki/Dolomite_(mineral)",
         "default": None,
     }},

    # House mouse -> correct
    {"wrong_url_contains": "House%20mouse",
     "fixes_by_modern": {
         "Mouse": None,  # keep
         "house": "https://en.wikipedia.org/wiki/House",
         "default": None,
     }},

    # Political demonstration -> Demon
    {"wrong_url_contains": "Political%20demonstration",
     "fixes_by_modern": {
         "Demon": "https://en.wikipedia.org/wiki/Demon",
         "Demonstration": None,  # keep
         "default": None,
     }},

    # Animal migration -> Organism
    {"wrong_url_contains": "Animal%20migration",
     "fixes_by_modern": {
         "Organism": "https://en.wikipedia.org/wiki/Organism",
         "default": None,
     }},

    # Horse -> seawater for agua do mar cluster
    {"wrong_url_contains": "/Horse",
     "fixes_by_category_modern": {
         # Only fix if modern_name suggests it's not actually about horses
         ("Horse", "ANIMAL"): None,  # keep for actual horse clusters
         ("Horses", "ANIMAL"): None,
         ("mares", "ANIMAL"): None,
     },
     "fixes_by_modern": {
         "Horse": None,
         "Horses": None,
         "mares": None,
         "default": None,  # Don't touch horse clusters
     }},

    # Distilled water -> clear for cap. cluster
    {"wrong_url_contains": "Distilled%20water",
     "fixes_by_modern": {
         "chapter": "CLEAR",
         "Chapter": "CLEAR",
         "default": None,  # keep for actual distilled water
     }},

    # Wine -> Copper for rame cluster
    {"wrong_url_contains": "/Wine",
     "fixes_by_modern": {
         "Copper": "https://en.wikipedia.org/wiki/Copper",
         "default": None,  # keep for actual wine clusters
     }},

    # Cannabis sativa -> Skin for Hemp/Skin cluster
    {"wrong_url_contains": "Cannabis%20sativa",
     "fixes_by_modern": {
         "Skin": "https://en.wikipedia.org/wiki/Skin",
         "default": None,
     }},

    # Japan -> clear for generic "land" clusters
    {"wrong_url_contains": "/Japan",
     "fixes_by_modern": {
         "Japan": None,  # keep
         "Land": "CLEAR",
         "default": None,
     }},
]


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    fixed = 0
    cleared = 0

    for c in clusters:
        gt = c.get("ground_truth") or {}
        url = gt.get("wikipedia_url", "")
        if not url:
            continue

        name = c.get("canonical_name", "?")
        modern = gt.get("modern_name", "")
        category = c.get("category", "")

        for rule in FIXES:
            if rule["wrong_url_contains"] not in url:
                continue

            # Check skip conditions
            if modern in rule.get("skip_modern", []):
                continue

            # Determine correct URL
            new_url = None
            if "fixes_by_canonical" in rule:
                new_url = rule["fixes_by_canonical"].get(name, rule["fixes_by_canonical"].get("default"))
            elif "fixes_by_modern" in rule:
                new_url = rule["fixes_by_modern"].get(modern, rule["fixes_by_modern"].get("default"))
            elif "fixes" in rule:
                new_url = rule["fixes"].get("default")

            if new_url is None:
                continue  # keep as-is

            if new_url == "CLEAR":
                print(f"  [clear] {name} ({modern}): {url.split('/wiki/')[-1] if '/wiki/' in url else url[:50]}")
                if not dry_run:
                    gt["wikipedia_url"] = ""
                    gt["wikipedia_extract"] = ""
                    c["ground_truth"] = gt
                cleared += 1
            elif new_url != url:
                old_title = urllib.parse.unquote(url.split("/wiki/")[-1]) if "/wiki/" in url else url[:50]
                new_title = urllib.parse.unquote(new_url.split("/wiki/")[-1])
                print(f"  [fix]   {name} ({modern}): {old_title} -> {new_title}")
                if not dry_run:
                    gt["wikipedia_url"] = new_url
                    # Clear extract so it can be re-fetched with correct article
                    gt["wikipedia_extract"] = ""
                    c["ground_truth"] = gt
                fixed += 1
            break  # only apply first matching rule

    print(f"\n  URLs fixed:   {fixed}")
    print(f"  URLs cleared: {cleared}")
    print(f"  Total changes: {fixed + cleared}")

    if not dry_run and (fixed + cleared) > 0:
        print(f"\nSaving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB")
    elif dry_run:
        print("\nNo changes written (dry run).")


if __name__ == "__main__":
    main()

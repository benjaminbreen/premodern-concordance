#!/usr/bin/env python3
"""
Batch fix Wikipedia URLs that point to wrong articles.
Catches (surname), (beetle), (journal), (Internet personality), etc.

Usage:
    python3 scripts/fix_wiki_urls_batch2.py [--dry-run]
"""

import json
import sys
import urllib.parse
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"

# Patterns in URL titles that indicate wrong article
BAD_PATTERNS = [
    "(surname)", "(beetle)", "(journal)", "(magazine)", "(band)", "(film)",
    "(TV_series)", "(TV series)", "(Internet", "(disambiguation)",
    "(footballer)", "(cricketer)", "(singer)", "(musician)", "(actor)",
    "(comics)", "(video game)", "(song)", "(album)",
]

# URLs that are clearly wrong matches (specific known bad ones)
SPECIFIC_BAD_URLS = {
    "Insecticide": "Insect",
    "Wikispecies": "Species",
    "Sport_of_athletics": "Light",
    "Plantago": "Plant",
    "Rainbow_trout": "Steel",
    "Canis_familiaris": "Dog",
    "Sovereign_state": "Country",
    "Zoology": "Animal",
}

# Manual overrides: canonical_name -> correct Wikipedia article title
# For clusters where the correct article is non-obvious
MANUAL_CORRECTIONS = {
    "America": "Americas",
    "Africa": "Africa",
    "insects": "Insect",
    "birds": "Bird",
    "reason": "Reason",
    "Christ": "Jesus",
    "Plants": "Plant",
    "animals": "Animal",
    "Nature": "Nature",
    "species": "Species",
    "Mexique": "Mexico",
    "brain": "Brain",
    "June": "June",
    "pain": "Pain",
    "Wind": "Wind",
    "snow": "Snow",
    "April": "April",
    "Fear": "Fear",
    "Solomon": "Solomon",
    "criança": "Child",
    "Diamante": "Diamond",
    "Livro": "Book",
    "Cicero": "Cicero",
    "Adam": "Adam",
    "fingers": "Finger",
    "montagnes": "Mountain",
    "Mr. Brooke": "CLEAR",  # too specific to resolve
    "cannon": "Cannon",
    "Human Nature": "Human_nature",
    "Evolution": "Evolution",
    "Musa": "Moses",
    "organ": "Organ_(biology)",
    "cooling": "Cooling",
    "lune": "Moon",
    "French": "French_people",
    "music": "Music",
    "marmo": "Marble",
    "Cornea": "Cornea",
    "anger": "Anger",
    "winds": "Wind",
    "innate": "Heredity",
    "Palaeontology": "Paleontology",
    "dias": "Day",
    "fallar": "CLEAR",  # too ambiguous
    "sparrow": "Sparrow",
    "David": "David",
    "Hills": "Hill",
    "pedras": "Rock_(geology)",
    "elrey": "Monarch",
    "fontes": "Spring_(hydrology)",
    "May": "May",
    "blue": "Blue",
    "Bacchus": "Bacchus",
    "maître": "CLEAR",  # "master" too generic
    "masses": "Mass",
    "Senhor": "Lord",
    "Pacem": "Peace",
    "Flood": "Flood",
    "wisdom": "Wisdom",
    "Broom Field": "CLEAR",
    "Steel": "Steel",
    "country": "Country",
    "dogs": "Dog",
    "light": "Light",
    "terra": "Soil",
}


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
        if not url or "/wiki/" not in url:
            continue

        title = urllib.parse.unquote(url.split("/wiki/")[-1]).replace("_", " ")
        name = c.get("canonical_name", "?")

        # Check if URL matches any bad pattern
        is_bad = any(p.lower() in title.lower() for p in BAD_PATTERNS)

        # Check specific bad URLs
        url_key = url.split("/wiki/")[-1]
        specific_fix = None
        for bad_url, correct_title in SPECIFIC_BAD_URLS.items():
            if bad_url in url_key:
                specific_fix = correct_title
                is_bad = True
                break

        if not is_bad:
            continue

        # Determine correct URL
        if name in MANUAL_CORRECTIONS:
            correct_title = MANUAL_CORRECTIONS[name]
        elif specific_fix:
            correct_title = specific_fix
        else:
            # Try stripping the disambiguation suffix
            import re
            base = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
            if base:
                correct_title = base
            else:
                correct_title = "CLEAR"

        if correct_title == "CLEAR":
            print(f"  [clear] {name}: {title}")
            if not dry_run:
                gt["wikipedia_url"] = ""
                gt["wikipedia_extract"] = ""
                c["ground_truth"] = gt
            cleared += 1
        else:
            new_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(correct_title.replace(' ', '_'))}"
            if new_url != url:
                print(f"  [fix]   {name}: {title} -> {correct_title}")
                if not dry_run:
                    gt["wikipedia_url"] = new_url
                    gt["wikipedia_extract"] = ""  # clear for re-fetch
                    c["ground_truth"] = gt
                fixed += 1

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

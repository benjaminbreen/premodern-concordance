#!/usr/bin/env python3
"""
Fetch portrait image URLs from Wikidata P18 for PERSON clusters.

Queries Wikidata for each PERSON cluster that has a wikidata_id, retrieves
the P18 (image) property, and constructs a Wikimedia Commons URL.
Stores result in ground_truth.portrait_url.

Usage:
    python fetch_portraits.py              # fetch and write
    python fetch_portraits.py --dry-run    # preview only
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
CONCORDANCE_PATH = DATA_DIR / "concordance.json"

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_THUMB = "https://commons.wikimedia.org/w/thumb.php"


def fetch_image_filename(qid: str) -> str | None:
    """Get the P18 (image) filename from Wikidata for a given QID."""
    params = urllib.parse.urlencode({
        "action": "wbgetclaims",
        "entity": qid,
        "property": "P18",
        "format": "json",
    })
    url = f"{WIKIDATA_API}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    Error fetching {qid}: {e}")
        return None

    claims = data.get("claims", {}).get("P18", [])
    if not claims:
        return None

    return claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")


def commons_thumb_url(filename: str, width: int = 400) -> str:
    """Construct a Wikimedia Commons thumbnail URL from a filename."""
    encoded = filename.replace(" ", "_")
    return f"{COMMONS_THUMB}?f={urllib.parse.quote(encoded)}&w={width}"


def main():
    parser = argparse.ArgumentParser(description="Fetch portraits from Wikidata P18")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--width", type=int, default=400, help="Thumbnail width in px")
    args = parser.parse_args()

    print(f"Loading {CONCORDANCE_PATH}...")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    persons = [c for c in clusters if c["category"] == "PERSON"]
    with_wd = [c for c in persons if c.get("ground_truth", {}).get("wikidata_id")]

    # Skip clusters that already have a portrait_url
    to_fetch = [c for c in with_wd if not c.get("ground_truth", {}).get("portrait_url")]

    print(f"  {len(persons)} PERSON clusters")
    print(f"  {len(with_wd)} with Wikidata ID")
    print(f"  {len(to_fetch)} need portrait lookup ({len(with_wd) - len(to_fetch)} already done)")

    found = 0
    not_found = 0

    for i, cluster in enumerate(to_fetch):
        gt = cluster["ground_truth"]
        qid = gt["wikidata_id"]
        name = cluster["canonical_name"]

        filename = fetch_image_filename(qid)
        time.sleep(0.2)  # Respect rate limits

        if filename:
            thumb = commons_thumb_url(filename, args.width)
            gt["portrait_url"] = thumb
            found += 1
            print(f"  [{i+1}/{len(to_fetch)}] {name} ({qid}) -> {filename[:50]}...")
        else:
            not_found += 1
            if (i + 1) % 10 == 0 or i == len(to_fetch) - 1:
                print(f"  [{i+1}/{len(to_fetch)}] {name} ({qid}) -> no image")

    print(f"\nResults: {found} portraits found, {not_found} without images")

    if args.dry_run:
        print("[DRY RUN] No file written.")
        return

    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Written to {CONCORDANCE_PATH}")


if __name__ == "__main__":
    main()

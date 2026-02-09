#!/usr/bin/env python3
"""
Resolve person graph nodes to Wikipedia identities and download portrait thumbnails.

Reads person_graphs.json, applies curated overrides, searches Wikipedia for
unresolved persons, downloads thumbnails, and outputs person_identities.json.

Usage:
    python3 resolve_person_identities.py                  # full run
    python3 resolve_person_identities.py --dry-run        # preview only
    python3 resolve_person_identities.py --skip-download  # resolve but don't download
    python3 resolve_person_identities.py --force          # re-resolve all (ignore cache)
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "web" / "public" / "data"
THUMB_DIR = ROOT / "web" / "public" / "thumbnails"
OVERRIDES_PATH = ROOT / "data" / "person_overrides.json"
PERSON_GRAPHS_PATH = DATA_DIR / "person_graphs.json"
OUTPUT_PATH = DATA_DIR / "person_identities.json"

WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_SEARCH_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "PremodernConcordance/1.0 (educational project; portrait thumbnails)"

THUMB_WIDTH = 200  # px — enough for retina display at 64px rendered


def load_overrides():
    """Load curated overrides from data/person_overrides.json."""
    if not OVERRIDES_PATH.exists():
        return {"wikipedia_slugs": {}, "aliases": {}, "exclude": []}
    with open(OVERRIDES_PATH) as f:
        return json.load(f)


def collect_unique_persons(graphs: dict) -> dict:
    """Collect unique persons across all books from person_graphs.json."""
    persons = {}
    for book_id, g in graphs.items():
        for n in g["nodes"]:
            pid = n["id"]
            if pid not in persons:
                persons[pid] = {
                    "id": pid,
                    "name": n["name"],
                    "aliases": n.get("aliases", []),
                    "count": 0,
                    "subcategory": n.get("subcategory", ""),
                    "books": [],
                }
            persons[pid]["count"] += n.get("count", 0)
            persons[pid]["books"].append(book_id)
    return persons


def fetch_json(url: str, timeout: int = 10):
    """Fetch JSON from a URL with proper headers."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def fetch_wikipedia_summary(slug: str) -> dict | None:
    """Fetch Wikipedia summary for a given article slug."""
    encoded = urllib.parse.quote(slug, safe="")
    url = f"{WIKIPEDIA_SUMMARY_API}/{encoded}"
    return fetch_json(url)


def search_wikipedia(query: str) -> dict | None:
    """Search Wikipedia and return summary of the best result."""
    params = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 3,
    })
    url = f"{WIKIPEDIA_SEARCH_API}?{params}"
    data = fetch_json(url)
    if not data:
        return None

    results = data.get("query", {}).get("search", [])
    if not results:
        return None

    # Try the first result
    title = results[0]["title"]
    return fetch_wikipedia_summary(title.replace(" ", "_"))


def score_match(person_name: str, summary: dict) -> int:
    """Score how confident we are that a Wikipedia result matches our person."""
    if not summary:
        return 0

    score = 0
    desc = summary.get("description", "").lower()
    extract = summary.get("extract", "").lower()
    title = summary.get("title", "").lower()
    text = desc + " " + extract

    # Person indicators
    person_keywords = [
        "born", "died", "was a", "philosopher", "physician", "scientist",
        "naturalist", "botanist", "writer", "scholar", "king", "emperor",
        "author", "historian", "explorer", "theologian", "mathematician",
        "surgeon", "pharmacist", "pharmacologist", "apothecary", "alchemist",
        "psychologist", "physiologist", "biologist", "geographer", "astronomer",
        "chemist", "physicist", "anatomist", "zoologist", "entomologist",
        "geologist", "missionary", "navigator", "conquistador", "herbalist",
    ]
    for kw in person_keywords:
        if kw in text:
            score += 8

    # Name similarity
    pname = person_name.lower().split()[-1]  # surname
    if pname in title:
        score += 25

    # Has thumbnail
    if summary.get("thumbnail"):
        score += 10

    # Historical period markers (relevant for our premodern/early modern focus)
    period_markers = [
        "century", "ancient", "medieval", "renaissance", "early modern",
        "classical", "roman", "greek", "persian", "arab", "islamic",
    ]
    for marker in period_markers:
        if marker in text:
            score += 3

    return min(score, 100)


def get_thumbnail_url(summary: dict, width: int = THUMB_WIDTH) -> str | None:
    """Extract and resize thumbnail URL from Wikipedia summary."""
    thumb = summary.get("thumbnail", {})
    source = thumb.get("source")
    if not source:
        # Try originalimage
        orig = summary.get("originalimage", {})
        source = orig.get("source")
    if not source:
        return None

    # Resize to desired width via Wikimedia thumbnail URL pattern
    # e.g., .../300px-Image.jpg → .../200px-Image.jpg
    import re
    resized = re.sub(r"/\d+px-", f"/{width}px-", source)
    return resized


def download_thumbnail(url: str, filepath: Path, retries: int = 3) -> bool:
    """Download a thumbnail image to the given path with retry on 429."""
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
                if len(content) < 500:  # Too small, probably an error
                    return False
                with open(filepath, "wb") as f:
                    f.write(content)
                return True
        except urllib.request.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"    Download failed: {e}")
            return False
        except Exception as e:
            print(f"    Download failed: {e}")
            return False
    return False


def main():
    parser = argparse.ArgumentParser(description="Resolve person identities and download portraits")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write files")
    parser.add_argument("--skip-download", action="store_true", help="Resolve but don't download images")
    parser.add_argument("--force", action="store_true", help="Re-resolve all persons")
    parser.add_argument("--min-score", type=int, default=25, help="Minimum confidence score (default: 25)")
    args = parser.parse_args()

    # Load data
    print("Loading person graphs...")
    with open(PERSON_GRAPHS_PATH) as f:
        graphs = json.load(f)

    overrides = load_overrides()
    wiki_slugs = overrides.get("wikipedia_slugs", {})
    aliases = overrides.get("aliases", {})
    exclude = set(overrides.get("exclude", []))

    # Load existing identities if not forcing
    existing = {}
    if not args.force and OUTPUT_PATH.exists():
        with open(OUTPUT_PATH) as f:
            existing = json.load(f)
        print(f"  Loaded {len(existing)} existing identities")

    # Collect unique persons
    persons = collect_unique_persons(graphs)
    print(f"  {len(persons)} unique person IDs across {len(graphs)} books")

    # Create thumbnail directory
    if not args.dry_run and not args.skip_download:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)

    identities = {}
    resolved = 0
    skipped = 0
    failed = 0
    downloaded = 0

    for pid, person in sorted(persons.items(), key=lambda x: -x[1]["count"]):
        # Skip excluded non-persons
        if pid in exclude:
            skipped += 1
            continue

        # Resolve alias to canonical ID
        canonical_id = aliases.get(pid, pid)
        if canonical_id in exclude:
            skipped += 1
            continue

        # Check if already resolved (use cached result)
        if canonical_id in existing and not args.force:
            identities[pid] = existing[canonical_id].copy()
            if pid != canonical_id:
                identities[pid]["alias_of"] = canonical_id
            resolved += 1
            continue

        # If this is an alias and the canonical was already resolved this run
        if canonical_id != pid and canonical_id in identities:
            identities[pid] = identities[canonical_id].copy()
            identities[pid]["alias_of"] = canonical_id
            resolved += 1
            continue

        # Try to resolve via Wikipedia
        summary = None
        source = "auto"

        # 1. Try curated Wikipedia slug
        if canonical_id in wiki_slugs:
            slug = wiki_slugs[canonical_id]
            summary = fetch_wikipedia_summary(slug)
            source = "curated"
            time.sleep(0.1)

        # 2. Try direct slug from person name
        if not summary:
            name = person["name"]
            slug = name.replace(" ", "_")
            summary = fetch_wikipedia_summary(slug)
            source = "direct"
            time.sleep(0.1)

        # 3. Try search
        if not summary or score_match(person["name"], summary) < args.min_score:
            summary_search = search_wikipedia(person["name"])
            if summary_search and score_match(person["name"], summary_search) > score_match(person["name"], summary or {}):
                summary = summary_search
                source = "search"
            time.sleep(0.15)

        # Score the match
        score = score_match(person["name"], summary) if summary else 0

        if summary and score >= args.min_score:
            thumb_url = get_thumbnail_url(summary)
            wiki_title = summary.get("title", "")
            wiki_slug = wiki_title.replace(" ", "_")
            description = summary.get("description", "")

            # Determine thumbnail filename
            thumb_file = None
            if thumb_url:
                # Use canonical_id as filename
                ext = "jpg"
                if ".png" in thumb_url.lower():
                    ext = "png"
                elif ".svg" in thumb_url.lower():
                    ext = "svg"
                elif ".webp" in thumb_url.lower():
                    ext = "webp"
                thumb_file = f"{canonical_id}.{ext}"

                # Download thumbnail
                if not args.dry_run and not args.skip_download:
                    thumb_path = THUMB_DIR / thumb_file
                    if not thumb_path.exists() or args.force:
                        if download_thumbnail(thumb_url, thumb_path):
                            downloaded += 1
                            time.sleep(0.5)  # Respect Wikimedia rate limits
                        else:
                            thumb_file = None

            identity = {
                "name": wiki_title,
                "wikipedia_slug": wiki_slug,
                "description": description,
                "thumbnail": thumb_file,
                "confidence": score,
                "source": source,
            }

            identities[pid] = identity

            # If this is a canonical ID, also create entries for aliases
            for alias_id, canon in aliases.items():
                if canon == canonical_id and alias_id in persons and alias_id != pid:
                    identities[alias_id] = identity.copy()
                    identities[alias_id]["alias_of"] = canonical_id

            resolved += 1
            status = "+" if thumb_file else "~"
            print(f"  {status} {pid} -> {wiki_title} (score={score}, src={source}, thumb={'yes' if thumb_file else 'no'})")
        else:
            failed += 1
            if person["count"] >= 10:  # Only log notable failures
                print(f"  x {pid} ({person['name']}, count={person['count']}) -> no match (score={score})")

    print(f"\nResults:")
    print(f"  Resolved: {resolved}")
    print(f"  Failed:   {failed}")
    print(f"  Skipped:  {skipped} (excluded non-persons)")
    print(f"  Downloaded: {downloaded} thumbnails")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        # Show what would be written
        with_thumb = sum(1 for v in identities.values() if v.get("thumbnail"))
        print(f"  Would write {len(identities)} identities ({with_thumb} with thumbnails)")
        return

    # Write identities
    with open(OUTPUT_PATH, "w") as f:
        json.dump(identities, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(identities)} identities to {OUTPUT_PATH}")

    with_thumb = sum(1 for v in identities.values() if v.get("thumbnail"))
    print(f"  {with_thumb} with thumbnails")

    if THUMB_DIR.exists():
        thumbs = list(THUMB_DIR.glob("*.*"))
        total_kb = sum(t.stat().st_size for t in thumbs) / 1024
        print(f"  {len(thumbs)} thumbnail files ({total_kb:.0f} KB total)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build page maps: for each book, download Internet Archive djvu.xml,
extract per-page OCR text, match entity mention excerpts to IA scan pages.

Output: web/public/data/page_maps/{book_id}.json

Each output file contains:
{
  "ia_id": "...",
  "total_mentions": N,
  "matched": N,
  "leaves": { "offset": leaf_number, ... }
}

The frontend can then look up mention.offset → leaf number,
and construct https://archive.org/details/{ia_id}/page/n{leaf}
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

BASE_DIR = Path(__file__).resolve().parent.parent
ENTITY_DIR = BASE_DIR / "web" / "public" / "data"
OUTPUT_DIR = BASE_DIR / "web" / "public" / "data" / "page_maps"
CACHE_DIR = BASE_DIR / "data" / "page_maps"  # cache downloaded XML here

BOOKS = {
    "english_physician_1652": {
        "ia_id": "b30335310",
        "entity_file": "culpeper_entities.json",
    },
    "polyanthea_medicinal": {
        "ia_id": "b3040941x",
        "entity_file": "semedo_entities.json",
    },
    "coloquios_da_orta_1563": {
        "ia_id": "coloquiosdossimp01ortauoft",
        "entity_file": "orta_entities.json",
    },
    "historia_medicinal_monardes_1574": {
        "ia_id": "primeraysegunda01monagoog",
        "entity_file": "monardes_entities.json",
    },
    "relation_historique_humboldt_vol3_1825": {
        "ia_id": "relationhistoriq03humb",
        "entity_file": "humboldt_entities.json",
    },
    "ricettario_fiorentino_1597": {
        "ia_id": "hin-wel-all-00000667-001",
        "entity_file": "ricettario_entities.json",
    },
    "principles_of_psychology_james_1890": {
        "ia_id": "theprinciplesofp01jameuoft",
        "entity_file": "james_psychology_entities.json",
    },
}


def normalize(s: str) -> str:
    """Normalize whitespace, OCR artifacts, and lowercase for fuzzy matching."""
    s = s.lower()
    # Normalize long-s and common OCR variants
    s = s.replace("ſ", "s").replace("ﬁ", "fi").replace("ﬂ", "fl")
    s = s.replace("ê", "e").replace("ë", "e")
    # Strip accents that OCR may drop (basic normalization)
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def download_djvu_xml(ia_id: str) -> bytes:
    """Download djvu.xml from IA, with caching."""
    cache_path = CACHE_DIR / f"{ia_id}_djvu.xml"
    if cache_path.exists():
        print(f"  Using cached {cache_path.name}")
        return cache_path.read_bytes()

    url = f"https://archive.org/download/{ia_id}/{ia_id}_djvu.xml"
    print(f"  Downloading {url} ...")
    req = Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
    try:
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
    except URLError as e:
        print(f"  ERROR downloading: {e}")
        return b""

    print(f"  Downloaded {len(data) / 1024 / 1024:.1f} MB")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    return data


def parse_pages(xml_data: bytes) -> list[dict]:
    """Parse djvu.xml to extract per-page text. Returns [{leaf, text}, ...]."""
    root = ET.fromstring(xml_data)
    pages = []
    leaf = 0

    for obj in root.iter("OBJECT"):
        leaf += 1
        words = []
        hiddentext = obj.find("HIDDENTEXT")
        if hiddentext is not None:
            for word in hiddentext.iter("WORD"):
                if word.text:
                    words.append(word.text)

        pages.append({"leaf": leaf, "text": " ".join(words)})

    return pages


def build_page_index(pages: list[dict]) -> list[tuple[str, int]]:
    """Build normalized text → leaf index for searching."""
    index = []
    for p in pages:
        normed = normalize(p["text"])
        if len(normed) > 10:  # skip blank pages
            index.append((normed, p["leaf"]))
    return index


def find_page(excerpt: str, page_index: list[tuple[str, int]]) -> int | None:
    """Find which IA page contains the given excerpt text."""
    normed = normalize(excerpt)
    if len(normed) < 15:
        return None

    # Strategy 1: try a distinctive middle chunk (less likely to span pages)
    words = normed.split()
    if len(words) >= 8:
        mid = len(words) // 2
        chunk = " ".join(words[mid - 3 : mid + 3])
    elif len(words) >= 4:
        chunk = " ".join(words[1 : min(5, len(words))])
    else:
        chunk = normed

    for page_text, leaf in page_index:
        if chunk in page_text:
            return leaf

    # Strategy 2: try first 5 words
    if len(words) >= 5:
        chunk2 = " ".join(words[:5])
        for page_text, leaf in page_index:
            if chunk2 in page_text:
                return leaf

    # Strategy 3: try last 5 words
    if len(words) >= 5:
        chunk3 = " ".join(words[-5:])
        for page_text, leaf in page_index:
            if chunk3 in page_text:
                return leaf

    return None


def download_page_numbers(ia_id: str) -> dict[int, str]:
    """Download _page_numbers.json and return leaf → printed page number map."""
    cache_path = CACHE_DIR / f"{ia_id}_page_numbers.json"
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
    else:
        url = f"https://archive.org/download/{ia_id}/{ia_id}_page_numbers.json"
        print(f"  Downloading page numbers...")
        req = Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
            data = json.loads(raw)
            cache_path.write_bytes(raw)
        except Exception as e:
            print(f"  Page numbers not available: {e}")
            return {}

    leaf_to_page = {}
    for p in data.get("pages", []):
        pn = p.get("pageNumber", "")
        if pn and pn.strip():
            leaf_to_page[p["leafNum"]] = pn.strip()
    print(f"  {len(leaf_to_page)} leaves have printed page numbers")
    return leaf_to_page


def process_book(book_id: str, info: dict) -> dict:
    """Process a single book: download XML, parse pages, match mentions."""
    ia_id = info["ia_id"]
    entity_path = ENTITY_DIR / info["entity_file"]

    if not entity_path.exists():
        print(f"  Entity file not found: {entity_path}")
        return {"ia_id": ia_id, "total_mentions": 0, "matched": 0, "leaves": {}, "pages": {}}

    # Load entity data
    with open(entity_path) as f:
        entity_data = json.load(f)

    # Collect all mentions
    all_mentions = []
    for entity in entity_data["entities"]:
        for mention in entity.get("mentions", []):
            all_mentions.append(mention)

    print(f"  {len(all_mentions)} total mentions")
    if not all_mentions:
        return {"ia_id": ia_id, "total_mentions": 0, "matched": 0, "leaves": {}, "pages": {}}

    # Download and parse IA pages
    xml_data = download_djvu_xml(ia_id)
    if not xml_data:
        return {"ia_id": ia_id, "total_mentions": len(all_mentions), "matched": 0, "leaves": {}, "pages": {}}

    pages = parse_pages(xml_data)
    print(f"  {len(pages)} IA pages parsed")

    page_index = build_page_index(pages)
    print(f"  {len(page_index)} pages with text")

    # Download leaf → printed page number mapping
    leaf_to_page = download_page_numbers(ia_id)

    # Match mentions to pages
    leaves = {}
    page_nums = {}
    matched = 0
    for mention in all_mentions:
        excerpt = mention.get("excerpt", "")
        offset = mention.get("offset")
        if offset is None or not excerpt:
            continue

        leaf = find_page(excerpt, page_index)
        if leaf is not None:
            offset_str = str(offset)
            leaves[offset_str] = leaf
            matched += 1
            # Add printed page number if available
            printed = leaf_to_page.get(leaf)
            if printed:
                page_nums[offset_str] = printed

    print(f"  Matched {matched}/{len(all_mentions)} mentions ({100*matched/max(len(all_mentions),1):.1f}%)")
    print(f"  {len(page_nums)} have printed page numbers")

    return {
        "ia_id": ia_id,
        "total_mentions": len(all_mentions),
        "matched": matched,
        "leaves": leaves,
        "pages": page_nums,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build IA page maps for entity mentions")
    parser.add_argument("--book", type=str, help="Process only this book ID")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output files")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    books_to_process = {args.book: BOOKS[args.book]} if args.book else BOOKS

    for book_id, info in books_to_process.items():
        print(f"\n{'='*60}")
        print(f"Processing: {book_id}")
        print(f"{'='*60}")

        result = process_book(book_id, info)

        if not args.dry_run:
            out_path = OUTPUT_DIR / f"{book_id}.json"
            with open(out_path, "w") as f:
                json.dump(result, f)
            size_kb = out_path.stat().st_size / 1024
            print(f"  Wrote {out_path.name} ({size_kb:.0f} KB)")
        else:
            print(f"  [DRY RUN] Would write {book_id}.json")

    print(f"\nDone!")


if __name__ == "__main__":
    main()

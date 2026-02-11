#!/usr/bin/env python3
"""
Enrich concordance clusters with Wikipedia extracts.

For each cluster, fetches a 4-6 sentence Wikipedia summary using the
modern_name (or linnaean/canonical_name as fallback) and stores it in
ground_truth.wikipedia_extract.

This text is then used by build_search_index.py to produce richer
embeddings and better lexical matching.

Usage:
    python3 scripts/enrich_wikipedia.py
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak4")

# Wikipedia API endpoints
SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
EXTRACT_API = (
    "https://{lang}.wikipedia.org/w/api.php"
    "?action=query&titles={title}&prop=extracts"
    "&explaintext=true&exsectionformat=plain&format=json&origin=*"
)

DELAY = 0.2  # seconds between requests (Wikipedia allows 200 req/sec)
MAX_SENTENCES = 6


def fetch_json(url: str) -> dict | None:
    """Fetch JSON from a URL, returning None on error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None


def resolve_wikipedia_title(search_terms: list[str]) -> tuple[str, str] | None:
    """Try to resolve a Wikipedia article title from search terms.

    Returns (lang, title) or None.
    """
    for term in search_terms:
        if not term:
            continue
        encoded = urllib.parse.quote(term.replace(" ", "_"))
        data = fetch_json(SUMMARY_API.format(encoded))
        if not data:
            time.sleep(0.3)
            continue
        # Skip disambiguation pages
        if data.get("type") == "disambiguation":
            time.sleep(0.3)
            continue
        # Got a real article
        title = data.get("title")
        if title:
            return ("en", title)
        time.sleep(0.3)
    return None


def fetch_extract(lang: str, title: str) -> str | None:
    """Fetch the full plain-text extract for a Wikipedia article."""
    encoded_title = urllib.parse.quote(title)
    url = EXTRACT_API.format(lang=lang, title=encoded_title)
    data = fetch_json(url)
    if not data:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page_id, page_data in pages.items():
        if page_id == "-1":
            return None
        extract = page_data.get("extract", "")
        if extract:
            return extract
    return None


def truncate_to_sentences(text: str, max_sentences: int = MAX_SENTENCES) -> str:
    """Extract the first N sentences from text.

    Splits on sentence boundaries (. ! ?) followed by whitespace.
    Filters out very short fragments and section headers.
    """
    # Take first ~2000 chars to avoid processing huge articles
    text = text[:2000]

    # Split into paragraphs, take the first substantive ones
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    # Filter out short fragments (section headers, etc.)
    paragraphs = [p for p in paragraphs if len(p) > 40]

    if not paragraphs:
        return ""

    # Join paragraphs and split into sentences
    joined = " ".join(paragraphs)
    # Sentence boundary: period/exclamation/question followed by space and uppercase
    # or end of string
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', joined)

    # Take first N sentences
    selected = sentences[:max_sentences]
    result = " ".join(selected).strip()

    # Ensure it ends with punctuation
    if result and result[-1] not in ".!?":
        # Find last sentence boundary
        last_period = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
        if last_period > 0:
            result = result[:last_period + 1]

    return result


def main():
    # Load concordance
    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Backup
    print(f"Backing up to {BACKUP_PATH}")
    with open(BACKUP_PATH, "w") as f:
        json.dump(data, f)

    # Count existing extracts
    already_have = sum(
        1 for c in clusters
        if c.get("ground_truth", {}).get("wikipedia_extract")
    )
    print(f"  {already_have} clusters already have wikipedia_extract")

    # Process clusters
    enriched = 0
    failed = 0
    skipped = 0

    for i, cluster in enumerate(clusters):
        gt = cluster.get("ground_truth", {})
        name = cluster["canonical_name"]

        # Skip if already enriched
        if gt.get("wikipedia_extract"):
            skipped += 1
            continue

        # Build search terms (best to worst)
        search_terms = []
        if gt.get("linnaean"):
            search_terms.append(gt["linnaean"])
        if gt.get("modern_name") and gt["modern_name"] != name:
            search_terms.append(gt["modern_name"])
        search_terms.append(gt.get("modern_name", name))
        # Also try canonical name if different
        if name.lower() != (gt.get("modern_name") or "").lower():
            search_terms.append(name)

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for t in search_terms:
            if not t:
                continue
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                unique_terms.append(t)

        if (i + 1) % 50 == 0 or i == 0:
            print(f"\n[{i+1}/{len(clusters)}] Processing '{name}' (enriched={enriched}, failed={failed})...")

        # Step 1: Resolve Wikipedia title
        result = resolve_wikipedia_title(unique_terms)
        if not result:
            failed += 1
            time.sleep(DELAY * 0.5)
            continue

        lang, title = result

        # Step 2: Fetch full extract
        extract = fetch_extract(lang, title)
        if not extract:
            failed += 1
            time.sleep(DELAY)
            continue

        # Step 3: Truncate to ~6 sentences
        summary = truncate_to_sentences(extract, MAX_SENTENCES)
        if not summary or len(summary) < 30:
            failed += 1
            time.sleep(DELAY)
            continue

        # Store it
        gt["wikipedia_extract"] = summary
        cluster["ground_truth"] = gt
        enriched += 1

        if enriched <= 5 or enriched % 100 == 0:
            print(f"  ✓ {name} → {title}: {summary[:80]}...")

        # Checkpoint save every 100 enrichments to avoid losing progress on crash
        if enriched % 100 == 0 and enriched > 0:
            print(f"  [checkpoint] Saving {enriched} new enrichments to disk...")
            with open(CONCORDANCE_PATH, "w") as f:
                json.dump(data, f, ensure_ascii=False)

        time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"Results: {enriched} enriched, {failed} failed, {skipped} skipped")
    print(f"Total with extract: {enriched + already_have}/{len(clusters)}")

    # Save
    print(f"\nSaving to {CONCORDANCE_PATH}...")
    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB")
    print("\nDone! Now rebuild the search index:")
    print("  python3 scripts/build_search_index.py")


if __name__ == "__main__":
    main()

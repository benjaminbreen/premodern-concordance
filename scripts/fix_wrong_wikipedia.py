#!/usr/bin/env python3
"""
Fix clusters that got matched to the wrong Wikipedia article.

Two actions:
1. CLEAR: Remove bad wikipedia_extract/wikidata fields for clusters that
   matched to journals, modern people, films, etc.
2. CORRECT: For important clusters, manually set the right Wikipedia title
   and re-fetch the correct extract.

Usage:
    python3 scripts/fix_wrong_wikipedia.py [--dry-run]
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
DRY_RUN = "--dry-run" in sys.argv

# ── Clusters to CLEAR (bad wikipedia_extract, wrong article) ──
# These matched to modern people, journals, films, etc.
# Format: canonical_name → reason
CLEAR_EXTRACT = {
    # Journals / periodicals
    "round": "matched to fitness magazine",
    "Pulp": "matched to Pulp Fiction",
    "Fascination": "matched to TV show",
    # Modern people (footballers, wrestlers, etc.)
    "emplastro": "matched to Portuguese footballer",
    "pólvora": "matched to Mexican wrestler Pólvora",
    "abelha": "matched to Brazilian footballer",
    "tiburones": "matched to Ricky Martin song",
    "Chesnut": "matched to modern person, not chestnut tree",
    # Films / TV / media
    "freneticos": "matched to Hitchcock's Frenzy (1972)",
    "neiges perpétuelles": "matched to Snow White film",
    "comer": "matched to TV show ALF",
    "pureté": "matched to Mary Douglas book (1966)",
    # Wrong concept entirely
    "Hayhay": "wrong geographic match",
    "Falattouaroc": "OCR artifact, bad match",
}

# ── Clusters to CORRECT (set right Wikipedia title + re-fetch) ──
# Format: canonical_name → correct English Wikipedia title
CORRECT_TITLE = {
    "Evolution": "Evolution",  # concept, not the journal
    "storms": "Storm",
    "celestial body": "Astronomical object",
    "nebula": "Nebula",
    "blood": "Blood",
    "organ": "Organ (biology)",
    "fusion": "Nuclear fusion",
    "alcohol": "Alcohol",
    "pitch": "Pitch (resin)",
    "Conserve": "Fruit preserves",
    "magnetic needle": "Compass",
    "measurement": "Measurement",
    "floraison": "Flowering plant",
    "silence": "Silence",
    "experiment": "Experiment",
    "poetry": "Poetry",
    "mosses": "Moss",
}

SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
EXTRACT_API = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&titles={title}&prop=extracts"
    "&explaintext=true&exsectionformat=plain&format=json&origin=*"
)
MAX_SENTENCES = 6


def fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def fetch_correct_extract(title: str) -> tuple[str, str] | None:
    """Fetch summary + extract for a specific Wikipedia title."""
    encoded = urllib.parse.quote(title.replace(" ", "_"))

    # Get summary for description
    summary_data = fetch_json(SUMMARY_API.format(encoded))
    description = ""
    if summary_data and summary_data.get("type") != "disambiguation":
        description = summary_data.get("description", "")

    # Get full extract
    url = EXTRACT_API.format(title=urllib.parse.quote(title))
    data = fetch_json(url)
    if not data:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page_id, page_data in pages.items():
        if page_id == "-1":
            return None
        extract = page_data.get("extract", "")
        if extract:
            # Truncate to ~6 sentences
            import re
            text = extract[:2000]
            paragraphs = [p.strip() for p in text.split("\n") if p.strip() and len(p.strip()) > 40]
            if not paragraphs:
                return None
            joined = " ".join(paragraphs)
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', joined)
            result = " ".join(sentences[:MAX_SENTENCES]).strip()
            if result and result[-1] not in ".!?":
                last_period = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
                if last_period > 0:
                    result = result[:last_period + 1]
            return (result, description)
    return None


def main():
    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    by_name = {c["canonical_name"]: c for c in clusters}
    print(f"  {len(clusters)} clusters")

    # ── 1. CLEAR bad extracts ──
    cleared = 0
    for name, reason in CLEAR_EXTRACT.items():
        if name not in by_name:
            print(f"  WARNING: not found: \"{name}\"")
            continue
        c = by_name[name]
        gt = c.get("ground_truth", {})
        had_extract = bool(gt.get("wikipedia_extract"))
        if had_extract:
            del gt["wikipedia_extract"]
            # Also clear wikidata fields if they came from the wrong match
            for key in ["wikidata_id", "wikidata_description", "wikipedia_url"]:
                if key in gt:
                    del gt[key]
            cleared += 1
            print(f"  CLEAR: id={c['id']} \"{name}\" — {reason}")
        else:
            # Check if just wikidata_description is wrong
            wd_desc = (gt.get("wikidata_description") or "").lower()
            if any(w in wd_desc for w in ["journal", "periodical", "magazine"]):
                for key in ["wikidata_id", "wikidata_description", "wikipedia_url"]:
                    if key in gt:
                        del gt[key]
                cleared += 1
                print(f"  CLEAR (wd only): id={c['id']} \"{name}\" — {reason}")

    print(f"\n  Cleared: {cleared}")

    # ── 2. CORRECT important clusters ──
    corrected = 0
    for name, wiki_title in CORRECT_TITLE.items():
        if name not in by_name:
            print(f"  WARNING: not found: \"{name}\"")
            continue
        c = by_name[name]
        gt = c.get("ground_truth", {})

        if DRY_RUN:
            print(f"  WOULD CORRECT: id={c['id']} \"{name}\" → {wiki_title}")
            corrected += 1
            continue

        print(f"  CORRECTING: id={c['id']} \"{name}\" → {wiki_title}...", end=" ", flush=True)
        result = fetch_correct_extract(wiki_title)
        if result:
            extract_text, description = result
            gt["wikipedia_extract"] = extract_text
            if description:
                gt["wikidata_description"] = description
            gt["wikipedia_url"] = f"https://en.wikipedia.org/wiki/{wiki_title.replace(' ', '_')}"
            c["ground_truth"] = gt
            corrected += 1
            print(f"OK ({len(extract_text)} chars)")
        else:
            print("FAILED")
        time.sleep(0.3)

    print(f"\n  Corrected: {corrected}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"Summary: {cleared} cleared, {corrected} corrected")

    if DRY_RUN:
        print("\n  DRY RUN — no changes saved")
        return

    print(f"\nSaving to {CONCORDANCE_PATH}...")
    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB")
    print("\nDone! Rebuild search index:")
    print("  python3 scripts/build_search_index.py")


if __name__ == "__main__":
    main()

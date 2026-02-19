#!/usr/bin/env python3
"""
Fix bad Wikidata QIDs and miscategorized PERSON clusters.

Strategy:
1. For clusters with BOTH wikipedia_url AND wikidata_id:
   Extract the correct QID from the Wikipedia article's Wikidata sitelink.
   If it differs from the current wikidata_id, replace it and fetch fresh description.

2. For clusters with suspicious wikidata_description but no wikipedia_url:
   Clear the bad wikidata_id and wikidata_description (better to have none than wrong).

3. Recategorize occupations/collectives/generics from PERSON → CONCEPT.

Usage:
    python3 scripts/fix_wikidata_and_categories.py [--dry-run]
"""

import json
import sys
import time
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime

CONC_PATH = Path("web/public/data/concordance.json")

# Suspicious phrases in wikidata_description that indicate a bad QID match
BAD_DESCRIPTION_PHRASES = [
    "family name", "given name", "scholarly article", "scientific article",
    "street", "Peerage", "commune", "municipality", "human settlement",
    "census-designated place", "Wikimedia", "village", "internet personality",
    "basketball", "unincorporated community", "television", "film",
    "video game", "magazine", "surname", "disambiguation",
    "album", "song", "band", "TV series", "manga", "anime",
    "railway station", "metro station", "asteroid",
    # Genus/species/taxon mismatches (very common failure mode)
    "genus of beetles", "genus of insects", "genus of moths", "genus of spiders",
    "genus of flies", "genus of wasps", "genus of ants", "genus of snails",
    "genus of fungi", "genus of algae", "genus of bacteria", "genus of mites",
    "genus of crustaceans", "genus of nematodes", "genus of fish",
    "genus of sea slugs", "genus of sea snails", "genus of land snails",
    "genus of gastropods", "genus of bivalves", "genus of polychaetes",
    "genus of lizards", "genus of frogs", "genus of ticks",
    # Modern/irrelevant matches
    "electoral district", "football", "wrestler", "singer",
    "actor", "actress", "rapper", "youtuber", "podcast",
    "county in", "township in", "borough", "unincorporated",
    "CDU politician", "politician", "Olympic",
]

# Category-aware bad phrases: these are suspicious ONLY for certain categories
# e.g., "genus of plants" is fine for PLANT clusters, but wrong for PLACE/CONCEPT/etc.
CATEGORY_BAD_PHRASES = {
    # For non-PLANT, non-ANIMAL clusters, any genus/species/taxon is wrong
    "genus of plants": {"PLACE", "CONCEPT", "SUBSTANCE", "PERSON", "DISEASE", "OBJECT"},
    "genus of": {"PLACE", "CONCEPT", "SUBSTANCE", "PERSON", "DISEASE", "OBJECT"},
    "species of": {"PLACE", "CONCEPT", "SUBSTANCE", "PERSON", "DISEASE", "OBJECT"},
    "family of": {"PLACE", "CONCEPT", "PERSON", "DISEASE", "OBJECT"},
    "taxon": {"PLACE", "CONCEPT", "SUBSTANCE", "PERSON", "DISEASE", "OBJECT"},
}

# PERSON clusters that should be recategorized to CONCEPT
# Maps modern_name (lowercased) → True
RECAT_TO_CONCEPT = {
    # Occupations
    "physician", "physicians", "doctor", "doctors", "surgeon", "surgeons",
    "chemist", "chemists", "apothecary", "apothecaries", "naturalist", "naturalists",
    "botanist", "botanists", "philosopher", "philosophers", "priest", "priests",
    "merchants", "merchant", "monk", "monks", "scholars", "scholar",
    "author", "authors",
    # Ethnic/national groups
    "greeks", "ancient greeks", "romans", "spaniards", "turks", "moors",
    "english people", "portuguese people", "europeans", "arab physicians",
    "indigenous peoples", "indigenous peoples of the americas",
    # Generic human terms
    "god", "woman", "women", "child", "children", "human being", "human",
    "humans", "king", "emperor", "individuals", "organism", "people",
    "man", "men",
}


def fetch_json(url, retries=2):
    """Fetch JSON from URL with retries and rate limiting."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(2)
            else:
                return None


def get_qid_from_wikipedia(wiki_url):
    """Extract the correct Wikidata QID from a Wikipedia article URL."""
    try:
        url_obj = urllib.parse.urlparse(wiki_url)
        lang = url_obj.hostname.split(".")[0]
        title = urllib.parse.unquote(url_obj.path.split("/wiki/")[1])
    except (AttributeError, IndexError):
        return None, None

    # Use Wikipedia API to get Wikidata item
    api_url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        f"action=query&titles={urllib.parse.quote(title)}&prop=pageprops&ppprop=wikibase_item&format=json"
    )
    data = fetch_json(api_url)
    if not data:
        return None, None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        qid = page.get("pageprops", {}).get("wikibase_item")
        if qid:
            return qid, None
    return None, None


def get_wikidata_description(qid):
    """Fetch the English description for a Wikidata QID."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={qid}&props=descriptions&languages=en&format=json"
    data = fetch_json(url)
    if not data:
        return None
    entities = data.get("entities", {})
    entity = entities.get(qid, {})
    desc = entity.get("descriptions", {}).get("en", {}).get("value")
    return desc


def is_suspicious_description(desc, category=None):
    """Check if a wikidata_description looks like a bad match."""
    if not desc:
        return False
    desc_lower = desc.lower()
    for phrase in BAD_DESCRIPTION_PHRASES:
        if phrase.lower() in desc_lower:
            return True
    # Category-aware checks
    if category:
        for phrase, bad_cats in CATEGORY_BAD_PHRASES.items():
            if category in bad_cats and phrase.lower() in desc_lower:
                return True
    return False


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading {CONC_PATH}...")
    with open(CONC_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Total clusters: {len(clusters)}")

    # Stats
    stats = {
        "qid_fixed_via_wikipedia": 0,
        "qid_cleared_suspicious": 0,
        "qid_already_correct": 0,
        "qid_no_wikipedia": 0,
        "recategorized": 0,
        "errors": 0,
    }

    log = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "qid_fixes": [],
        "qid_clears": [],
        "recategorizations": [],
    }

    # ── Phase 1: Fix Wikidata QIDs via Wikipedia cross-check ──
    print("\n── Phase 1: Cross-checking Wikidata QIDs against Wikipedia ──")

    clusters_with_both = [
        c for c in clusters
        if c.get("ground_truth", {}).get("wikipedia_url")
        and c.get("ground_truth", {}).get("wikidata_id")
    ]
    print(f"Clusters with both wikipedia_url and wikidata_id: {len(clusters_with_both)}")

    # Check ALL clusters with both, not just suspicious ones — many have
    # normal descriptions but the QID is still wrong (the Wikipedia URL is
    # the more reliable source of truth)
    suspicious_with_wiki = clusters_with_both
    print(f"Checking all {len(suspicious_with_wiki)} for QID/URL mismatch")

    for i, cluster in enumerate(suspicious_with_wiki):
        gt = cluster["ground_truth"]
        old_qid = gt["wikidata_id"]
        wiki_url = gt["wikipedia_url"]
        old_desc = gt.get("wikidata_description", "")

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(suspicious_with_wiki)}] checking...")

        correct_qid, _ = get_qid_from_wikipedia(wiki_url)
        time.sleep(0.3)  # Rate limiting

        if correct_qid and correct_qid != old_qid:
            # Fetch the correct description
            new_desc = get_wikidata_description(correct_qid)
            time.sleep(0.3)

            log["qid_fixes"].append({
                "cluster_id": cluster["id"],
                "canonical_name": cluster["canonical_name"],
                "old_qid": old_qid,
                "old_desc": old_desc,
                "new_qid": correct_qid,
                "new_desc": new_desc,
                "wikipedia_url": wiki_url,
            })

            if not dry_run:
                gt["wikidata_id"] = correct_qid
                if new_desc:
                    gt["wikidata_description"] = new_desc

            stats["qid_fixed_via_wikipedia"] += 1
            print(f"  FIX: [{cluster['id']}] {cluster['canonical_name']}: {old_qid} ({old_desc[:40]}...) → {correct_qid} ({(new_desc or '')[:40]}...)")
        elif correct_qid and correct_qid == old_qid:
            stats["qid_already_correct"] += 1
        else:
            stats["errors"] += 1

    # ── Phase 2: Clear suspicious QIDs on clusters WITHOUT wikipedia_url ──
    print("\n── Phase 2: Clearing suspicious QIDs without Wikipedia backup ──")

    clusters_suspicious_no_wiki = [
        c for c in clusters
        if c.get("ground_truth", {}).get("wikidata_id")
        and not c.get("ground_truth", {}).get("wikipedia_url")
        and is_suspicious_description(c.get("ground_truth", {}).get("wikidata_description", ""), c.get("category"))
    ]
    print(f"Suspicious QIDs without Wikipedia URL: {len(clusters_suspicious_no_wiki)}")

    for cluster in clusters_suspicious_no_wiki:
        gt = cluster["ground_truth"]
        old_qid = gt.get("wikidata_id", "")
        old_desc = gt.get("wikidata_description", "")

        log["qid_clears"].append({
            "cluster_id": cluster["id"],
            "canonical_name": cluster["canonical_name"],
            "old_qid": old_qid,
            "old_desc": old_desc,
        })

        if not dry_run:
            gt.pop("wikidata_id", None)
            gt.pop("wikidata_description", None)

        stats["qid_cleared_suspicious"] += 1

    # ── Phase 3: Recategorize PERSON → CONCEPT ──
    print("\n── Phase 3: Recategorizing occupations/collectives/generics ──")

    for cluster in clusters:
        if cluster["category"] != "PERSON":
            continue
        gt = cluster.get("ground_truth", {})
        modern = (gt.get("modern_name") or cluster["canonical_name"]).lower().strip()

        if modern in RECAT_TO_CONCEPT:
            log["recategorizations"].append({
                "cluster_id": cluster["id"],
                "canonical_name": cluster["canonical_name"],
                "modern_name": gt.get("modern_name"),
                "old_category": "PERSON",
                "new_category": "CONCEPT",
            })

            if not dry_run:
                cluster["category"] = "CONCEPT"
                cluster["subcategory"] = "CONCEPT"
                for member in cluster["members"]:
                    member["category"] = "CONCEPT"
                    member["subcategory"] = "CONCEPT"

            stats["recategorized"] += 1
            print(f"  RECAT: [{cluster['id']}] {cluster['canonical_name']} ({modern}) PERSON → CONCEPT")

    # ── Summary ──
    print("\n── Summary ──")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if not dry_run:
        # Backup
        backup = CONC_PATH.with_suffix(f".json.bak_wikidata_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        print(f"\nBacking up to {backup}...")
        import shutil
        shutil.copy2(CONC_PATH, backup)

        # Save
        print(f"Saving {CONC_PATH}...")
        with open(CONC_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        print("Done!")
    else:
        print("\n[DRY RUN — no changes written]")

    # Save log
    log_path = Path("data/wikidata_fix_log.json")
    log["stats"] = stats
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print(f"Log saved to {log_path}")


if __name__ == "__main__":
    main()

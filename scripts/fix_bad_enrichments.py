#!/usr/bin/env python3
"""
Fix bad Wikidata QIDs and Wikipedia URLs across the concordance.

The enrichment pipeline sometimes matches entities to surname/name disambiguation
pages instead of the actual concept. This script:

1. Clears ALL wikidata_id + wikidata_description that match suspicious phrases
   (family name, given name, surname, disambiguation, etc.)
2. Fixes wikipedia_urls pointing to surname/name pages by stripping the suffix
   and looking up the correct article
3. For corrected URLs, fetches the correct Wikidata QID

Usage:
    python3 scripts/fix_bad_enrichments.py [--dry-run]
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

CONC_PATH = Path("web/public/data/concordance.json")

BAD_DESCRIPTION_PHRASES = [
    "family name", "given name", "surname", "scholarly article", "scientific article",
    "street", "peerage", "commune", "municipality", "human settlement",
    "census-designated place", "wikimedia", "village", "internet personality",
    "basketball", "unincorporated community", "television", "film",
    "video game", "magazine", "disambiguation", "album", "song", "band",
    "TV series", "manga", "anime", "railway station", "metro station",
    "football", "soccer", "rapper", "singer", "actor", "actress",
    "unisex given name", "female given name", "male given name",
]

# Wikipedia URL suffixes that indicate a wrong article
BAD_WIKI_SUFFIXES = [
    "_(surname)", "_(name)", "_(given_name)", "_(family_name)",
    "_(disambiguation)", "_(film)", "_(TV_series)", "_(band)",
    "_(album)", "_(song)", "_(video_game)",
]


def fetch_json(url, retries=2):
    """Fetch JSON from URL with retries."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(2)
    return None


def get_qid_from_wikipedia(wiki_url):
    """Extract the Wikidata QID from a Wikipedia article URL."""
    try:
        url_obj = urllib.parse.urlparse(wiki_url)
        lang = url_obj.hostname.split(".")[0]
        title = urllib.parse.unquote(url_obj.path.split("/wiki/")[1])
    except (AttributeError, IndexError):
        return None

    api_url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        f"action=query&titles={urllib.parse.quote(title)}&prop=pageprops&ppprop=wikibase_item&format=json"
    )
    data = fetch_json(api_url)
    if not data:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if page.get("missing") is not None:
            return None
        qid = page.get("pageprops", {}).get("wikibase_item")
        if qid:
            return qid
    return None


def get_wikidata_description(qid):
    """Fetch English description for a Wikidata QID."""
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={qid}&props=descriptions&languages=en&format=json"
    data = fetch_json(url)
    if not data:
        return None
    return data.get("entities", {}).get(qid, {}).get("descriptions", {}).get("en", {}).get("value")


def is_bad_description(desc):
    """Check if a wikidata_description indicates a bad match."""
    if not desc:
        return False
    desc_lower = desc.lower()
    return any(phrase in desc_lower for phrase in BAD_DESCRIPTION_PHRASES)


def fix_wikipedia_url(url):
    """Try to fix a bad Wikipedia URL by removing surname/name suffix."""
    if not url:
        return None

    decoded = urllib.parse.unquote(url)
    # Normalize spaces/underscores for matching
    normalized = decoded.replace(" ", "_")
    for suffix in BAD_WIKI_SUFFIXES:
        if suffix in normalized:
            # Remove the suffix (handle both space and underscore variants)
            fixed = decoded
            for sep in [" ", "_", "%20"]:
                space_suffix = suffix.replace("_", sep)
                if space_suffix in fixed:
                    fixed = fixed.replace(space_suffix, "")
                    break
            else:
                # Try normalized version
                fixed = normalized.replace(suffix, "").replace("_", " ")
                # Reconstruct proper URL
                parts = urllib.parse.urlparse(url)
                path_parts = parts.path.split("/wiki/")
                if len(path_parts) == 2:
                    title = urllib.parse.unquote(path_parts[1]).replace(suffix.replace("_", " "), "")
                    fixed = f"https://{parts.hostname}/wiki/{urllib.parse.quote(title)}"
                    return fixed
            return fixed

    return None


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading {CONC_PATH}...")
    with open(CONC_PATH) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Total clusters: {len(clusters)}")

    stats = {
        "qid_cleared": 0,
        "wiki_url_fixed": 0,
        "wiki_url_cleared": 0,
        "qid_refetched": 0,
        "wiki_extract_cleared": 0,
        "already_clean": 0,
    }
    log_entries = []

    # Find all clusters with bad descriptions
    bad_clusters = []
    for c in clusters:
        gt = c.get("ground_truth") or {}
        desc = gt.get("wikidata_description") or ""
        if is_bad_description(desc):
            bad_clusters.append(c)

    print(f"Clusters with bad wikidata_description: {len(bad_clusters)}")

    # Also find clusters with bad wikipedia_urls even if description is clean
    bad_wiki_only = []
    for c in clusters:
        if c in bad_clusters:
            continue
        gt = c.get("ground_truth") or {}
        wiki_url = gt.get("wikipedia_url") or ""
        decoded = urllib.parse.unquote(wiki_url)
        if any(suffix in decoded for suffix in BAD_WIKI_SUFFIXES):
            bad_wiki_only.append(c)

    print(f"Additional clusters with bad wikipedia_url: {len(bad_wiki_only)}")
    all_bad = bad_clusters + bad_wiki_only
    print(f"Total to fix: {len(all_bad)}")

    # Track how many need API calls for URL fixes
    url_fix_candidates = 0

    for i, cluster in enumerate(all_bad):
        gt = cluster.get("ground_truth") or {}
        cid = cluster["id"]
        cname = cluster.get("canonical_name", "?")
        old_qid = gt.get("wikidata_id", "")
        old_desc = gt.get("wikidata_description", "")
        old_wiki = gt.get("wikipedia_url", "")

        entry = {
            "cluster_id": cid,
            "canonical_name": cname,
            "old_qid": old_qid,
            "old_desc": old_desc,
            "old_wiki_url": old_wiki,
            "actions": [],
        }

        # Step 1: Clear bad QID and description
        if old_qid or is_bad_description(old_desc):
            if not dry_run:
                gt.pop("wikidata_id", None)
                gt.pop("wikidata_description", None)
            entry["actions"].append("cleared_qid_and_desc")
            stats["qid_cleared"] += 1

        # Step 2: Fix bad Wikipedia URL
        if old_wiki:
            fixed_url = fix_wikipedia_url(old_wiki)
            if fixed_url:
                url_fix_candidates += 1
                # Try the fixed URL — check if it exists via API
                new_qid = get_qid_from_wikipedia(fixed_url)
                time.sleep(0.3)

                if new_qid:
                    new_desc = get_wikidata_description(new_qid)
                    time.sleep(0.3)

                    # Make sure the new description isn't also bad
                    if not is_bad_description(new_desc):
                        if not dry_run:
                            gt["wikipedia_url"] = fixed_url
                            gt["wikidata_id"] = new_qid
                            if new_desc:
                                gt["wikidata_description"] = new_desc
                        entry["actions"].append(f"fixed_wiki_url → {fixed_url}")
                        entry["new_qid"] = new_qid
                        entry["new_desc"] = new_desc
                        stats["wiki_url_fixed"] += 1
                        stats["qid_refetched"] += 1
                    else:
                        # Fixed URL also points to junk — clear everything
                        if not dry_run:
                            gt.pop("wikipedia_url", None)
                            gt.pop("wikipedia_extract", None)
                        entry["actions"].append("cleared_wiki_url (fixed URL also bad)")
                        stats["wiki_url_cleared"] += 1
                        stats["wiki_extract_cleared"] += 1
                else:
                    # Fixed URL doesn't exist — clear the bad URL
                    if not dry_run:
                        gt.pop("wikipedia_url", None)
                        gt.pop("wikipedia_extract", None)
                    entry["actions"].append("cleared_wiki_url (fixed URL not found)")
                    stats["wiki_url_cleared"] += 1
                    stats["wiki_extract_cleared"] += 1
            else:
                # Wikipedia URL isn't a surname/name page but description was bad
                # Check if the existing URL is actually correct
                decoded = urllib.parse.unquote(old_wiki)
                is_bad_url = any(suffix in decoded for suffix in BAD_WIKI_SUFFIXES)
                if is_bad_url:
                    if not dry_run:
                        gt.pop("wikipedia_url", None)
                        gt.pop("wikipedia_extract", None)
                    entry["actions"].append("cleared_wiki_url (bad suffix)")
                    stats["wiki_url_cleared"] += 1
                    stats["wiki_extract_cleared"] += 1

        log_entries.append(entry)
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(all_bad)}] processed...")

    # Also handle special cases: wikipedia_url is fine but points to wrong topic
    # (e.g., Volcano, Hawaii instead of volcanos)
    # These have bad descriptions but non-surname wiki URLs
    for cluster in all_bad:
        gt = cluster.get("ground_truth") or {}
        wiki_url = gt.get("wikipedia_url", "")
        if not wiki_url:
            continue
        decoded = urllib.parse.unquote(wiki_url)
        # Check for geographic mismatch patterns
        mismatches = [
            ",_Colorado", ",_Hawaii", ",_Virginia", ",_California",
            ",_Nueva_Ecija", ",_Zamboanga", ",_Nova_Scotia", ",_Finland",
            ",_Netherlands", ",_Gloucestershire",
            "Extremadura", "Molières-sur-Cèze",
        ]
        for pattern in mismatches:
            if pattern in decoded:
                if not dry_run:
                    gt.pop("wikipedia_url", None)
                    gt.pop("wikipedia_extract", None)
                    gt.pop("wikidata_id", None)
                    gt.pop("wikidata_description", None)
                stats["wiki_url_cleared"] += 1
                stats["wiki_extract_cleared"] += 1
                break

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if not dry_run:
        # Backup
        import shutil
        backup = CONC_PATH.with_suffix(f".bak_enrichfix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        print(f"\nBacking up to {backup}...")
        shutil.copy2(CONC_PATH, backup)

        # Save
        print(f"Saving {CONC_PATH}...")
        with open(CONC_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        print("Done!")
    else:
        print("\n[DRY RUN — no changes written]")

    # Save log
    log_path = Path("data/enrichment_fix_log.json")
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "stats": stats,
        "fixes": log_entries,
    }
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
    print(f"Log saved to {log_path}")


if __name__ == "__main__":
    main()

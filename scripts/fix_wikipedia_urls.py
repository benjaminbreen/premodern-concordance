#!/usr/bin/env python3
"""
Fix mismatched wikipedia_url values using Wikidata sitelinks as ground truth.

For every cluster that has a wikidata_id, this script:
1. Looks up the correct Wikipedia article via Wikidata sitelinks
2. If the current wikipedia_url doesn't match, replaces it
3. Re-fetches the wikipedia_extract from the correct article

This fixes the systematic issue where enrich_wikipedia.py's naive search
sometimes linked to wrong articles (e.g. "demoniaco" → Ed and Lorraine Warren
instead of demonic possession).

Usage:
    python3 scripts/fix_wikipedia_urls.py [--dry-run]
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
OVERRIDES_PATH = Path(__file__).parent.parent / "data" / "wikipedia_overrides.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak7")

WIKIDATA_ENTITY_API = (
    "https://www.wikidata.org/w/api.php"
    "?action=wbgetentities&ids={qid}&props=sitelinks&format=json"
)
EXTRACT_API = (
    "https://{lang}.wikipedia.org/w/api.php"
    "?action=query&titles={title}&prop=extracts"
    "&explaintext=true&exsectionformat=plain&format=json&origin=*"
)

MAX_SENTENCES = 6
REQUEST_DELAY = 0.15
CHECKPOINT_EVERY = 100
PREFERRED_WIKIS = ["enwiki", "frwiki", "eswiki", "ptwiki", "itwiki", "dewiki", "lawiki"]


def fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def get_wikidata_sitelink(qid: str, cache: dict) -> tuple[str, str] | None:
    """Look up the best Wikipedia sitelink for a Wikidata QID."""
    if qid in cache:
        return cache[qid]

    url = WIKIDATA_ENTITY_API.format(qid=urllib.parse.quote(qid))
    data = fetch_json(url)
    if not data:
        cache[qid] = None
        return None

    entity = data.get("entities", {}).get(qid, {})
    sitelinks = entity.get("sitelinks", {})
    for key in PREFERRED_WIKIS:
        sl = sitelinks.get(key)
        if sl and sl.get("title"):
            lang = key.replace("wiki", "")
            val = (lang, sl["title"])
            cache[qid] = val
            return val

    cache[qid] = None
    return None


def make_wikipedia_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def extract_wikipedia_title(url: str) -> tuple[str, str] | None:
    """Parse a Wikipedia URL into (lang, title)."""
    try:
        parsed = urllib.parse.urlparse(url)
        if ".wikipedia.org" not in parsed.netloc:
            return None
        lang = parsed.netloc.split(".")[0]
        if not parsed.path.startswith("/wiki/"):
            return None
        title = urllib.parse.unquote(parsed.path[6:]).replace("_", " ").strip()
        return (lang, title) if title else None
    except Exception:
        return None


def fetch_extract(lang: str, title: str) -> str | None:
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
    text = text[:2400]
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    paragraphs = [p for p in paragraphs if len(p) > 35]
    if not paragraphs:
        return ""
    joined = " ".join(paragraphs)
    sentences = re.split(r"(?<=[.!?])\s+", joined)
    selected = sentences[:max_sentences]
    result = " ".join(selected).strip()
    if result and result[-1] not in ".!?":
        last_period = max(result.rfind("."), result.rfind("!"), result.rfind("?"))
        if last_period > 0:
            result = result[:last_period + 1]
    return result


def urls_match(url1: str, url2: str) -> bool:
    """Check if two Wikipedia URLs point to the same article."""
    p1 = extract_wikipedia_title(url1)
    p2 = extract_wikipedia_title(url2)
    if not p1 or not p2:
        return False
    return p1[0] == p2[0] and p1[1].lower() == p2[1].lower()


def normalize(s: str) -> str:
    """Lowercase, strip accents/underscores/parens for fuzzy matching."""
    import unicodedata
    s = s.lower().replace("_", " ").replace("-", " ")
    # Remove parenthetical disambiguation
    s = re.sub(r"\s*\(.*?\)", "", s)
    # Strip accents
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip()


def title_is_relevant(article_title: str, cluster: dict) -> bool:
    """Check whether a Wikipedia article title is plausibly related to this cluster.

    Returns True if the article title shares significant words with the cluster's
    modern_name, canonical_name, or member names. This prevents bad Wikidata QIDs
    from replacing a URL with something completely unrelated.
    """
    gt = cluster.get("ground_truth", {})
    title_norm = normalize(article_title)
    title_words = set(title_norm.split())

    # Collect reference terms from the cluster
    ref_terms = []
    for field in ["modern_name", "description"]:
        v = gt.get(field, "")
        if v:
            ref_terms.append(v)
    ref_terms.append(cluster.get("canonical_name", ""))
    # Add member names
    for m in cluster.get("members", []):
        ref_terms.append(m.get("name", ""))

    ref_norm = " ".join(normalize(t) for t in ref_terms if t)
    ref_words = set(ref_norm.split())

    # Remove stopwords
    stopwords = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to",
                 "for", "by", "with", "from", "is", "it", "its", "de", "da",
                 "do", "dos", "das", "del", "la", "le", "les", "el", "que",
                 "des", "du", "di", "e", "o", "um", "una"}
    title_words -= stopwords
    ref_words -= stopwords

    if not title_words:
        return True  # can't tell, allow it

    # Check for word overlap (at least one significant word in common)
    overlap = title_words & ref_words
    if overlap:
        return True

    # Check for substring matches (e.g. "asphalt" in "rock asphalt")
    for tw in title_words:
        if len(tw) < 3:
            continue
        for rw in ref_words:
            if len(rw) < 3:
                continue
            if tw in rw or rw in tw:
                return True

    # Known cross-lingual equivalences we can catch
    # (title word is an English/Latin equivalent of a cluster word)
    # This is a loose check — if the title has 3+ words and none match, reject
    if len(title_words) >= 2:
        return False

    # Single-word titles get more leeway (might be a valid translation)
    return True


# Titles that are obviously wrong domains regardless of matching
BAD_TITLE_PATTERNS = [
    r"agents of s\.h\.i\.e\.l\.d",
    r"\(surname\)",
    r"\(given name\)",
    r"deaths in \w+ \d{4}",
    r"births in \w+ \d{4}",
    r"\(tv series\)",
    r"\(film\)",
    r"\(album\)",
    r"\(song\)",
    r"\(video game\)",
]

def title_is_bad(title: str) -> bool:
    """Reject titles that are obviously from wrong domains."""
    t = title.lower()
    return any(re.search(p, t) for p in BAD_TITLE_PATTERNS)


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Load manual overrides
    overrides = {}
    if OVERRIDES_PATH.exists():
        with open(OVERRIDES_PATH) as f:
            overrides = json.load(f)
        overrides.pop("_comment", None)
        print(f"  {len(overrides)} manual overrides loaded")

    if not dry_run:
        print(f"Backing up to {BACKUP_PATH}")
        with open(BACKUP_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)

    # Find clusters with wikidata_id
    has_wd = [c for c in clusters if c.get("ground_truth", {}).get("wikidata_id")]
    print(f"  {len(has_wd)} clusters with wikidata_id")

    sitelink_cache: dict[str, tuple[str, str] | None] = {}
    stats = {"checked": 0, "url_fixed": 0, "extract_fixed": 0, "override_applied": 0,
             "no_sitelink": 0, "already_correct": 0, "extract_failed": 0,
             "rejected_irrelevant": 0}

    for i, cluster in enumerate(has_wd, 1):
        gt = cluster.get("ground_truth", {})
        name = cluster.get("canonical_name", "?")
        qid = gt["wikidata_id"]
        current_url = gt.get("wikipedia_url", "")
        stats["checked"] += 1

        if i == 1 or i % 50 == 0:
            print(
                f"\n[{i}/{len(has_wd)}] "
                f"fixed_url={stats['url_fixed']} fixed_extract={stats['extract_fixed']} "
                f"overrides={stats['override_applied']} correct={stats['already_correct']} "
                f"no_sitelink={stats['no_sitelink']} rejected={stats['rejected_irrelevant']}"
            )

        # Check for manual override first
        if name in overrides:
            correct_url = make_wikipedia_url("en", overrides[name])
            if not urls_match(current_url, correct_url):
                print(f"  [override] {name}: {current_url} -> {correct_url}")
                if not dry_run:
                    gt["wikipedia_url"] = correct_url
                    # Re-fetch extract
                    extract = fetch_extract("en", overrides[name])
                    if extract:
                        summary = truncate_to_sentences(extract)
                        if summary and len(summary) >= 30:
                            gt["wikipedia_extract"] = summary
                    cluster["ground_truth"] = gt
                stats["override_applied"] += 1
                time.sleep(REQUEST_DELAY)
                continue

        # Look up correct article via Wikidata sitelink
        sitelink = get_wikidata_sitelink(qid, sitelink_cache)
        time.sleep(REQUEST_DELAY)

        if not sitelink:
            stats["no_sitelink"] += 1
            continue

        lang, title = sitelink
        correct_url = make_wikipedia_url(lang, title)

        # Check if current URL already matches
        if urls_match(current_url, correct_url):
            stats["already_correct"] += 1
            continue

        # Validate: reject obviously bad titles
        if title_is_bad(title):
            print(f"  [REJECT-bad] {name} ({qid}) -> {title}")
            stats["rejected_irrelevant"] += 1
            continue

        # Validate: check if the sitelink article is actually related to this cluster
        if not title_is_relevant(title, cluster):
            print(f"  [REJECT] {name} ({qid}) -> {lang}:{title} (no relevance to cluster)")
            stats["rejected_irrelevant"] += 1
            continue

        # URL is wrong and sitelink is relevant — fix it
        print(f"  [fix] {name} ({qid})")
        if current_url:
            old_title = extract_wikipedia_title(current_url)
            old_display = old_title[1] if old_title else current_url
            print(f"         was: {old_display}")
        print(f"         now: {lang}:{title}")

        if not dry_run:
            gt["wikipedia_url"] = correct_url

            # Re-fetch the extract from the correct article
            extract = fetch_extract(lang, title)
            time.sleep(REQUEST_DELAY)

            if extract:
                summary = truncate_to_sentences(extract)
                if summary and len(summary) >= 30:
                    gt["wikipedia_extract"] = summary
                    stats["extract_fixed"] += 1
                else:
                    stats["extract_failed"] += 1
            else:
                stats["extract_failed"] += 1

            cluster["ground_truth"] = gt
            stats["url_fixed"] += 1

            # Checkpoint save
            if stats["url_fixed"] % CHECKPOINT_EVERY == 0 and stats["url_fixed"] > 0:
                print("  [checkpoint] saving...")
                with open(CONCORDANCE_PATH, "w") as f:
                    json.dump(data, f, ensure_ascii=False)
        else:
            stats["url_fixed"] += 1

        time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print(f"Results ({('DRY RUN' if dry_run else 'APPLIED')}):")
    print(f"  Checked:            {stats['checked']}")
    print(f"  Already correct:    {stats['already_correct']}")
    print(f"  URL fixed:          {stats['url_fixed']}")
    print(f"  Extract re-fetched: {stats['extract_fixed']}")
    print(f"  Extract failed:     {stats['extract_failed']}")
    print(f"  Overrides applied:  {stats['override_applied']}")
    print(f"  Rejected (bad QID): {stats['rejected_irrelevant']}")
    print(f"  No sitelink found:  {stats['no_sitelink']}")

    if not dry_run:
        print(f"\nSaving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB")
        print("\nRebuild search index:")
        print("  python3 scripts/build_search_index.py")
    else:
        print("\nNo changes written (dry run).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
High-yield second-pass Wikipedia enrichment.

Strategy order (most reliable first):
1) Existing `ground_truth.wikipedia_url` title fetch
2) Manual overrides from `data/wikipedia_overrides.json`
3) Wikidata sitelinks from `ground_truth.wikidata_id`
4) Category-aware Wikipedia search fallback

Usage:
  python3 scripts/enrich_wikipedia_pass2.py
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
OVERRIDES_PATH = Path(__file__).parent.parent / "data" / "wikipedia_overrides.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak6")

EXTRACT_API = (
    "https://{lang}.wikipedia.org/w/api.php"
    "?action=query&titles={title}&prop=extracts"
    "&explaintext=true&exsectionformat=plain&format=json&origin=*"
)
SEARCH_API = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&list=search&srsearch={query}"
    "&srnamespace=0&srlimit=5&format=json&origin=*"
)
SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
WIKIDATA_ENTITY_API = (
    "https://www.wikidata.org/w/api.php"
    "?action=wbgetentities&ids={qid}&props=sitelinks&format=json"
)

MAX_SENTENCES = 6
REQUEST_DELAY = 0.12
CHECKPOINT_EVERY = 50
PREFERRED_WIKIS = ["enwiki", "frwiki", "eswiki", "ptwiki", "itwiki", "dewiki", "lawiki"]


def fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def wiki_key_to_lang(wiki_key: str) -> str:
    return wiki_key.replace("wiki", "")


def wikipedia_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"


def parse_wikipedia_url(url: str) -> tuple[str, str] | None:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if ".wikipedia.org" not in host:
            return None
        lang = host.split(".")[0]
        if not parsed.path.startswith("/wiki/"):
            return None
        title = unquote(parsed.path[len("/wiki/"):]).replace("_", " ").strip()
        if not title:
            return None
        return lang, title
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


def get_wikidata_sitelink(qid: str, cache: dict[str, tuple[str, str] | None]) -> tuple[str, str] | None:
    if not qid:
        return None
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
            val = (wiki_key_to_lang(key), sl["title"])
            cache[qid] = val
            return val

    cache[qid] = None
    return None


def search_wikipedia_titles(query: str) -> list[str]:
    encoded = urllib.parse.quote(query)
    url = SEARCH_API.format(query=encoded)
    data = fetch_json(url)
    if not data:
        return []
    return [r.get("title", "") for r in data.get("query", {}).get("search", []) if r.get("title")]


def score_summary_for_category(summary: dict | None, category: str) -> int:
    if not summary:
        return -100
    if summary.get("type") == "disambiguation":
        return -100
    desc = (summary.get("description") or "").lower()
    score = 0

    # Penalize obvious bad hits.
    bad_terms = [
        "film", "album", "song", "tv", "television", "video game", "wrestler",
        "footballer", "band", "journal", "magazine", "episode", "sitcom",
        "surname", "given name", "unisex given name", "list of",
    ]
    if any(t in desc for t in bad_terms):
        score -= 5

    cat_hints = {
        "PERSON": ["person", "physician", "philosopher", "scholar", "pope", "saint"],
        "PLACE": ["city", "country", "region", "island", "river", "town", "province"],
        "PLANT": ["plant", "genus", "species", "flowering", "tree", "herb"],
        "ANIMAL": ["animal", "species", "bird", "fish", "mammal", "reptile"],
        "DISEASE": ["disease", "condition", "syndrome", "disorder", "infection"],
        "SUBSTANCE": ["chemical", "compound", "substance", "resin", "mineral", "drug"],
        "OBJECT": ["instrument", "tool", "object", "device", "artifact"],
        "CONCEPT": ["concept", "theory", "philosophy", "practice", "method"],
        "ANATOMY": ["anatomy", "organ", "body", "anatomical"],
    }
    hints = cat_hints.get(category, [])
    score += sum(1 for h in hints if h in desc)
    return score


def try_title(cluster: dict, lang: str, title: str, source: str) -> bool:
    gt = cluster.get("ground_truth", {})
    category = cluster.get("category", "")

    # Skip disambiguation / obvious wrong-domain pages before pulling extract.
    summary_data = fetch_json(SUMMARY_API.format(urllib.parse.quote(title)))
    if source != "override":
        if score_summary_for_category(summary_data, category) < -3:
            return False

    extract = fetch_extract(lang, title)
    if not extract:
        return False
    summary = truncate_to_sentences(extract)
    if not summary or len(summary) < 30:
        return False
    gt["wikipedia_extract"] = summary
    gt["wikipedia_url"] = wikipedia_url(lang, title)
    cluster["ground_truth"] = gt
    if source != "search":
        print(f"  [{source}] {cluster['canonical_name']} -> {lang}:{title}", flush=True)
    return True


def main():
    print(f"Loading concordance from {CONCORDANCE_PATH}", flush=True)
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters", flush=True)

    overrides = {}
    if OVERRIDES_PATH.exists():
        with open(OVERRIDES_PATH) as f:
            overrides = json.load(f)
        overrides.pop("_comment", None)
        print(f"  {len(overrides)} manual overrides loaded", flush=True)

    print(f"Backing up to {BACKUP_PATH}", flush=True)
    with open(BACKUP_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    missing = [c for c in clusters if not c.get("ground_truth", {}).get("wikipedia_extract")]
    print(f"  {len(missing)} clusters missing wikipedia_extract", flush=True)

    stats = {
        "url": 0,
        "override": 0,
        "wikidata": 0,
        "search": 0,
        "failed": 0,
    }
    sitelink_cache: dict[str, tuple[str, str] | None] = {}

    for i, cluster in enumerate(missing, 1):
        gt = cluster.get("ground_truth", {})
        name = cluster["canonical_name"]
        category = cluster.get("category", "")
        found = False

        if i == 1 or i % 25 == 0:
            print(
                f"\n[{i}/{len(missing)}] "
                f"url={stats['url']} override={stats['override']} "
                f"wikidata={stats['wikidata']} search={stats['search']} "
                f"failed={stats['failed']}",
                flush=True,
            )

        # 1) Existing wikipedia_url.
        url = gt.get("wikipedia_url")
        if url:
            parsed = parse_wikipedia_url(url)
            if parsed:
                lang, title = parsed
                found = try_title(cluster, lang, title, "url")
                if found:
                    stats["url"] += 1

        # 2) Manual override by canonical name.
        if not found and name in overrides:
            found = try_title(cluster, "en", overrides[name], "override")
            if found:
                stats["override"] += 1

        # 3) Wikidata sitelink.
        if not found:
            qid = gt.get("wikidata_id", "")
            sl = get_wikidata_sitelink(qid, sitelink_cache)
            if sl:
                lang, title = sl
                found = try_title(cluster, lang, title, "wikidata")
                if found:
                    stats["wikidata"] += 1

        # 4) Search fallback.
        if not found:
            modern = (gt.get("modern_name") or "").strip()
            desc = (gt.get("description") or "").strip()
            queries = []
            if modern:
                queries.append(modern)
            if modern and category:
                queries.append(f"{modern} {category.lower()}")
            if name and name.lower() != modern.lower():
                queries.append(name)
            if name and desc:
                queries.append(f"{name} {' '.join(desc.split()[:5])}")

            seen_q = set()
            queries = [q for q in queries if q and not (q.lower() in seen_q or seen_q.add(q.lower()))]
            candidate_titles = []
            for q in queries[:3]:
                candidate_titles.extend(search_wikipedia_titles(q))
                time.sleep(REQUEST_DELAY)

            seen_t = set()
            unique_titles = [t for t in candidate_titles if t and not (t.lower() in seen_t or seen_t.add(t.lower()))]

            ranked: list[tuple[int, str]] = []
            for t in unique_titles[:6]:
                summary = fetch_json(SUMMARY_API.format(urllib.parse.quote(t)))
                ranked.append((score_summary_for_category(summary, category), t))
                time.sleep(REQUEST_DELAY)
            ranked.sort(reverse=True)

            for score, title in ranked:
                if score < -3:
                    continue
                if try_title(cluster, "en", title, "search"):
                    stats["search"] += 1
                    found = True
                    break
                time.sleep(REQUEST_DELAY)

        if not found:
            stats["failed"] += 1

        if i % CHECKPOINT_EVERY == 0:
            print("  [checkpoint] saving...", flush=True)
            with open(CONCORDANCE_PATH, "w") as f:
                json.dump(data, f, ensure_ascii=False)

        time.sleep(REQUEST_DELAY)

    total_with_extract = sum(
        1 for c in clusters if c.get("ground_truth", {}).get("wikipedia_extract")
    )
    total = len(clusters)
    print("\n" + "=" * 60, flush=True)
    print("Pass 2 results:", flush=True)
    print(f"  Resolved via wikipedia_url: {stats['url']}", flush=True)
    print(f"  Resolved via overrides:     {stats['override']}", flush=True)
    print(f"  Resolved via wikidata:      {stats['wikidata']}", flush=True)
    print(f"  Resolved via search:        {stats['search']}", flush=True)
    print(f"  Still missing:              {stats['failed']}", flush=True)
    print(f"  Coverage: {total_with_extract}/{total} ({100*total_with_extract/total:.2f}%)", flush=True)

    print(f"\nSaving to {CONCORDANCE_PATH}...", flush=True)
    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"  {size_mb:.1f} MB", flush=True)
    print("\nRebuild search index:", flush=True)
    print("  python3 scripts/build_search_index.py", flush=True)


if __name__ == "__main__":
    main()

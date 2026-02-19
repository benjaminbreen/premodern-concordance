#!/usr/bin/env python3
"""
Backfill missing Wikidata IDs for concordance clusters (precision-first).

This script only considers clusters that already have `ground_truth` but are missing
`ground_truth.wikidata_id`. Existing IDs are never overwritten.

Resolution strategy:
1. Build high-signal query terms from modern_name/canonical/member names
2. Search Wikidata candidates (wbsearchentities)
3. Score candidates with deterministic signals:
   - lexical agreement with cluster terms
   - category compatibility using P31 instance-of claims
   - description/domain sanity checks
   - optional agreement with existing Wikipedia URL title
4. Auto-accept only high-confidence matches; send medium-confidence to review queue

Usage:
  python3 scripts/backfill_wikidata_ids.py --dry-run
  python3 scripts/backfill_wikidata_ids.py
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
REVIEW_PATH = Path(__file__).parent.parent / "data" / "review" / "wikidata_backfill_queue.jsonl"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak_wikidata_backfill")

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "PremodernConcordance/1.0"
REQUEST_DELAY = 0.10

PREFERRED_WIKIS = ["enwiki", "frwiki", "eswiki", "ptwiki", "itwiki", "dewiki", "lawiki"]

BAD_DESC_TERMS = {
    "film", "album", "song", "television", "tv series", "video game", "wrestler",
    "footballer", "actor", "actress", "band", "surname", "given name", "comic",
    "anime", "manga", "episode", "season",
}

CATEGORY_POSITIVE_DESC = {
    "PERSON": {"physician", "philosopher", "scholar", "scientist", "author", "pope", "saint", "naturalist", "explorer"},
    "PLACE": {"city", "country", "region", "island", "river", "town", "province", "municipality", "village"},
    "PLANT": {"plant", "genus", "species", "tree", "herb", "flowering", "taxon"},
    "ANIMAL": {"animal", "species", "bird", "fish", "mammal", "reptile", "insect", "taxon"},
    "DISEASE": {"disease", "syndrome", "disorder", "infection", "symptom", "condition"},
    "SUBSTANCE": {"chemical", "compound", "substance", "mineral", "metal", "element", "drug", "resin"},
    "OBJECT": {"instrument", "tool", "object", "device", "artifact", "vessel"},
    "CONCEPT": {"concept", "theory", "practice", "method", "process", "philosophy"},
    "ANATOMY": {"anatomical", "organ", "muscle", "bone", "nerve", "body"},
}

CATEGORY_NEGATIVE_DESC = {
    "PLACE": {"person", "singer", "actor", "wrestler", "film"},
    "PERSON": {"genus", "species", "chemical", "element", "mineral"},
    "PLANT": {"person", "actor", "singer", "footballer"},
    "ANIMAL": {"person", "actor", "singer", "footballer"},
    "DISEASE": {"film", "song", "person", "actor", "wrestler"},
    "SUBSTANCE": {"person", "actor", "singer", "footballer"},
}

# Common high-value P31 targets (not exhaustive; used as soft signals only).
CATEGORY_ALLOWED_P31 = {
    "PERSON": {"Q5"},
    "PLACE": {"Q515", "Q6256", "Q486972", "Q82794", "Q3957", "Q15284", "Q17334923"},
    "PLANT": {"Q756", "Q16521"},
    "ANIMAL": {"Q729", "Q16521"},
    "DISEASE": {"Q12136", "Q12078", "Q929833"},
    "SUBSTANCE": {"Q11173", "Q79529", "Q8066", "Q11344", "Q12140", "Q42240"},
    "OBJECT": {"Q223557", "Q2424752", "Q39546", "Q8205328"},
    "CONCEPT": {"Q151885", "Q7184903", "Q621184"},
    "ANATOMY": {"Q4936952", "Q811430"},
}

P31_HARD_BAD = {
    "Q11424",   # film
    "Q482994",  # album
    "Q7366",    # song
    "Q5398426", # television series
    "Q7889",    # video game
    "Q215380",  # band
    "Q101352",  # family name
    "Q202444",  # given name
}


@dataclass
class CandidateScore:
    qid: str
    label: str
    description: str
    score: float
    name_score: float
    category_score: float
    desc_score: float
    wiki_score: float
    reasons: list[str]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {t for t in normalize_text(text).split() if len(t) >= 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parse_wikipedia_url(url: str) -> tuple[str, str] | None:
    try:
        parsed = urllib.parse.urlparse(url)
        if ".wikipedia.org" not in parsed.netloc:
            return None
        lang = parsed.netloc.split(".")[0]
        if not parsed.path.startswith("/wiki/"):
            return None
        title = urllib.parse.unquote(parsed.path[len("/wiki/"):]).replace("_", " ").strip()
        if not title:
            return None
        return lang, title
    except Exception:
        return None


def load_json_with_retries(path: Path, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            if attempt == retries - 1:
                raise
            time.sleep(0.4)
    raise RuntimeError("Failed to read JSON")


def fetch_json(url: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(0.4 * (attempt + 1))
    return None


def wikidata_search(query: str, cache: dict[str, list[dict]], limit: int) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    if q in cache:
        return cache[q]

    params = {
        "action": "wbsearchentities",
        "search": q,
        "language": "en",
        "format": "json",
        "type": "item",
        "limit": str(limit),
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    data = fetch_json(url)
    results = data.get("search", []) if data else []
    cache[q] = results
    return results


def wikidata_entity_details(qid: str, cache: dict[str, dict]) -> dict | None:
    if qid in cache:
        return cache[qid]

    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels|descriptions|aliases|claims|sitelinks",
        "languages": "en|fr|es|pt|it|de|la",
        "format": "json",
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    data = fetch_json(url)
    if not data:
        cache[qid] = None
        return None

    entity = data.get("entities", {}).get(qid)
    cache[qid] = entity
    return entity


def extract_claim_qids(entity: dict, prop: str) -> set[str]:
    out = set()
    claims = (entity or {}).get("claims", {})
    for claim in claims.get(prop, []):
        mainsnak = claim.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue", {})
        value = datavalue.get("value", {})
        qid = value.get("id")
        if isinstance(qid, str) and qid.startswith("Q"):
            out.add(qid)
    return out


def collect_candidate_names(entity: dict) -> list[str]:
    names: list[str] = []

    labels = entity.get("labels", {}) if entity else {}
    for lang in ["en", "fr", "es", "pt", "it", "de", "la"]:
        if lang in labels and labels[lang].get("value"):
            names.append(labels[lang]["value"])

    aliases = entity.get("aliases", {}) if entity else {}
    for lang in ["en", "fr", "es", "pt", "it", "de", "la"]:
        for item in aliases.get(lang, [])[:6]:
            v = item.get("value")
            if v:
                names.append(v)

    # Deduplicate preserving order
    seen = set()
    dedup = []
    for n in names:
        key = normalize_text(n)
        if key and key not in seen:
            seen.add(key)
            dedup.append(n)
    return dedup


def preferred_sitelink(entity: dict) -> tuple[str, str] | None:
    sitelinks = entity.get("sitelinks", {}) if entity else {}
    for wiki_key in PREFERRED_WIKIS:
        sl = sitelinks.get(wiki_key)
        if sl and sl.get("title"):
            lang = wiki_key.replace("wiki", "")
            return lang, sl["title"]
    return None


def wikipedia_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def build_cluster_terms(cluster: dict) -> tuple[list[str], str | None]:
    gt = cluster.get("ground_truth") or {}
    canonical = (cluster.get("canonical_name") or "").strip()
    modern = (gt.get("modern_name") or "").strip()

    terms: list[str] = []
    if modern:
        terms.append(modern)
    if canonical and normalize_text(canonical) != normalize_text(modern):
        terms.append(canonical)

    parsed = parse_wikipedia_url(gt.get("wikipedia_url", ""))
    existing_title = None
    if parsed:
        _, existing_title = parsed
        if existing_title:
            terms.append(existing_title)

    members = sorted(cluster.get("members", []), key=lambda m: m.get("count", 0), reverse=True)
    for member in members[:8]:
        name = (member.get("name") or "").strip()
        if name:
            terms.append(name)
        for v in (member.get("variants") or [])[:2]:
            v = (v or "").strip()
            if v:
                terms.append(v)

    # Deduplicate normalized, keep terms with some substance.
    seen = set()
    dedup: list[str] = []
    for t in terms:
        key = normalize_text(t)
        if len(key) < 3:
            continue
        if key in seen:
            continue
        seen.add(key)
        dedup.append(t)

    return dedup[:12], existing_title


def score_candidate(cluster: dict, terms: list[str], existing_title: str | None, entity: dict, qid: str) -> CandidateScore:
    category = cluster.get("category", "")
    names = collect_candidate_names(entity)
    label = names[0] if names else qid
    desc = (entity.get("descriptions", {}).get("en", {}) or {}).get("value", "")
    desc_l = desc.lower()

    reasons: list[str] = []

    # Name agreement
    term_norm = [normalize_text(t) for t in terms]
    term_tokens = [tokens(t) for t in terms]
    cand_name_norm = [normalize_text(n) for n in names]
    cand_name_tokens = [tokens(n) for n in names]

    name_score = 0.0
    best_j = 0.0
    exact = False

    for tn, tt in zip(term_norm, term_tokens):
        for cn, ct in zip(cand_name_norm, cand_name_tokens):
            if not tn or not cn:
                continue
            if tn == cn:
                exact = True
                if tn == normalize_text((cluster.get("ground_truth") or {}).get("modern_name", "")):
                    name_score = max(name_score, 7.0)
                    reasons.append("exact modern_name")
                elif tn == normalize_text(cluster.get("canonical_name", "")):
                    name_score = max(name_score, 6.5)
                    reasons.append("exact canonical_name")
                else:
                    name_score = max(name_score, 5.5)
                    reasons.append("exact member/variant")
            j = jaccard(tt, ct)
            best_j = max(best_j, j)

    if not exact:
        if best_j >= 0.9:
            name_score += 4.0
            reasons.append(f"name token overlap {best_j:.2f}")
        elif best_j >= 0.6:
            name_score += 2.5
            reasons.append(f"name token overlap {best_j:.2f}")
        elif best_j >= 0.4:
            name_score += 1.0
            reasons.append(f"weak token overlap {best_j:.2f}")

        # Prefix/substring heuristic for OCR/orthographic variance.
        for tn in term_norm:
            for cn in cand_name_norm:
                if len(tn) >= 5 and len(cn) >= 5 and (tn in cn or cn in tn):
                    name_score += 0.8
                    reasons.append("substring agreement")
                    break
            else:
                continue
            break

    # Category/P31 agreement
    p31 = extract_claim_qids(entity, "P31")
    category_score = 0.0
    bad_type_hit = False

    allowed = CATEGORY_ALLOWED_P31.get(category, set())
    if allowed and (p31 & allowed):
        category_score += 3.0
        reasons.append("P31 category-compatible")
    elif allowed and p31:
        category_score -= 1.0
        reasons.append("P31 not category-aligned")

    hard_bad = p31 & P31_HARD_BAD
    if hard_bad:
        category_score -= 6.0
        bad_type_hit = True
        reasons.append("P31 hard-bad media/name class")

    # Description/domain checks
    desc_score = 0.0
    bad_desc = False

    for t in BAD_DESC_TERMS:
        if t in desc_l:
            desc_score -= 2.0
            bad_desc = True

    for t in CATEGORY_POSITIVE_DESC.get(category, set()):
        if t in desc_l:
            desc_score += 1.0
    desc_score = min(desc_score, 3.0)

    for t in CATEGORY_NEGATIVE_DESC.get(category, set()):
        if t in desc_l:
            desc_score -= 1.5

    if desc_score > 0:
        reasons.append("description category hints")
    if bad_desc:
        reasons.append("description contains bad-domain terms")

    # Existing wikipedia_url agreement bonus/penalty
    wiki_score = 0.0
    if existing_title:
        existing_n = normalize_text(existing_title)
        sl = preferred_sitelink(entity)
        if sl:
            _, sl_title = sl
            sl_n = normalize_text(sl_title)
            if sl_n == existing_n:
                wiki_score += 2.5
                reasons.append("matches existing wikipedia title")
            else:
                wiki_score -= 0.7
                reasons.append("differs from existing wikipedia title")

    total = name_score + category_score + desc_score + wiki_score

    return CandidateScore(
        qid=qid,
        label=label,
        description=desc,
        score=total,
        name_score=name_score,
        category_score=category_score,
        desc_score=desc_score,
        wiki_score=wiki_score,
        reasons=reasons,
    )


def decide_confidence(best: CandidateScore, second: CandidateScore | None, args: argparse.Namespace) -> str:
    gap = best.score - (second.score if second else -999.0)
    has_strong_name = best.name_score >= 4.0
    category_ok = best.category_score >= 0
    bad_domain = best.desc_score <= -3.0

    if (
        best.score >= args.min_high_score
        and gap >= args.min_gap
        and has_strong_name
        and category_ok
        and not bad_domain
    ):
        return "high"

    if best.score >= args.min_medium_score and has_strong_name and not bad_domain:
        return "medium"

    return "low"


def write_review_queue(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing Wikidata IDs (precision-first)")
    parser.add_argument("--concordance", default=str(CONCORDANCE_PATH), help="Path to concordance JSON")
    parser.add_argument("--output", help="Output path (default: overwrite --concordance)")
    parser.add_argument("--review-out", default=str(REVIEW_PATH), help="JSONL review queue path")
    parser.add_argument("--dry-run", action="store_true", help="Do not write concordance changes")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N missing-ID clusters")
    parser.add_argument("--search-limit", type=int, default=8, help="Wikidata search candidates per query")
    parser.add_argument("--max-candidates", type=int, default=10, help="Max unique candidates scored per cluster")
    parser.add_argument("--min-high-score", type=float, default=8.5, help="Minimum score for auto-accept")
    parser.add_argument("--min-medium-score", type=float, default=6.0, help="Minimum score for review queue")
    parser.add_argument("--min-gap", type=float, default=2.0, help="Min score gap over 2nd candidate for high")
    parser.add_argument("--checkpoint-every", type=int, default=50, help="Save progress every N accepted IDs")
    parser.add_argument("--set-wikipedia-url", action="store_true", help="Set wikipedia_url from sitelink when missing")
    args = parser.parse_args()

    concordance_path = Path(args.concordance)
    output_path = Path(args.output) if args.output else concordance_path
    review_path = Path(args.review_out)

    print(f"Loading concordance from {concordance_path}")
    data = load_json_with_retries(concordance_path)
    clusters = data.get("clusters", [])
    print(f"  {len(clusters)} clusters")

    if not args.dry_run:
        print(f"Backing up to {BACKUP_PATH}")
        with open(BACKUP_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    targets = [
        c for c in clusters
        if c.get("ground_truth") and not (c.get("ground_truth") or {}).get("wikidata_id")
    ]

    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    print(f"  {len(targets)} clusters missing wikidata_id in scope")

    search_cache: dict[str, list[dict]] = {}
    entity_cache: dict[str, dict | None] = {}

    accepted = 0
    medium = 0
    low = 0
    no_candidates = 0
    reviewed_rows: list[dict] = []

    for idx, cluster in enumerate(targets, 1):
        gt = cluster.get("ground_truth") or {}
        terms, existing_title = build_cluster_terms(cluster)

        if idx == 1 or idx % 25 == 0:
            print(
                f"\n[{idx}/{len(targets)}] accepted={accepted} medium={medium} "
                f"low={low} no_candidates={no_candidates}"
            )

        query_terms = terms[:5]
        candidate_ids: list[str] = []
        seen_ids = set()

        for q in query_terms:
            results = wikidata_search(q, search_cache, args.search_limit)
            time.sleep(REQUEST_DELAY)
            for r in results:
                qid = r.get("id")
                if not qid or qid in seen_ids:
                    continue
                seen_ids.add(qid)
                candidate_ids.append(qid)
                if len(candidate_ids) >= args.max_candidates:
                    break
            if len(candidate_ids) >= args.max_candidates:
                break

        if not candidate_ids:
            no_candidates += 1
            continue

        scored: list[CandidateScore] = []
        for qid in candidate_ids:
            entity = wikidata_entity_details(qid, entity_cache)
            time.sleep(REQUEST_DELAY)
            if not entity:
                continue
            scored.append(score_candidate(cluster, terms, existing_title, entity, qid))

        if not scored:
            no_candidates += 1
            continue

        scored.sort(key=lambda s: s.score, reverse=True)
        best = scored[0]
        second = scored[1] if len(scored) > 1 else None
        confidence = decide_confidence(best, second, args)

        if confidence == "high":
            accepted += 1

            if not args.dry_run:
                gt["wikidata_id"] = best.qid
                if best.description:
                    gt["wikidata_description"] = best.description

                if args.set_wikipedia_url and not gt.get("wikipedia_url"):
                    entity = entity_cache.get(best.qid)
                    sl = preferred_sitelink(entity or {})
                    if sl:
                        lang, title = sl
                        gt["wikipedia_url"] = wikipedia_url(lang, title)

                cluster["ground_truth"] = gt

                if accepted % args.checkpoint_every == 0:
                    print("  [checkpoint] saving concordance + review queue")
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                    write_review_queue(review_path, reviewed_rows)

            gap = best.score - (second.score if second else 0.0)
            print(
                f"  [HIGH] {cluster.get('canonical_name')} -> {best.qid} "
                f"({best.label}) score={best.score:.2f} gap={gap:.2f}"
            )

        elif confidence == "medium":
            medium += 1
            row = {
                "cluster_id": cluster.get("id"),
                "stable_key": cluster.get("stable_key", ""),
                "canonical_name": cluster.get("canonical_name", ""),
                "category": cluster.get("category", ""),
                "modern_name": gt.get("modern_name", ""),
                "decision": "review",
                "best": {
                    "qid": best.qid,
                    "label": best.label,
                    "description": best.description,
                    "score": round(best.score, 3),
                    "reasons": best.reasons,
                },
                "second": None
                if not second
                else {
                    "qid": second.qid,
                    "label": second.label,
                    "description": second.description,
                    "score": round(second.score, 3),
                },
            }
            reviewed_rows.append(row)

        else:
            low += 1

    # Final writes
    if not args.dry_run:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    write_review_queue(review_path, reviewed_rows)

    # Final metrics
    final_clusters = data.get("clusters", [])
    with_qid = sum(1 for c in final_clusters if (c.get("ground_truth") or {}).get("wikidata_id"))

    print("\n" + "=" * 60)
    print("Backfill results:")
    print(f"  Processed missing-ID clusters: {len(targets)}")
    print(f"  Auto-accepted (high):         {accepted}")
    print(f"  Review queue (medium):        {medium}")
    print(f"  Rejected/low:                 {low}")
    print(f"  No candidates:                {no_candidates}")
    print(f"  Review queue written:         {review_path} ({len(reviewed_rows)} rows)")
    if args.dry_run:
        print("  Mode: dry-run (no concordance writes)")
    print(f"  Total clusters with Wikidata: {with_qid}/{len(final_clusters)} ({100*with_qid/len(final_clusters):.2f}%)")

    if not args.dry_run:
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\nSaved to: {output_path} ({size_mb:.1f} MB)")
        print("Next recommended steps:")
        print("  python3 scripts/fix_wikipedia_urls.py")
        print("  python3 scripts/enrich_wikipedia_pass2.py")
        print("  python3 scripts/build_search_index.py")


if __name__ == "__main__":
    main()

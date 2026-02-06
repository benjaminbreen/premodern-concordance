#!/usr/bin/env python3
"""
Enrich concordance clusters with ground truth identifications.

For each cluster, uses Gemini to identify the modern referent, then
queries Wikidata to get stable identifiers (Q-IDs, Wikipedia URLs,
taxonomic info, dates, coordinates, etc.).

Usage:
    python enrich_concordance.py
    python enrich_concordance.py --dry-run          # show Gemini identifications only
    python enrich_concordance.py --batch-size 8     # clusters per Gemini call
"""

import argparse
import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

from google import genai

DEFAULT_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def build_enrichment_prompt(clusters: list[dict]) -> str:
    """Build a prompt for Gemini to identify modern referents for a batch of clusters."""
    lines = [
        "You are a historian of science and medicine with expertise in early modern",
        "texts (1500-1900) in Portuguese, Spanish, Latin, and English.",
        "",
        "For each entity cluster below from early modern medical/scientific texts,",
        "identify the modern referent. Return a JSON array with one object per cluster.",
        "",
        "For each cluster, return:",
        '{',
        '  "cluster_id": <number>,',
        '  "modern_name": "<modern English name>",',
        '  "type": "<person|plant|animal|mineral|chemical|disease|place|concept|object|text>",',
        '',
        '  // For PERSONS:',
        '  "birth_year": <number or null>,',
        '  "death_year": <number or null>,',
        '  "description": "<brief role/significance, 5-15 words>",',
        '',
        '  // For PLANTS:',
        '  "linnaean": "<Genus species Author>" or null if uncertain,',
        '  "family": "<botanical family>" or null,',
        '',
        '  // For PLACES:',
        '  "modern_name": "<current name if different>",',
        '  "country": "<modern country>",',
        '',
        '  // For DISEASES:',
        '  "modern_term": "<current medical term>",',
        '',
        '  // For all:',
        '  "wikidata_search": "<best search term for Wikidata lookup>",',
        '  "confidence": "high" | "medium" | "low",',
        '  "note": "<brief note if identification is contested or ambiguous>" or null',
        '}',
        "",
        "IMPORTANT RULES:",
        "- This is a HISTORICAL RESEARCH project about early modern medicine and natural",
        "  philosophy (1500-1900). All entities are from this historical domain.",
        "- For plants, ALWAYS try to give the Linnaean binomial if known",
        "- Use 'low' confidence when the early modern term is genuinely ambiguous",
        "- For contested identifications, explain briefly in 'note'",
        "- If a cluster contains OCR noise or is unidentifiable, set confidence to 'low'",
        "  and modern_name to the best guess",
        "- For wikidata_search: use SHORT, SPECIFIC search terms (1-3 words) that will",
        "  find the correct historical/scientific/medical entity on Wikidata.",
        "  Keep it simple — Wikidata search is literal, not semantic.",
        "  - For common words with many meanings, just use the modern name (the scoring",
        "    system will prefer medical/historical/scientific results over pop culture).",
        "  - For persons, use their most common name: 'Galen', 'Avicenna', 'Paracelsus'",
        "  - For plants, use common English name: 'cinnamon', 'tobacco', 'ginger'",
        "  - For diseases, use modern medical term: 'sciatica', 'fever', 'dropsy'",
        "- Return ONLY the JSON array, no other text",
        "",
        "CLUSTERS:",
        "",
    ]

    for cluster in clusters:
        members_str = "; ".join(
            f'"{m["name"]}" ({m["book_id"]}, {m["count"]}x)'
            for m in cluster["members"][:5]
        )
        contexts = []
        for m in cluster["members"]:
            contexts.extend(m.get("contexts", [])[:1])
        ctx_str = " | ".join(contexts[:3]) if contexts else "no context"

        lines.append(
            f"  ID {cluster['id']} [{cluster['category']}] "
            f"\"{cluster['canonical_name']}\" — Members: {members_str}"
        )
        if cluster.get("subcategory"):
            lines.append(f"    Subcategory: {cluster['subcategory']}")
        lines.append(f"    Contexts: {ctx_str}")
        lines.append("")

    return "\n".join(lines)


def call_gemini(prompt: str, client, model: str) -> list[dict] | None:
    """Send prompt to Gemini and parse JSON response."""
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"    API error: {e}")
        return None


def search_wikidata(query: str, entity_type: str = "", language: str = "en") -> dict | None:
    """Search Wikidata for an entity and return basic info.

    Uses entity_type to prefer domain-relevant results over pop culture hits.
    """
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": language,
        "format": "json",
        "limit": 7,
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("search", [])
        if not results:
            return None

        # Score results by domain relevance
        # Prefer medical, botanical, historical, scientific descriptions
        GOOD_KEYWORDS = {
            "disease", "symptom", "medical", "medicine", "condition", "disorder",
            "plant", "species", "genus", "family", "flowering", "herb", "tree",
            "mineral", "chemical", "element", "compound", "substance",
            "physician", "philosopher", "scholar", "theologian", "author", "scientist",
            "historian", "explorer", "king", "pope", "saint", "bishop", "emperor",
            "city", "region", "province", "country", "river", "island", "port",
            "animal", "bird", "fish", "insect", "mammal", "reptile",
            "anatomical", "organ", "body", "surgery", "remedy", "therapy",
            "concept", "theory", "practice", "technique", "process",
        }
        BAD_KEYWORDS = {
            "album", "song", "film", "movie", "tv", "television", "series",
            "video game", "band", "rapper", "singer", "actor", "actress",
            "novel", "comic", "manga", "anime", "podcast", "mixtape",
            "software", "desktop environment", "programming", "app",
            "football", "basketball", "soccer", "baseball", "wrestler",
        }

        def score_result(r):
            desc = r.get("description", "").lower()
            score = 0
            for kw in GOOD_KEYWORDS:
                if kw in desc:
                    score += 1
            for kw in BAD_KEYWORDS:
                if kw in desc:
                    score -= 5
            # Bonus if entity type appears in description
            if entity_type and entity_type.lower() in desc:
                score += 2
            return score

        scored = [(score_result(r), i, r) for i, r in enumerate(results)]
        scored.sort(key=lambda x: (-x[0], x[1]))  # Best score first, tiebreak by position

        top = scored[0][2]
        return {
            "wikidata_id": top["id"],
            "label": top.get("label", ""),
            "description": top.get("description", ""),
        }
    except Exception:
        return None


def get_wikipedia_url(wikidata_id: str, lang: str = "en") -> str | None:
    """Get Wikipedia URL from a Wikidata ID."""
    params = {
        "action": "wbgetentities",
        "ids": wikidata_id,
        "format": "json",
        "props": "sitelinks",
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        entity = data.get("entities", {}).get(wikidata_id, {})
        sitelinks = entity.get("sitelinks", {})

        # Try requested language first, then English
        for wiki_key in [f"{lang}wiki", "enwiki"]:
            if wiki_key in sitelinks:
                title = sitelinks[wiki_key]["title"]
                wiki_lang = wiki_key.replace("wiki", "")
                return f"https://{wiki_lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}"
        return None
    except Exception:
        return None


def enrich_cluster(cluster: dict, gemini_result: dict) -> dict:
    """Apply Gemini identification and Wikidata data to a cluster."""
    ground_truth = {
        "modern_name": gemini_result.get("modern_name", cluster["canonical_name"]),
        "confidence": gemini_result.get("confidence", "low"),
    }

    entity_type = gemini_result.get("type", "")
    ground_truth["type"] = entity_type

    # Copy type-specific fields
    if entity_type == "person":
        for field in ["birth_year", "death_year", "description"]:
            if gemini_result.get(field):
                ground_truth[field] = gemini_result[field]

    elif entity_type == "plant":
        for field in ["linnaean", "family"]:
            if gemini_result.get(field):
                ground_truth[field] = gemini_result[field]

    elif entity_type == "place":
        for field in ["country"]:
            if gemini_result.get(field):
                ground_truth[field] = gemini_result[field]

    elif entity_type == "disease":
        if gemini_result.get("modern_term"):
            ground_truth["modern_term"] = gemini_result["modern_term"]

    if gemini_result.get("note"):
        ground_truth["note"] = gemini_result["note"]

    # Wikidata lookup
    search_term = gemini_result.get("wikidata_search", ground_truth["modern_name"])
    if search_term:
        wd = search_wikidata(search_term, entity_type=entity_type)
        if wd:
            ground_truth["wikidata_id"] = wd["wikidata_id"]
            ground_truth["wikidata_description"] = wd["description"]

            # Get Wikipedia URL
            wiki_url = get_wikipedia_url(wd["wikidata_id"])
            if wiki_url:
                ground_truth["wikipedia_url"] = wiki_url

    cluster["ground_truth"] = ground_truth
    return cluster


def main():
    parser = argparse.ArgumentParser(description="Enrich concordance with ground truth")
    parser.add_argument("--concordance", default=str(DEFAULT_PATH), help="Concordance JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show identifications only")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model")
    parser.add_argument("--batch-size", type=int, default=8, help="Clusters per Gemini call")
    parser.add_argument("--output", help="Output file (default: overwrites input)")
    parser.add_argument("--skip-wikidata", action="store_true", help="Skip Wikidata lookups")
    args = parser.parse_args()

    # Load
    concordance_path = Path(args.concordance)
    with open(concordance_path) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Loaded {len(clusters)} clusters")

    # Filter to clusters without ground truth (for incremental runs)
    to_enrich = [c for c in clusters if "ground_truth" not in c]
    already_enriched = len(clusters) - len(to_enrich)
    if already_enriched > 0:
        print(f"  {already_enriched} already enriched, {len(to_enrich)} remaining")

    if not to_enrich:
        print("All clusters already enriched.")
        return

    # Initialize Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found")

    client = genai.Client(api_key=api_key)
    print(f"Using model: {args.model}")
    print(f"Batch size: {args.batch_size}")

    # Process in batches
    total_enriched = 0
    total_wikidata = 0
    failed_batches = 0

    num_batches = (len(to_enrich) + args.batch_size - 1) // args.batch_size
    print(f"\nProcessing {len(to_enrich)} clusters in {num_batches} batches...\n")

    for batch_idx in range(0, len(to_enrich), args.batch_size):
        batch = to_enrich[batch_idx:batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1

        print(f"Batch {batch_num}/{num_batches} ({len(batch)} clusters)...", flush=True)

        # Get Gemini identifications
        prompt = build_enrichment_prompt(batch)
        results = call_gemini(prompt, client, args.model)

        if not results:
            print(f"  Failed — keeping clusters unenriched")
            failed_batches += 1
            time.sleep(2)
            continue

        # Map results by cluster_id
        results_by_id = {}
        for r in results:
            cid = r.get("cluster_id")
            if cid is not None:
                results_by_id[cid] = r

        # Apply to clusters
        for cluster in batch:
            result = results_by_id.get(cluster["id"])
            if not result:
                continue

            if args.dry_run:
                modern = result.get("modern_name", "?")
                conf = result.get("confidence", "?")
                rtype = result.get("type", "?")
                linnaean = result.get("linnaean", "")
                note = result.get("note", "")
                extra = ""
                if linnaean:
                    extra = f" [{linnaean}]"
                if note:
                    extra += f" — {note}"
                print(f"  {cluster['canonical_name']} -> {modern} ({rtype}, {conf}){extra}")
                total_enriched += 1
                continue

            # Wikidata lookup (with rate limiting)
            if not args.skip_wikidata:
                enrich_cluster(cluster, result)
                if cluster.get("ground_truth", {}).get("wikidata_id"):
                    total_wikidata += 1
                time.sleep(0.2)  # Rate limit Wikidata
            else:
                # Just apply Gemini result without Wikidata
                ground_truth = {
                    "modern_name": result.get("modern_name", cluster["canonical_name"]),
                    "confidence": result.get("confidence", "low"),
                    "type": result.get("type", ""),
                }
                for field in ["birth_year", "death_year", "description", "linnaean",
                              "family", "country", "modern_term", "note",
                              "wikidata_search"]:
                    if result.get(field):
                        ground_truth[field] = result[field]
                cluster["ground_truth"] = ground_truth

            total_enriched += 1

        if not args.dry_run:
            print(f"  Enriched {len([c for c in batch if 'ground_truth' in c])}/{len(batch)}"
                  f" (Wikidata: {sum(1 for c in batch if c.get('ground_truth', {}).get('wikidata_id'))})")

        # Rate limiting between batches
        time.sleep(1)

    if args.dry_run:
        print(f"\nDry run complete. {total_enriched} clusters identified.")
        return

    # Stats
    enriched_count = sum(1 for c in clusters if "ground_truth" in c)
    with_wikidata = sum(1 for c in clusters if c.get("ground_truth", {}).get("wikidata_id"))
    with_wikipedia = sum(1 for c in clusters if c.get("ground_truth", {}).get("wikipedia_url"))
    with_linnaean = sum(1 for c in clusters if c.get("ground_truth", {}).get("linnaean"))
    high_conf = sum(1 for c in clusters if c.get("ground_truth", {}).get("confidence") == "high")
    med_conf = sum(1 for c in clusters if c.get("ground_truth", {}).get("confidence") == "medium")
    low_conf = sum(1 for c in clusters if c.get("ground_truth", {}).get("confidence") == "low")

    data["metadata"]["enriched"] = True
    data["metadata"]["enrichment_model"] = args.model
    data["stats"]["enriched_clusters"] = enriched_count
    data["stats"]["with_wikidata"] = with_wikidata
    data["stats"]["with_wikipedia"] = with_wikipedia
    data["stats"]["with_linnaean"] = with_linnaean

    print(f"\nEnrichment Results:")
    print(f"  Total enriched: {enriched_count}/{len(clusters)}")
    print(f"  With Wikidata ID: {with_wikidata}")
    print(f"  With Wikipedia URL: {with_wikipedia}")
    print(f"  With Linnaean name: {with_linnaean}")
    print(f"  Confidence: {high_conf} high, {med_conf} medium, {low_conf} low")
    print(f"  Failed batches: {failed_batches}")

    # Save
    output_path = Path(args.output) if args.output else concordance_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nSaved to: {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

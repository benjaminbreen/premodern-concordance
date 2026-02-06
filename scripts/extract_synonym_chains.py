#!/usr/bin/env python3
"""
Second-pass entity extraction: find unextracted entity names in synonym chains.

Scans existing text excerpts (from *_entities.json) for passages that contain
synonym chain markers (cross-linguistic equivalences like "o vero", "called",
"chamam", etc.) and asks Gemini to identify entity names mentioned alongside
already-known entities that were missed in the initial extraction.

Usage:
    python3 extract_synonym_chains.py                    # full run
    python3 extract_synonym_chains.py --dry-run          # show excerpts only
    python3 extract_synonym_chains.py --batch-size 10    # excerpts per Gemini call
    python3 extract_synonym_chains.py --limit 50         # process only first N excerpts
"""

import argparse
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local")

from google import genai

BASE_DIR = Path(__file__).resolve().parent.parent
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"
DATA_DIR = BASE_DIR / "web" / "public" / "data"
OUTPUT_DIR = BASE_DIR / "data" / "synonym_chains"

# Book ID → entity file mapping
BOOK_ENTITY_FILES = {
    "ricettario_fiorentino_1597": "ricettario_entities.json",
    "coloquios_da_orta_1563": "orta_entities.json",
    "english_physician_1652": "culpeper_entities.json",
    "historia_medicinal_monardes_1574": "monardes_entities.json",
    "polyanthea_medicinal": "semedo_entities.json",
    "relation_historique_humboldt_vol3_1825": "humboldt_entities.json",
}

# Synonym chain markers by language — regex patterns that signal cross-linguistic
# equivalences or alternative names in early modern texts
SYNONYM_MARKERS = re.compile(
    r"""
    # Italian (Ricettario)
    \bo\s+vero\b |
    \bcioè\b |
    \bche\s+si\s+chiama\b |
    \bdetto\b |
    \bovero\b |

    # Portuguese (Orta, Semedo)
    \bchamam\b |
    \bchamão\b |
    \bpor\s+outro\s+nome\b |
    \bque\s+(?:os|he|é)\b.{0,20}\bcham[aã]\b |
    \bvulgarmente\b |

    # Spanish (Monardes)
    \bllamada?\b |
    \bque\s+llaman\b |
    \bpor\s+otro\s+nombre\b |

    # English (Culpeper)
    \bcalled\b |
    \balso\s+called\b |
    \bknown\s+(?:as|by)\b |
    \bwhich\s+(?:is|some)\s+call\b |

    # French (Humboldt)
    \bnommée?\b |
    \bqu['\u2019]on\s+appelle\b |
    \bdit(?:e|s)?\b |

    # Latin (appears across all)
    \bvulgo\b |
    \bid\s+est\b |
    \bsive\b |
    \bquod\b.{0,15}\bvocant\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# Minimum excerpt length to bother analyzing
MIN_EXCERPT_LEN = 80


def load_entity_index(book_id: str) -> dict[str, list[dict]]:
    """Load entity file and return {entity_name_lower: [mentions]}."""
    fname = BOOK_ENTITY_FILES.get(book_id)
    if not fname:
        return {}
    path = DATA_DIR / fname
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    index = {}
    for ent in data["entities"]:
        key = ent["name"].lower()
        index[key] = ent.get("mentions", [])
    return index


def build_concordance_vocab(clusters: list[dict]) -> tuple[set[str], dict[str, list[int]]]:
    """Build a set of all known entity names and a name→cluster_id mapping."""
    vocab = set()
    name_to_clusters = defaultdict(list)
    for cluster in clusters:
        canon = cluster["canonical_name"].lower()
        vocab.add(canon)
        name_to_clusters[canon].append(cluster["id"])
        if cluster.get("ground_truth", {}).get("modern_name"):
            mn = cluster["ground_truth"]["modern_name"].lower()
            vocab.add(mn)
            name_to_clusters[mn].append(cluster["id"])
        for member in cluster["members"]:
            n = member["name"].lower()
            vocab.add(n)
            name_to_clusters[n].append(cluster["id"])
            for v in member.get("variants", []):
                vl = v.lower()
                vocab.add(vl)
                name_to_clusters[vl].append(cluster["id"])
    return vocab, dict(name_to_clusters)


def find_synonym_chain_excerpts(clusters: list[dict]) -> list[dict]:
    """Find excerpts with synonym chain markers for concordance members."""
    results = []
    seen_excerpts = set()

    # Load all entity files
    entity_indices = {}
    for book_id in BOOK_ENTITY_FILES:
        entity_indices[book_id] = load_entity_index(book_id)

    for cluster in clusters:
        for member in cluster["members"]:
            book_id = member["book_id"]
            entity_name = member["name"].lower()

            mentions = entity_indices.get(book_id, {}).get(entity_name, [])
            if not mentions:
                # Try variants
                for v in member.get("variants", []):
                    mentions = entity_indices.get(book_id, {}).get(v.lower(), [])
                    if mentions:
                        break

            for mention in mentions:
                excerpt = mention.get("excerpt", "")
                if len(excerpt) < MIN_EXCERPT_LEN:
                    continue

                # Check for synonym chain markers
                if not SYNONYM_MARKERS.search(excerpt):
                    continue

                # Deduplicate by excerpt content (first 100 chars + book)
                dedup_key = (book_id, excerpt[:100])
                if dedup_key in seen_excerpts:
                    continue
                seen_excerpts.add(dedup_key)

                results.append({
                    "cluster_id": cluster["id"],
                    "cluster_name": cluster["canonical_name"],
                    "category": cluster["category"],
                    "modern_name": cluster.get("ground_truth", {}).get("modern_name", ""),
                    "member_name": member["name"],
                    "book_id": book_id,
                    "excerpt": excerpt,
                    "matched_term": mention.get("matched_term", ""),
                })

    return results


def build_extraction_prompt(batch: list[dict], known_vocab_sample: list[str]) -> str:
    """Build Gemini prompt for extracting unextracted entity names from excerpts."""
    lines = [
        "You are an expert in early modern medicine, pharmacy, and natural history (1500-1900).",
        "You read Italian, Portuguese, Spanish, English, French, and Latin.",
        "",
        "I will show you text excerpts from early modern books. Each excerpt was originally",
        "found because it mentions a KNOWN entity. Your task is to find OTHER entity names",
        "in the same excerpt that were NOT extracted — especially synonym chains where the",
        "author lists equivalent terms across languages or nomenclatural traditions.",
        "",
        "For each excerpt, identify any substance, plant, animal, disease, place, or person",
        "names that appear but are NOT the known entity. Focus especially on:",
        "- Cross-linguistic synonyms (e.g. 'pompholige' alongside 'Spodio')",
        "- Alternative names introduced by 'o vero', 'called', 'chamam', 'detto', 'sive', etc.",
        "- Trade names, vernacular names, or classical names for the same thing",
        "",
        "Return a JSON array. For each excerpt where you find unextracted entities, return:",
        '{',
        '  "excerpt_idx": <0-based index in the list below>,',
        '  "new_entities": [',
        '    {',
        '      "name": "<the entity name as it appears in the text>",',
        '      "normalized": "<modern/standard form if known, else same as name>",',
        '      "category": "<SUBSTANCE|PLANT|ANIMAL|DISEASE|PERSON|PLACE|CONCEPT>",',
        '      "relationship": "<what it is in relation to the known entity>",',
        '      "confidence": "<high|medium|low>"',
        '    }',
        '  ]',
        '}',
        "",
        "RULES:",
        "- Only extract NAMED entities — not generic words like 'medicine' or 'water'",
        "  (unless they are being used as a specific name, e.g. 'aqua vitae')",
        "- DO NOT re-extract the known entity or obvious variants of it",
        "- DO extract cross-linguistic equivalents even if they look similar",
        "  (e.g. 'pompholige' is different from 'pompholix')",
        "- Skip excerpts with no new entities (don't include them in output)",
        "- Keep 'name' as the EXACT text from the excerpt (preserve OCR spelling)",
        "- Return ONLY the JSON array, no other text",
        "",
        "EXCERPTS:",
        "",
    ]

    for i, item in enumerate(batch):
        lines.append(f"[{i}] Known entity: \"{item['member_name']}\" "
                     f"(cluster: {item['cluster_name']}, {item['category']}"
                     f"{', modern: ' + item['modern_name'] if item['modern_name'] else ''})")
        lines.append(f"    Book: {item['book_id']}")
        lines.append(f"    Excerpt: \"{item['excerpt'][:500]}\"")
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


def match_to_clusters(entity_name: str, name_to_clusters: dict[str, list[int]]) -> list[int]:
    """Try to match a newly found entity name to existing concordance clusters."""
    key = entity_name.lower().strip()
    if key in name_to_clusters:
        return name_to_clusters[key]

    # Try without trailing punctuation
    cleaned = re.sub(r'[.,;:!?\'"]+$', '', key)
    if cleaned in name_to_clusters:
        return name_to_clusters[cleaned]

    # Try with common OCR substitutions
    for old, new in [('ſ', 's'), ('ƒ', 'f'), ('ﬁ', 'fi'), ('ﬂ', 'fl')]:
        alt = key.replace(old, new)
        if alt in name_to_clusters:
            return name_to_clusters[alt]

    return []


def main():
    parser = argparse.ArgumentParser(description="Extract synonym chains from excerpts")
    parser.add_argument("--dry-run", action="store_true", help="Show excerpts without LLM calls")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model")
    parser.add_argument("--batch-size", type=int, default=8, help="Excerpts per Gemini call")
    parser.add_argument("--limit", type=int, default=0, help="Max excerpts to process (0=all)")
    args = parser.parse_args()

    # Load concordance
    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        conc = json.load(f)
    clusters = conc["clusters"]
    print(f"  {len(clusters)} clusters")

    # Build vocabulary of known entity names
    print("Building vocabulary...")
    vocab, name_to_clusters = build_concordance_vocab(clusters)
    print(f"  {len(vocab)} known entity names/variants")

    # Find synonym chain excerpts
    print("Scanning for synonym chain excerpts...")
    excerpts = find_synonym_chain_excerpts(clusters)
    print(f"  Found {len(excerpts)} excerpts with synonym chain markers")

    # Book breakdown
    by_book = defaultdict(int)
    for e in excerpts:
        by_book[e["book_id"]] += 1
    for book, count in sorted(by_book.items(), key=lambda x: -x[1]):
        print(f"    {book}: {count}")

    if args.limit > 0:
        excerpts = excerpts[:args.limit]
        print(f"  Limited to {len(excerpts)} excerpts")

    if args.dry_run:
        # Just show some examples
        print(f"\nSample excerpts with synonym chain markers:\n")
        for ex in excerpts[:20]:
            markers = SYNONYM_MARKERS.findall(ex["excerpt"])
            print(f"  [{ex['cluster_id']}] {ex['cluster_name']} — {ex['member_name']} ({ex['book_id']})")
            print(f"    Markers: {markers[:3]}")
            print(f"    Excerpt: {ex['excerpt'][:150]}...")
            print()

        print(f"\nDry run complete. {len(excerpts)} excerpts would be processed.")
        return

    # Initialize Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found. Set it in .env.local or environment.")
    client = genai.Client(api_key=api_key)
    print(f"\nUsing model: {args.model}")

    # Process in batches
    all_findings = []
    total_new_entities = 0
    total_matched = 0
    total_unmatched = 0
    failed_batches = 0

    num_batches = (len(excerpts) + args.batch_size - 1) // args.batch_size
    print(f"Processing {len(excerpts)} excerpts in {num_batches} batches...\n")

    for batch_idx in range(0, len(excerpts), args.batch_size):
        batch = excerpts[batch_idx:batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1

        print(f"Batch {batch_num}/{num_batches} ({len(batch)} excerpts)...", end=" ", flush=True)

        prompt = build_extraction_prompt(batch, [])
        results = call_gemini(prompt, client, args.model)

        if results is None:
            print("FAILED")
            failed_batches += 1
            time.sleep(2)
            continue

        batch_new = 0
        batch_matched = 0
        for result in results:
            idx = result.get("excerpt_idx")
            if idx is None or idx >= len(batch):
                continue

            source_excerpt = batch[idx]
            new_entities = result.get("new_entities", [])

            for entity in new_entities:
                ename = entity.get("name", "")
                if not ename:
                    continue

                # Try to match to existing clusters
                matching_clusters = match_to_clusters(ename, name_to_clusters)
                normalized = entity.get("normalized", ename)
                matching_clusters_norm = match_to_clusters(normalized, name_to_clusters)
                all_matches = list(set(matching_clusters + matching_clusters_norm))

                finding = {
                    "source_cluster_id": source_excerpt["cluster_id"],
                    "source_cluster_name": source_excerpt["cluster_name"],
                    "source_category": source_excerpt["category"],
                    "source_modern_name": source_excerpt["modern_name"],
                    "source_member": source_excerpt["member_name"],
                    "source_book": source_excerpt["book_id"],
                    "found_name": ename,
                    "found_normalized": normalized,
                    "found_category": entity.get("category", ""),
                    "found_relationship": entity.get("relationship", ""),
                    "found_confidence": entity.get("confidence", ""),
                    "matched_cluster_ids": all_matches,
                    "is_cross_cluster_link": len(all_matches) > 0 and source_excerpt["cluster_id"] not in all_matches,
                    "excerpt_snippet": source_excerpt["excerpt"][:200],
                }
                all_findings.append(finding)
                batch_new += 1
                if all_matches:
                    batch_matched += 1

        total_new_entities += batch_new
        total_matched += batch_matched
        total_unmatched += (batch_new - batch_matched)
        print(f"found {batch_new} entities ({batch_matched} matched to existing clusters)")

        time.sleep(1)  # Rate limit

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Full findings
    findings_path = OUTPUT_DIR / "findings.json"
    with open(findings_path, "w") as f:
        json.dump(all_findings, f, indent=2, ensure_ascii=False)

    # Cross-cluster links (the gold: entity A's excerpt mentions entity B)
    cross_links = [f for f in all_findings if f["is_cross_cluster_link"]]
    links_path = OUTPUT_DIR / "cross_cluster_links.json"
    with open(links_path, "w") as f:
        json.dump(cross_links, f, indent=2, ensure_ascii=False)

    # Unmatched entities (potential new clusters or members)
    unmatched = [f for f in all_findings if not f["matched_cluster_ids"]]
    unmatched_path = OUTPUT_DIR / "unmatched_entities.json"
    with open(unmatched_path, "w") as f:
        json.dump(unmatched, f, indent=2, ensure_ascii=False)

    # Summary CSV
    csv_path = OUTPUT_DIR / "summary.csv"
    with open(csv_path, "w") as f:
        f.write("source_cluster,source_modern,found_name,found_normalized,category,relationship,confidence,matched_clusters,is_cross_link\n")
        for finding in all_findings:
            matched = ";".join(str(c) for c in finding["matched_cluster_ids"])
            rel = finding["found_relationship"].replace(",", ";").replace('"', "'")
            f.write(f'"{finding["source_cluster_name"]}","{finding["source_modern_name"]}",'
                    f'"{finding["found_name"]}","{finding["found_normalized"]}",'
                    f'{finding["found_category"]},"{rel}",'
                    f'{finding["found_confidence"]},{matched},{finding["is_cross_cluster_link"]}\n')

    # Print summary
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Excerpts processed:     {len(excerpts)}")
    print(f"Failed batches:         {failed_batches}")
    print(f"New entities found:     {total_new_entities}")
    print(f"  Matched to clusters:  {total_matched}")
    print(f"  Unmatched (new):      {total_unmatched}")
    print(f"  Cross-cluster links:  {len(cross_links)}")
    print(f"\nOutput files:")
    print(f"  {findings_path}")
    print(f"  {links_path} ({len(cross_links)} links)")
    print(f"  {unmatched_path} ({len(unmatched)} entities)")
    print(f"  {csv_path}")

    # Show some cross-cluster link examples
    if cross_links:
        print(f"\nSample cross-cluster links:")
        for link in cross_links[:10]:
            target_ids = [c for c in link["matched_cluster_ids"] if c != link["source_cluster_id"]]
            # Look up target cluster names
            cmap = {c["id"]: c["canonical_name"] for c in clusters}
            targets = [f"{cmap.get(tid, '?')} (#{tid})" for tid in target_ids]
            print(f"  {link['source_cluster_name']} excerpt mentions '{link['found_name']}' "
                  f"→ links to {', '.join(targets)}")
            print(f"    Relationship: {link['found_relationship']}")


if __name__ == "__main__":
    main()

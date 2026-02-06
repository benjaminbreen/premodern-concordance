#!/usr/bin/env python3
"""
Enrich concordance clusters with semantic glosses for improved search.

Generates a 2-3 sentence `semantic_gloss` for each cluster describing its
thematic/conceptual associations in early modern medicine and natural philosophy.

Usage:
    python enrich_semantic_tags.py
    python enrich_semantic_tags.py --dry-run
    python enrich_semantic_tags.py --batch-size 8
"""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).parent.parent / ".env.local")

DEFAULT_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"


def build_gloss_prompt(clusters: list[dict]) -> str:
    """Build a prompt for Gemini to generate semantic glosses for a batch of clusters."""
    lines = [
        "You are a historian of science and medicine with deep expertise in early modern",
        "texts (1500-1800) in Portuguese, Spanish, Latin, and English.",
        "",
        "For each entity cluster below from a database of early modern medical/scientific texts,",
        "write a SHORT semantic gloss (2-3 sentences) describing its thematic and conceptual",
        "associations in the early modern period.",
        "",
        "IMPORTANT RULES:",
        "- This is a HISTORICAL DATABASE covering 1500-1800. Interpret everything in that context.",
        '  "Mercury" = the alchemical element/planet, NOT a musician or spacecraft.',
        '  "Dragon" = a real or mythical creature in natural history, NOT a fantasy game creature.',
        "- Focus on THEMATIC and CONCEPTUAL associations, not encyclopedic facts.",
        "- Include related concepts, medical uses, symbolic meanings, and cultural associations",
        "  that someone searching this database might use as query terms.",
        "- Use plain language. Include keywords that a researcher might search for.",
        "- Do NOT start with the entity name. Jump straight into the thematic description.",
        "",
        "Return a JSON array with one object per cluster:",
        '[{"cluster_id": <number>, "semantic_gloss": "<2-3 sentence thematic description>"}]',
        "",
        "Return ONLY the JSON array, no other text.",
        "",
        "CLUSTERS:",
        "",
    ]

    for cluster in clusters:
        gt = cluster.get("ground_truth", {})
        modern_name = gt.get("modern_name", "")
        entity_type = gt.get("type", cluster.get("category", ""))
        description = gt.get("description", "") or gt.get("wikidata_description", "")

        members_str = "; ".join(
            f'"{m["name"]}" ({m["book_id"]})'
            for m in cluster["members"][:5]
        )

        # Gather context strings from source texts
        contexts = []
        for m in cluster["members"]:
            contexts.extend(m.get("contexts", [])[:2])
        ctx_str = " | ".join(contexts[:5]) if contexts else "no context available"

        lines.append(
            f"  ID {cluster['id']} [{cluster['category']}/"
            f"{cluster.get('subcategory', '')}] "
            f'"{cluster["canonical_name"]}"'
        )
        if modern_name and modern_name != cluster["canonical_name"]:
            lines.append(f"    Modern name: {modern_name}")
        if description:
            lines.append(f"    Description: {description}")
        lines.append(f"    Members: {members_str}")
        lines.append(f"    Source contexts: {ctx_str}")
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


def main():
    parser = argparse.ArgumentParser(description="Enrich clusters with semantic glosses")
    parser.add_argument("--concordance", default=str(DEFAULT_PATH), help="Concordance JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print glosses without saving")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model")
    parser.add_argument("--batch-size", type=int, default=8, help="Clusters per Gemini call")
    parser.add_argument("--output", help="Output file (default: overwrites input)")
    args = parser.parse_args()

    # Load
    concordance_path = Path(args.concordance)
    with open(concordance_path) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Loaded {len(clusters)} clusters")

    # Filter to clusters without semantic_gloss (incremental)
    to_enrich = [c for c in clusters if not c.get("ground_truth", {}).get("semantic_gloss")]
    already_done = len(clusters) - len(to_enrich)
    if already_done > 0:
        print(f"  {already_done} already have glosses, {len(to_enrich)} remaining")

    if not to_enrich:
        print("All clusters already have semantic glosses.")
        return

    # Initialize Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found. Set it in .env.local or environment.")

    client = genai.Client(api_key=api_key)
    print(f"Using model: {args.model}")
    print(f"Batch size: {args.batch_size}")

    # Process in batches
    total_glossed = 0
    failed_batches = 0

    num_batches = (len(to_enrich) + args.batch_size - 1) // args.batch_size
    print(f"\nProcessing {len(to_enrich)} clusters in {num_batches} batches...\n")

    for batch_idx in range(0, len(to_enrich), args.batch_size):
        batch = to_enrich[batch_idx:batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1

        print(f"Batch {batch_num}/{num_batches} ({len(batch)} clusters)...", flush=True)

        prompt = build_gloss_prompt(batch)
        results = call_gemini(prompt, client, args.model)

        if not results:
            print(f"  Failed — skipping batch")
            failed_batches += 1
            time.sleep(2)
            continue

        # Map results by cluster_id
        results_by_id = {}
        for r in results:
            cid = r.get("cluster_id")
            if cid is not None:
                results_by_id[cid] = r

        # Apply glosses
        batch_count = 0
        for cluster in batch:
            result = results_by_id.get(cluster["id"])
            if not result or not result.get("semantic_gloss"):
                continue

            gloss = result["semantic_gloss"].strip()

            if args.dry_run:
                print(f"  [{cluster['category']}] {cluster['canonical_name']}")
                print(f"    -> {gloss}")
                total_glossed += 1
                continue

            # Ensure ground_truth exists
            if "ground_truth" not in cluster:
                cluster["ground_truth"] = {}
            cluster["ground_truth"]["semantic_gloss"] = gloss
            total_glossed += 1
            batch_count += 1

        if not args.dry_run:
            print(f"  Glossed {batch_count}/{len(batch)} clusters")

        # Rate limiting between batches
        time.sleep(1)

    if args.dry_run:
        print(f"\nDry run complete. {total_glossed} glosses generated.")
        return

    # Stats
    with_gloss = sum(1 for c in clusters if c.get("ground_truth", {}).get("semantic_gloss"))
    print(f"\nResults:")
    print(f"  Total with semantic gloss: {with_gloss}/{len(clusters)}")
    print(f"  Newly glossed: {total_glossed}")
    print(f"  Failed batches: {failed_batches}")

    # Save
    output_path = Path(args.output) if args.output else concordance_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nSaved to: {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Export expert-reviewed membership decisions as fine-tuning training data.

Generates a JSONL file with labeled examples of whether a member belongs in a
cluster. Each example includes the cluster context (canonical name, category,
modern identification) and the member context (name, book, usage context),
plus the expert verdict (KEEP or SPLIT) with reasoning.

This data can be used for:
1. Fine-tuning embedding models (contrastive pairs: positive=KEEP, negative=SPLIT)
2. Fine-tuning classification models (binary: belongs/doesn't belong)
3. Training cross-linguistic entity matching models
"""

import json
from pathlib import Path

# Import the SPLITS dictionary from apply_member_splits
from apply_member_splits import SPLITS

FLAGGED = Path("/private/tmp/claude-501/-Users-benjaminbreen-code-Premodern-Concordance/1875c373-eedc-4712-921e-bb6790800ad5/scratchpad/flagged.json")
CONCORDANCE = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "concordance.json"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "training" / "membership_decisions.jsonl"

# Reasoning for KEEP decisions — organized by pattern type
KEEP_REASONS = {
    # Cross-language translations
    "translation": "Valid cross-language translation of the same concept",
    # Descriptive phrases containing the concept
    "phrase": "Descriptive phrase containing the canonical concept",
    # Historical variant name
    "variant": "Historical variant name or spelling for the same entity",
    # OCR artifact of the correct word
    "ocr": "OCR artifact of the canonical name, same entity",
    # Contextually related subtype
    "subtype": "Specific subtype or variety of the canonical concept",
    # Same concept in different register/context
    "register": "Same concept in a different medical/scholarly register",
}


def classify_keep_reason(member, cluster_name, modern, category):
    """Heuristically classify why a KEEP member belongs."""
    name = member["member"].lower()
    canon = cluster_name.lower()
    mod = (modern or "").lower()

    # If the member name contains the canonical name
    if canon in name or (mod and mod in name):
        return "phrase", f"Contains '{canon}' — descriptive phrase for {modern or cluster_name}"

    # If it's from a different language book
    book = member["book"]
    lang_map = {
        "english_physician_1652": "English",
        "historia_medicinal_monardes_1574": "Spanish",
        "coloquios_da_orta_1563": "Portuguese",
        "ricettario_fiorentino_1597": "Italian",
        "polyanthea_medicinal": "Portuguese",
        "relation_historique_humboldt_vol3_1825": "French",
    }
    lang = lang_map.get(book, "unknown")

    # Check if context confirms relationship
    ctx = (member.get("ctx") or "").lower()
    if mod and mod.lower() in ctx:
        return "translation", f"{lang} term for {modern}: context confirms '{mod}' meaning"

    if canon in ctx:
        return "translation", f"{lang} term related to {cluster_name}: context mentions '{canon}'"

    # Low string similarity but valid — likely translation
    if member["sc"] < 0.3 and member["sm"] < 0.3:
        return "translation", f"Cross-linguistic match: '{member['member']}' ({lang}) = {modern or cluster_name}"

    # Moderate similarity — variant
    if member["sc"] >= 0.3:
        return "variant", f"Variant spelling/form of {cluster_name}: '{member['member']}'"

    return "subtype", f"Related term in {lang}: '{member['member']}' for {modern or cluster_name}"


def main():
    # Load flagged members
    with open(FLAGGED) as f:
        flagged = json.load(f)

    # Load concordance for additional context
    with open(CONCORDANCE) as f:
        conc = json.load(f)
    cluster_map = {c["id"]: c for c in conc["clusters"]}

    # Build split set for quick lookup
    split_set = set(SPLITS.keys())

    # Generate training examples
    examples = []

    for entry in flagged:
        cid = entry["cid"]
        member_name = entry["member"]
        key = (cid, member_name)

        cluster = cluster_map.get(cid)
        if not cluster:
            continue

        gt = cluster.get("ground_truth", {})
        modern = gt.get("modern_name") or ""
        wikidata_desc = gt.get("wikidata_description") or ""

        # Build the cluster context string (what an embedding model would see)
        cluster_text = f"{entry['cluster']} ({entry['cat']})"
        if modern:
            cluster_text += f" — modern: {modern}"
        if wikidata_desc:
            cluster_text += f" — {wikidata_desc}"

        # Build the member context string
        member_text = f"{member_name}"
        if entry.get("ctx"):
            member_text += f" — context: {entry['ctx']}"

        # Source book
        book_labels = {
            "english_physician_1652": "Culpeper's English Physician (1652, English)",
            "historia_medicinal_monardes_1574": "Monardes' Historia Medicinal (1574, Spanish)",
            "coloquios_da_orta_1563": "Garcia de Orta's Colóquios (1563, Portuguese)",
            "ricettario_fiorentino_1597": "Ricettario Fiorentino (1597, Italian)",
            "polyanthea_medicinal": "Polyanthea Medicinal (c.1700, Portuguese)",
            "relation_historique_humboldt_vol3_1825": "Humboldt's Relation Historique (1825, French)",
        }
        source = book_labels.get(entry["book"], entry["book"])

        if key in split_set:
            # SPLIT decision
            verdict = "SPLIT"
            reason = SPLITS[key]
            pattern = "mismatch"
        else:
            # KEEP decision
            verdict = "KEEP"
            pattern, reason = classify_keep_reason(entry, entry["cluster"], modern, entry["cat"])

        example = {
            # Cluster info
            "cluster_id": cid,
            "cluster_name": entry["cluster"],
            "category": entry["cat"],
            "modern_name": modern,
            "wikidata_description": wikidata_desc,

            # Member info
            "member_name": member_name,
            "member_book": entry["book"],
            "member_source": source,
            "member_count": entry["count"],
            "member_context": entry.get("ctx", ""),

            # Similarity scores
            "sim_to_canonical": entry["sc"],
            "sim_to_modern": entry["sm"],
            "sim_to_best_other": entry["so"],

            # Expert verdict
            "verdict": verdict,
            "pattern": pattern,
            "reason": reason,

            # Embedding-ready text pairs (for contrastive learning)
            "anchor_text": cluster_text,
            "candidate_text": member_text,
            "label": 1 if verdict == "KEEP" else 0,
        }

        examples.append(example)

    # Sort: SPLITs first (more interesting for training), then KEEPs
    examples.sort(key=lambda x: (x["verdict"] != "SPLIT", x["cluster_id"]))

    # Write output
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Also write a summary CSV for easy viewing
    csv_path = OUTPUT.with_suffix(".csv")
    with open(csv_path, "w") as f:
        f.write("verdict,cluster_name,modern_name,category,member_name,source_lang,pattern,reason,sim_canonical,sim_modern\n")
        for ex in examples:
            lang = ex["member_source"].split("(")[-1].rstrip(")").split(",")[-1].strip() if "(" in ex["member_source"] else ""
            reason_clean = ex["reason"].replace(",", ";").replace('"', "'")
            f.write(f'{ex["verdict"]},{ex["cluster_name"]},{ex["modern_name"]},{ex["category"]},'
                    f'{ex["member_name"]},{lang},{ex["pattern"]},"{reason_clean}",'
                    f'{ex["sim_to_canonical"]},{ex["sim_to_modern"]}\n')

    # Print stats
    n_split = sum(1 for e in examples if e["verdict"] == "SPLIT")
    n_keep = sum(1 for e in examples if e["verdict"] == "KEEP")

    print(f"Exported {len(examples)} training examples to {OUTPUT}")
    print(f"  CSV summary: {csv_path}")
    print(f"  SPLIT (negative): {n_split}")
    print(f"  KEEP  (positive): {n_keep}")
    print(f"  Ratio: {n_keep/n_split:.1f}:1 positive:negative")

    # Pattern breakdown
    from collections import Counter
    patterns = Counter(e["pattern"] for e in examples)
    print(f"\nPattern breakdown:")
    for pat, cnt in patterns.most_common():
        print(f"  {pat}: {cnt}")

    # Category breakdown
    cats = Counter((e["category"], e["verdict"]) for e in examples)
    print(f"\nBy category:")
    for cat in sorted(set(c for c, _ in cats)):
        k = cats.get((cat, "KEEP"), 0)
        s = cats.get((cat, "SPLIT"), 0)
        print(f"  {cat}: {k} keep, {s} split")


if __name__ == "__main__":
    main()

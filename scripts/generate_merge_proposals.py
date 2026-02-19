#!/usr/bin/env python3
"""
Generate merge proposals for concordance clusters.

Finds clusters that likely refer to the same entity based on:
  1. Same Wikidata ID + same category
  2. Same modern_name + same category (different or no QIDs)

Outputs a reviewable JSON file with proposals grouped by confidence.

Usage:
    python3 scripts/generate_merge_proposals.py
    python3 scripts/generate_merge_proposals.py --output data/merge_proposals.json
"""

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "merge_proposals.json"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def member_name_set(cluster: dict) -> set[str]:
    names = set()
    for m in cluster.get("members", []):
        n = normalize(m.get("name", ""))
        if n:
            names.add(n)
    return names


def has_name_overlap(clusters: list[dict]) -> bool:
    """Check if any two clusters share a normalized member name."""
    all_names = []
    for c in clusters:
        all_names.append(member_name_set(c))
    for i in range(len(all_names)):
        for j in range(i + 1, len(all_names)):
            if all_names[i] & all_names[j]:
                return True
    return False


def canonical_overlap(clusters: list[dict]) -> bool:
    """Check if canonical names share significant substrings."""
    names = [normalize(c.get("canonical_name", "")) for c in clusters]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if not a or not b:
                continue
            # Substring check
            if a in b or b in a:
                return True
            # Shared word check
            wa = set(a.split())
            wb = set(b.split())
            shared = wa & wb - {"the", "a", "of", "de", "da", "do", "di", "del", "la", "le", "el"}
            if shared:
                return True
    return False


def format_cluster_summary(c: dict) -> dict:
    gt = c.get("ground_truth") or {}
    members = c.get("members", [])
    member_names = sorted(set(m["name"] for m in members))[:8]
    return {
        "id": c["id"],
        "canonical_name": c.get("canonical_name", ""),
        "category": c.get("category", ""),
        "modern_name": gt.get("modern_name", ""),
        "wikidata_id": gt.get("wikidata_id", ""),
        "book_count": c.get("book_count", 0),
        "total_mentions": c.get("total_mentions", 0),
        "member_count": len(members),
        "sample_names": member_names,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"Loaded {len(clusters)} clusters")

    proposals = []

    # --- Tier 1: Same Wikidata ID + same category ---
    by_qid_cat = defaultdict(list)
    for c in clusters:
        gt = c.get("ground_truth") or {}
        qid = (gt.get("wikidata_id") or "").strip()
        if qid:
            key = (qid, c.get("category", ""))
            by_qid_cat[key].append(c)

    for (qid, cat), group in by_qid_cat.items():
        if len(group) < 2:
            continue

        overlap = has_name_overlap(group)
        can_overlap = canonical_overlap(group)

        if overlap or can_overlap:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"

        proposals.append({
            "reason": f"same_wikidata_id ({qid})",
            "confidence": confidence,
            "merge": True,
            "clusters": [format_cluster_summary(c) for c in group],
        })

    # --- Tier 2: Same modern_name + same category, different QIDs ---
    by_mn_cat = defaultdict(list)
    for c in clusters:
        gt = c.get("ground_truth") or {}
        mn = (gt.get("modern_name") or "").strip().lower()
        if mn and len(mn) > 2:
            key = (mn, c.get("category", ""))
            by_mn_cat[key].append(c)

    # Track QID groups to avoid duplicates
    qid_cat_keys = set(by_qid_cat.keys())

    for (mn, cat), group in by_mn_cat.items():
        if len(group) < 2:
            continue

        # Skip if all share a single QID (already in tier 1)
        qids = set()
        for c in group:
            qid = ((c.get("ground_truth") or {}).get("wikidata_id") or "").strip()
            if qid:
                qids.add(qid)
        if len(qids) == 1 and (list(qids)[0], cat) in qid_cat_keys:
            continue

        overlap = has_name_overlap(group)
        can_overlap = canonical_overlap(group)

        if overlap:
            confidence = "HIGH"
        elif can_overlap:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        proposals.append({
            "reason": f"same_modern_name (\"{mn}\")",
            "confidence": confidence,
            "merge": True,
            "clusters": [format_cluster_summary(c) for c in group],
        })

    # Sort: HIGH first, then by total mentions
    confidence_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    proposals.sort(key=lambda p: (
        confidence_order.get(p["confidence"], 99),
        -sum(c["total_mentions"] for c in p["clusters"]),
    ))

    # Stats
    high = sum(1 for p in proposals if p["confidence"] == "HIGH")
    med = sum(1 for p in proposals if p["confidence"] == "MEDIUM")
    low = sum(1 for p in proposals if p["confidence"] == "LOW")

    print(f"\nMerge proposals: {len(proposals)}")
    print(f"  HIGH confidence: {high}")
    print(f"  MEDIUM confidence: {med}")
    print(f"  LOW confidence: {low}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"proposals": proposals, "stats": {"high": high, "medium": med, "low": low, "total": len(proposals)}}, f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_path}")

    # Print summary for quick review
    print(f"\n=== HIGH confidence proposals ({high}) ===")
    for p in proposals:
        if p["confidence"] != "HIGH":
            continue
        names = " + ".join(c["canonical_name"] for c in p["clusters"])
        cat = p["clusters"][0]["category"]
        mentions = sum(c["total_mentions"] for c in p["clusters"])
        print(f"  [{cat}] {names}  ({p['reason']}, {mentions} mentions)")

    print(f"\n=== MEDIUM confidence proposals ({med}) — review these ===")
    for p in proposals:
        if p["confidence"] != "MEDIUM":
            continue
        names = " + ".join(c["canonical_name"] for c in p["clusters"])
        cat = p["clusters"][0]["category"]
        mentions = sum(c["total_mentions"] for c in p["clusters"])
        samples = []
        for c in p["clusters"]:
            samples.extend(c["sample_names"][:3])
        print(f"  [{cat}] {names}  ({p['reason']}, {mentions} mentions)")
        print(f"         samples: {samples[:6]}")


if __name__ == "__main__":
    main()

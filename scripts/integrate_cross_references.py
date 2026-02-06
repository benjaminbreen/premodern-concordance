#!/usr/bin/env python3
"""
Integrate classified synonym chain findings into concordance.json as cross_references.

Reads the classified findings (from classify_findings.py), filters to genuine links,
maps auto_labels to the typed annotation schema, deduplicates, and adds a
`cross_references` array to each cluster in concordance.json.

Also generates reverse references: if cluster A → cluster B, then B gets a
back-reference to A.

Typed annotation schema (for CS research on entity resolution):

  POSITIVE link types:
    same_referent        — A = B, same substance/species/entity
    cross_linguistic     — same entity named in different languages
    contested_identity   — historical sources disagree whether A = B
    conceptual_overlap   — related but non-identical (subtype, part-whole)
    derivation           — one derived from another (source→product)
    orthographic_variant — same term, spelling/OCR difference

  NEGATIVE types (stored separately, not in cross_references):
    recipe_cooccurrence, authority_cooccurrence, ocr_artifact, generic_term

Usage:
    python3 integrate_cross_references.py [--dry-run]
"""

import json
import re
import shutil
from pathlib import Path
from collections import defaultdict, Counter
import argparse

BASE_DIR = Path(__file__).resolve().parent.parent
CLASSIFIED_PATH = BASE_DIR / "data" / "synonym_chains" / "classified_findings.json"
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"


# ─────────────────────────────────────────────────────────────
# LABEL MAPPING: auto_label → typed annotation schema
# ─────────────────────────────────────────────────────────────

def map_link_type(finding: dict) -> str:
    """Map a classified finding's auto_label to the typed annotation schema."""
    label = finding.get("auto_label", "")
    relationship = finding.get("found_relationship", "").lower()

    # Direct mappings from heuristic labels
    if label == "true_synonym":
        return "same_referent"
    if label == "cross_linguistic":
        return "cross_linguistic"
    if label == "contested_identity":
        return "contested_identity"
    if label == "subtype_relation":
        # Check relationship field for derivation vs overlap
        if any(kw in relationship for kw in ["derived", "source of", "product of",
                                               "extracted from", "made from"]):
            return "derivation"
        return "conceptual_overlap"

    # LLM-classified genuine links — infer type from relationship field
    if label in ("llm_genuine", "probable_link", "possible_link", "entity_in_recipe"):
        # Cross-linguistic signals
        if any(kw in relationship for kw in ["called", "name used", "known as",
                                               "named", "translation", "language",
                                               "vernacular", "local name"]):
            return "cross_linguistic"
        # Derivation signals
        if any(kw in relationship for kw in ["source of", "derived", "extracted",
                                               "made from", "product", "part of"]):
            return "derivation"
        # Subtype/overlap signals
        if any(kw in relationship for kw in ["type of", "variety", "kind of",
                                               "similar", "comparison", "related"]):
            return "conceptual_overlap"
        # Default for LLM-genuine without specific signal
        return "same_referent"

    # Fallback
    return "same_referent"


def map_link_strength(link_type: str) -> float:
    """Graduated link strength for the typed annotation schema."""
    return {
        "same_referent": 1.0,
        "orthographic_variant": 0.95,
        "cross_linguistic": 0.9,
        "contested_identity": 0.7,
        "conceptual_overlap": 0.5,
        "derivation": 0.4,
    }.get(link_type, 0.5)


# ─────────────────────────────────────────────────────────────
# BUILD CROSS-REFERENCES
# ─────────────────────────────────────────────────────────────

def build_cross_references(findings: list[dict], cluster_map: dict) -> dict[int, list[dict]]:
    """
    Build cross_references grouped by cluster ID.

    Returns dict mapping cluster_id → list of cross_reference dicts.
    Includes both forward references (from source cluster) and reverse
    references (from target cluster back to source).
    """
    # Filter to genuine findings only
    genuine = [f for f in findings if f.get("auto_is_genuine") is True]
    print(f"  Genuine findings: {len(genuine)}")

    refs_by_cluster = defaultdict(list)

    for f in genuine:
        source_id = f["source_cluster_id"]
        link_type = map_link_type(f)
        strength = map_link_strength(link_type)
        confidence = f.get("auto_confidence", 0.5)

        # Build the reference object
        ref = {
            "found_name": f["found_name"],
            "link_type": link_type,
            "link_strength": strength,
            "target_cluster_id": None,
            "target_cluster_name": None,
            "source_book": f["source_book"],
            "evidence_snippet": f.get("excerpt_snippet", "")[:300],
            "confidence": round(confidence, 2),
            "auto_label": f["auto_label"],
            "found_relationship": f.get("found_relationship", ""),
        }

        # Fill target info if matched to cluster(s)
        matched_ids = f.get("matched_cluster_ids", [])
        if matched_ids:
            # Use first matched cluster as primary target
            target_id = matched_ids[0]
            target_cluster = cluster_map.get(target_id, {})
            ref["target_cluster_id"] = target_id
            ref["target_cluster_name"] = target_cluster.get("canonical_name", f"#{target_id}")

            # Add forward reference to source cluster
            refs_by_cluster[source_id].append(ref)

            # Add reverse reference to target cluster (if different from source)
            if target_id != source_id:
                reverse_ref = {
                    "found_name": f["source_cluster_name"],
                    "link_type": link_type,
                    "link_strength": strength,
                    "target_cluster_id": source_id,
                    "target_cluster_name": cluster_map.get(source_id, {}).get(
                        "canonical_name", f"#{source_id}"),
                    "source_book": f["source_book"],
                    "evidence_snippet": ref["evidence_snippet"],
                    "confidence": round(confidence, 2),
                    "auto_label": ref["auto_label"],
                    "found_relationship": f"reverse: {ref['found_relationship']}",
                    "is_reverse": True,
                }
                refs_by_cluster[target_id].append(reverse_ref)

            # Handle additional matched clusters
            for extra_id in matched_ids[1:]:
                extra_cluster = cluster_map.get(extra_id, {})
                extra_ref = dict(ref)
                extra_ref["target_cluster_id"] = extra_id
                extra_ref["target_cluster_name"] = extra_cluster.get(
                    "canonical_name", f"#{extra_id}")
                refs_by_cluster[source_id].append(extra_ref)
        else:
            # Unmatched — still add to source cluster (no target to link to)
            refs_by_cluster[source_id].append(ref)

    return refs_by_cluster


def deduplicate_refs(refs: list[dict]) -> list[dict]:
    """
    Deduplicate cross-references for a single cluster.
    Keep highest-confidence entry for each (found_name, target_cluster_id) pair.
    """
    best = {}
    for ref in refs:
        key = (ref["found_name"].lower(), ref.get("target_cluster_id"))
        existing = best.get(key)
        if existing is None or ref["confidence"] > existing["confidence"]:
            best[key] = ref

    # Sort: matched targets first (by strength desc), then unmatched
    result = sorted(best.values(),
                    key=lambda r: (r["target_cluster_id"] is not None,
                                   r["link_strength"],
                                   r["confidence"]),
                    reverse=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without modifying concordance.json")
    args = parser.parse_args()

    # Load data
    print("Loading classified findings...")
    with open(CLASSIFIED_PATH) as f:
        findings = json.load(f)
    print(f"  {len(findings)} total findings")

    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    cluster_map = {c["id"]: c for c in data["clusters"]}
    print(f"  {len(data['clusters'])} clusters")

    # Build cross-references
    print("\nBuilding cross-references...")
    refs_by_cluster = build_cross_references(findings, cluster_map)

    # Deduplicate
    deduped_by_cluster = {}
    total_before = 0
    total_after = 0
    for cid, refs in refs_by_cluster.items():
        total_before += len(refs)
        deduped = deduplicate_refs(refs)
        total_after += len(deduped)
        deduped_by_cluster[cid] = deduped

    print(f"  Before dedup: {total_before} references")
    print(f"  After dedup:  {total_after} references")
    print(f"  Clusters with references: {len(deduped_by_cluster)}")

    # Stats
    all_refs = [r for refs in deduped_by_cluster.values() for r in refs]
    type_counts = Counter(r["link_type"] for r in all_refs)
    matched_count = sum(1 for r in all_refs if r["target_cluster_id"] is not None)
    unmatched_count = sum(1 for r in all_refs if r["target_cluster_id"] is None)
    reverse_count = sum(1 for r in all_refs if r.get("is_reverse"))

    print(f"\n{'='*60}")
    print("CROSS-REFERENCE SUMMARY")
    print(f"{'='*60}")
    print(f"\nTotal references: {len(all_refs)}")
    print(f"  Linked to another cluster: {matched_count}")
    print(f"  Unmatched (new entities):   {unmatched_count}")
    print(f"  Reverse references:         {reverse_count}")
    print(f"\nBy link type:")
    for lt, count in type_counts.most_common():
        strength = map_link_strength(lt)
        print(f"  {lt:25s} {count:5d}  (strength {strength})")

    # Per-cluster distribution
    ref_counts = [len(refs) for refs in deduped_by_cluster.values()]
    ref_counts.sort(reverse=True)
    print(f"\nReferences per cluster:")
    print(f"  Max: {ref_counts[0]}, Median: {ref_counts[len(ref_counts)//2]}, "
          f"Min: {ref_counts[-1]}")
    print(f"  Top 5 clusters:")
    for cid, refs in sorted(deduped_by_cluster.items(),
                             key=lambda x: len(x[1]), reverse=True)[:5]:
        cname = cluster_map.get(cid, {}).get("canonical_name", f"#{cid}")
        print(f"    #{cid} {cname}: {len(refs)} refs")

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        return

    # Backup concordance
    backup_path = CONCORDANCE_PATH.with_suffix(".json.bak2")
    if backup_path.exists():
        backup_path = CONCORDANCE_PATH.with_suffix(".json.bak3")
    shutil.copy(CONCORDANCE_PATH, backup_path)
    print(f"\nBackup: {backup_path}")

    # Integrate into concordance
    clusters_updated = 0
    for cluster in data["clusters"]:
        cid = cluster["id"]
        if cid in deduped_by_cluster:
            cluster["cross_references"] = deduped_by_cluster[cid]
            clusters_updated += 1
        else:
            # Ensure field exists even if empty (consistent schema)
            cluster["cross_references"] = []

    # Write
    with open(CONCORDANCE_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    file_size = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
    print(f"Updated {clusters_updated} clusters in concordance.json ({file_size:.1f} MB)")

    # Also save the full typed reference dataset for research
    research_path = BASE_DIR / "data" / "synonym_chains" / "typed_cross_references.json"
    research_data = {
        "schema_version": "1.0",
        "link_types": {
            "same_referent": {"strength": 1.0, "description": "Same species, substance, or process"},
            "cross_linguistic": {"strength": 0.9, "description": "Same entity named in different languages"},
            "contested_identity": {"strength": 0.7, "description": "Historical sources disagree whether A = B"},
            "conceptual_overlap": {"strength": 0.5, "description": "Related but non-identical (subtype, part-whole)"},
            "derivation": {"strength": 0.4, "description": "One derived from another (source→product)"},
            "orthographic_variant": {"strength": 0.95, "description": "Same term, spelling/OCR difference"},
        },
        "negative_types": {
            "recipe_cooccurrence": "Co-occur in formula, not synonyms",
            "authority_cooccurrence": "Scholars cited together",
            "ocr_artifact": "Not a real entity",
            "generic_term": "Too broad for entity status",
        },
        "total_references": len(all_refs),
        "clusters_with_references": len(deduped_by_cluster),
        "references_by_cluster": {str(k): v for k, v in deduped_by_cluster.items()},
    }
    with open(research_path, "w") as f:
        json.dump(research_data, f, ensure_ascii=False, indent=2)
    print(f"Research dataset: {research_path}")


if __name__ == "__main__":
    main()

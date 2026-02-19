#!/usr/bin/env python3
"""
Integrate classified synonym chain findings into concordance.json as cross_references.

Reads the classified findings (from classify_findings.py), filters to genuine links,
maps auto_labels to the typed annotation schema, deduplicates, and adds a
`cross_references` array to each cluster in concordance.json.

Also generates reverse references: if cluster A → cluster B, then B gets a
back-reference to A.

Source matching: Each finding is matched to its source cluster in the CURRENT
concordance by direct (book_id, member_name) lookup — no fragile old→new ID
remapping required.

Target matching: found_name is matched only against canonical_name and
modern_name (clean, curated fields) to avoid noisy matches from OCR variants.

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
    python3 integrate_cross_references.py [--dry-run] [--strict] [--validate]
"""

import json
import re
import shutil
import unicodedata
from pathlib import Path
from collections import defaultdict, Counter
import argparse

BASE_DIR = Path(__file__).resolve().parent.parent
CLASSIFIED_PATH = BASE_DIR / "data" / "synonym_chains" / "classified_findings.json"
LLM_XREFS_PATH = BASE_DIR / "data" / "llm_cross_references.json"
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"


# ─────────────────────────────────────────────────────────────
# TEXT NORMALIZATION (adapted from migrate_ground_truth.py)
# ─────────────────────────────────────────────────────────────

def normalize_name(text: str) -> str:
    """Lowercase, strip diacritics, keep only alnum+spaces."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def member_names(member: dict) -> set[str]:
    """Return normalized member names/variants."""
    out = set()
    n = normalize_name(member.get("name", ""))
    if n:
        out.add(n)
    for variant in member.get("variants", []):
        v = normalize_name(variant)
        if v:
            out.add(v)
    return out


def cluster_aliases(cluster: dict) -> set[str]:
    """Return normalized aliases for a cluster."""
    aliases = set()
    canonical = normalize_name(cluster.get("canonical_name", ""))
    if canonical:
        aliases.add(canonical)
    gt = cluster.get("ground_truth") or {}
    modern = normalize_name(gt.get("modern_name", ""))
    if modern:
        aliases.add(modern)
    for member in cluster.get("members", []):
        aliases.update(member_names(member))
    return aliases


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
        # Only keep as contested if the relationship text indicates a real
        # naming/identity confusion. Downgrade geographic co-occurrences
        # and vague "possibly related" findings to conceptual_overlap.
        CONTESTED_SIGNALS = [
            "mistaken", "confused", "conflated", "mistakenly identified",
            "mistaken for", "confused with", "wrongly", "erroneously",
            "not the same", "falsely", "spurious",
        ]
        if any(signal in relationship for signal in CONTESTED_SIGNALS):
            return "contested_identity"
        return "conceptual_overlap"
    if label == "subtype_relation":
        # Check relationship field for derivation vs overlap
        if any(kw in relationship for kw in ["derived", "source of", "product of",
                                               "extracted from", "made from"]):
            return "derivation"
        return "conceptual_overlap"

    # LLM-classified genuine links — infer type from relationship field
    if label in ("llm_genuine", "probable_link", "possible_link", "entity_in_recipe"):
        # Guard: geographic/contextual co-occurrences are NOT synonyms
        if any(kw in relationship for kw in [
            "region", "port", "place", "found in", "grows in", "traded",
            "ingredient", "used with", "mixed with", "combined",
            "mentioned alongside", "compared to", "related to",
            "source of", "origin", "comes from", "exported",
            "territory", "province", "kingdom", "island", "city",
            "people of", "natives", "inhabitants", "merchants",
            "remedy for", "cure for", "treatment", "disease",
            "brought from", "shipped from", "imported",
        ]):
            return "conceptual_overlap"
        # Cross-linguistic signals
        if any(kw in relationship for kw in ["called", "name used", "known as",
                                               "named", "translation", "language",
                                               "vernacular", "local name"]):
            return "cross_linguistic"
        # Derivation signals
        if any(kw in relationship for kw in ["derived", "extracted",
                                               "made from", "product", "part of"]):
            return "derivation"
        # Subtype/overlap signals
        if any(kw in relationship for kw in ["type of", "variety", "kind of",
                                               "similar", "comparison", "related"]):
            return "conceptual_overlap"
        # Default: safe fallback to conceptual_overlap instead of same_referent
        return "conceptual_overlap"

    # Fallback: unknown labels get safe default
    return "conceptual_overlap"


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
# DIRECT SOURCE MATCHING
# ─────────────────────────────────────────────────────────────

def build_source_lookup(clusters: list[dict]) -> tuple[dict, dict, dict]:
    """
    Build lookups to resolve findings to their source cluster in the CURRENT
    concordance, without any old→new ID remapping.

    Returns three dicts (checked in priority order):
      1. (book_id, normalized_member_name) → cluster_id  (book-specific, highest precision)
      2. (normalized_canonical_name, category) → cluster_id  (curated names)
      3. (normalized_member_name, category) → cluster_id  (cross-book fallback)
    """
    by_book_member = {}   # (book_id, name) → cid
    by_canonical = {}     # (canonical/modern name, category) → cid
    by_any_member = {}    # (name, category) → cid

    for cluster in clusters:
        cid = cluster["id"]
        category = cluster.get("category", "")

        # Index canonical name
        cn = normalize_name(cluster.get("canonical_name", ""))
        if cn:
            by_canonical.setdefault((cn, category), cid)

        # Index modern name
        gt = cluster.get("ground_truth") or {}
        mn = normalize_name(gt.get("modern_name", ""))
        if mn:
            by_canonical.setdefault((mn, category), cid)

        # Index all member names + variants
        for member in cluster.get("members", []):
            book = member.get("book_id", "")
            for name in [member.get("name", "")] + member.get("variants", []):
                n = normalize_name(name)
                if n:
                    by_book_member.setdefault((book, n), cid)
                    by_any_member.setdefault((n, category), cid)

    return by_book_member, by_canonical, by_any_member


def resolve_source_clusters(findings: list[dict],
                            by_book_member: dict,
                            by_canonical: dict,
                            by_any_member: dict) -> list[dict]:
    """
    Resolve each finding's source cluster directly against the current concordance
    using the entity's actual name, not an old cluster ID remap.

    Mutates source_cluster_id in-place and updates source_cluster_name.
    Returns only successfully matched findings.
    """
    resolved = []
    strategy_counts = Counter()

    for f in findings:
        book = f.get("source_book", "")
        member = normalize_name(f.get("source_member", ""))
        cname = normalize_name(f.get("source_cluster_name", ""))
        category = f.get("source_category", "")

        # Strategy 1: exact book + member name (highest precision)
        cid = by_book_member.get((book, member))
        if cid is not None:
            strategy_counts["book_member"] += 1
        else:
            # Strategy 2: canonical/modern name + category
            cid = by_canonical.get((cname, category))
            if cid is not None:
                strategy_counts["canonical_name"] += 1
            else:
                # Strategy 3: member name + category (cross-book)
                cid = by_any_member.get((member, category))
                if cid is not None:
                    strategy_counts["cross_book_member"] += 1

        if cid is not None:
            f2 = dict(f)
            f2["source_cluster_id"] = cid
            # Clear stale matched_cluster_ids — will be re-matched fresh
            f2["matched_cluster_ids"] = []
            resolved.append(f2)
        # else: drop — entity not in current concordance

    dropped = len(findings) - len(resolved)
    print(f"  Resolved {len(resolved)}/{len(findings)} findings to current clusters "
          f"(dropped {dropped})")
    for strategy, count in strategy_counts.most_common():
        print(f"    {strategy}: {count}")

    return resolved


# ─────────────────────────────────────────────────────────────
# TARGET MATCHING (tight: canonical + modern names only)
# ─────────────────────────────────────────────────────────────

def build_target_lookup(clusters: list[dict]) -> dict[tuple[str, str], int]:
    """
    Build (normalized_name, category) → cluster_id lookup for target matching.

    Only indexes canonical_name and modern_name — the clean, curated fields.
    Does NOT index member variants to avoid noisy OCR matches.
    """
    lookup = {}
    for cluster in clusters:
        category = cluster.get("category", "")
        cid = cluster["id"]
        # Canonical name
        cn = normalize_name(cluster.get("canonical_name", ""))
        if cn:
            lookup.setdefault((cn, category), cid)
        # Modern name
        gt = cluster.get("ground_truth") or {}
        modern = normalize_name(gt.get("modern_name", ""))
        if modern:
            lookup.setdefault((modern, category), cid)
    return lookup


def match_targets(findings: list[dict], current_clusters: list[dict]) -> int:
    """
    Match found_name/found_normalized against curated cluster names.
    Mutates findings in-place. Returns count of matched targets.
    """
    lookup = build_target_lookup(current_clusters)
    matched = 0

    for f in findings:
        if f.get("auto_is_genuine") is not True:
            continue

        source_category = f.get("source_category", "")
        found_category = f.get("found_category", source_category)

        # Try found_normalized first, then found_name
        for name_field in ("found_normalized", "found_name"):
            name = normalize_name(f.get(name_field, ""))
            if not name:
                continue
            # Try found_category, then source_category
            categories_to_try = list(dict.fromkeys(
                [cat for cat in (found_category, source_category) if cat]
            ))
            for cat in categories_to_try:
                cid = lookup.get((name, cat))
                if cid is not None and cid != f.get("source_cluster_id"):
                    f["matched_cluster_ids"] = [cid]
                    matched += 1
                    break
            if f.get("matched_cluster_ids"):
                break

    return matched


# ─────────────────────────────────────────────────────────────
# LLM-GENERATED CROSS-REFERENCES (from generate_llm_cross_references.py)
# ─────────────────────────────────────────────────────────────

def load_llm_cross_references(clusters: list[dict]) -> dict[int, list[dict]]:
    """
    Load LLM-generated cross-references from cache and resolve stable keys
    to current cluster IDs. Returns dict: cluster_id → list of ref dicts.
    """
    if not LLM_XREFS_PATH.exists():
        return {}

    with open(LLM_XREFS_PATH) as f:
        cache = json.load(f)
    entries = cache.get("entries", {})
    if not entries:
        return {}

    # Build lookups to resolve stable keys → current cluster IDs
    by_wikidata = {}
    by_modern = {}
    by_canonical = {}
    for c in clusters:
        gt = c.get("ground_truth") or {}
        wd = (gt.get("wikidata_id") or "").strip()
        if wd:
            by_wikidata[f"wd:{wd}"] = c["id"]
        mn = normalize_name(gt.get("modern_name", ""))
        if mn:
            by_modern[(mn, c["category"])] = c["id"]
        cn = normalize_name(c.get("canonical_name", ""))
        if cn:
            by_canonical[(cn, c["category"])] = c["id"]

    # Build name→cluster_id lookup for resolving target names
    target_lookup = {}
    for c in clusters:
        gt = c.get("ground_truth") or {}
        cat = c["category"]
        mn = normalize_name(gt.get("modern_name", ""))
        if mn:
            target_lookup.setdefault((mn, cat), c["id"])
        cn = normalize_name(c.get("canonical_name", ""))
        if cn:
            target_lookup.setdefault((cn, cat), c["id"])
        # Also index member names for cross-linguistic matches
        for m in c.get("members", []):
            n = normalize_name(m.get("name", ""))
            if n:
                target_lookup.setdefault((n, cat), c["id"])

    # Map link type names from LLM output to schema types
    TYPE_MAP = {
        "synonyms": "same_referent",
        "cross_linguistic": "cross_linguistic",
        "contested": "contested_identity",
        "related": "conceptual_overlap",
    }

    refs_by_cluster = defaultdict(list)
    resolved_sources = 0
    resolved_targets = 0
    unresolved_targets = 0

    # Build cluster_id → cluster lookup once (not inside loop)
    cluster_map_local = {c["id"]: c for c in clusters}

    for stable_key, entry in entries.items():
        # Resolve source cluster
        source_id = by_wikidata.get(stable_key)
        if source_id is None:
            mn = normalize_name(entry.get("modern_name", ""))
            cat = entry.get("category", "")
            source_id = by_modern.get((mn, cat))
        if source_id is None:
            cn = normalize_name(entry.get("canonical_name", ""))
            cat = entry.get("category", "")
            source_id = by_canonical.get((cn, cat))
        if source_id is None:
            continue
        resolved_sources += 1

        category = entry["category"]
        source_name = cluster_map_local.get(source_id, {}).get(
            "canonical_name", f"#{source_id}")

        # Process each link type
        for llm_key, link_type in TYPE_MAP.items():
            for ref_entry in entry.get(llm_key, []):
                target_name = ref_entry.get("name", "")
                reason = ref_entry.get("reason", "")
                reason_lower = reason.lower()
                target_norm = normalize_name(target_name)
                if not target_norm:
                    continue

                # Reclassify "related" entries that are actually synonyms,
                # cross-linguistic equivalents, or derivations
                if link_type == "conceptual_overlap":
                    CROSS_LING_SIGNALS = [
                        "portuguese name", "spanish name", "italian name",
                        "latin name", "french name", "german name",
                        "arabic name", "chinese name", "dutch name",
                        "historical name for", "local name for",
                        "vernacular name", "common name for",
                        "translation of", "translated as",
                        "portuguese term", "spanish term", "italian term",
                        "portuguese for", "spanish for", "italian for",
                        "italian word for", "french word for",
                        "german word for", "spanish word for",
                        "portuguese word for", "latin word for",
                        "cross-linguistic equivalent",
                    ]
                    SYNONYM_SIGNALS = [
                        "same as", "identical to", "another name for",
                        "also known as", "synonym for", "synonymous",
                        "alternative name", "alternate name",
                        "referred to as", "equivalent to",
                        "interchangeable", "same species",
                        "same substance", "same entity",
                    ]
                    DERIVATION_SIGNALS = [
                        "derived from", "extracted from", "made from",
                        "product of", "distilled from", "prepared from",
                        "obtained from", "produced from", "refined from",
                        "processed from", "yields", "produces",
                    ]
                    CONTESTED_SIGNALS = [
                        "debated whether", "confused with", "mistaken for",
                        "disputed identity", "possibly the same",
                        "conflated with", "erroneously identified",
                    ]
                    # Drop low-value taxonomy refs ("X is a type of Y")
                    TAXONOMY_SIGNALS = [
                        " is a type of ", " is a species of ",
                        " is a kind of ", " is a variety of ",
                        " is a class of ", " is a subtype of ",
                        " is a form of ", " are a type of ",
                        " are a species of ", " are a kind of ",
                        " are types of ",
                    ]
                    if any(s in reason_lower for s in TAXONOMY_SIGNALS):
                        link_type = "_skip"  # will be filtered out below
                    elif any(s in reason_lower for s in CROSS_LING_SIGNALS):
                        link_type = "cross_linguistic"
                    elif any(s in reason_lower for s in SYNONYM_SIGNALS):
                        link_type = "same_referent"
                    elif any(s in reason_lower for s in DERIVATION_SIGNALS):
                        link_type = "derivation"
                    elif any(s in reason_lower for s in CONTESTED_SIGNALS):
                        link_type = "contested_identity"

                # Skip taxonomy refs
                if link_type == "_skip":
                    continue

                # Resolve target name → cluster ID
                target_id = target_lookup.get((target_norm, category))
                if target_id is None or target_id == source_id:
                    unresolved_targets += 1
                    continue
                resolved_targets += 1

                target_cluster_name = cluster_map_local.get(target_id, {}).get(
                    "canonical_name", f"#{target_id}")

                ref = {
                    "found_name": target_name,
                    "link_type": link_type,
                    "link_strength": map_link_strength(link_type),
                    "target_cluster_id": target_id,
                    "target_cluster_name": target_cluster_name,
                    "source_book": "llm_generated",
                    "evidence_snippet": reason,
                    "confidence": 0.85,
                    "auto_label": f"llm_{llm_key}",
                    "found_relationship": reason,
                }
                refs_by_cluster[source_id].append(ref)

                # Reverse reference
                reverse_ref = {
                    "found_name": source_name,
                    "link_type": link_type,
                    "link_strength": map_link_strength(link_type),
                    "target_cluster_id": source_id,
                    "target_cluster_name": source_name,
                    "source_book": "llm_generated",
                    "evidence_snippet": reason,
                    "confidence": 0.85,
                    "auto_label": f"llm_{llm_key}",
                    "found_relationship": f"reverse: {reason}",
                    "is_reverse": True,
                }
                refs_by_cluster[target_id].append(reverse_ref)

    print(f"  LLM cross-refs: {resolved_sources} sources resolved, "
          f"{resolved_targets} target links, {unresolved_targets} unresolved targets")
    return dict(refs_by_cluster)


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
        source_cluster = cluster_map.get(source_id, {})
        source_name = source_cluster.get("canonical_name", f"#{source_id}")
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
                    "found_name": source_name,
                    "link_type": link_type,
                    "link_strength": strength,
                    "target_cluster_id": source_id,
                    "target_cluster_name": source_name,
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


# ─────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────

def validate_cross_references(data: dict) -> bool:
    """Validate cross-references in concordance data. Returns True if all checks pass."""
    clusters = data["clusters"]
    cluster_ids = {c["id"] for c in clusters}
    errors = []
    warnings = []

    clusters_with_refs = 0
    total_refs = 0
    orphan_targets = 0
    self_refs = 0
    type_counts = Counter()

    for cluster in clusters:
        cid = cluster["id"]
        refs = cluster.get("cross_references", [])
        if not refs:
            continue
        clusters_with_refs += 1

        for ref in refs:
            total_refs += 1
            type_counts[ref.get("link_type", "unknown")] += 1

            tid = ref.get("target_cluster_id")
            if tid is not None:
                if tid not in cluster_ids:
                    orphan_targets += 1
                    errors.append(f"  Cluster #{cid}: target #{tid} does not exist")
                if tid == cid:
                    self_refs += 1
                    warnings.append(f"  Cluster #{cid}: self-reference via '{ref.get('found_name')}'")

    # Check bidirectional: if A→B exists, B→A should exist
    forward_pairs = set()
    reverse_pairs = set()
    for cluster in clusters:
        cid = cluster["id"]
        for ref in cluster.get("cross_references", []):
            tid = ref.get("target_cluster_id")
            if tid is None:
                continue
            if ref.get("is_reverse"):
                reverse_pairs.add((cid, tid))
            else:
                forward_pairs.add((cid, tid))

    missing_reverse = 0
    for src, tgt in forward_pairs:
        if (tgt, src) not in reverse_pairs:
            missing_reverse += 1

    print(f"\n{'='*60}")
    print("VALIDATION RESULTS")
    print(f"{'='*60}")
    print(f"  Clusters with references: {clusters_with_refs}")
    print(f"  Total references: {total_refs}")
    print(f"  Orphan target IDs: {orphan_targets}")
    print(f"  Self-references: {self_refs}")
    print(f"  Missing reverse refs: {missing_reverse}")
    print(f"  Link type distribution:")
    for lt, count in type_counts.most_common():
        pct = 100 * count / total_refs if total_refs else 0
        print(f"    {lt:25s} {count:5d}  ({pct:.1f}%)")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors[:20]:
            print(e)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings[:10]:
            print(w)

    ok = len(errors) == 0
    print(f"\nValidation: {'PASSED' if ok else 'FAILED'}")
    return ok


# ─────────────────────────────────────────────────────────────
# BACKUP LOGIC
# ─────────────────────────────────────────────────────────────

def find_next_backup_path(base_path: Path) -> Path:
    """Find the next available .bakN suffix."""
    for n in range(2, 100):
        candidate = base_path.parent / f"{base_path.stem}.json.bak{n}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Too many backup files (checked .bak2 through .bak99)")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without modifying concordance.json")
    parser.add_argument("--validate", action="store_true",
                        help="Validate existing cross-references in concordance.json")
    parser.add_argument("--strict", action="store_true",
                        help="Only use high-confidence labels (true_synonym, cross_linguistic, "
                             "contested_identity, subtype_relation). Excludes noisy llm_genuine.")
    args = parser.parse_args()

    # Load concordance
    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    cluster_map = {c["id"]: c for c in data["clusters"]}
    print(f"  {len(data['clusters'])} clusters")

    # Validate-only mode
    if args.validate:
        validate_cross_references(data)
        return

    # Load findings
    print("Loading classified findings...")
    with open(CLASSIFIED_PATH) as f:
        findings = json.load(f)
    print(f"  {len(findings)} total findings")

    # Filter to high-quality labels if --strict
    STRICT_LABELS = {"true_synonym", "cross_linguistic", "contested_identity", "subtype_relation"}
    if args.strict:
        before = len(findings)
        findings = [f for f in findings
                    if f.get("auto_label") in STRICT_LABELS or not f.get("auto_is_genuine")]
        print(f"  --strict: kept {len(findings)}/{before} findings (high-quality labels only)")

    # Resolve source clusters directly against the current concordance
    # (no old→new ID remapping — uses entity's actual name for matching)
    print("\nResolving source clusters...")
    by_book_member, by_canonical, by_any_member = build_source_lookup(data["clusters"])
    findings = resolve_source_clusters(
        findings, by_book_member, by_canonical, by_any_member)

    # Match targets against curated cluster names (canonical + modern only)
    print("\nMatching targets against curated cluster names...")
    matched = match_targets(findings, data["clusters"])
    print(f"  Matched {matched} findings to target clusters")

    # Build cross-references from synonym chain findings
    print("\nBuilding cross-references from synonym chains...")
    refs_by_cluster = build_cross_references(findings, cluster_map)

    # Merge LLM-generated cross-references (if cache exists)
    print("\nLoading LLM-generated cross-references...")
    llm_refs = load_llm_cross_references(data["clusters"])
    if llm_refs:
        for cid, refs in llm_refs.items():
            refs_by_cluster[cid].extend(refs)
        print(f"  Merged LLM refs into {len(llm_refs)} clusters")
    else:
        print("  No LLM cross-reference cache found (run generate_llm_cross_references.py)")

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
    if deduped_by_cluster:
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
    backup_path = find_next_backup_path(CONCORDANCE_PATH)
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

    # Validate the result
    print("\nValidating...")
    validate_cross_references(data)

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

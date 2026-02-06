#!/usr/bin/env python3
"""
Automated quality classification for synonym chain findings.

Applies heuristic + embedding-based filters to separate:
  - True synonym/equivalence links (high value)
  - Recipe ingredient co-occurrences (different value)
  - OCR garbage (discard)
  - Ambiguous/other (needs review or LLM classification)

Designed to scale to 500-5000 books without human review bottleneck.

Usage:
    python3 classify_findings.py                           # heuristics only
    python3 classify_findings.py --validate                # compare vs curated labels
    python3 classify_findings.py --llm-reclassify          # heuristics + LLM
    python3 classify_findings.py --llm-reclassify --validate  # full pipeline + validate
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env.local")

from google import genai

BASE_DIR = Path(__file__).resolve().parent.parent
FINDINGS_PATH = BASE_DIR / "data" / "synonym_chains" / "findings.json"
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"
CURATED_PATH = BASE_DIR / "data" / "training" / "synonym_chain_examples.jsonl"
OUTPUT_PATH = BASE_DIR / "data" / "synonym_chains" / "classified_findings.json"


# ═══════════════════════════════════════════════════════════════
# FILTER A: Recipe ingredient list detection
# ═══════════════════════════════════════════════════════════════

# Pharmaceutical quantity markers — if the excerpt has 2+ of these,
# it's almost certainly a recipe/formula, not a synonym chain
QUANTITY_MARKERS = re.compile(
    r"""
    \bonc\b\.? |           # once (ounces)
    \b[35ʒ℥]\b |           # dram/ounce symbols
    \bdr(?:am|\.)\b |      # dram
    \blb\b\.? |            # libra (pound)
    \bgr(?:ani?)?\b\.? |   # grani (grains)
    \bscrup\b\.? |         # scrupoli (scruples)
    \bman(?:ip)?\b\.? |    # manipoli (handfuls)
    \bana?\b\s*[\d.] |     # ana (equal parts) + number
    \b[jJiI]{2,4}\b |      # Roman numerals (ii, iii, iiii)
    \b\d+\s*(?:onc|lib|gr) # number + unit
    """,
    re.IGNORECASE | re.VERBOSE
)

# Recipe structural markers — headings, preparation instructions
RECIPE_STRUCTURAL = re.compile(
    r"""
    \bRICETTA\b |
    \bRECIPE\b |
    \bfa\s+(?:lattouaro|poluere|sciroppo|vnguento|ceroto|empiastro)\b |
    \bFa\s+(?:pillole|poluere)\b |
    \bsecondo\s+l['']arte\b |
    \bquanto\s+bast[aà]\b |           # quanto basta (q.s.)
    \bfecondo\s+Tai\s+te\b |
    \bcon\s+(?:Mele|zucchero)\s+(?:ftiumato|ftiamato)\b |
    \bbolii?\s+[aà]\b |              # boil to...
    \binfond[ie]\b |                  # infuse
    \bfa\s+ma[fſ][fſ]a\b             # make a paste
    """,
    re.IGNORECASE | re.VERBOSE
)

# Count of distinct entity-like capitalized words in excerpt
# Recipe excerpts tend to have 5+ distinct capitalized substance names
def count_capitalized_terms(excerpt: str) -> int:
    """Count distinct capitalized multi-char words (likely entity names)."""
    words = re.findall(r'\b[A-Z][a-zà-ú]{2,}(?:\s+[a-zà-ú]+)?\b', excerpt)
    return len(set(words))


def is_recipe_ingredient_list(finding: dict) -> tuple[bool, str]:
    """Detect whether an excerpt is a recipe ingredient list."""
    excerpt = finding.get('excerpt_snippet', '')

    # Count quantity markers
    qty_matches = QUANTITY_MARKERS.findall(excerpt)
    qty_count = len(qty_matches)

    # Check structural markers
    has_structural = bool(RECIPE_STRUCTURAL.search(excerpt))

    # Count capitalized terms (potential ingredients)
    cap_terms = count_capitalized_terms(excerpt)

    # High quantity marker density = recipe
    if qty_count >= 3:
        return True, f"recipe: {qty_count} quantity markers"

    # Structural recipe marker + any quantities
    if has_structural and qty_count >= 1:
        return True, f"recipe: structural marker + {qty_count} quantities"

    # Many capitalized terms with quantities = ingredient list
    if cap_terms >= 6 and qty_count >= 1:
        return True, f"recipe: {cap_terms} named substances + quantities"

    # The "relationship" field from Gemini is also a signal
    rel = finding.get('found_relationship', '').lower()
    if any(w in rel for w in ['ingredient', 'component', 'recipe', 'compound',
                               'formula', 'preparation', 'listed in']):
        if qty_count >= 1 or cap_terms >= 5:
            return True, f"recipe: relationship says '{rel[:40]}' + structural signals"

    return False, ""


# ═══════════════════════════════════════════════════════════════
# FILTER B: Vocabulary matching precision (Tabaco/Tabaxir problem)
# ═══════════════════════════════════════════════════════════════

def check_vocabulary_match_quality(finding: dict, cmap: dict) -> tuple[bool, str]:
    """
    Check if matched cluster IDs are plausible or spurious.

    The Tabaco/Tabaxir problem: "tabaxir" matches both tabaschir (#248)
    and Tabaco (#33) by substring. We can detect these by:
    1. Checking category match (substance ≠ plant for tabaco/tabaxir)
    2. Checking if the found entity's normalized form matches better
    3. Checking semantic distance between source and target clusters
    """
    matched_ids = finding.get('matched_cluster_ids', [])
    if len(matched_ids) <= 1:
        return True, ""  # No ambiguity

    source_cat = finding.get('source_category', '')
    found_cat = finding.get('found_category', '')
    found_name = finding.get('found_name', '').lower()
    found_norm = finding.get('found_normalized', '').lower()

    # Check each matched cluster
    suspicious = []
    good = []
    for cid in matched_ids:
        cluster = cmap.get(cid, {})
        cluster_cat = cluster.get('category', '')
        cluster_name = cluster.get('canonical_name', '').lower()
        modern = cluster.get('ground_truth', {}).get('modern_name', '').lower()

        # Category mismatch between found entity and target cluster
        if found_cat and cluster_cat and found_cat != cluster_cat:
            suspicious.append((cid, f"category mismatch: found={found_cat}, cluster={cluster_cat}"))
            continue

        # Check name similarity more carefully
        # If the normalized form matches the cluster name well, it's good
        if found_norm in cluster_name or cluster_name in found_norm:
            good.append(cid)
        elif found_norm in modern or modern in found_norm:
            good.append(cid)
        elif found_name in cluster_name or cluster_name in found_name:
            good.append(cid)
        else:
            # Check if it's a substring match that's too loose
            # e.g. "tabaxir" matching "tabaco" because of shared prefix
            common_prefix = 0
            for a, b in zip(found_name, cluster_name):
                if a == b:
                    common_prefix += 1
                else:
                    break
            # If less than 60% of the shorter name is shared, suspicious
            min_len = min(len(found_name), len(cluster_name))
            if min_len > 0 and common_prefix / min_len < 0.6:
                suspicious.append((cid, f"weak substring: '{found_name}' vs '{cluster_name}'"))
            else:
                good.append(cid)

    if suspicious and not good:
        return False, f"all matches suspicious: {suspicious}"
    elif suspicious:
        return True, f"some suspicious matches: {suspicious} (but {len(good)} good)"
    return True, ""


# ═══════════════════════════════════════════════════════════════
# FILTER C: OCR garbage detection
# ═══════════════════════════════════════════════════════════════

# Characters that should never appear in entity names
OCR_NOISE_CHARS = set('»«^§|{}†‡¶≫≪●◆■□★☆♦♣♠♥')

# Patterns that indicate OCR corruption
OCR_NOISE_PATTERNS = re.compile(
    r"""
    [»«^§|{}†‡¶] |          # noise characters
    \b[A-Z]{1,2}\s[A-Z]{1,2}\b |  # fragmented caps (e.g., "LO CE HI»")
    [^\w\s.,;:'''\-()]{2,} |  # 2+ consecutive non-word/punct chars
    \w+\^\w+ |                # word^word (caret in middle)
    \d{3,}                    # long number sequences
    """,
    re.VERBOSE
)

# Minimum viable entity name: at least 2 alpha chars
MIN_ALPHA_CHARS = 2


def is_ocr_garbage(finding: dict) -> tuple[bool, str]:
    """Detect OCR garbage masquerading as entity names."""
    name = finding.get('found_name', '')

    # Check for noise characters
    noise_chars = [c for c in name if c in OCR_NOISE_CHARS]
    if noise_chars:
        return True, f"noise chars: {''.join(noise_chars)}"

    # Check noise patterns
    if OCR_NOISE_PATTERNS.search(name):
        return True, f"noise pattern in '{name}'"

    # Too few alpha characters
    alpha_count = sum(1 for c in name if c.isalpha())
    if alpha_count < MIN_ALPHA_CHARS:
        return True, f"too few alpha chars ({alpha_count}) in '{name}'"

    # Mostly digits
    if alpha_count < len(name) * 0.3 and len(name) > 3:
        return True, f"mostly non-alpha in '{name}'"

    return False, ""


# ═══════════════════════════════════════════════════════════════
# FILTER D: Relationship classification
# ═══════════════════════════════════════════════════════════════

# Keyword-based classification of the "found_relationship" field
RELATIONSHIP_KEYWORDS = {
    'true_synonym': [
        'synonym', 'equivalent', 'same as', 'identical', 'also called',
        'alternative name', 'known as', 'that is', 'i.e.', 'namely',
    ],
    'cross_linguistic': [
        'called in', 'portuguese', 'spanish', 'italian', 'french',
        'english', 'latin', 'arabic', 'greek', 'persian', 'sanskrit',
        'local name', 'vernacular', 'vulgar name', 'trade name',
        'in malabar', 'in persia',
    ],
    'contested_identity': [
        'debated', 'confused', 'conflated', 'mistaken', 'disputed',
        'may be', 'possibly', 'uncertain', 'different from', 'distinct',
        'some say', 'others claim',
    ],
    'subtype_relation': [
        'type of', 'variety', 'subtype', 'specific form', 'kind of',
        'preparation of', 'derived from', 'extracted from', 'made from',
    ],
    'ingredient_cooccurrence': [
        'ingredient', 'component', 'listed', 'recipe', 'compound',
        'formula', 'mixed with', 'added to', 'preparation',
    ],
    'authority_cooccurrence': [
        'authority', 'cited', 'mentioned alongside', 'mentioned by',
        'according to', 'writes that', 'says that',
    ],
}


def classify_relationship(finding: dict) -> tuple[str, float]:
    """
    Classify the relationship type and assign a confidence score.

    Returns (label, confidence) where confidence is 0.0-1.0.
    """
    rel = finding.get('found_relationship', '').lower()
    found_cat = finding.get('found_category', '').upper()
    source_cat = finding.get('source_category', '').upper()

    # Score each category
    scores = {}
    for label, keywords in RELATIONSHIP_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in rel)
        scores[label] = score

    best_label = max(scores, key=scores.get)
    best_score = scores[best_label]

    # If no keywords match, use structural heuristics
    if best_score == 0:
        # Person sources mentioning other persons = authority co-occurrence
        if source_cat == 'PERSON' and found_cat == 'PERSON':
            return 'authority_cooccurrence', 0.7

        # If found_cat matches source_cat, more likely genuine
        if found_cat == source_cat:
            return 'possible_synonym', 0.4

        return 'unclassified', 0.2

    # Confidence based on keyword count
    confidence = min(0.5 + best_score * 0.15, 0.95)

    return best_label, confidence


# ═══════════════════════════════════════════════════════════════
# FILTER E: Generic term detection
# ═══════════════════════════════════════════════════════════════

GENERIC_TERMS = {
    # Dosage forms / pharmaceutical preparations (NOT substances)
    # Italian
    'lattouaro', 'sciroppo', 'vnguento', 'ceroto', 'empiastro', 'pillole',
    'polvere', 'decottione', 'collirio',
    # Portuguese
    'po', 'xarope', 'unguento', 'emplastro', 'pilulas',
    # Spanish
    'polvo', 'jarabe', 'ungüento', 'emplasto', 'pildoras',
    # English
    'ointment', 'plaster', 'syrup', 'pill', 'powder', 'decoction',
    'poultice', 'lozenge', 'electuary',
    # French
    'poudre', 'onguent', 'emplâtre', 'pilule', 'sirop',
    # Latin
    'pulvis', 'unguentum', 'emplastrum', 'pilulae', 'syrupus',

    # Plant parts (too generic without a qualifier)
    'radice', 'foglia', 'seme', 'fiore', 'corteccia', 'erba', 'herba',
    'frutto', 'legno',
    'raiz', 'folha', 'flor', 'suco', 'casca', 'erva', 'fruta',
    'hoja', 'jugo', 'corteza', 'hierba', 'fruto',
    'root', 'leaf', 'seed', 'herb', 'flower', 'bark', 'juice',
    'racine', 'feuille', 'graine', 'herbe', 'fleur', 'ecorce', 'jus',
    'radix', 'folium', 'semen', 'flos', 'cortex', 'succus',
}


def is_generic_term(finding: dict) -> tuple[bool, str]:
    """Detect entity names that are too generic to be useful."""
    name = finding.get('found_name', '').lower().strip()

    # Exact match to generic terms
    if name in GENERIC_TERMS:
        return True, f"generic term: '{name}'"

    # Single common word (not a proper noun or specific name)
    if len(name.split()) == 1 and len(name) <= 6 and not name[0].isupper():
        if name in GENERIC_TERMS:
            return True, f"short generic: '{name}'"

    return False, ""


# ═══════════════════════════════════════════════════════════════
# MEGA-CLUSTER FILTER: Too many entities in one excerpt = recipe
# ═══════════════════════════════════════════════════════════════

def detect_mega_clusters(findings: list[dict]) -> set[str]:
    """
    Find excerpts that generate 5+ entities — almost always recipes.
    Returns set of excerpt snippet prefixes to flag.
    """
    excerpt_counts = Counter()
    for f in findings:
        key = f['excerpt_snippet'][:80]
        excerpt_counts[key] += 1

    return {k for k, v in excerpt_counts.items() if v >= 5}


# ═══════════════════════════════════════════════════════════════
# MAIN CLASSIFICATION PIPELINE
# ═══════════════════════════════════════════════════════════════

def is_specific_substance_name(name: str) -> bool:
    """
    Check if a name is a specific substance/plant/disease name rather than
    a generic word. Specific names are real entities even in recipe contexts.

    The key insight: "Zafferano" in a recipe IS a genuine Italian name for saffron.
    The recipe context doesn't make it less of a cross-linguistic naming link.
    """
    name_l = name.lower().strip()

    # Too short to be specific
    if len(name_l) < 4:
        return False

    # Already filtered as generic
    if name_l in GENERIC_TERMS:
        return False

    # Multi-word names are almost always specific
    if len(name_l.split()) >= 2:
        return True

    # Capitalized names in the middle of text are usually entities
    if name and name[0].isupper() and len(name_l) >= 5:
        return True

    # Latinate pharmaceutical names (ending in -um, -is, -a, -os)
    if re.search(r'(?:ium|eum|icum|osum|alis|aris|inus|atus|ica|osa|ola)$', name_l):
        return True

    return False


def classify_all(findings: list[dict], cmap: dict) -> list[dict]:
    """Run all filters on all findings.

    Priority order:
    1. OCR garbage → discard (highest confidence negative)
    2. Generic terms → discard
    3. Relationship signals (synonym/cross-linguistic) → TAKE PRIORITY over recipe context
    4. Vocabulary match quality check
    5. Recipe context as TIE-BREAKER when no positive signal exists
    6. Needs review (no strong signal either way)
    """

    mega_excerpts = detect_mega_clusters(findings)

    for f in findings:
        # ── Step 1: OCR garbage (hard reject) ──
        is_ocr, ocr_reason = is_ocr_garbage(f)
        if is_ocr:
            f['auto_label'] = 'ocr_noise'
            f['auto_confidence'] = 0.95
            f['auto_reason'] = ocr_reason
            f['auto_is_genuine'] = False
            continue

        # ── Step 2: Generic terms (hard reject) ──
        is_generic, generic_reason = is_generic_term(f)
        if is_generic:
            f['auto_label'] = 'generic_term'
            f['auto_confidence'] = 0.85
            f['auto_reason'] = generic_reason
            f['auto_is_genuine'] = False
            continue

        # ── Gather all signals ──
        is_recipe, recipe_reason = is_recipe_ingredient_list(f)
        excerpt_key = f['excerpt_snippet'][:80]
        if excerpt_key in mega_excerpts:
            is_recipe = True
            recipe_reason = "mega-cluster excerpt (5+ entities from same passage)"

        match_ok, match_reason = check_vocabulary_match_quality(f, cmap)
        rel_label, rel_confidence = classify_relationship(f)

        # Is this a specific named entity (not a generic word)?
        specific = is_specific_substance_name(f.get('found_name', ''))

        # Does the found name match an existing concordance cluster?
        # If so, it's a real entity regardless of recipe context
        has_cluster_match = len(f.get('matched_cluster_ids', [])) > 0
        is_cross_cluster = f.get('is_cross_cluster_link', False)

        # ── Step 3: POSITIVE signals take priority ──
        # The key fix: synonym/cross-linguistic/contested signals override recipe context.
        # An entity name like "Zafferano" is a genuine Italian saffron name even in a recipe.

        if rel_label == 'true_synonym':
            f['auto_label'] = 'true_synonym'
            f['auto_confidence'] = rel_confidence
            f['auto_reason'] = f'synonym signal: "{f.get("found_relationship", "")[:60]}"'
            f['auto_is_genuine'] = True
            continue

        if rel_label == 'cross_linguistic':
            f['auto_label'] = 'cross_linguistic'
            f['auto_confidence'] = rel_confidence
            f['auto_reason'] = f'language signal: "{f.get("found_relationship", "")[:60]}"'
            f['auto_is_genuine'] = True
            continue

        if rel_label == 'contested_identity':
            f['auto_label'] = 'contested_identity'
            f['auto_confidence'] = rel_confidence
            f['auto_reason'] = f'contested: "{f.get("found_relationship", "")[:60]}"'
            f['auto_is_genuine'] = True
            continue

        if rel_label == 'subtype_relation':
            f['auto_label'] = 'subtype_relation'
            f['auto_confidence'] = rel_confidence
            f['auto_reason'] = f'subtype: "{f.get("found_relationship", "")[:60]}"'
            f['auto_is_genuine'] = True
            continue

        # ── Step 4: Vocabulary match quality ──
        if not match_ok:
            f['auto_label'] = 'spurious_match'
            f['auto_confidence'] = 0.8
            f['auto_reason'] = match_reason
            f['auto_is_genuine'] = False
            continue

        # ── Step 5: Authority co-occurrence ──
        if rel_label == 'authority_cooccurrence':
            f['auto_label'] = 'authority_cooccurrence'
            f['auto_confidence'] = rel_confidence
            f['auto_reason'] = 'authority citation pattern'
            f['auto_is_genuine'] = False
            continue

        # ── Step 6: Recipe context as tiebreaker ──
        # Only classify as recipe ingredient if:
        # - Recipe structural markers present AND
        # - No positive synonym/naming signal AND
        # - Entity doesn't match a known cluster (or only matches source cluster)
        if is_recipe:
            if rel_label == 'ingredient_cooccurrence':
                # Both recipe structure AND relationship say ingredient
                # But if the entity is a specific named substance, lower confidence
                # so the LLM can reclassify it — it might be a real cross-linguistic name
                if specific:
                    f['auto_label'] = 'ingredient_cooccurrence'
                    f['auto_confidence'] = 0.7  # below 0.85 threshold → LLM will reclassify
                    f['auto_reason'] = f'{recipe_reason} (but specific name: {f["found_name"]})'
                    f['auto_is_genuine'] = False
                else:
                    f['auto_label'] = 'ingredient_cooccurrence'
                    f['auto_confidence'] = 0.9
                    f['auto_reason'] = recipe_reason
                    f['auto_is_genuine'] = False
                continue

            if is_cross_cluster and specific:
                # Recipe context but entity IS a specific name linking to another cluster
                # → classify as genuine but with recipe context noted
                f['auto_label'] = 'entity_in_recipe'
                f['auto_confidence'] = 0.6
                f['auto_reason'] = f'specific entity ({f["found_name"]}) in recipe context, cross-cluster link'
                f['auto_is_genuine'] = True
                continue

            if not has_cluster_match and not specific:
                # Recipe context, no cluster match, not a specific name → ingredient list
                f['auto_label'] = 'ingredient_cooccurrence'
                f['auto_confidence'] = 0.8
                f['auto_reason'] = recipe_reason
                f['auto_is_genuine'] = False
                continue

            if has_cluster_match and specific:
                # Specific entity in recipe that matches a cluster — split decision
                f['auto_label'] = 'entity_in_recipe'
                f['auto_confidence'] = 0.55
                f['auto_reason'] = f'specific entity in recipe context'
                f['auto_is_genuine'] = True
                continue

            # Recipe but ambiguous
            f['auto_label'] = 'probable_recipe'
            f['auto_confidence'] = 0.6
            f['auto_reason'] = recipe_reason
            f['auto_is_genuine'] = False
            continue

        # ── Step 7: No strong signal → needs review ──
        # But if the entity matches a different cluster and is specific, lean genuine
        if is_cross_cluster and specific:
            f['auto_label'] = 'probable_link'
            f['auto_confidence'] = 0.5
            f['auto_reason'] = f'cross-cluster link with specific name, no other signal'
            f['auto_is_genuine'] = True
            continue

        if has_cluster_match:
            f['auto_label'] = 'possible_link'
            f['auto_confidence'] = 0.4
            f['auto_reason'] = f'cluster match exists but relationship unclear'
            f['auto_is_genuine'] = None

        else:
            f['auto_label'] = 'needs_review'
            f['auto_confidence'] = 0.3
            f['auto_reason'] = f'no strong signal (rel: {rel_label})'
            f['auto_is_genuine'] = None

    return findings


def validate_against_curated(findings: list[dict], curated: list[dict]):
    """Compare automated classifications against expert-curated labels."""
    print("\n" + "="*70)
    print("VALIDATION AGAINST CURATED EXAMPLES")
    print("="*70)

    # Build lookup from curated examples
    curated_map = {}
    for ex in curated:
        key = (ex['source_cluster_id'], ex['found_name'].lower())
        curated_map[key] = ex

    matches = 0
    mismatches = 0
    not_found = 0
    details = []

    for ex in curated:
        key = (ex['source_cluster_id'], ex['found_name'].lower())

        # Find corresponding finding
        match = None
        for f in findings:
            if (f['source_cluster_id'] == ex['source_cluster_id'] and
                f['found_name'].lower() == ex['found_name'].lower()):
                match = f
                break

        if not match:
            not_found += 1
            continue

        expert_genuine = ex['is_genuine_link']
        auto_genuine = match.get('auto_is_genuine')
        expert_label = ex['expert_label']
        auto_label = match.get('auto_label', '?')

        # Compare binary genuine/not-genuine
        if auto_genuine is None:
            status = 'REVIEW'
        elif auto_genuine == expert_genuine:
            status = 'AGREE'
            matches += 1
        else:
            status = 'DISAGREE'
            mismatches += 1

        details.append({
            'name': ex['found_name'],
            'expert': expert_label,
            'auto': auto_label,
            'expert_genuine': expert_genuine,
            'auto_genuine': auto_genuine,
            'status': status,
        })

    # Print results
    total_decided = matches + mismatches
    review_count = sum(1 for d in details if d['status'] == 'REVIEW')

    print(f"\nCurated examples found: {len(details)}/{len(curated)}")
    print(f"Agreement (genuine/not-genuine): {matches}/{total_decided} "
          f"({matches/total_decided*100:.0f}%)" if total_decided > 0 else "")
    print(f"Disagreements: {mismatches}")
    print(f"Sent to review (no auto decision): {review_count}")
    print()

    # Show disagreements
    if mismatches > 0:
        print("DISAGREEMENTS:")
        for d in details:
            if d['status'] == 'DISAGREE':
                print(f"  '{d['name']}': expert={d['expert']}(genuine={d['expert_genuine']}) "
                      f"auto={d['auto']}(genuine={d['auto_genuine']})")
        print()

    # Show review items
    if review_count > 0:
        print(f"NEEDS REVIEW ({review_count}):")
        for d in details:
            if d['status'] == 'REVIEW':
                print(f"  '{d['name']}': expert={d['expert']} auto={d['auto']}")

    return matches, mismatches, review_count


def build_reclassify_prompt(batch: list[dict]) -> str:
    """Build an LLM prompt to reclassify ambiguous findings using few-shot examples."""
    lines = [
        "You are classifying entity relationships found in early modern (1500-1900) medical texts.",
        "",
        "For each finding below, an entity name was found in a text excerpt alongside a known entity.",
        "Classify the relationship as ONE of:",
        "",
        "  GENUINE_LINK — The found entity is a real substance/plant/disease/person name that has",
        "    a meaningful relationship to the source entity (synonym, translation, subtype, or",
        "    contested identification). Even if found in a recipe, specific named substances",
        "    like 'Zafferano' (saffron), 'Cinnamomo' (cinnamon), 'mandragora' (mandrake) are",
        "    genuine cross-linguistic entity names worth linking.",
        "",
        "  RECIPE_ONLY — The found entity appears ONLY as an ingredient in a recipe formula",
        "    alongside the source entity. It IS a real entity, but the relationship is just",
        "    'listed in the same compound medicine' — no equivalence or naming claim.",
        "    Example: 'Aloe' and 'Colocynth' in a purgative pill recipe.",
        "",
        "  NOT_ENTITY — OCR garbage, generic term (salt, water, powder), or not a real entity name.",
        "",
        "Return a JSON array with one object per finding:",
        '  {"idx": <number>, "label": "GENUINE_LINK"|"RECIPE_ONLY"|"NOT_ENTITY", "reason": "<10 words>"}',
        "",
        "FINDINGS:",
        "",
    ]

    for i, f in enumerate(batch):
        lines.append(f"[{i}] Source: {f['source_cluster_name']} ({f['source_category']}, "
                     f"modern: {f.get('source_modern_name', '?')})")
        lines.append(f"    Found: \"{f['found_name']}\" (normalized: {f.get('found_normalized', '?')}, "
                     f"category: {f.get('found_category', '?')})")
        lines.append(f"    Relationship: {f.get('found_relationship', '?')}")
        lines.append(f"    Book: {f['source_book']}")
        lines.append(f"    Excerpt: \"{f.get('excerpt_snippet', '')[:200]}\"")
        lines.append("")

    lines.append("Return ONLY the JSON array.")
    return "\n".join(lines)


def llm_reclassify(findings: list[dict], client, model: str, batch_size: int = 15) -> list[dict]:
    """Use LLM to reclassify ambiguous findings."""
    import time

    # Select findings that need reclassification
    ambiguous = [(i, f) for i, f in enumerate(findings)
                 if f.get('auto_label') in ('ingredient_cooccurrence', 'probable_recipe',
                                             'entity_in_recipe', 'probable_link',
                                             'possible_link', 'needs_review')
                 and f.get('auto_confidence', 1.0) < 0.85]

    if not ambiguous:
        print("  No ambiguous findings to reclassify.")
        return findings

    print(f"  Reclassifying {len(ambiguous)} ambiguous findings...")
    reclassified = 0
    failed = 0

    for batch_start in range(0, len(ambiguous), batch_size):
        batch_items = ambiguous[batch_start:batch_start + batch_size]
        batch_findings = [f for _, f in batch_items]
        batch_indices = [i for i, _ in batch_items]

        prompt = build_reclassify_prompt(batch_findings)
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("```", 1)[0]
                text = text.strip()
            results = json.loads(text)

            for result in results:
                idx_in_batch = result.get('idx')
                if idx_in_batch is None or idx_in_batch >= len(batch_items):
                    continue

                original_idx = batch_indices[idx_in_batch]
                label = result.get('label', '')
                reason = result.get('reason', '')

                if label == 'GENUINE_LINK':
                    findings[original_idx]['auto_label'] = 'llm_genuine'
                    findings[original_idx]['auto_confidence'] = 0.8
                    findings[original_idx]['auto_reason'] = f'LLM: {reason}'
                    findings[original_idx]['auto_is_genuine'] = True
                    reclassified += 1
                elif label == 'RECIPE_ONLY':
                    findings[original_idx]['auto_label'] = 'llm_recipe'
                    findings[original_idx]['auto_confidence'] = 0.8
                    findings[original_idx]['auto_reason'] = f'LLM: {reason}'
                    findings[original_idx]['auto_is_genuine'] = False
                    reclassified += 1
                elif label == 'NOT_ENTITY':
                    findings[original_idx]['auto_label'] = 'llm_not_entity'
                    findings[original_idx]['auto_confidence'] = 0.8
                    findings[original_idx]['auto_reason'] = f'LLM: {reason}'
                    findings[original_idx]['auto_is_genuine'] = False
                    reclassified += 1

        except Exception as e:
            failed += 1

        time.sleep(0.5)

    print(f"  Reclassified: {reclassified}, Failed batches: {failed}")
    return findings


def main():
    parser = argparse.ArgumentParser(description="Classify synonym chain findings")
    parser.add_argument("--validate", action="store_true", help="Validate against curated labels")
    parser.add_argument("--llm-reclassify", action="store_true", help="Use LLM for ambiguous cases")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model for LLM step")
    args = parser.parse_args()

    # Load data
    print("Loading findings...")
    with open(FINDINGS_PATH) as f:
        findings = json.load(f)
    print(f"  {len(findings)} findings")

    with open(CONCORDANCE_PATH) as f:
        conc = json.load(f)
    cmap = {c['id']: c for c in conc['clusters']}

    # Run heuristic classification
    print("Phase 1: Heuristic classification...")
    findings = classify_all(findings, cmap)

    # Phase 2: LLM reclassification for ambiguous cases
    if args.llm_reclassify:
        print("\nPhase 2: LLM reclassification...")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            from dotenv import load_dotenv
            load_dotenv(BASE_DIR / ".env.local")
            api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            findings = llm_reclassify(findings, client, args.model)
        else:
            print("  Skipped: GEMINI_API_KEY not set")

    # Summary
    labels = Counter(f.get('auto_label', '?') for f in findings)
    genuine_count = sum(1 for f in findings if f.get('auto_is_genuine') is True)
    not_genuine = sum(1 for f in findings if f.get('auto_is_genuine') is False)
    review_count = sum(1 for f in findings if f.get('auto_is_genuine') is None)

    print(f"\nCLASSIFICATION RESULTS")
    print(f"{'='*60}")
    print(f"\nBy label:")
    for label, count in labels.most_common():
        pct = count / len(findings) * 100
        genuine_marker = {True: '+', False: '-', None: '?'}.get(
            findings[[f.get('auto_label') for f in findings].index(label)].get('auto_is_genuine'), '?')
        print(f"  [{genuine_marker}] {label}: {count} ({pct:.0f}%)")

    print(f"\nGenuine links: {genuine_count} ({genuine_count/len(findings)*100:.0f}%)")
    print(f"Not genuine:   {not_genuine} ({not_genuine/len(findings)*100:.0f}%)")
    print(f"Needs review:  {review_count} ({review_count/len(findings)*100:.0f}%)")

    # Confidence distribution
    confs = [f.get('auto_confidence', 0) for f in findings]
    high_conf = sum(1 for c in confs if c >= 0.7)
    med_conf = sum(1 for c in confs if 0.4 <= c < 0.7)
    low_conf = sum(1 for c in confs if c < 0.4)
    print(f"\nConfidence: {high_conf} high (≥0.7), {med_conf} medium, {low_conf} low (<0.4)")
    print(f"Auto-decidable (conf ≥ 0.7): {high_conf} ({high_conf/len(findings)*100:.0f}%)")
    print(f"Human review needed: {len(findings) - high_conf} ({(len(findings)-high_conf)/len(findings)*100:.0f}%)")

    # Save classified findings
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {OUTPUT_PATH}")

    # Validate against curated examples if requested
    if args.validate and CURATED_PATH.exists():
        with open(CURATED_PATH) as f:
            curated = [json.loads(line) for line in f]
        validate_against_curated(findings, curated)

    # Scaling analysis
    print(f"\n{'='*60}")
    print(f"SCALING ANALYSIS")
    print(f"{'='*60}")
    print(f"\nCurrent: 6 books, 1,629 excerpts → {len(findings)} findings")
    print(f"Projected at 500 books: ~{len(findings) * 500 // 6:,} findings")
    print(f"Projected at 5000 books: ~{len(findings) * 5000 // 6:,} findings")
    print(f"\nWith current filters at ≥0.7 confidence:")
    print(f"  Auto-decided: {high_conf/len(findings)*100:.0f}% of findings need NO human review")
    print(f"  Human review: {(len(findings)-high_conf)/len(findings)*100:.0f}% need review")
    print(f"  At 500 books: ~{(len(findings)-high_conf) * 500 // 6:,} items for human review")
    print(f"  At 5000 books: ~{(len(findings)-high_conf) * 5000 // 6:,} items for human review")


if __name__ == '__main__':
    main()

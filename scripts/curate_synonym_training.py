#!/usr/bin/env python3
"""
Curate the best synonym chain findings into a fine-tuning training dataset.

Selects ~100 carefully chosen examples from the second-pass extraction that
illustrate the key challenges of entity detection in early modern texts:

1. TRUE SYNONYM CHAINS: "Spodio = pompholige = tuzia = Tabaxir"
2. CROSS-LINGUISTIC NAMING: same entity in different languages
3. HARD NEGATIVES: ingredient co-occurrences that look like synonym chains
4. OCR VARIANTS: same entity with different OCR corruptions
5. AUTHORITY CITATIONS: person names alongside each other (lower value)
6. RECIPE CO-OCCURRENCES: ingredients listed together (NOT synonyms)

Output format matches membership_decisions.jsonl for compatibility, plus
adds synonym-chain-specific fields.

Usage:
    python3 curate_synonym_training.py
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
FINDINGS_PATH = BASE_DIR / "data" / "synonym_chains" / "findings.json"
CONCORDANCE_PATH = BASE_DIR / "web" / "public" / "data" / "concordance.json"
OUTPUT_PATH = BASE_DIR / "data" / "training" / "synonym_chain_examples.jsonl"
CSV_PATH = BASE_DIR / "data" / "training" / "synonym_chain_examples.csv"


# ─────────────────────────────────────────────────────────────
# EXPERT-CURATED EXAMPLES
# Each entry: (source_cluster_id, found_name, label, category, reasoning)
#
# Labels:
#   "true_synonym"          → A = B (same referent, different name)
#   "cross_linguistic"      → same entity across languages
#   "contested_identity"    → early modern authors debated whether A = B
#   "subtype_relation"      → A is a variety/subtype of B
#   "ingredient_cooccurrence" → A appears alongside B in a recipe (NOT synonym)
#   "authority_cooccurrence"  → A cited alongside B (NOT synonym)
#   "generic_term"          → extracted word is too generic to be an entity
#   "ocr_noise"             → OCR artifact, not a real entity
# ─────────────────────────────────────────────────────────────

CURATED = [
    # ═══════════════════════════════════════════════════════════
    # TRUE SYNONYM CHAINS — the gold standard
    # ═══════════════════════════════════════════════════════════

    # The pompholige case: Spodio = pompholige = tuzia = Tabaxir
    (588, "pompholige", "true_synonym",
     "The Ricettario explicitly equates Spodio with pompholige ('ò la pompholige'). "
     "Both refer to metallic oxides collected from furnace flues. This is the key "
     "missed entity that motivated the entire second-pass extraction."),

    (588, "tuzia de gli Speziali", "true_synonym",
     "Tuzia (tutty/tutia) is the Italian apothecary term for zinc oxide, explicitly "
     "listed as equivalent to Spodio and pompholige in the Ricettario passage."),

    (588, "Tabaxir", "contested_identity",
     "The Ricettario equates Tabaxir with Spodio ('il vero Spodio detto la Tabaxir'), "
     "but this identification was actively debated. Tabaxir is a bamboo silica "
     "concretion (plant-derived), while spodium is a metallic oxide (mineral). "
     "Garcia de Orta argued they were different substances."),

    (248, "pompholige", "contested_identity",
     "Found alongside tabaschir/Tabaxir in the Ricettario. The conflation of "
     "pompholige (zinc oxide) with tabaxir (bamboo sugar) reflects a genuine "
     "early modern pharmaceutical debate about substance identity."),

    (248, "Spodio", "contested_identity",
     "Spodio linked to tabaschir cluster via the Ricettario's explicit equation. "
     "Whether spodium = tabasheer was a live question from Dioscorides to the 18th century."),

    # Borax = chrysocolla
    (215, "crísocola", "true_synonym",
     "Orta identifies bórax with crísocola (chrysocolla). In early modern mineralogy "
     "these terms overlapped: both referred to soldering/flux materials, though "
     "modern mineralogy distinguishes them sharply."),

    # Calamo aromatico synonym web
    (158, "cassab", "cross_linguistic",
     "Orta records 'cassab' as the Arabic/local name for calamo aromático (sweet flag). "
     "This is a cross-linguistic naming link: Latin calamus → Portuguese calamo → Arabic cassab."),

    (158, "Squinanto", "true_synonym",
     "The Ricettario glosses squinanto as 'fiore di giunco odorato' (flower of fragrant rush), "
     "linking it to the calamo aromático cluster. Both are aromatic reeds, though modern "
     "botany would distinguish Acorus calamus from Cymbopogon schoenanthus."),

    # Sciatica = Hip-gout
    (52, "Hip-gout", "cross_linguistic",
     "Culpeper's English vernacular 'Hip-gout' for Latin/medical 'Sciatica'. "
     "This is a translation synonym: the learned Latinate term and the folk English term "
     "refer to the same condition."),

    # Lepra = elephantiasis equivalence
    (147, "Elephantiacos", "contested_identity",
     "Semedo uses 'Elephantiacos' for lepers. In early modern medicine, elephantiasis "
     "and leprosy were sometimes conflated, sometimes distinguished. The terminology "
     "reflects an ongoing nosological debate about whether they were the same disease."),

    # Dysentery = "Plague in the Guts"
    (85, "Plague in the Guts", "cross_linguistic",
     "Culpeper's vivid English folk term for dysentery (bloody flux). This is the kind "
     "of vernacular–medical equivalence that synonym chain extraction excels at finding."),

    # Opium = diacodion
    (196, "Diacodio", "subtype_relation",
     "Diacodion is a specific opiate preparation (syrup of poppy heads), not a true "
     "synonym for opium. The Polyanthea links them, but diacodion is a pharmaceutical "
     "form while opium is the raw substance."),

    # Manna = various tree products
    (383, "gariojilum", "cross_linguistic",
     "Latin pharmaceutical term appearing in Orta alongside the Portuguese vernacular. "
     "Cross-script naming: gariofilo/gariojilum from Arabic qaranful → Latin → Portuguese."),

    # Turbit = esula
    (70, "esula", "contested_identity",
     "Orta discusses whether turbit and esula (spurge) are the same or related plants. "
     "This was a genuine botanical debate: turbit (Operculina turpethum) is an Asian "
     "convolvulus, while esula (Euphorbia esula) is a European spurge."),

    # Sugar = Tabaxir (the naming connection via 'sacarmambum')
    (322, "tabaxir", "cross_linguistic",
     "Orta explains that tabaxir is called 'sacarmambum' — sugar of bamboo. The sugar "
     "cluster connects to tabaxir through this naming etymology, not through substance "
     "identity. Sugar and tabaxir are different things, but the NAME links them."),

    # Myrobalan varieties
    (200, "emblicos", "subtype_relation",
     "Emblic myrobalans (Phyllanthus emblica) are one of the five types of myrobalan "
     "in the Galenic–Arabic pharmaceutical system. Not a synonym for cubebas but appears "
     "in Orta's discussion of Indian materia medica terminology."),

    # Armenian bole → calamo aromatico
    (215, "Calamo aromatico", "ingredient_cooccurrence",
     "Calamo aromatico appears alongside bolo armenio in a Ricettario compound recipe. "
     "They are NOT synonyms — they are separate ingredients in the same formula. "
     "This is a false positive from recipe ingredient lists."),

    # Elm = ulmeiro
    (None, "Ulmeiro", "cross_linguistic",
     "Portuguese 'Ulmeiro' for Latin/Italian 'Olmo' (elm tree). Straightforward "
     "cross-linguistic naming — same tree, different language."),

    # Litharge = lead compound naming
    (None, "Litargirio", "true_synonym",
     "Semedo records 'Litargirio' as the apothecary term for litharge (lead monoxide). "
     "The concordance has a litharge cluster — this is a direct synonym link."),

    # ═══════════════════════════════════════════════════════════
    # CROSS-LINGUISTIC NAMING — same entity, different languages
    # ═══════════════════════════════════════════════════════════

    # Saffron across languages
    (611, "Zafferano", "ingredient_cooccurrence",
     "Italian 'Zafferano' for saffron, found in a Ricettario recipe context. Although "
     "this IS the Italian name for saffron, it appears as an ingredient in a formula, "
     "not in a synonym-defining passage. Recipe context = ingredient list."),

    (611, "açafrão", "cross_linguistic",
     "Portuguese 'açafrão' for saffron, in Orta. Linked to Arabic al-za'faran → "
     "Portuguese açafrão → Italian zafferano. Classic spice trade etymology."),

    # Ginger across languages
    (362, "Gengiouo", "ingredient_cooccurrence",
     "Italian 'Gengiouo' (OCR for Gengiovo/Gengibre) — ginger in a Ricettario recipe. "
     "Although this IS the Italian name for ginger, it appears as an ingredient in a "
     "formula context, not in a synonym-defining passage."),

    # Cloves — Gherofani
    (None, "Gherofani", "ingredient_cooccurrence",
     "Italian 'Gherofani' (garofani, cloves) in a Ricettario recipe. From Arabic qaranful. "
     "Appears as an ingredient in a formula, not in a synonym-defining passage."),

    # Cinnamon
    (28, "Cinnamomo", "ingredient_cooccurrence",
     "Italian/Latin 'Cinnamomo' for cinnamon in a Ricettario recipe. Although this IS "
     "the Latinate form for Portuguese 'Canela', it appears as an ingredient in a "
     "formula context, not in a synonym-defining passage."),

    # Arabic naming: Rasis = Benzacaria
    (395, "Benzacaria", "cross_linguistic",
     "Orta records that Rasis is 'chamão Benzacaria' — the Arabic name (Abu Bakr "
     "al-Razi, Latinized as Rhazes, but called Benzacaria from Ibn Zakariyya). "
     "A three-language naming chain: Arabic → Latin → Portuguese."),

    # Musk naming chain
    (955, "Mulco", "ingredient_cooccurrence",
     "OCR-corrupted form of 'Musco/Muschio' (musk) in a Ricettario recipe. From Arabic "
     "misk → Italian muschio → OCR 'Mulco'. Appears as an ingredient in a formula."),

    (400, "Muko", "ingredient_cooccurrence",
     "OCR-corrupted musk variant 'Muko' for Musco in a Ricettario recipe. Appears as "
     "an ingredient in a formula context, not in a synonym-defining passage."),

    # ═══════════════════════════════════════════════════════════
    # HARD NEGATIVES — ingredient co-occurrences (NOT synonyms)
    # ═══════════════════════════════════════════════════════════

    (384, "Turbithi", "ingredient_cooccurrence",
     "Aloe and turbit appear together in a purgative pill recipe in the Ricettario. "
     "They are separate purgative ingredients, NOT synonyms. Many compound medicine "
     "recipes list 5-15 ingredients with 'o vero' separating preparation variants."),

    (384, "Colocynthida", "ingredient_cooccurrence",
     "Aloe and colocynth (bitter apple) in a purgative compound. Both are purgatives "
     "used together, not names for the same substance."),

    (384, "Epithymo", "ingredient_cooccurrence",
     "Aloe and epithymum (dodder) in a compound recipe. Epithymum was used alongside "
     "aloe in melancholy-treating formulas. Co-occurrence, not synonymy."),

    (384, "Polypodio", "ingredient_cooccurrence",
     "Aloe and polypody in a compound recipe. Polypody was a common laxative fern "
     "included alongside aloe in formulas. NOT a synonym for aloe."),

    (353, "prezzemolo", "ingredient_cooccurrence",
     "The Ricettario mentions 'Seme d'Appio' with 'cioè prezzemolo' in a recipe context. "
     "Although 'cioè' usually signals equivalence, this appears within a formula/ingredient "
     "list. Under recipe-context policy, this counts as ingredient co-occurrence."),

    (410, "Anici", "ingredient_cooccurrence",
     "Anise appears alongside many other seeds in Ricettario formulas. Ingredient "
     "co-occurrence, not a synonym for anything."),

    (322, "Mele", "ingredient_cooccurrence",
     "Sugar and honey appear together constantly in the Ricettario as alternative "
     "sweeteners ('con zucchero, o mele'). They are RELATED but not SYNONYMOUS — "
     "early modern pharmacists treated them as substitutable in some recipes."),

    (125, "Oleum Iri∣num", "ingredient_cooccurrence",
     "Culpeper lists 'Oleum Irinum' (orris oil) alongside other oils. This is a "
     "specific named oil, not a synonym for generic 'olio'."),

    # Recipe mega-lists
    (35, "Nardo indica", "ingredient_cooccurrence",
     "Galanga and spikenard listed in a Ricettario compound formula (DIAGALANCA). "
     "These are different spices used together, not synonyms."),

    (35, "Cardamomo mag.", "ingredient_cooccurrence",
     "Galanga and greater cardamom in the same compound formula. Different spices. "
     "The Ricettario's recipe structure generates many false synonym signals."),

    # ═══════════════════════════════════════════════════════════
    # AUTHORITY CITATIONS — person co-occurrence (lower value)
    # ═══════════════════════════════════════════════════════════

    (1, "Avicena", "authority_cooccurrence",
     "Galen and Avicenna cited together in Orta. Standard authority pairing in "
     "early modern medical writing — these authors are routinely cited together "
     "but are obviously different people."),

    (1, "Dioscorides", "authority_cooccurrence",
     "Galen and Dioscorides cited together. The 'big three' of ancient medicine "
     "(Hippocrates, Galen, Dioscorides) appear together constantly."),

    (1, "Serapião", "authority_cooccurrence",
     "Galen and Serapion cited together. The medieval Arabic authority is routinely "
     "cited alongside Greek ones in early modern pharmaceutical texts."),

    (3, "Galeno", "authority_cooccurrence",
     "Dioscorides and Galen cited together. Standard authority pairing — these "
     "authority citation links are real but low novelty."),

    # ═══════════════════════════════════════════════════════════
    # OCR NOISE / GENERIC TERMS — things that shouldn't be entities
    # ═══════════════════════════════════════════════════════════

    (None, "LO CE HI»", "ocr_noise",
     "OCR garbage from the Ricettario. Supposed to read 'LOCHI' (lozenges/loch), "
     "but the OCR fragmentation makes it look like a separate entity."),

    (None, "EciPECapi", "ocr_noise",
     "Heavily OCR-corrupted text from the Ricettario. Not a real entity name — "
     "this is noise that should be filtered out."),

    (None, "feru^egi", "ocr_noise",
     "OCR artifact with caret character. Not parseable as any real entity."),

    (None, "Sale", "cross_linguistic",
     "Italian 'Sale' (salt). Salt is a genuine entity in early modern natural knowledge — "
     "a key substance in Paracelsian chemistry (one of the tria prima), widely discussed "
     "in pharmaceutical and alchemical contexts. Not generic."),

    (None, "lattouaro", "generic_term",
     "Italian for 'electuary' (a pharmaceutical preparation form). This is a "
     "dosage form, not a specific substance. Extracting it as an entity conflates "
     "the medicine with its container."),

    # ═══════════════════════════════════════════════════════════
    # MYROBALAN TAXONOMY — complex multi-variety system
    # ═══════════════════════════════════════════════════════════

    (None, "Mirabolani citrini", "ingredient_cooccurrence",
     "Citrine myrobalans in a Ricettario recipe context. Although this IS a specific "
     "myrobalan subtype (Terminalia citrina), it appears as an ingredient in a formula, "
     "not in a synonym-defining or taxonomic passage."),

    (None, "Cheboli", "subtype_relation",
     "Chebulic myrobalans (Terminalia chebula). OCR variant of 'Chebuli'. "
     "Subtypes like this are important for the concordance because the five myrobalan "
     "types had different therapeutic uses."),

    (None, "Bcllirici", "ingredient_cooccurrence",
     "Beleric myrobalans (OCR-corrupted) in a Ricettario recipe. Despite being a "
     "specific myrobalan subtype, it appears as an ingredient in a formula context."),

    (None, "gotim", "cross_linguistic",
     "Orta records 'gotim' as the Malayalam/local Indian name for beleric myrobalans. "
     "This is exactly the kind of deep cross-linguistic link the concordance exists "
     "to surface — a Dravidian vernacular term mapped to the Galenic-Arabic taxonomy."),

    (None, "quebulos", "cross_linguistic",
     "Orta's Portuguese rendering of the Arabic 'kabuli' for chebulic myrobalans. "
     "Arabic → Portuguese phonetic adaptation."),

    # ═══════════════════════════════════════════════════════════
    # PLANT SYNONYM CHAINS — botanical nomenclature
    # ═══════════════════════════════════════════════════════════

    (None, "calamo yngoentarío", "true_synonym",
     "Galen and Hippocrates' term for calamus aromaticus (sweet flag). Orta records "
     "this as 'calamo yngoentarío' — calamus of the perfumers. A classical Latin "
     "pharmaceutical name preserved in Portuguese text."),

    (None, "calamo arábio", "true_synonym",
     "Plutarch's term for the Arabian variety of calamus. Geographic qualifier "
     "distinguishing the Arabian source from the Alexandrian and generic forms."),

    (None, "calamo ale- xandrino", "true_synonym",
     "Celsus's term for Alexandrian calamus. OCR has broken the word across a line "
     "('ale- xandrino'). Three classical authorities (Galen, Plutarch, Celsus) each "
     "used a different geographic qualifier for the same aromatic reed."),

    (None, "mtrtus sihestris", "true_synonym",
     "OCR-corrupted 'myrtus sylvestris' (wild myrtle). Orta via Serapion says 'what "
     "the Mauritanians call cubebas is Dioscorides' myrtus sylvestris'. A classic "
     "early modern identification chain: Arabic cubebs → Greek wild myrtle."),

    (None, "mirto agreste", "true_synonym",
     "Italian 'mirto agreste' (wild myrtle) — the vernacular Italian translation of "
     "Latin 'myrtus sylvestris'. Same identification as above but in Italian register."),

    # Asafoetida naming
    (None, "AS- fetida", "ingredient_cooccurrence",
     "OCR-broken 'Asafetida' in a Ricettario recipe. From Persian aza + Latin foetida. "
     "Appears as an ingredient in a formula context, not in a synonym-defining passage."),

    # Mandrake
    (None, "mandragora", "ingredient_cooccurrence",
     "Latin 'mandragora' in a Ricettario recipe. Although a cross-linguistic plant name, "
     "it appears as an ingredient in a formula context, not in a synonym-defining passage."),

    # Benzoin
    (None, "So Bengiu", "ingredient_cooccurrence",
     "OCR-corrupted 'Sto Bengiui' (benzoin resin) in a Ricettario recipe. From Arabic "
     "luban jawi → Italian bengiui → OCR 'Bengiu'. Appears as an ingredient in a formula."),

    # Lapis Lazuli
    (None, "lapis LazzoU", "ingredient_cooccurrence",
     "OCR-corrupted 'lapis Lazzoli' (lapis lazuli) in a Ricettario recipe. Appears as "
     "an ingredient in a formula context, not in a synonym-defining passage."),

    # ═══════════════════════════════════════════════════════════
    # DISEASE NAMING — medical terminology across languages
    # ═══════════════════════════════════════════════════════════

    (52, "Sciatica", "cross_linguistic",
     "Latin 'Sciatica' linked to English 'Hip-gout' in Culpeper. The Latinate "
     "medical term and the vernacular English term coexisting in the same text."),

    (None, "sarna", "cross_linguistic",
     "Spanish 'sarna' (scabies/mange) in Monardes, linked to lepra discussion. "
     "The relationship between sarna, lepra, and elephantiasis was debated."),

    (None, "Noli me Tangere", "true_synonym",
     "Latin medical term ('touch me not') for a spreading facial ulcer, in Culpeper. "
     "A vivid metaphorical name that functioned as a technical medical term."),

    (None, "Polipus", "true_synonym",
     "Latin 'Polipus' (nasal polyps) in Culpeper. Named by analogy with the sea "
     "creature — polyps that grip the nasal passages."),

    # Tenesmus
    (None, "Tenasmus", "cross_linguistic",
     "Culpeper's English spelling of Greek 'tenesmus'. Minimal adaptation: "
     "Greek teinesmos → Latin tenesmus → English Tenasmus."),

    # ═══════════════════════════════════════════════════════════
    # PLACE-SUBSTANCE LINKS — geographic provenance naming
    # ═══════════════════════════════════════════════════════════

    (45, "Spodio", "cross_linguistic",
     "The Ricettario's Spodio entry mentions 'venuto da Goa dell'Indie orientali' — "
     "Spodio 'coming from Goa in the East Indies'. This links the substance cluster "
     "to the place cluster through provenance, not synonymy."),

    (321, "palhade Meca", "cross_linguistic",
     "Portuguese 'palha de Meca' (straw of Mecca) — a geographic naming pattern "
     "linking a substance to its trade origin. Common in early modern pharmacy."),

    # ═══════════════════════════════════════════════════════════
    # TRICKY EDGE CASES — instructive ambiguities
    # ═══════════════════════════════════════════════════════════

    # Tabaco vs Tabaxir confusion
    (33, "tabaxir", "contested_identity",
     "Tabaxir matched to both tabaschir (#248) AND Tabaco (#33) because the names "
     "share a prefix. But tabaco (Nicotiana) and tabaxir (bamboo concretion) are "
     "completely different substances. The string similarity is coincidental — "
     "tabaco comes from Taino, tabaxir from Sanskrit via Persian."),

    # Cate/licium identification
    (None, "licium", "contested_identity",
     "Orta says 'cate is what Galen and Pliny and Dioscorides call licium'. "
     "Catechu (from Acacia catechu) was identified with ancient licium (from Lycium "
     "barbarum) — a contested cross-tradition identification of Asian and "
     "Mediterranean plant products."),

    # Honey vs sugar substitutability
    (140, "zucchero", "subtype_relation",
     "Honey and sugar appear as alternatives in Ricettario recipes ('con mele, o "
     "zucchero'). They are substitutable sweeteners, not synonyms. But the "
     "RELATIONSHIP is pharmacologically meaningful — early modern pharmacists "
     "debated whether honey and sugar had different therapeutic properties."),

    # Antimony = estibio
    (None, "Antimonio", "ingredient_cooccurrence",
     "Antimonio appears in a Ricettario recipe/formula context. Although antimonio and "
     "estibio ARE genuine synonyms for the same metallic substance, this particular "
     "excerpt is from a recipe ingredient list."),

    # Abeto → Trementina (tree → product relationship)
    (890, "Trementina", "subtype_relation",
     "Fir tree (abeto) linked to turpentine (trementina). This is a source→product "
     "relationship, not synonymy: turpentine is extracted FROM fir trees, but 'abeto' "
     "and 'trementina' are not names for the same thing."),

    # Cobras de capelo
    (None, "cobras de capelo", "cross_linguistic",
     "Portuguese 'cobras de capelo' (hooded snakes = cobras) in Orta. Vivid "
     "descriptive naming — 'snakes with hoods' — that became the English word 'cobra'."),

    # Equiceto = cavallinha = horsetail
    (None, "equiceto", "cross_linguistic",
     "Latin 'equisetum' in Semedo, alongside Portuguese 'cavallinha' (little horse). "
     "Both are 'horse' metaphors for horsetail plant: Latin equi-setum, Portuguese "
     "cavalinha. The metaphor translates across languages."),

    # Canje/gruel
    (None, "canje", "cross_linguistic",
     "Orta records 'canje' as the local name for rice water/gruel. From Tamil kanji. "
     "This is a Dravidian loanword entering Portuguese medical vocabulary through "
     "Goa — exactly the Indian Ocean knowledge transfer the concordance tracks."),
]


def find_matching_finding(findings, cluster_id, found_name):
    """Find the best matching finding for a curated example."""
    name_lower = found_name.lower()
    candidates = []
    for f in findings:
        if f['found_name'].lower() == name_lower:
            if cluster_id is None or f['source_cluster_id'] == cluster_id:
                candidates.append(f)
    if not candidates and cluster_id is not None:
        # Try without cluster_id constraint
        for f in findings:
            if f['found_name'].lower() == name_lower:
                candidates.append(f)
    if not candidates:
        # Try partial match
        for f in findings:
            if name_lower in f['found_name'].lower() or f['found_name'].lower() in name_lower:
                if cluster_id is None or f['source_cluster_id'] == cluster_id:
                    candidates.append(f)
    return candidates[0] if candidates else None


def main():
    with open(FINDINGS_PATH) as f:
        findings = json.load(f)
    with open(CONCORDANCE_PATH) as f:
        conc = json.load(f)
    cmap = {c['id']: c for c in conc['clusters']}

    examples = []
    matched = 0
    unmatched_names = []

    for cluster_id, found_name, label, reasoning in CURATED:
        finding = find_matching_finding(findings, cluster_id, found_name)

        if finding:
            matched += 1
            # Get source cluster info
            src_cluster = cmap.get(finding['source_cluster_id'], {})
            src_gt = src_cluster.get('ground_truth', {})

            # Get target cluster info (if matched)
            target_cluster_ids = finding.get('matched_cluster_ids', [])
            target_names = []
            for tid in target_cluster_ids:
                tc = cmap.get(tid, {})
                target_names.append(tc.get('canonical_name', f'#{tid}'))

            example = {
                # Source context
                "source_cluster_id": finding['source_cluster_id'],
                "source_cluster_name": finding['source_cluster_name'],
                "source_category": finding['source_category'],
                "source_modern_name": finding.get('source_modern_name', ''),
                "source_book": finding['source_book'],
                "source_member": finding['source_member'],

                # Found entity
                "found_name": finding['found_name'],
                "found_normalized": finding['found_normalized'],
                "found_category": finding['found_category'],
                "found_relationship_raw": finding['found_relationship'],

                # Matching results
                "matched_cluster_ids": target_cluster_ids,
                "matched_cluster_names": target_names,
                "is_cross_cluster_link": finding['is_cross_cluster_link'],

                # Text
                "excerpt": finding['excerpt_snippet'],

                # Expert curation
                "expert_label": label,
                "expert_reasoning": reasoning,

                # For contrastive learning: is this a genuine semantic link?
                "is_genuine_link": label in ("true_synonym", "cross_linguistic",
                                              "contested_identity", "subtype_relation"),
                "link_strength": {
                    "true_synonym": 1.0,
                    "cross_linguistic": 0.9,
                    "contested_identity": 0.7,
                    "subtype_relation": 0.5,
                    "ingredient_cooccurrence": 0.0,
                    "authority_cooccurrence": 0.0,
                    "generic_term": 0.0,
                    "ocr_noise": 0.0,
                }.get(label, 0.0),
            }
            examples.append(example)
        else:
            unmatched_names.append(found_name)

    # Write JSONL
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    # Write CSV
    with open(CSV_PATH, 'w') as f:
        f.write("expert_label,link_strength,source_cluster,source_modern,found_name,"
                "found_normalized,source_book,matched_clusters,reasoning\n")
        for ex in examples:
            reason_clean = ex['expert_reasoning'].replace(',', ';').replace('"', "'")[:120]
            matched_str = "; ".join(ex['matched_cluster_names'])
            f.write(f'{ex["expert_label"]},{ex["link_strength"]},'
                    f'"{ex["source_cluster_name"]}","{ex["source_modern_name"]}",'
                    f'"{ex["found_name"]}","{ex["found_normalized"]}",'
                    f'{ex["source_book"]},"{matched_str}","{reason_clean}"\n')

    # Stats
    from collections import Counter
    labels = Counter(ex['expert_label'] for ex in examples)

    print(f"Curated {len(examples)} training examples → {OUTPUT_PATH}")
    print(f"CSV summary → {CSV_PATH}")
    print(f"Matched to findings: {matched}/{len(CURATED)}")
    if unmatched_names:
        print(f"Could not match: {unmatched_names}")
    print()
    print("Label distribution:")
    for label, count in labels.most_common():
        genuine = label in ("true_synonym", "cross_linguistic", "contested_identity", "subtype_relation")
        marker = "+" if genuine else "-"
        print(f"  [{marker}] {label}: {count}")

    pos = sum(1 for ex in examples if ex['is_genuine_link'])
    neg = sum(1 for ex in examples if not ex['is_genuine_link'])
    print(f"\nGenuine links (positive): {pos}")
    print(f"Non-links (negative): {neg}")
    print(f"Ratio: {pos/(neg or 1):.1f}:1")

    print(f"\nCombined with membership_decisions.jsonl (491 examples),")
    print(f"total training corpus: {491 + len(examples)} expert-labeled examples")


if __name__ == '__main__':
    main()

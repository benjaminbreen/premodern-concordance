#!/usr/bin/env python3
"""
Curate training pairs using strict quality filters + domain knowledge.

Reads the v3 extracted pairs, applies blocklists for known-bad clusters,
filters by quality heuristics, and outputs a curated batch file in an
additive format that future sessions can append to.

The output file (data/curated_training_pairs.json) uses a batch structure:
each batch has a contributor, date, and list of pairs. New batches can be
appended without modifying existing ones.

Usage:
    python3 scripts/curate_training_pairs.py
    python3 scripts/curate_training_pairs.py --dry-run
"""

import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

V3_PATH = Path(__file__).parent.parent / "data" / "training_pairs_v3.json"
CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "curated_training_pairs.json"
DRY_RUN = "--dry-run" in sys.argv

BOOK_LANGS = {
    "coloquios_da_orta_1563": "pt",
    "historia_medicinal_monardes_1574": "es",
    "ricettario_fiorentino_1597": "it",
    "english_physician_1652": "en",
    "pseudodoxia_epidemica_browne_1646": "en",
    "polyanthea_medicinal": "pt",
    "relation_historique_humboldt_vol3_1825": "fr",
    "kosmos_humboldt_1845": "en",
    "connexion_physical_sciences_somerville_1858": "en",
    "origin_of_species_darwin_1859": "en",
    "first_principles_spencer_1862": "en",
    "principles_of_psychology_james_1890": "en",
}

BOOK_SHORT = {
    "coloquios_da_orta_1563": "Orta 1563",
    "historia_medicinal_monardes_1574": "Monardes 1574",
    "ricettario_fiorentino_1597": "Ricettario 1597",
    "english_physician_1652": "Culpeper 1652",
    "pseudodoxia_epidemica_browne_1646": "Browne 1646",
    "polyanthea_medicinal": "Semedo 1741",
    "relation_historique_humboldt_vol3_1825": "Humboldt 1825",
    "kosmos_humboldt_1845": "Kosmos 1845",
    "connexion_physical_sciences_somerville_1858": "Somerville 1858",
    "origin_of_species_darwin_1859": "Darwin 1859",
    "first_principles_spencer_1862": "Spencer 1862",
    "principles_of_psychology_james_1890": "James 1890",
}

# ── Clusters to BLOCK entirely (known bad from audit) ──
BLOCKED_CLUSTERS = {
    "consciousness",      # 49 monolingual en-en phrase variants
    "crusados",           # Conflates currency, crucibles, crosses, stars
    "Chapter X.",         # Chapter headings, not entities
    "Man",                # Conflates human + manatee
    "Sapa",               # Conflates grape must, soap, sap, toads
    "gallica",            # Conflates syphilis with Welsh/Irish language terms
    "milagre",            # Conflates miracle, magical, mirage
    "nardirt",            # OCR garble conflated with coconut
    "round",              # Matched to fitness magazine
    "Fascination",        # Matched to TV show
    "Pulp",               # Matched to Pulp Fiction
    "Hayhay",             # Wrong geographic match
    "Falattouaroc",       # OCR artifact
    "comer",              # Matched to ALF TV show
    "Reyes",              # Village name conflated with "kingdom"
    "Capricorn",          # Conflates zodiac sign, tropic, and Scorpio
    "Centuria",           # Conflates book numbering with Alpha Centauri
    "a Centauri",         # Conflates star with mythological centaurs
    "alpha Centauri",     # Bad cluster
    "hakims",             # Conflates physicians with judges
    "vino caliente",      # Too transparent
    "Lisbon",             # Conflates city with castle
}

# ── Specific BAD PAIRS to exclude (from audit) ──
BLOCKED_PAIRS = {
    # Wrong matches found in audit
    ("agua hydroptica", "cooled water"),
    ("reyes", "kingdom"),
    ("gale-irlandois", "french disease"),
    ("a. du centaure", "centuria"),
    ("capi", "maidenhair fern"),
    ("milagre", "magical"),
    ("nardirt", "coconut"),
    ("archiac, m. de", "arcet, m. d'"),
    ("petit", "claude-louis mathieu"),
    ("alph. de candolle", "augustin pyramus de candolle"),
    ("polonia", "bologna"),
    ("teguiza", "isthmus of tehuantepec"),
    ("ochotzk", "oltzow"),
    ("manatee", "human"),
    ("manatee", "human race"),
    ("lepidosteus", "lungfish"),
    ("venery", "transit of venus"),
    ("catarros", "ciatica"),
    ("dores da madre", "pain"),
    ("sanguinha", "sangria"),
    ("croco indiaco", "croco"),
}


def normalize(s):
    return s.strip().lower()


def is_transparent_cognate(source, target):
    """Check if pair is a trivially transparent cognate translation."""
    s, t = normalize(source), normalize(target)
    # Same first 4+ chars and similar length = likely cognate
    if len(s) >= 4 and len(t) >= 4:
        if s[:4] == t[:4] and abs(len(s) - len(t)) <= 3:
            return True
    # Multi-word where most words are cognates
    s_words = s.split()
    t_words = t.split()
    if len(s_words) >= 2 and len(t_words) >= 2 and len(s_words) == len(t_words):
        cognate_count = sum(1 for sw, tw in zip(s_words, t_words)
                          if sw[:3] == tw[:3])
        if cognate_count >= len(s_words) - 1:
            return True
    return False


def has_ocr_garbage(name):
    """Check if name looks like OCR garbage."""
    # High ratio of non-alpha chars
    alpha = sum(1 for c in name if c.isalpha())
    if len(name) > 0 and alpha / len(name) < 0.6:
        return True
    # Contains obvious OCR artifacts
    if any(x in name for x in ['ſ', '­', '¬']):
        # These are common in historical texts — not garbage per se
        # but skip if combined with other issues
        pass
    return False


def filter_v3_positives(v3_data):
    """Filter v3 positive pairs using blocklists and quality heuristics."""
    kept = []
    removed_reasons = defaultdict(int)

    for cat, cat_data in v3_data.get("categories", {}).items():
        for pair in cat_data.get("positive_pairs", []):
            source = pair["source"]
            target = pair["target"]
            note = pair.get("note", "")

            # Extract cluster name from note
            cluster = ""
            m = re.search(r"from '([^']+)'", note)
            if m:
                cluster = m.group(1)

            # Check blocked cluster
            if cluster in BLOCKED_CLUSTERS:
                removed_reasons[f"blocked cluster: {cluster}"] += 1
                continue

            # Check blocked pair
            key = (normalize(source), normalize(target))
            rkey = (normalize(target), normalize(source))
            if key in BLOCKED_PAIRS or rkey in BLOCKED_PAIRS:
                removed_reasons["blocked pair"] += 1
                continue

            # Skip transparent cognates
            if is_transparent_cognate(source, target):
                removed_reasons["transparent cognate"] += 1
                continue

            # Skip if either name is OCR garbage
            if has_ocr_garbage(source) or has_ocr_garbage(target):
                removed_reasons["OCR garbage"] += 1
                continue

            # Skip same-language pairs that are just morphological variants
            langs = pair.get("langs", "")
            if langs in ("en-en", "pt-pt", "es-es", "it-it", "fr-fr"):
                # Only keep if they're genuinely different forms
                if pair.get("score", 0) < 1.0:
                    removed_reasons["low-value same-language"] += 1
                    continue

            pair["category"] = cat
            pair["cluster"] = cluster
            kept.append(pair)

    print(f"\nFiltering results:")
    print(f"  Kept: {len(kept)}")
    for reason, count in sorted(removed_reasons.items(), key=lambda x: -x[1]):
        print(f"  Removed ({reason}): {count}")

    return kept


def mine_curated_pairs_from_concordance(concordance):
    """
    Directly mine the best cross-lingual pairs from high-quality clusters.
    These are hand-picked cluster types where I know the matches are good.
    """
    clusters = concordance["clusters"]
    by_name = {c["canonical_name"]: c for c in clusters}

    extra_pairs = []

    # Target the linguistically richest clusters for direct mining
    PRIORITY_CLUSTERS = [
        # Geography — these are reliably correct across languages
        "Allemagne", "Egypto", "Veneza", "grego", "Roma", "France",
        "Italie", "China", "Pologne", "Russie", "Antilles",
        "Persia", "Tartaria", "Japão",
        # Diseases — rich cross-lingual medical vocabulary
        "febre", "Paralyticos", "Hydropesia", "melancholia", "Gout",
        "epilepsia", "ictericia", "Lepra", "peste", "podagra",
        # Substances — key materia medica
        "porcelana", "humores", "sangue", "opio", "vinagre",
        "canfora", "alcanfor", "mercurio", "chumbo",
        # Plants — core botanical vocabulary
        "oliveira", "folhas", "canela", "pimenta", "gengibre",
        "açafrão", "aloés", "ruibarbo", "tamarindo",
        # Animals
        "horse", "Scorpio", "ovo", "duck", "elefante",
        # Concepts
        "purga", "experiment", "crystallization",
        # Anatomy
        "brain", "estomago",
    ]

    seen = set()
    for cname in PRIORITY_CLUSTERS:
        if cname not in by_name:
            continue
        cluster = by_name[cname]
        if cname in BLOCKED_CLUSTERS:
            continue

        gt = cluster.get("ground_truth", {})
        category = cluster["category"]
        members = cluster.get("members", [])
        modern = gt.get("modern_name", "")

        # Collect unique name/lang pairs
        info = []
        seen_names = set()
        for m in members:
            name = m["name"]
            lang = BOOK_LANGS.get(m["book_id"], "??")
            n = normalize(name)
            if n not in seen_names and len(name.strip()) >= 3:
                seen_names.add(n)
                info.append({"name": name, "lang": lang, "book": m["book_id"]})

        if modern and normalize(modern) not in seen_names and len(modern) >= 3:
            info.append({"name": modern, "lang": "en", "book": "_gt"})
            seen_names.add(normalize(modern))

        # Generate cross-language pairs, prioritizing max language distance
        for a, b in combinations(info, 2):
            if a["book"] == b["book"]:
                continue
            if a["lang"] == b["lang"]:
                continue  # Only cross-lingual for priority clusters

            key = tuple(sorted([normalize(a["name"]), normalize(b["name"])]))
            if key in seen or key[0] == key[1]:
                continue
            if is_transparent_cognate(a["name"], b["name"]):
                continue
            seen.add(key)

            extra_pairs.append({
                "source": a["name"],
                "target": b["name"],
                "category": category,
                "langs": f"{a['lang']}-{b['lang']}",
                "score": 1.0,  # Priority cluster pairs are high quality
                "cluster": cname,
                "origin": "priority_mined",
                "note": f"priority cluster '{cname}'"
            })

    return extra_pairs


def build_hard_negatives():
    """
    Hand-crafted hard negatives based on domain knowledge.

    These are pairs that look similar or share roots but are genuinely
    different entities. They represent the exact kind of confusion the
    model needs to learn to avoid.
    """
    negatives = [
        # ── Surface-similar, semantically different ──
        # Geographic confusables
        {"source": "Castella", "target": "Castille", "category": "PLACE",
         "reasoning": "Castella (Orta, refers to Castile) vs Castille (French spelling) — actually same, SKIP"},
        {"source": "Thames", "target": "Thales", "category": "PLACE/PERSON",
         "reasoning": "River in England vs ancient Greek philosopher"},
        {"source": "Corte", "target": "Corée", "category": "PLACE",
         "reasoning": "Portuguese 'court' vs French 'Korea'"},
        {"source": "Samarcanda", "target": "Samarang", "category": "PLACE",
         "reasoning": "Samarkand (Central Asia) vs Semarang (Java)"},
        {"source": "Cassiquiare", "target": "Cassiopeia", "category": "PLACE/OBJECT",
         "reasoning": "River in Venezuela vs constellation"},
        {"source": "Jorullo", "target": "Jaurù", "category": "PLACE",
         "reasoning": "Volcano in Mexico vs river in Brazil"},
        {"source": "Siara", "target": "Syra", "category": "PLACE",
         "reasoning": "Ceará (Brazil) vs Syros (Greek island)"},
        {"source": "Georgia", "target": "Géorgie", "category": "PLACE",
         "reasoning": "US state vs French name — actually same concept, SKIP"},
        {"source": "Java", "target": "Japon", "category": "PLACE",
         "reasoning": "Indonesian island vs Japan"},
        {"source": "Lima", "target": "Limon", "category": "PLACE/PLANT",
         "reasoning": "Capital of Peru vs lemon fruit"},
        {"source": "Chile", "target": "China", "category": "PLACE",
         "reasoning": "South American country vs East Asian country"},
        {"source": "Persia", "target": "Prussia", "category": "PLACE",
         "reasoning": "Iran vs German state"},
        {"source": "Bologna", "target": "Polonia", "category": "PLACE",
         "reasoning": "Italian city vs Poland"},

        # Person confusables
        {"source": "Vespucci", "target": "Vespasian", "category": "PERSON",
         "reasoning": "Explorer Amerigo Vespucci vs Roman emperor"},
        {"source": "Galeno", "target": "Galileo", "category": "PERSON",
         "reasoning": "Galen (physician) vs Galileo (astronomer)"},
        {"source": "Plinio", "target": "Plotinus", "category": "PERSON",
         "reasoning": "Pliny the Elder (naturalist) vs Plotinus (philosopher)"},
        {"source": "Seneca", "target": "Semedo", "category": "PERSON",
         "reasoning": "Roman philosopher vs Portuguese physician João Curvo Semedo"},
        {"source": "Avicena", "target": "Averroes", "category": "PERSON",
         "reasoning": "Ibn Sina (physician) vs Ibn Rushd (philosopher) — both Islamic scholars but different people"},
        {"source": "Scaliger", "target": "Scheele", "category": "PERSON",
         "reasoning": "Julius Caesar Scaliger (humanist) vs Carl Wilhelm Scheele (chemist)"},
        {"source": "Augustin Pyramus de Candolle", "target": "Alph. de Candolle", "category": "PERSON",
         "reasoning": "Father (botanist, d.1841) vs son (botanist, d.1893) — different people"},

        # Substance/plant confusables
        {"source": "canela", "target": "canola", "category": "SUBSTANCE",
         "reasoning": "Cinnamon vs rapeseed oil"},
        {"source": "sangria", "target": "purga", "category": "CONCEPT",
         "reasoning": "Bloodletting vs purging — different therapeutic practices"},
        {"source": "alcanfor", "target": "alcanço", "category": "SUBSTANCE",
         "reasoning": "Camphor vs attainment/reach"},
        {"source": "aguardiente", "target": "agua", "category": "SUBSTANCE",
         "reasoning": "Distilled spirit vs water — share root but different substances"},
        {"source": "opio", "target": "oleo", "category": "SUBSTANCE",
         "reasoning": "Opium vs oil"},
        {"source": "chumbo", "target": "chuva", "category": "SUBSTANCE",
         "reasoning": "Lead (metal) vs rain"},
        {"source": "plumbago", "target": "plumbea", "category": "SUBSTANCE",
         "reasoning": "Graphite vs lead-colored — different substances"},
        {"source": "mosses", "target": "Mochi", "category": "PLANT",
         "reasoning": "Bryophyte plants vs Japanese rice cake"},
        {"source": "gengibre", "target": "genebra", "category": "PLANT/PLACE",
         "reasoning": "Ginger vs Geneva (or juniper/gin)"},

        # Disease confusables
        {"source": "podagra", "target": "pellagra", "category": "DISEASE",
         "reasoning": "Gout (of the foot) vs pellagra (niacin deficiency)"},
        {"source": "epilepsia", "target": "erisipela", "category": "DISEASE",
         "reasoning": "Epilepsy vs erysipelas (skin infection)"},
        {"source": "ictericia", "target": "idropisia", "category": "DISEASE",
         "reasoning": "Jaundice vs dropsy — different conditions with similar-looking names"},
        {"source": "febre", "target": "lepra", "category": "DISEASE",
         "reasoning": "Fever vs leprosy"},
        {"source": "peste", "target": "posta", "category": "DISEASE/CONCEPT",
         "reasoning": "Plague vs mail/post"},
        {"source": "malaria", "target": "melancholia", "category": "DISEASE",
         "reasoning": "Mosquito-borne disease vs mental condition — both 'mal-' prefix"},
        {"source": "scurvy", "target": "scrofula", "category": "DISEASE",
         "reasoning": "Vitamin C deficiency vs tuberculosis of lymph nodes"},

        # Concept confusables
        {"source": "retentissement", "target": "Retentive", "category": "CONCEPT",
         "reasoning": "French 'reverberation/echo' vs English 'holding/keeping'"},
        {"source": "creation", "target": "correlation", "category": "CONCEPT",
         "reasoning": "Making something new vs statistical relationship"},
        {"source": "evolution", "target": "revolution", "category": "CONCEPT",
         "reasoning": "Gradual change vs sudden overthrow"},
        {"source": "digestion", "target": "distillation", "category": "CONCEPT",
         "reasoning": "Biological process vs chemical separation"},
        {"source": "composition", "target": "decomposition", "category": "CONCEPT",
         "reasoning": "Putting together vs breaking apart — antonyms"},

        # Animal confusables
        {"source": "sparrow", "target": "Archaeopteryx", "category": "ANIMAL",
         "reasoning": "Modern bird vs extinct dinosaur-bird"},
        {"source": "Leaõ", "target": "Leech", "category": "ANIMAL",
         "reasoning": "Portuguese 'lion' vs English 'leech'"},
        {"source": "cavallo", "target": "cavalo marinho", "category": "ANIMAL",
         "reasoning": "Horse vs seahorse — the 'marinho' makes it a completely different animal"},
        {"source": "elefante", "target": "elegante", "category": "ANIMAL/CONCEPT",
         "reasoning": "Elephant vs elegant"},

        # Object confusables
        {"source": "Horn-Church", "target": "Horn", "category": "OBJECT/PLACE",
         "reasoning": "Hornchurch (place in Essex) vs horn (object/animal part)"},
        {"source": "telescope", "target": "telegraph", "category": "OBJECT",
         "reasoning": "Optical instrument vs communication device — both 'tele-' prefix"},
        {"source": "barometer", "target": "thermometer", "category": "OBJECT",
         "reasoning": "Measures pressure vs measures temperature"},

        # ── More geographic confusables ──
        {"source": "Quito", "target": "Kyoto", "category": "PLACE",
         "reasoning": "Capital of Ecuador vs Japanese city"},
        {"source": "Madeira", "target": "Madera", "category": "PLACE",
         "reasoning": "Portuguese island vs Spanish word for wood — often confused"},
        {"source": "Malabar", "target": "Malacca", "category": "PLACE",
         "reasoning": "Coast of SW India vs strait/city in Malaysia"},
        {"source": "Bengala", "target": "Bengal", "category": "PLACE",
         "reasoning": "Actually same — SKIP"},
        {"source": "Ceylão", "target": "Ceilán", "category": "PLACE",
         "reasoning": "Actually same (Ceylon) — SKIP"},
        {"source": "Andes", "target": "Antilles", "category": "PLACE",
         "reasoning": "Mountain range in South America vs Caribbean islands"},
        {"source": "Mar Vermelho", "target": "Mar Morto", "category": "PLACE",
         "reasoning": "Red Sea vs Dead Sea — both 'Mar' + color/quality"},
        {"source": "Nilo", "target": "Niger", "category": "PLACE",
         "reasoning": "Nile River vs Niger River — different African rivers"},
        {"source": "Borneo", "target": "Bornéo", "category": "PLACE",
         "reasoning": "Actually same — SKIP"},
        {"source": "Sumatra", "target": "Siam", "category": "PLACE",
         "reasoning": "Indonesian island vs Thailand"},
        {"source": "Goa", "target": "Goya", "category": "PLACE/PERSON",
         "reasoning": "Portuguese India vs Spanish painter"},
        {"source": "Caledonia", "target": "California", "category": "PLACE",
         "reasoning": "Scotland vs US state"},
        {"source": "Cuzco", "target": "Cusco", "category": "PLACE",
         "reasoning": "Actually same — SKIP"},
        {"source": "Arabia", "target": "Aragon", "category": "PLACE",
         "reasoning": "Peninsula in Middle East vs Spanish kingdom"},
        {"source": "Tartaria", "target": "Tartaro", "category": "PLACE/SUBSTANCE",
         "reasoning": "Central Asian region vs tartar (chemical deposit)"},
        {"source": "Hispaniola", "target": "Hispania", "category": "PLACE",
         "reasoning": "Caribbean island vs Iberian Peninsula"},
        {"source": "Strasbourg", "target": "St. Petersburg", "category": "PLACE",
         "reasoning": "French/German city vs Russian capital"},

        # ── More substance/plant confusables ──
        {"source": "canfora", "target": "canela", "category": "SUBSTANCE",
         "reasoning": "Camphor vs cinnamon — both 'can-' prefix, different substances"},
        {"source": "ruibarbo", "target": "rabão", "category": "PLANT",
         "reasoning": "Rhubarb vs radish — both root vegetables, different species"},
        {"source": "tamarindo", "target": "tamarix", "category": "PLANT",
         "reasoning": "Tamarind tree vs tamarisk shrub — similar names, different species"},
        {"source": "aloés", "target": "alecrim", "category": "PLANT",
         "reasoning": "Aloe vs rosemary — both medicinal plants, 'ale-' prefix"},
        {"source": "açafrão", "target": "açúcar", "category": "SUBSTANCE",
         "reasoning": "Saffron vs sugar — both valuable commodities, 'aça-' prefix"},
        {"source": "pimenta", "target": "pimienta", "category": "PLANT",
         "reasoning": "Actually same (pepper, pt vs es) — SKIP"},
        {"source": "coral", "target": "copal", "category": "SUBSTANCE",
         "reasoning": "Marine organism vs tree resin"},
        {"source": "benjoim", "target": "bezoar", "category": "SUBSTANCE",
         "reasoning": "Benzoin resin vs bezoar stone — both from Arabic, different substances"},
        {"source": "mirra", "target": "mirto", "category": "SUBSTANCE/PLANT",
         "reasoning": "Myrrh (resin) vs myrtle (shrub)"},
        {"source": "opium", "target": "oleum", "category": "SUBSTANCE",
         "reasoning": "Narcotic latex vs oil"},
        {"source": "vitriolo", "target": "vitreo", "category": "SUBSTANCE",
         "reasoning": "Sulfuric acid compound vs glassy/vitreous"},
        {"source": "antimonio", "target": "amonio", "category": "SUBSTANCE",
         "reasoning": "Antimony (metalloid) vs ammonium (nitrogen compound)"},
        {"source": "sal ammoniac", "target": "sal gemma", "category": "SUBSTANCE",
         "reasoning": "Ammonium chloride vs rock salt — both 'sal' but different chemicals"},
        {"source": "mercurio", "target": "Mercury", "category": "SUBSTANCE/PERSON",
         "reasoning": "Actually same — SKIP"},
        {"source": "incenso", "target": "innocente", "category": "SUBSTANCE/CONCEPT",
         "reasoning": "Frankincense vs innocent"},

        # ── More disease confusables ──
        {"source": "pleurisia", "target": "paralisia", "category": "DISEASE",
         "reasoning": "Pleurisy (lung inflammation) vs paralysis"},
        {"source": "cólica", "target": "colirio", "category": "DISEASE/SUBSTANCE",
         "reasoning": "Intestinal pain vs eye drops"},
        {"source": "variola", "target": "varicela", "category": "DISEASE",
         "reasoning": "Smallpox vs chickenpox — related but distinct diseases"},
        {"source": "tísica", "target": "típica", "category": "DISEASE/CONCEPT",
         "reasoning": "Tuberculosis/consumption vs typical"},
        {"source": "angina", "target": "anguia", "category": "DISEASE/ANIMAL",
         "reasoning": "Throat infection/chest pain vs eel"},
        {"source": "catarata", "target": "catarro", "category": "DISEASE",
         "reasoning": "Eye condition (cataract) vs respiratory congestion (catarrh)"},

        # ── More concept confusables ──
        {"source": "fermentação", "target": "fomentação", "category": "CONCEPT",
         "reasoning": "Fermentation (chemical process) vs fomentation (warm compress application)"},
        {"source": "putrefação", "target": "purificação", "category": "CONCEPT",
         "reasoning": "Rotting vs purifying — opposite processes"},
        {"source": "atracção", "target": "abstracção", "category": "CONCEPT",
         "reasoning": "Attraction (physical force) vs abstraction (mental process)"},
        {"source": "sensação", "target": "sensibilidade", "category": "CONCEPT",
         "reasoning": "Sensation (individual feeling) vs sensibility (capacity to feel) — related but distinct"},
        {"source": "electricidade", "target": "elasticidade", "category": "CONCEPT",
         "reasoning": "Electricity vs elasticity — both physical properties, 'el-' prefix"},
        {"source": "gravidade", "target": "gravidez", "category": "CONCEPT",
         "reasoning": "Gravity vs pregnancy — both from Latin 'gravis'"},

        # ── More person confusables ──
        {"source": "Aristoteles", "target": "Aristophanes", "category": "PERSON",
         "reasoning": "Philosopher vs playwright — both ancient Greek 'Aristo-'"},
        {"source": "Dioscórides", "target": "Demócrito", "category": "PERSON",
         "reasoning": "Pharmacologist vs philosopher — both ancient Greek 'D-'"},
        {"source": "Humboldt", "target": "Helmholtz", "category": "PERSON",
         "reasoning": "Alexander von Humboldt (naturalist) vs Hermann von Helmholtz (physicist)"},
        {"source": "Lamarck", "target": "Laplace", "category": "PERSON",
         "reasoning": "Evolutionary biologist vs mathematician/astronomer"},
        {"source": "Cuvier", "target": "Culpeper", "category": "PERSON",
         "reasoning": "French naturalist vs English herbalist"},
        {"source": "Linnaeus", "target": "Lyell", "category": "PERSON",
         "reasoning": "Botanist/taxonomist vs geologist"},
        {"source": "Buffon", "target": "Button", "category": "PERSON/OBJECT",
         "reasoning": "French naturalist vs fastening device"},
    ]

    # Filter out the ones I marked as SKIP
    return [n for n in negatives if "SKIP" not in n.get("reasoning", "")]


def main():
    print("Loading v3 pairs...")
    with open(V3_PATH) as f:
        v3_data = json.load(f)

    print("Loading concordance...")
    with open(CONCORDANCE_PATH) as f:
        concordance = json.load(f)

    # 1. Filter v3 positives
    print("\n=== Filtering v3 positives ===")
    filtered_pos = filter_v3_positives(v3_data)

    # 2. Mine priority clusters
    print("\n=== Mining priority clusters ===")
    priority_pairs = mine_curated_pairs_from_concordance(concordance)
    print(f"  {len(priority_pairs)} pairs from priority clusters")

    # 3. Merge, dedup, take top ~800
    seen = set()
    all_pos = []
    for p in filtered_pos:
        key = tuple(sorted([normalize(p["source"]), normalize(p["target"])]))
        if key not in seen and key[0] != key[1]:
            seen.add(key)
            all_pos.append(p)
    for p in priority_pairs:
        key = tuple(sorted([normalize(p["source"]), normalize(p["target"])]))
        if key not in seen:
            seen.add(key)
            all_pos.append(p)

    # Sort by score
    all_pos.sort(key=lambda p: p.get("score", 0), reverse=True)

    # Take top 800
    selected = all_pos[:800]

    print(f"\n=== Final positive selection: {len(selected)} ===")
    cat_counts = defaultdict(int)
    lang_counts = defaultdict(int)
    for p in selected:
        cat_counts[p["category"]] += 1
        lang_counts[p.get("langs", "??")] += 1
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")
    print(f"\nTop language pairs:")
    for lp, n in sorted(lang_counts.items(), key=lambda x: -x[1])[:8]:
        print(f"  {lp}: {n}")

    # 4. Build hard negatives
    print("\n=== Building hard negatives ===")
    negatives = build_hard_negatives()
    print(f"  {len(negatives)} hand-crafted hard negatives")

    # 5. Build output in additive batch format
    batch = {
        "batch_id": "opus-2026-02-11-001",
        "contributor": "Claude Opus 4.6",
        "date": "2026-02-11",
        "notes": (
            "Initial curation from concordance. Filtered v3 extraction "
            "(removed ~20 blocked clusters, transparent cognates, OCR garbage, "
            "known bad pairs) + priority-mined pairs from richest cross-lingual "
            "clusters. Hand-crafted hard negatives from domain knowledge."
        ),
        "positive_pairs": [
            {
                "source": p["source"],
                "target": p["target"],
                "langs": p.get("langs", "??"),
                "category": p["category"],
                "cluster": p.get("cluster", ""),
                "score": p.get("score", 0),
            }
            for p in selected
        ],
        "hard_negatives": [
            {
                "source": n["source"],
                "target": n["target"],
                "category": n["category"],
                "reasoning": n["reasoning"],
            }
            for n in negatives
        ],
    }

    output = {
        "description": (
            "Curated training pairs for fine-tuning cross-lingual entity matching "
            "in early modern scientific texts (1500s-1890s). Additive format: each "
            "batch is independently contributed. Append new batches to train on more data."
        ),
        "format_version": "1.0",
        "instructions": (
            "To add pairs: append a new batch object to the 'batches' array with a "
            "unique batch_id. Do not modify existing batches. To exclude a pair from "
            "a previous batch, add it to an 'exclusions' list in your new batch. "
            "Positive pairs teach the model that source ↔ target are the same entity. "
            "Hard negatives teach it that source ≠ target despite surface similarity."
        ),
        "statistics": {
            "total_batches": 1,
            "total_positives": len(batch["positive_pairs"]),
            "total_negatives": len(batch["hard_negatives"]),
        },
        "batches": [batch],
    }

    print(f"\n{'='*60}")
    print(f"Output: {len(batch['positive_pairs'])} positives, {len(batch['hard_negatives'])} negatives")

    if DRY_RUN:
        print("\nDry run — not saving.")

        # Print sample
        print("\n--- Sample positives (every 40th) ---")
        for i in range(0, len(selected), 40):
            p = selected[i]
            print(f"  [{p.get('score',0):.2f}] {p['source']} ↔ {p['target']} ({p.get('langs','??')}) [{p['category']}] — {p.get('cluster','')}")

        print("\n--- Sample negatives (first 10) ---")
        for n in negatives[:10]:
            print(f"  {n['source']} ≠ {n['target']} [{n['category']}] — {n['reasoning']}")
        return

    print(f"\nSaving to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"  {size_kb:.0f} KB")
    print("Done!")


if __name__ == "__main__":
    main()

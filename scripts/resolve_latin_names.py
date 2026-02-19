#!/usr/bin/env python3
"""
Auto-resolve unresolved person names in the knowledge graph.

Strategy:
1. Try direct Wikipedia search for the name as-is
2. Try Latin suffix stripping (-us, -ius, -erus, -aeus) then search
3. Generate proposed additions to person_overrides.json for human review

Usage:
    python3 scripts/resolve_latin_names.py [--apply]
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
WEB_DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"

# Latin suffix patterns to strip, ordered by specificity
LATIN_SUFFIXES = [
    (r"erus$", "er"),      # Kircherus → Kircher
    (r"aeus$", "ae"),      # Linnaeus → Linnae (then search)
    (r"aeus$", ""),        # Linnaeus → Linn
    (r"ius$", ""),         # Fernelius → Fernel
    (r"ius$", "i"),        # Fernelius → Ferneli? (less common)
    (r"eus$", ""),         # Burnetus → Burnet? no, that's -etus
    (r"etus$", "et"),      # Burnetus → Burnet
    (r"atus$", "at"),      # Capivatius → Capivati? less useful
    (r"inus$", "in"),      # Solinus → Solin
    (r"anus$", "an"),      # Tralianus → Tralian
    (r"us$", ""),          # Gilbertus → Gilbert (most general, try last)
    (r"us$", "e"),         # Cabeus → Cabe? less useful
]

# Names that should be excluded (not real persons, or too generic)
SKIP_NAMES = {
    "ancients", "european", "romans", "egyptians", "astronomers",
    "physicists", "physiologists", "physiologist", "chemist",
    "savage", "translator", "astronomer", "angels", "devil",
    "satan", "christ", "saviour", "eve", "john", "moses",
    "austin",  # too ambiguous
}

# Known manual resolutions — domain knowledge for history of science figures
# None = skip (too obscure or not a real person)
KNOWN_RESOLUTIONS = {
    # === Browne's Pseudodoxia Epidemica (17th c. natural philosophy) ===
    "kircherus": "Athanasius_Kircher",
    "gilbertus": "William_Gilbert_(physicist)",
    "albertus": "Albertus_Magnus",
    "cabeus": "Niccolò_Cabeo",
    "scaliger": "Julius_Caesar_Scaliger",
    "solinus": "Gaius_Julius_Solinus",
    "porta": "Giambattista_della_Porta",
    "homer": "Homer",
    "ælian": "Claudius_Aelianus",
    "pythagoras": "Pythagoras",
    "moses": "Moses",

    # === Kosmos / Humboldt (19th c. geography & natural science) ===
    "herschel": "John_Herschel",
    "laplace": "Pierre-Simon_Laplace",
    "bessel": "Friedrich_Bessel",
    "darwin": "Charles_Darwin",
    "newton": "Isaac_Newton",
    "strabo": "Strabo",
    "beaumont": "Jean-Baptiste_Élie_de_Beaumont",
    "ehrenberg": "Christian_Gottfried_Ehrenberg",
    "olbers": "Heinrich_Wilhelm_Matthias_Olbers",
    "rose": "Gustav_Rose",
    "daubeney": "Charles_Daubeny",
    "plutarch": "Plutarch",
    "columbus": "Christopher_Columbus",
    "halley": "Edmond_Halley",
    "gilbert": "William_Gilbert_(physicist)",
    "madler": "Johann_Heinrich_von_Mädler",
    "seneca": "Seneca_the_Younger",
    "plato": "Plato",
    "encke": "Johann_Franz_Encke",
    "aristot": "Aristotle",
    "kepler": "Johannes_Kepler",
    "erman": "Georg_Adolf_Erman",
    "mantell": "Gideon_Mantell",
    "biot": "Jean-Baptiste_Biot",
    "poisson": "Siméon_Denis_Poisson",
    "bravais": "Auguste_Bravais",
    "bischof": "Gustav_Bischof",
    "kamtz": "Ludwig_Friedrich_Kämtz",
    "mitscherlich": "Eilhard_Mitscherlich",
    "dove": "Heinrich_Wilhelm_Dove",
    "schumacher": "Heinrich_Christian_Schumacher",
    "brandes": "Heinrich_Wilhelm_Brandes",
    "huygens": "Christiaan_Huygens",
    "wrangel": "Ferdinand_von_Wrangel",
    "hoffmann": "Friedrich_Hoffmann",
    "goppert": "Heinrich_Robert_Göppert",
    "dechen": "Ernst_Heinrich_Karl_von_Dechen",
    "varenius": "Bernhardus_Varenius",
    "cassini": "Giovanni_Domenico_Cassini",
    "faraday": "Michael_Faraday",
    "otte": None,  # translator, not notable enough

    # === Somerville (19th c. physical sciences) ===
    "fahrenheit": "Daniel_Gabriel_Fahrenheit",
    "brewster": "David_Brewster",
    "melloni": "Macedonio_Melloni",
    "wheatstone": "Charles_Wheatstone",
    "airy": "George_Biddell_Airy",
    "becquerel": "Antoine_César_Becquerel",
    "ptolemy": "Ptolemy",
    "fraunhofer": "Joseph_von_Fraunhofer",
    "fresnel": "Augustin-Jean_Fresnel",
    "joule": "James_Prescott_Joule",
    "davy": "Humphry_Davy",
    "argelander": "Friedrich_Wilhelm_August_Argelander",
    "rosse": "William_Parsons,_3rd_Earl_of_Rosse",
    "ampere": "André-Marie_Ampère",
    "struve": "Friedrich_Georg_Wilhelm_von_Struve",
    "thomson": "William_Thomson,_1st_Baron_Kelvin",
    "niepce": "Nicéphore_Niépce",
    "messier": "Charles_Messier",
    "biela": "Wilhelm_von_Biela",
    "faye": "Hervé_Faye",
    "adams": "John_Couch_Adams",
    "secchi": "Angelo_Secchi",
    "matteucci": "Carlo_Matteucci",
    "henderson": "Thomas_Henderson_(astronomer)",
    "savart": "Félix_Savart",
    "peters": "Christian_Heinrich_Friedrich_Peters",
    "grove": "William_Robert_Grove",
    "hind": "John_Russell_Hind",
    "hunt": "Robert_Hunt_(scientist)",
    "young": "Thomas_Young_(scientist)",
    "ritter": "Carl_Ritter",
    "moser": "Ludwig_Moser",
    "mossotti": "Ottaviano-Fabrizio_Mossotti",
    "plateau": "Joseph_Plateau",
    "draper": "John_William_Draper",
    "pouillet": "Claude_Pouillet",
    "powell": "Baden_Powell_(mathematician)",
    "fox": "Robert_Were_Fox_the_Younger",
    "place": "Pierre-Simon_Laplace",
    "grange": "Joseph-Louis_Lagrange",
    "verrier": "Urbain_Le_Verrier",

    # === Spencer (19th c. philosophy) ===
    "mansel": "Henry_Longueville_Mansel",
    "tyndall": "John_Tyndall",
    "boscovich": "Roger_Joseph_Boscovich",

    # === Polyanthea Medicinal (17th c. Portuguese medicine) ===
    "vanelmonte": "Jan_Baptist_van_Helmont",
    "altomari": "Donato_Antonio_de_Altomari",
    "burnetus": "Thomas_Burnet",
    "augenius": "Horace_Augenii",
    "vidus": "Vidus_Vidius",
    "borelus": "Pierre_Borel",
    "poterius": None,  # Pedro Poterio — Portuguese physician, not in Wikipedia
    "tralianus": "Alexander_of_Tralles",
    "hartmanus": None,  # Johann Hartmann? Too ambiguous
    "celfus": "Aulus_Cornelius_Celsus",
    "senense": "Pietro_Andrea_Mattioli",

    # === Colóquios / Orta ===
    "fliickiger": "Friedrich_August_Flückiger",
    "menardo": None,  # Menardo — 16th c. commentator, not in Wikipedia
    "lisboa": None,  # It's a place, not a person

    # === Humboldt's Relation historique ===
    "mart": "Peter_Martyr_d%27Anghiera",
    "malasp": "Alessandro_Malaspina",
    "espinosa": None,  # Too many Espinosas; ambiguous in this context
    "caulin": None,  # Antonio Caulin — obscure friar/chronicler

    # === Too obscure or OCR artifacts ===
    "bumell": None,
    "perdulcis": None,
    "graanen": None,
    "zuvelf": None,
    "malheyro": None,
    "capivatius": None,
    "maroja": None,
    "angeja": None,
    "tschisch": None,
    "nizamoxa": None,  # Nizam of Ahmadnagar — could be resolved but niche
    "barcaiztegui": None,
    "florentino": None,
    "cileno": None,
}


def delatinize(name: str) -> list[str]:
    """Generate possible de-Latinized forms of a name."""
    candidates = []
    for pattern, replacement in LATIN_SUFFIXES:
        if re.search(pattern, name, re.IGNORECASE):
            stripped = re.sub(pattern, replacement, name, flags=re.IGNORECASE)
            if stripped and len(stripped) >= 3 and stripped != name:
                candidates.append(stripped)
    return candidates


def search_wikipedia(query: str) -> dict | None:
    """Search Wikipedia for a person. Returns {title, description, pageid} or None."""
    encoded = urllib.parse.quote(query)
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&srnamespace=0&srlimit=3&format=json"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PremodernConcordance/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = data.get("query", {}).get("search", [])
        if not results:
            return None

        # Return the top result
        top = results[0]
        return {
            "title": top["title"],
            "pageid": top["pageid"],
            "snippet": re.sub(r"<[^>]+>", "", top.get("snippet", "")),
        }
    except Exception as e:
        print(f"    Wikipedia search error for '{query}': {e}")
        return None


def is_person_article(title: str, snippet: str) -> bool:
    """Heuristic check if a Wikipedia result is about a person."""
    person_signals = [
        "born", "died", "was a", "were a", "philosopher", "scientist",
        "mathematician", "astronomer", "physician", "naturalist", "explorer",
        "scholar", "writer", "poet", "historian", "theologian", "bishop",
        "geologist", "chemist", "physicist", "botanist", "zoologist",
        "anatomist", "surgeon", "monk", "friar", "jesuit",
    ]
    snippet_lower = snippet.lower()
    return any(s in snippet_lower for s in person_signals)


def main():
    apply = "--apply" in sys.argv

    # Load data
    with open(WEB_DATA_DIR / "person_graphs.json") as f:
        pg = json.load(f)
    with open(DATA_DIR / "person_overrides.json") as f:
        overrides = json.load(f)

    identities_path = WEB_DATA_DIR / "person_identities.json"
    if identities_path.exists():
        with open(identities_path) as f:
            identities = json.load(f)
    else:
        identities = {}

    slugs = overrides["wikipedia_slugs"]
    aliases = overrides["aliases"]
    exclude = set(overrides["exclude"])

    # Find unresolved persons
    unresolved = {}
    for book_id, graph in pg.items():
        for node in graph["nodes"]:
            pid = node["id"]
            if pid in exclude or pid in SKIP_NAMES:
                continue
            canonical = aliases.get(pid, pid)
            if canonical in slugs or canonical in identities:
                continue
            if pid in slugs or pid in identities:
                continue
            if pid not in unresolved:
                unresolved[pid] = {"name": node["name"], "count": node["count"], "books": []}
            unresolved[pid]["books"].append(book_id)

    print(f"Found {len(unresolved)} unresolved person IDs\n")

    # Try to resolve each one
    proposed_slugs = {}
    proposed_aliases = {}
    proposed_exclude = []

    for pid, info in sorted(unresolved.items(), key=lambda x: -x[1]["count"]):
        if info["count"] < 3:
            continue

        name = info["name"]
        print(f"  {pid:20s} ({name}, count={info['count']})")

        # Check known manual resolutions first (domain knowledge > Wikipedia search)
        if pid in KNOWN_RESOLUTIONS:
            wiki_title = KNOWN_RESOLUTIONS[pid]
            if wiki_title is None:
                print(f"    → SKIP (too obscure / not a person)")
                proposed_exclude.append(pid)
                continue
            else:
                print(f"    → KNOWN: {wiki_title}")
                proposed_slugs[pid] = wiki_title
                continue

        # For names NOT in known resolutions, try Wikipedia search (results need human review)
        # Try direct Wikipedia search
        result = search_wikipedia(name)
        time.sleep(0.3)  # rate limit

        if result and is_person_article(result["title"], result["snippet"]):
            wiki_title = result["title"].replace(" ", "_")
            print(f"    → DIRECT: {result['title']} ({result['snippet'][:60]}...)")
            proposed_slugs[pid] = wiki_title
            continue

        # Try de-Latinized forms
        candidates = delatinize(pid)
        resolved = False
        for candidate in candidates:
            # Check if the stripped form is already in slugs
            if candidate in slugs:
                print(f"    → ALIAS: {pid} → {candidate} (already in slugs)")
                proposed_aliases[pid] = candidate
                resolved = True
                break

            # Try Wikipedia search with the stripped form
            result = search_wikipedia(candidate)
            time.sleep(0.3)
            if result and is_person_article(result["title"], result["snippet"]):
                wiki_title = result["title"].replace(" ", "_")
                print(f"    → DELATINIZED ({candidate}): {result['title']}")
                proposed_slugs[pid] = wiki_title
                resolved = True
                break

        if not resolved:
            # Try Wikipedia with "name + historian/scientist" etc.
            for suffix in ["scientist", "scholar", "philosopher"]:
                result = search_wikipedia(f"{name} {suffix}")
                time.sleep(0.3)
                if result and is_person_article(result["title"], result["snippet"]):
                    wiki_title = result["title"].replace(" ", "_")
                    print(f"    → QUALIFIED ({suffix}): {result['title']}")
                    proposed_slugs[pid] = wiki_title
                    resolved = True
                    break

            if not resolved:
                print(f"    → UNRESOLVED")

    # Summary
    print(f"\n{'='*60}")
    print(f"Proposed wikipedia_slugs additions: {len(proposed_slugs)}")
    for pid, slug in sorted(proposed_slugs.items()):
        print(f'    "{pid}": "{slug}",')

    print(f"\nProposed aliases additions: {len(proposed_aliases)}")
    for pid, canonical in sorted(proposed_aliases.items()):
        print(f'    "{pid}": "{canonical}",')

    print(f"\nProposed exclude additions: {len(proposed_exclude)}")
    for pid in sorted(proposed_exclude):
        print(f'    "{pid}",')

    print(f"\nTotal resolved: {len(proposed_slugs) + len(proposed_aliases)}")

    if apply and (proposed_slugs or proposed_aliases or proposed_exclude):
        print(f"\nApplying to {DATA_DIR / 'person_overrides.json'}...")
        overrides["wikipedia_slugs"].update(proposed_slugs)
        overrides["aliases"].update(proposed_aliases)
        overrides["exclude"].extend(proposed_exclude)
        # Deduplicate exclude list
        overrides["exclude"] = sorted(set(overrides["exclude"]))

        with open(DATA_DIR / "person_overrides.json", "w") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
        print("  Done!")
        print("\nNext step: run resolve_person_identities.py to download portraits and build identities")
    elif not apply:
        print("\nDry run. Use --apply to save changes.")


if __name__ == "__main__":
    main()

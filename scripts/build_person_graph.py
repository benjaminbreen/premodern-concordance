#!/usr/bin/env python3
"""
Build a co-citation person graph for each book.

For each book's entity file:
1. Extract PERSON entities (filtering generics)
2. Merge name variants by surname (Lyell / Sir C. Lyell / Sir Charles Lyell → Lyell)
3. Scan excerpts for co-mentions of other persons
4. Output a compact JSON with nodes + edges

Usage:
    python3 build_person_graph.py [--min-count 2] [--min-edge 1] [--top-n 60]
"""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
OUTPUT_DIR = DATA_DIR

# ── Name resolution ──────────────────────────────────────────────────────────

TITLE_PREFIXES = re.compile(
    r"^(Sir|Dr\.?|Mr\.?|Mrs\.?|Prof\.?|Professor|Rev\.?|Saint|St\.?|Herr|Señor|Dom)\s+",
    re.IGNORECASE,
)
INITIAL_PATTERN = re.compile(r"\b[A-Z]\.\s*")
PARTICLES = {"de", "da", "di", "von", "van", "del", "la", "le", "des", "du", "do", "dos"}

# OCR character normalization map
OCR_CHAR_MAP = str.maketrans({
    "ſ": "s",   # long s
    "ƒ": "f",   # script f
    "æ": "ae",
})

def normalize_ocr(text: str) -> str:
    """Normalize OCR artifacts and diacritics for comparison."""
    text = text.translate(OCR_CHAR_MAP).replace("ſ", "s")
    # Strip diacritics (â→a, è→e, ñ→n, etc.)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

# Generic PERSON entries to skip entirely (all lowercase, OCR-normalized)
GENERIC_PERSONS = {
    "naturalists", "naturalist", "progenitor", "women", "children", "man",
    "men", "physitians", "physicians", "apothecaries", "god", "patient",
    "patients", "author", "authors", "reader", "readers", "travellers",
    "breeders", "breeder", "gardeners", "gardener", "inhabitants",
    "savages", "natives", "slaves", "kings", "king", "queen", "prince",
    "experimenters", "experimenter", "collector", "collectors",
    "dr. reason", "mercury", "venus", "mars", "jupiter", "saturn", "sol",
    "moon", "sun", "doente", "doentes", "enfermo", "enfermos",
    "medico", "medicos", "boticario", "boticarios",
    # Titles/roles that get extracted as persons
    "professor", "professors", "doctor", "docters", "doctors",
    "husband", "wife", "father", "mother",
    "emperor", "empress", "princes", "princess", "senor", "maestro",
    "physitians", "auctores", "escribano", "efcriuano",
    # Group nouns (especially in Humboldt)
    "mulatres", "negres", "noirs", "blancs", "esclaves", "indiens",
    "creoles", "indigenes", "europeens", "missionnaires", "moines",
    "indios", "espanoles", "cristianos", "moros", "moro",
    "caribes", "caribs", "guayqueries",
    # Italian group nouns (Ricettario)
    "medici", "spetiali", "veditori", "consoli",
    # Portuguese group nouns
    "mouros", "gentios", "christaos", "judeos",
    # Ethnic/national group nouns
    "arabios", "arabes", "gregos", "griegos", "greci", "latini",
    "arabi", "anglois", "francois", "romains",
    # Additional group/role terms
    "rio", "reis", "capitao", "governador", "virrey", "obispo",
    # Abstract concepts / common nouns misidentified as persons
    "experience", "nature", "botanists", "botanist", "zoologists", "zoologist",
    "geologists", "geologist", "anatomists", "anatomist",
    "philosophers", "philosopher", "theologians", "theologian",
}

# Surname-level aliases to merge OCR variants of the same person
SURNAME_ALIASES = {
    "boneto": "bonet",       # Théophile Bonet
    "fabro": "fabr",         # Wilhelm Fabry → normalize to fabry below
    "lefand": "lefand",      # OCR noise, will be filtered by min length
}


def extract_surname(name: str) -> str:
    """Extract the key surname from a person name."""
    cleaned = TITLE_PREFIXES.sub("", name.strip())
    cleaned = INITIAL_PATTERN.sub("", cleaned).strip()
    # Remove trailing periods/commas
    cleaned = cleaned.rstrip(".,;:")
    # Normalize OCR characters
    cleaned = normalize_ocr(cleaned)

    parts = cleaned.split()
    if not parts:
        return name.lower().strip()

    # Filter particles to find the substantive surname
    substantive = [p for p in parts if p.lower() not in PARTICLES and len(p) > 1]
    if not substantive:
        return parts[-1].lower()

    # Take the last substantive word as surname
    surname = substantive[-1].lower().rstrip(".,;:")

    # Apply alias map for known OCR variants
    surname = SURNAME_ALIASES.get(surname, surname)
    return surname


def merge_persons(entities: list[dict], min_count: int = 2) -> list[dict]:
    """Group PERSON entities by surname, merge counts and excerpts."""
    # Filter to PERSON category, skip generics and low-count
    persons = []
    for e in entities:
        if e.get("category") != "PERSON":
            continue
        name_lower = normalize_ocr(e["name"].lower().strip())
        if name_lower in GENERIC_PERSONS:
            continue
        # Also check if the surname alone is generic
        surname = extract_surname(e["name"])
        if surname in GENERIC_PERSONS:
            continue
        # Skip names starting with non-alpha chars (OCR noise like ^, [, etc.)
        if e["name"] and not e["name"][0].isalpha():
            continue
        if e.get("subcategory") == "OTHER_PERSON":
            # Keep if count is high enough (might be a real person miscategorized)
            if e.get("count", 0) < 5:
                continue
        persons.append(e)

    # Group by surname
    surname_groups: dict[str, list[dict]] = defaultdict(list)
    for p in persons:
        key = extract_surname(p["name"])
        surname_groups[key].append(p)

    merged = []
    for surname, group in surname_groups.items():
        total_count = sum(e.get("count", 0) for e in group)
        if total_count < min_count:
            continue

        # Pick canonical name: prefer shortest non-initial form, or most common
        group.sort(key=lambda e: (-e.get("count", 0), len(e["name"])))
        canonical = group[0]["name"]
        # If canonical has initials/titles, try to find a cleaner one
        for e in group:
            name = e["name"]
            if not TITLE_PREFIXES.match(name) and not INITIAL_PATTERN.match(name):
                if len(name.split()) <= 2:
                    canonical = name
                    break

        aliases = sorted(set(e["name"] for e in group))
        all_variants = []
        for e in group:
            all_variants.extend(e.get("variants", []))
        all_variants = sorted(set(all_variants))

        # Collect all mentions
        all_mentions = []
        for e in group:
            all_mentions.extend(e.get("mentions", []))

        # Take most common subcategory
        sub_counts: dict[str, int] = defaultdict(int)
        for e in group:
            sc = e.get("subcategory", "OTHER_PERSON")
            sub_counts[sc] += e.get("count", 0)
        subcategory = max(sub_counts, key=lambda k: sub_counts[k])

        # Collect contexts
        all_contexts = []
        for e in group:
            all_contexts.extend(e.get("contexts", []))

        merged.append({
            "id": surname,
            "name": canonical,
            "aliases": aliases,
            "variants": all_variants,
            "count": total_count,
            "subcategory": subcategory,
            "contexts": all_contexts[:5],
            "mentions": all_mentions,
        })

    # Filter out entries with very short surnames or OCR noise in surname
    merged = [p for p in merged if len(p["id"]) >= 3 and p["id"].isalpha()]
    merged.sort(key=lambda p: -p["count"])
    return merged


# ── Co-citation extraction ───────────────────────────────────────────────────

def build_search_patterns(persons: list[dict]) -> list[tuple[str, re.Pattern]]:
    """Build regex patterns for finding person mentions in excerpts."""
    patterns = []
    for p in persons:
        # Collect all searchable name forms
        name_forms = set()
        name_forms.add(p["name"])
        name_forms.update(p["aliases"])
        # Add surname alone if it's distinctive (>= 4 chars)
        if len(p["id"]) >= 4:
            name_forms.add(p["id"].capitalize())
            name_forms.add(p["id"])

        # Add variants that look like person names (capitalized, > 3 chars)
        for v in p.get("variants", []):
            if len(v) > 3 and v[0].isupper():
                name_forms.add(v)

        # Build alternation pattern, longest first
        forms = sorted(name_forms, key=len, reverse=True)
        # Escape regex chars and require word boundaries
        escaped = [re.escape(f) for f in forms if len(f) > 2]
        if not escaped:
            continue
        pattern = re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)
        patterns.append((p["id"], pattern))

    return patterns


def find_co_citations(persons: list[dict], top_n: int = 60) -> list[dict]:
    """Scan excerpts to find co-occurring person mentions."""
    # Only use top N persons to keep it manageable
    top_persons = persons[:top_n]
    person_ids = {p["id"] for p in top_persons}
    patterns = build_search_patterns(top_persons)

    # Build a lookup from person_id to all their excerpt texts
    person_excerpts: dict[str, list[str]] = {}
    for p in top_persons:
        excerpts = [m["excerpt"] for m in p.get("mentions", []) if m.get("excerpt")]
        person_excerpts[p["id"]] = excerpts

    # For each person's excerpts, find which other persons are mentioned
    edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    edge_excerpts: dict[tuple[str, str], list[str]] = defaultdict(list)

    for person in top_persons:
        pid = person["id"]
        for excerpt in person_excerpts.get(pid, []):
            # Find all persons mentioned in this excerpt
            mentioned = set()
            for other_id, pattern in patterns:
                if other_id == pid:
                    continue
                if other_id not in person_ids:
                    continue
                if pattern.search(excerpt):
                    mentioned.add(other_id)

            # Create edges
            for other_id in mentioned:
                key = tuple(sorted([pid, other_id]))
                edge_counts[key] += 1
                if len(edge_excerpts[key]) < 3:
                    edge_excerpts[key].append(excerpt)

    edges = []
    for (src, tgt), count in sorted(edge_counts.items(), key=lambda x: -x[1]):
        edges.append({
            "source": src,
            "target": tgt,
            "weight": count,
            "excerpts": edge_excerpts[(src, tgt)],
        })

    return edges


# ── Main ─────────────────────────────────────────────────────────────────────

def process_book(filepath: Path, min_count: int, min_edge: int, top_n: int) -> dict | None:
    """Process a single book entity file into a person graph."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    book_info = data.get("book", {})
    entities = data.get("entities", [])
    book_id = book_info.get("id", filepath.stem)

    print(f"\n  Processing {book_info.get('title', book_id)}...")

    # Merge persons
    persons = merge_persons(entities, min_count=min_count)
    print(f"    {len(persons)} merged persons (from {sum(1 for e in entities if e.get('category') == 'PERSON')} raw)")

    if len(persons) < 2:
        print("    Skipping: too few persons")
        return None

    # Find co-citations
    edges = find_co_citations(persons, top_n=top_n)
    edges = [e for e in edges if e["weight"] >= min_edge]
    print(f"    {len(edges)} co-citation edges (min_weight={min_edge})")

    # Trim persons: only keep those that appear in at least one edge, or top 20 by count
    connected_ids = set()
    for e in edges:
        connected_ids.add(e["source"])
        connected_ids.add(e["target"])

    top_ids = {p["id"] for p in persons[:20]}
    keep_ids = connected_ids | top_ids

    # Build output nodes (strip mentions to save space)
    nodes = []
    for p in persons:
        if p["id"] not in keep_ids:
            continue
        nodes.append({
            "id": p["id"],
            "name": p["name"],
            "aliases": p["aliases"],
            "count": p["count"],
            "subcategory": p["subcategory"],
            "contexts": p["contexts"][:3],
        })

    print(f"    {len(nodes)} nodes in final graph")

    # Show top edges
    if edges:
        print(f"    Top edges:")
        for e in edges[:5]:
            print(f"      {e['source']} ↔ {e['target']}: {e['weight']}")

    return {
        "book_id": book_id,
        "book_title": book_info.get("title", ""),
        "book_author": book_info.get("author", ""),
        "book_year": book_info.get("year", 0),
        "nodes": nodes,
        "edges": edges,
    }


def main():
    parser = argparse.ArgumentParser(description="Build person co-citation graphs")
    parser.add_argument("--min-count", type=int, default=2,
                        help="Min mentions to include a person (default: 2)")
    parser.add_argument("--min-edge", type=int, default=1,
                        help="Min co-citations for an edge (default: 1)")
    parser.add_argument("--top-n", type=int, default=60,
                        help="Max persons to scan for co-citations (default: 60)")
    parser.add_argument("--book", type=str, default=None,
                        help="Process a single book (entity filename without .json)")
    args = parser.parse_args()

    entity_files = sorted(DATA_DIR.glob("*_entities.json"))
    if args.book:
        entity_files = [f for f in entity_files if args.book in f.name]

    if not entity_files:
        print("No entity files found in", DATA_DIR)
        return

    print(f"Found {len(entity_files)} entity files")

    all_graphs = {}
    for filepath in entity_files:
        result = process_book(filepath, args.min_count, args.min_edge, args.top_n)
        if result:
            all_graphs[result["book_id"]] = result

    # Write combined output
    output_path = OUTPUT_DIR / "person_graphs.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_graphs, f, ensure_ascii=False, indent=None)

    size_kb = output_path.stat().st_size / 1024
    print(f"\nSaved {len(all_graphs)} graphs to {output_path} ({size_kb:.0f} KB)")

    # Summary
    print("\nSummary:")
    for book_id, g in all_graphs.items():
        print(f"  {g['book_title']}: {len(g['nodes'])} persons, {len(g['edges'])} edges")


if __name__ == "__main__":
    main()

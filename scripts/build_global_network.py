#!/usr/bin/env python3
"""
Build a global cross-book person network from concordance data.

Nodes = PERSON clusters appearing in 2+ books.
Edges = two persons share an edge if they both appear in the same book.
Weight = number of shared books.

Usage:
    python3 scripts/build_global_network.py
"""

import json
from collections import defaultdict
from pathlib import Path

WEB_DATA = Path(__file__).parent.parent / "web" / "public" / "data"

# Maps book_id -> person identity_id for corpus authors
CORPUS_AUTHOR_IDS = {
    "origin_of_species_darwin_1859": "darwin",
    "relation_historique_humboldt_vol3_1825": "humboldt",
    "kosmos_humboldt_1845": "humboldt",
    "first_principles_spencer_1862": "spencer",
    "principles_of_psychology_james_1890": "james",
    "historia_medicinal_monardes_1574": "monardes",
    "connexion_physical_sciences_somerville_1858": "somerville",
    "pseudodoxia_epidemica_browne_1646": "browne",
    "coloquios_da_orta_1563": "orta",
    "english_physician_1652": "culpeper",
    "polyanthea_medicinal": "semedo",
    "ricettario_fiorentino_1597": None,  # Collegio Medico, not a person
}

# Generic PERSON clusters to skip (not real individuals)
SKIP_NAMES = {
    "god", "physician", "individuals", "romans", "greeks", "latins",
    "author", "soldier", "ancient egyptians", "patient", "philosophers",
    "naturalists", "children", "slave", "nurses",
}


def main():
    print("Loading data...")
    with open(WEB_DATA / "concordance.json") as f:
        data = json.load(f)

    identities = {}
    ident_path = WEB_DATA / "person_identities.json"
    if ident_path.exists():
        with open(ident_path) as f:
            identities = json.load(f)

    clusters = data["clusters"]
    books = data["books"]
    book_ids = {b["id"] for b in books}

    # Reverse lookup: identity_id -> set of book_ids where they're corpus author
    author_books = defaultdict(list)
    for bid, iid in CORPUS_AUTHOR_IDS.items():
        if iid:
            author_books[iid].append(bid)

    # Filter to PERSON clusters with book_count >= 3
    person_clusters = []
    for c in clusters:
        if c["category"] != "PERSON" or c["book_count"] < 3:
            continue
        name = (c.get("ground_truth", {}).get("modern_name") or c["canonical_name"]).lower()
        if name in SKIP_NAMES:
            continue
        person_clusters.append(c)

    print(f"  {len(person_clusters)} person clusters with 2+ books")

    # Build nodes
    nodes = []
    node_books = {}  # cluster_id -> set of book_ids

    for c in person_clusters:
        gt = c.get("ground_truth") or {}
        display_name = gt.get("modern_name") or c["canonical_name"]
        member_books = sorted(set(m["book_id"] for m in c["members"]))
        node_books[c["id"]] = set(member_books)

        # Try to find identity_id by matching against person_identities keys
        identity_id = None
        # Try canonical name lowercase as ID
        cname_lower = c["canonical_name"].lower().split()[-1]  # surname
        if cname_lower in identities:
            identity_id = cname_lower
        # Try member entity_ids
        if not identity_id:
            for m in c["members"]:
                eid = m["entity_id"]
                if eid in identities:
                    identity_id = eid
                    break

        # Check corpus author status
        is_corpus_author = False
        author_of = []
        if identity_id:
            for bid, iid in CORPUS_AUTHOR_IDS.items():
                if iid and iid == identity_id:
                    is_corpus_author = True
                    author_of.append(bid)

        # Get subcategory from most common member subcategory
        sub_counts = defaultdict(int)
        for m in c["members"]:
            sub_counts[m.get("subcategory", "OTHER_PERSON")] += m.get("count", 1)
        subcategory = max(sub_counts, key=lambda k: sub_counts[k]) if sub_counts else "OTHER_PERSON"

        nodes.append({
            "id": c["id"],
            "name": display_name,
            "identity_id": identity_id,
            "subcategory": subcategory,
            "book_count": c["book_count"],
            "total_mentions": c["total_mentions"],
            "books": member_books,
            "is_corpus_author": is_corpus_author,
            "author_of": author_of if author_of else None,
        })

    # Build edges: shared books between person pairs
    node_ids = [n["id"] for n in nodes]
    node_id_set = set(node_ids)

    # For each book, collect which person nodes appear in it
    book_persons = defaultdict(set)  # book_id -> set of cluster_ids
    for nid, bset in node_books.items():
        for bid in bset:
            book_persons[bid].add(nid)

    # Count shared books for each pair
    pair_books = defaultdict(list)  # (id1, id2) -> [shared_book_ids]
    for bid, persons in book_persons.items():
        persons_list = sorted(persons)
        for i in range(len(persons_list)):
            for j in range(i + 1, len(persons_list)):
                key = (persons_list[i], persons_list[j])
                pair_books[key].append(bid)

    # Book index for compact edge storage
    book_index = sorted(book_ids)
    book_to_idx = {bid: i for i, bid in enumerate(book_index)}

    # Build edge list (weight >= 2)
    edges = []
    for (s, t), shared in pair_books.items():
        w = len(shared)
        if w >= 2:
            edges.append({
                "s": s,
                "t": t,
                "w": w,
                "b": sorted(book_to_idx[bid] for bid in shared),
            })

    edges.sort(key=lambda e: -e["w"])

    # Build corpus_authors map
    corpus_authors = {}
    for n in nodes:
        if n["is_corpus_author"] and n["author_of"]:
            for bid in n["author_of"]:
                corpus_authors[bid] = {"cluster_id": n["id"], "name": n["name"]}

    # Stats
    print(f"  {len(nodes)} nodes")
    print(f"  {len(edges)} edges (weight >= 2)")
    weight_counts = defaultdict(int)
    for e in edges:
        weight_counts[e["w"]] += 1
    for w in sorted(weight_counts):
        print(f"    weight {w}: {weight_counts[w]} edges")
    print(f"  {len(corpus_authors)} corpus authors found:")
    for bid, info in corpus_authors.items():
        print(f"    {info['name']} -> {bid}")

    # Top edges
    print(f"\n  Top 10 edges:")
    for e in edges[:10]:
        n1 = next((n["name"] for n in nodes if n["id"] == e["s"]), "?")
        n2 = next((n["name"] for n in nodes if n["id"] == e["t"]), "?")
        print(f"    {n1} <-> {n2}: {e['w']} shared books")

    # Save
    output = {
        "book_index": book_index,  # array of book_ids, edges reference by index
        "nodes": nodes,
        "edges": edges,
        "corpus_authors": corpus_authors,
    }
    out_path = WEB_DATA / "global_person_network.json"
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False)

    size_kb = out_path.stat().st_size / 1024
    print(f"\nSaved to {out_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()

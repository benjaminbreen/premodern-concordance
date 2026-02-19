#!/usr/bin/env python3
"""
Apply additional merges found by review_clusters.py:
  1. Embedding-similarity based merges (manually approved)
  2. Same-category same-Wikipedia-URL merges
  3. Cross-category merges for same-entity duplicates (member overlap)

Also flags wrong Wikipedia URLs for later fixing.

Usage:
    python3 scripts/apply_review_merges.py [--dry-run]
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

CONCORDANCE_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"
BACKUP_PATH = CONCORDANCE_PATH.with_suffix(".json.bak9")

# ─── Manually approved embedding-similarity merges ───────────────────────
# Format: (canonical_name_a, canonical_name_b) — will match by canonical_name
EMBEDDING_MERGES = [
    ("microscope", "Microscopes"),
    ("Optic axis", "optic axes"),
    ("nabo", "Turnip"),
    ("ox", "oxen"),
    ("pao de Aguila", "Eaglewood"),
]

# ─── Cross-category merges (same entity in different categories) ─────────
# These are clear duplicates found via member overlap
# Format: (name_a, cat_a, name_b, cat_b) — merge cat_b into cat_a
CROSS_CATEGORY_MERGES = [
    # Keep the more appropriate category
    ("carne", "ANIMAL", "carne", "SUBSTANCE"),       # meat -> ANIMAL
    ("color", "CONCEPT", "colour", "SUBSTANCE"),      # color -> CONCEPT
    ("magnetism", "CONCEPT", "Magnetism", "SUBSTANCE"),  # magnetism -> CONCEPT
]

# ─── Wrong Wikipedia URLs to clear ───────────────────────────────────────
# These are Wikipedia URLs that point to completely wrong articles
WRONG_WIKI_URLS = {
    "Europe PubMed Central",
    "Mindat.org",
    "Florence",       # for fuego/fogo
    "Glass (surname)",
    "Magnetic resonance imaging",  # for magnet
    "Science project",
    "Cannabis (drug)",  # for flower/grass
    "Chapter (religion)",
    "Graphite",        # for Silver/Argento
    "Ruby",            # for rame (copper)
    "Ethics",          # for consumption/Ethicks
    "Congenital diaphragmatic hernia",  # for Ruptures
    "Aristotle",       # for Amat. cluster (mixed abbreviations)
}


def merge_ground_truth(clusters):
    """Merge ground_truth from multiple clusters, preferring the richest one."""
    best_gt = {}
    best_score = -1
    for c in clusters:
        gt = c.get("ground_truth") or {}
        score = 0
        if gt.get("wikidata_id"): score += 3
        if gt.get("wikipedia_url"): score += 2
        if gt.get("wikipedia_extract"): score += 2
        if gt.get("modern_name"): score += 1
        if gt.get("description"): score += 1
        if gt.get("time_period"): score += 1
        if score > best_score:
            best_score = score
            best_gt = dict(gt)
    for c in clusters:
        gt = c.get("ground_truth") or {}
        for key, val in gt.items():
            if val and not best_gt.get(key):
                best_gt[key] = val
    return best_gt


def merge_clusters(primary, others):
    """Merge other clusters into the primary cluster."""
    all_members = list(primary.get("members", []))
    seen_keys = set()
    for m in all_members:
        key = (m.get("entity_id", ""), m.get("book_id", ""), m.get("name", ""))
        seen_keys.add(key)
    for c in others:
        for m in c.get("members", []):
            key = (m.get("entity_id", ""), m.get("book_id", ""), m.get("name", ""))
            if key not in seen_keys:
                all_members.append(m)
                seen_keys.add(key)
    primary["members"] = all_members
    books = set(m.get("book_id", "") for m in all_members)
    primary["book_count"] = len(books)
    primary["total_mentions"] = sum(m.get("count", 0) for m in all_members)
    primary["member_count"] = len(all_members)
    primary["ground_truth"] = merge_ground_truth([primary] + list(others))
    return primary


def extract_title_from_url(url):
    """Extract the article title from a Wikipedia URL."""
    import urllib.parse
    if "/wiki/" not in url:
        return ""
    path = url.split("/wiki/")[1]
    return urllib.parse.unquote(path).replace("_", " ")


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Loading concordance from {CONCORDANCE_PATH}")
    with open(CONCORDANCE_PATH) as f:
        data = json.load(f)
    clusters = data["clusters"]
    print(f"  {len(clusters)} clusters")

    # Build lookup maps
    by_name = defaultdict(list)
    by_name_cat = defaultdict(list)
    for idx, c in enumerate(clusters):
        cn = c.get("canonical_name", "")
        cat = c.get("category", "")
        by_name[cn].append(idx)
        by_name_cat[(cn, cat)].append(idx)

    absorbed_ids = set()
    stats = {"embedding_merges": 0, "cross_cat_merges": 0, "wiki_urls_cleared": 0}

    # ─── Phase 1: Embedding-similarity merges ────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 1: Embedding-similarity merges")
    print(f"{'='*60}")

    for name_a, name_b in EMBEDDING_MERGES:
        idxs_a = by_name.get(name_a, [])
        idxs_b = by_name.get(name_b, [])
        if not idxs_a or not idxs_b:
            print(f"  [WARN] Could not find: {name_a} or {name_b}")
            continue
        ia = idxs_a[0]
        ib = idxs_b[0]
        ca = clusters[ia]
        cb = clusters[ib]
        if ca["id"] in absorbed_ids or cb["id"] in absorbed_ids:
            continue
        # Primary = one with more mentions
        if ca.get("total_mentions", 0) >= cb.get("total_mentions", 0):
            primary, other = ca, cb
        else:
            primary, other = cb, ca
        print(f"  Merging: {name_a} + {name_b} -> {primary.get('canonical_name')}")
        if not dry_run:
            merge_clusters(primary, [other])
        absorbed_ids.add(other["id"])
        stats["embedding_merges"] += 1

    # ─── Phase 2: Cross-category merges ──────────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 2: Cross-category merges")
    print(f"{'='*60}")

    for name_a, cat_a, name_b, cat_b in CROSS_CATEGORY_MERGES:
        idxs_a = by_name_cat.get((name_a, cat_a), [])
        idxs_b = by_name_cat.get((name_b, cat_b), [])
        if not idxs_a or not idxs_b:
            print(f"  [WARN] Could not find: ({name_a},{cat_a}) or ({name_b},{cat_b})")
            continue
        ia = idxs_a[0]
        ib = idxs_b[0]
        ca = clusters[ia]
        cb = clusters[ib]
        if ca["id"] in absorbed_ids or cb["id"] in absorbed_ids:
            continue
        print(f"  Merging: [{cat_a}] {name_a} + [{cat_b}] {name_b} -> [{cat_a}] {name_a}")
        if not dry_run:
            merge_clusters(ca, [cb])
        absorbed_ids.add(cb["id"])
        stats["cross_cat_merges"] += 1

    # ─── Phase 3: Fix wrong Wikipedia URLs ───────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 3: Clearing wrong Wikipedia URLs")
    print(f"{'='*60}")

    for c in clusters:
        if c["id"] in absorbed_ids:
            continue
        gt = c.get("ground_truth") or {}
        url = gt.get("wikipedia_url", "")
        if not url:
            continue
        title = extract_title_from_url(url)
        if title in WRONG_WIKI_URLS:
            name = c.get("canonical_name", "?")
            print(f"  [{name}] clearing wrong URL: {title}")
            if not dry_run:
                gt["wikipedia_url"] = ""
                gt["wikipedia_extract"] = ""
                c["ground_truth"] = gt
            stats["wiki_urls_cleared"] += 1

    # ─── Remove absorbed clusters ────────────────────────────────────
    if not dry_run:
        new_clusters = [c for c in clusters if c["id"] not in absorbed_ids]
        for i, c in enumerate(new_clusters):
            c["id"] = i
        data["clusters"] = new_clusters
        data["stats"]["cluster_count"] = len(new_clusters)
    else:
        new_clusters = [c for c in clusters if c["id"] not in absorbed_ids]

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Embedding merges:    {stats['embedding_merges']}")
    print(f"  Cross-cat merges:    {stats['cross_cat_merges']}")
    print(f"  Wrong URLs cleared:  {stats['wiki_urls_cleared']}")
    print(f"  Clusters before:     {len(clusters)}")
    print(f"  Clusters after:      {len(new_clusters)}")
    print(f"  Net reduction:       {len(clusters) - len(new_clusters)}")

    if not dry_run:
        print(f"\nBacking up to {BACKUP_PATH}")
        with open(CONCORDANCE_PATH) as f:
            original = f.read()
        with open(BACKUP_PATH, "w") as f:
            f.write(original)

        print(f"Saving to {CONCORDANCE_PATH}...")
        with open(CONCORDANCE_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        size_mb = CONCORDANCE_PATH.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:.1f} MB")
        print("\nNext: rebuild search index")
        print("  python3 scripts/build_search_index.py")
    else:
        print("\nNo changes written (dry run).")


if __name__ == "__main__":
    main()

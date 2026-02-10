#!/usr/bin/env python3
"""
Build a canonical entity registry from current JSON sources.

Inputs:
  - web/public/data/*_entities.json (book-local entities)
  - web/public/data/concordance.json (cross-book clusters)

Output:
  - web/public/data/entity_registry.json

This file is designed as a stable API contract for entity discoverability.
It can be backed by Turso later without changing frontend response shapes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "web" / "public" / "data"
CONCORDANCE_PATH = DATA_DIR / "concordance.json"
OUTPUT_PATH = DATA_DIR / "entity_registry.json"


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def slugify(text: str) -> str:
    s = normalize_text(text)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "entity"


def stable_id(parts: list[str]) -> str:
    payload = "|".join(parts).encode("utf-8")
    return "ent_" + hashlib.sha1(payload).hexdigest()[:12]


def book_hint(book_id: str) -> str:
    # Keep deterministic and short for slug disambiguation.
    hint = book_id.split("_")[0].strip()
    return slugify(hint) or "book"


def cluster_slug_map(clusters: list[dict]) -> dict[int, str]:
    base_counts: dict[str, int] = {}
    for c in clusters:
        base = slugify(c.get("canonical_name", "entity"))
        base_counts[base] = base_counts.get(base, 0) + 1

    out: dict[int, str] = {}
    for c in clusters:
        base = slugify(c.get("canonical_name", "entity"))
        if base_counts[base] > 1:
            out[int(c["id"])] = f"{base}-{c['id']}"
        else:
            out[int(c["id"])] = base
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical entity registry")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output JSON path")
    args = parser.parse_args()

    entity_files = sorted(DATA_DIR.glob("*_entities.json"))
    if not entity_files:
        raise SystemExit(f"No *_entities.json files found in {DATA_DIR}")

    books: dict[str, dict] = {}
    local_entities: dict[tuple[str, str], dict] = {}

    print(f"Loading {len(entity_files)} book entity files...")
    for path in entity_files:
        data = load_json(path)
        book = data["book"]
        book_id = book["id"]
        books[book_id] = {
            "id": book_id,
            "title": book.get("title", book_id),
            "author": book.get("author", ""),
            "year": book.get("year", 0),
            "language": book.get("language", ""),
            "description": book.get("description", ""),
        }
        for ent in data.get("entities", []):
            local_entities[(book_id, ent["id"])] = ent

    concordance = load_json(CONCORDANCE_PATH)
    clusters: list[dict] = concordance.get("clusters", [])
    cslug = cluster_slug_map(clusters)

    used_slugs: dict[str, dict] = {}
    member_to_global: dict[tuple[str, str], str] = {}
    registry_entities: list[dict] = []

    def allocate_slug(
        canonical_name: str,
        category: str,
        preferred_book_hint: str | None = None,
    ) -> str:
        base = slugify(canonical_name)
        existing = used_slugs.get(base)
        if not existing:
            used_slugs[base] = {"category": category}
            return base

        candidate = base
        if existing["category"] != category:
            candidate = f"{base}-{slugify(category)}"
            if candidate not in used_slugs:
                used_slugs[candidate] = {"category": category}
                return candidate

        if preferred_book_hint:
            candidate = f"{base}-{slugify(preferred_book_hint)}"
            if candidate not in used_slugs:
                used_slugs[candidate] = {"category": category}
                return candidate

        i = 2
        while True:
            candidate = f"{base}-{i}"
            if candidate not in used_slugs:
                used_slugs[candidate] = {"category": category}
                return candidate
            i += 1

    def build_attestation(member: dict, local: dict, book: dict) -> dict:
        mentions = local.get("mentions", []) if isinstance(local.get("mentions"), list) else []
        samples = [m.get("excerpt", "") for m in mentions[:3] if m.get("excerpt")]
        return {
            "book_id": book["id"],
            "book_title": book.get("title", book["id"]),
            "book_author": book.get("author", ""),
            "book_year": book.get("year", 0),
            "book_language": book.get("language", ""),
            "local_entity_id": local.get("id", member.get("entity_id", "")),
            "local_name": local.get("name", member.get("name", "")),
            "category": local.get("category", member.get("category", "")),
            "subcategory": local.get("subcategory", member.get("subcategory", "")),
            "count": int(local.get("count", member.get("count", 0))),
            "variants": local.get("variants", member.get("variants", [])),
            "contexts": local.get("contexts", member.get("contexts", [])),
            "mention_count": len(mentions),
            "excerpt_samples": samples,
            "entity_page_path": f"/books/{quote(book['id'])}/entity/{quote(local.get('id', member.get('entity_id', '')))}",
        }

    # 1) Concordance-backed entities first (clean slug priority)
    print(f"Building canonical entities from {len(clusters)} concordance clusters...")
    for cluster in sorted(clusters, key=lambda c: int(c["id"])):
        members = cluster.get("members", [])
        signatures = sorted(f"{m['book_id']}::{m['entity_id']}" for m in members)
        eid = stable_id(["cluster"] + signatures)

        att = []
        books_in_entity: set[str] = set()
        names: list[str] = []
        names_seen: set[str] = set()
        total_mentions = 0

        for m in members:
            bid = m["book_id"]
            lid = m["entity_id"]
            local = local_entities.get((bid, lid))
            if local is None:
                local = {
                    "id": lid,
                    "name": m.get("name", lid),
                    "category": m.get("category", cluster.get("category", "")),
                    "subcategory": m.get("subcategory", cluster.get("subcategory", "")),
                    "count": m.get("count", 0),
                    "variants": m.get("variants", [m.get("name", lid)]),
                    "contexts": m.get("contexts", []),
                    "mentions": [],
                }

            book = books.get(bid, {"id": bid, "title": bid, "author": "", "year": 0, "language": ""})
            a = build_attestation(m, local, book)
            att.append(a)
            books_in_entity.add(bid)
            total_mentions += int(a["count"])

            for candidate in [a["local_name"], *a["variants"]]:
                if not candidate:
                    continue
                key = normalize_text(candidate)
                if key in names_seen:
                    continue
                names_seen.add(key)
                names.append(candidate)

            member_to_global[(bid, lid)] = eid

        # Deterministic hint from first attestation by year/name
        att_sorted = sorted(att, key=lambda x: (x["book_year"], x["book_id"], x["local_name"]))
        hint = book_hint(att_sorted[0]["book_id"]) if att_sorted else None

        slug = allocate_slug(cluster.get("canonical_name", "entity"), cluster.get("category", ""), hint)
        registry_entities.append(
            {
                "id": eid,
                "slug": slug,
                "canonical_name": cluster.get("canonical_name", "entity"),
                "category": cluster.get("category", ""),
                "subcategory": cluster.get("subcategory", ""),
                "book_count": len(books_in_entity),
                "total_mentions": total_mentions,
                "is_concordance": True,
                "concordance_cluster_id": int(cluster["id"]),
                "concordance_slug": cslug.get(int(cluster["id"])),
                "ground_truth": cluster.get("ground_truth", {}),
                "books": sorted(books_in_entity),
                "names": names[:200],
                "attestations": att_sorted,
            }
        )

    # 2) Single-book entities not in concordance
    print("Adding single-book entities not present in concordance...")
    local_items = sorted(
        local_entities.items(),
        key=lambda kv: (kv[0][0], -int(kv[1].get("count", 0)), normalize_text(kv[1].get("name", ""))),
    )
    added_singletons = 0
    for (bid, lid), local in local_items:
        if (bid, lid) in member_to_global:
            continue

        eid = stable_id(["local", bid, lid])
        book = books[bid]
        member = {
            "book_id": bid,
            "entity_id": lid,
            "name": local.get("name", lid),
            "category": local.get("category", ""),
            "subcategory": local.get("subcategory", ""),
            "count": local.get("count", 0),
            "variants": local.get("variants", [local.get("name", lid)]),
            "contexts": local.get("contexts", []),
        }
        a = build_attestation(member, local, book)
        hint = book_hint(bid)
        slug = allocate_slug(local.get("name", lid), local.get("category", ""), hint)

        names = []
        seen = set()
        for candidate in [a["local_name"], *a["variants"]]:
            if not candidate:
                continue
            key = normalize_text(candidate)
            if key in seen:
                continue
            seen.add(key)
            names.append(candidate)

        registry_entities.append(
            {
                "id": eid,
                "slug": slug,
                "canonical_name": local.get("name", lid),
                "category": local.get("category", ""),
                "subcategory": local.get("subcategory", ""),
                "book_count": 1,
                "total_mentions": int(local.get("count", 0)),
                "is_concordance": False,
                "concordance_cluster_id": None,
                "concordance_slug": None,
                "ground_truth": {},
                "books": [bid],
                "names": names[:200],
                "attestations": [a],
            }
        )
        added_singletons += 1

    # Sort for deterministic output and strong default browse order
    registry_entities.sort(
        key=lambda e: (-int(e["is_concordance"]), -int(e["book_count"]), -int(e["total_mentions"]), normalize_text(e["canonical_name"]))
    )

    categories: dict[str, int] = {}
    total_mentions = 0
    total_attestations = 0
    for e in registry_entities:
        categories[e["category"]] = categories.get(e["category"], 0) + 1
        total_mentions += int(e["total_mentions"])
        total_attestations += len(e["attestations"])

    out = {
        "metadata": {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "version": "1.0",
            "source": {
                "entity_files": [p.name for p in entity_files],
                "concordance_file": CONCORDANCE_PATH.name,
            },
            "counts": {
                "books": len(books),
                "entities_total": len(registry_entities),
                "entities_concordance": len(clusters),
                "entities_singleton": added_singletons,
                "attestations_total": total_attestations,
                "mentions_total": total_mentions,
            },
            "by_category": categories,
        },
        "books": sorted(books.values(), key=lambda b: (b.get("year", 0), b["id"])),
        "entities": registry_entities,
    }

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Done. Wrote {len(registry_entities)} entities to {output_path} ({size_mb:.1f} MB)")
    print(f"  Concordance-backed: {len(clusters)}")
    print(f"  Single-book: {added_singletons}")


if __name__ == "__main__":
    main()

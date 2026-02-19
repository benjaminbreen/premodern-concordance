#!/usr/bin/env python3
"""
One-time migration: convert hash-based stable keys (clu_*) to human-readable
slugs and generate a redirect map for old URLs.

Run once:
    python3 scripts/migrate_to_readable_slugs.py

After running, also rebuild the search index:
    python3 scripts/build_search_index.py
"""

import json
import re
import unicodedata
from pathlib import Path

CONCORDANCE = Path("web/public/data/concordance.json")
REDIRECT_MAP = Path("web/public/data/slug_redirects.json")


def slugify(name: str) -> str:
    """Generate a URL-safe slug from a name."""
    text = unicodedata.normalize("NFD", (name or "").lower().strip())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "unnamed"


def migrate():
    data = json.loads(CONCORDANCE.read_text(encoding="utf-8"))
    clusters = data["clusters"]

    print(f"Migrating {len(clusters)} clusters to human-readable slugs...")

    redirects = {}  # old_key -> new_key
    used_keys = set()

    for cluster in clusters:
        old_key = cluster.get("stable_key", "")
        base = slugify(cluster.get("canonical_name", ""))

        # Determine new key with collision handling
        if base not in used_keys:
            new_key = base
        else:
            cat = cluster.get("category", "").lower()
            cat_slug = f"{base}-{cat}" if cat else base
            if cat_slug not in used_keys:
                new_key = cat_slug
            else:
                n = 2
                while f"{cat_slug}-{n}" in used_keys:
                    n += 1
                new_key = f"{cat_slug}-{n}"

        used_keys.add(new_key)
        cluster["stable_key"] = new_key

        # Record redirect if key changed
        if old_key and old_key != new_key:
            redirects[old_key] = new_key

    # Save updated concordance
    CONCORDANCE.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )

    # Save redirect map
    REDIRECT_MAP.write_text(
        json.dumps(redirects, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    hash_redirects = sum(1 for k in redirects if k.startswith("clu_"))
    print(f"\nResults:")
    print(f"  Updated {len(clusters)} cluster slugs")
    print(f"  Generated {len(redirects)} redirects ({hash_redirects} from clu_* hashes)")
    print(f"  Saved concordance: {CONCORDANCE}")
    print(f"  Saved redirect map: {REDIRECT_MAP}")

    # Show examples
    print(f"\nSample redirects:")
    examples = [(k, v) for k, v in list(redirects.items())[:10]]
    for old, new in examples:
        print(f"  {old} -> {new}")

    # Show collision stats
    cat_suffixed = sum(1 for k in used_keys if re.search(r'-(person|place|plant|animal|substance|concept|disease|object)$', k))
    num_suffixed = sum(1 for k in used_keys if re.search(r'-\d+$', k))
    print(f"\nCollision handling:")
    print(f"  Category-disambiguated: {cat_suffixed}")
    print(f"  Number-suffixed: {num_suffixed}")
    print(f"  Unique slugs: {len(used_keys)}")


if __name__ == "__main__":
    migrate()

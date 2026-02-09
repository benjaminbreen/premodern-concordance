#!/usr/bin/env python3
"""
Strip honorific prefixes from entity names and merge duplicates within each book.
E.g. "Mr. Galton" + "Galton" → single "Galton" entity with combined counts.

Only merges within the SAME category. Backs up files before writing.
"""

import json, re, sys, shutil
from pathlib import Path

HONORIFICS = re.compile(
    r"^(Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?|Sir|Saint|St\.?|Herr|Señor|Sr\.?|Dom|Fray|Frei|Abbé|Père|Don)\s+",
    re.IGNORECASE,
)

def normalize_name(name: str) -> str:
    """Strip leading honorific from a name."""
    return HONORIFICS.sub("", name).strip()

GENDERED = re.compile(r"^(Mr\.?|Mrs\.?|Ms\.?)\s+", re.IGNORECASE)

def _gendered_prefix(name: str) -> str | None:
    """Return 'mr'/'mrs'/'ms' if the name starts with one, else None."""
    m = GENDERED.match(name)
    return m.group(1).rstrip(".").lower() if m else None

def merge_entities(entities: list[dict]) -> list[dict]:
    """Group entities by (normalized_name_lower, category), merge duplicates.
    Never merge Mr. X with Mrs. X (different people)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for ent in entities:
        key = (normalize_name(ent["name"]).lower(), ent["category"])
        groups.setdefault(key, []).append(ent)

    # Split groups where Mr./Mrs./Ms. conflict
    refined: dict[tuple, list[dict]] = {}
    for key, group in groups.items():
        if len(group) <= 1:
            refined[key] = group
            continue
        prefixes = {_gendered_prefix(e["name"]) for e in group}
        # If group has BOTH mr and mrs/ms, only merge bare names with the majority prefix
        has_mr = "mr" in prefixes
        has_mrs = "mrs" in prefixes or "ms" in prefixes
        if has_mr and has_mrs:
            # Don't merge — keep each entity separate
            for i, e in enumerate(group):
                refined[(*key, i)] = [e]
        else:
            refined[key] = group
    groups = refined

    merged = []
    total_merges = 0
    for key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        # Pick the entity with highest count as primary
        group.sort(key=lambda e: e["count"], reverse=True)
        primary = group[0]

        for secondary in group[1:]:
            total_merges += 1
            print(f"  MERGE: '{secondary['name']}' ({secondary['count']}) → '{primary['name']}' ({primary['count']})")
            primary["count"] += secondary["count"]
            # Merge variants
            all_variants = set(primary.get("variants", []))
            all_variants.add(secondary["name"])
            all_variants.update(secondary.get("variants", []))
            primary["variants"] = sorted(all_variants)
            # Merge contexts (deduplicate)
            seen = set(primary.get("contexts", []))
            for ctx in secondary.get("contexts", []):
                if ctx not in seen:
                    primary.setdefault("contexts", []).append(ctx)
                    seen.add(ctx)
            # Merge mentions
            if "mentions" in secondary:
                primary.setdefault("mentions", []).extend(secondary["mentions"])

        # Re-sort mentions by offset
        if "mentions" in primary:
            primary["mentions"].sort(key=lambda m: m.get("offset", 0))

        merged.append(primary)

    return merged, total_merges

def process_file(path: Path, dry_run: bool = False):
    print(f"\n{'='*60}")
    print(f"Processing: {path.name}")
    data = json.loads(path.read_text())
    entities = data.get("entities", [])
    print(f"  Entities before: {len(entities)}")

    merged_entities, merge_count = merge_entities(entities)
    print(f"  Entities after:  {len(merged_entities)}  ({merge_count} merges)")

    if merge_count == 0:
        print("  No merges needed.")
        return 0

    if dry_run:
        print("  (dry run — no files changed)")
        return merge_count

    # Backup
    bak = path.with_suffix(".json.bak")
    if bak.exists():
        bak = path.with_suffix(".json.bak2")
    shutil.copy2(path, bak)
    print(f"  Backed up to {bak.name}")

    data["entities"] = merged_entities
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  Written.")
    return merge_count


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    entity_dir = Path(__file__).parent.parent / "web" / "public" / "data"
    files = sorted(entity_dir.glob("*_entities.json"))

    if not files:
        print("No entity files found!")
        sys.exit(1)

    print(f"Found {len(files)} entity files. {'DRY RUN' if dry_run else 'LIVE RUN'}")

    total = 0
    for f in files:
        total += process_file(f, dry_run)

    print(f"\n{'='*60}")
    print(f"Total merges: {total}")

#!/usr/bin/env python3
"""
validate_members.py — Context-aware member validation for concordance clusters.

Finds clusters where some members likely don't belong (merged by name similarity
but actually different entities), validates via LLM, and splits them out.

Steps:
  1. Heuristic pre-filter: flag clusters with suspicious members
  2. LLM validation: ask Gemini which members don't belong
  3. Auto-split: extract rejected members into new clusters

Usage:
  python scripts/validate_members.py                    # full run
  python scripts/validate_members.py --dry-run          # preview only
  python scripts/validate_members.py --dry-run --phase 1  # just show flagged clusters
"""

import argparse
import json
import os
import re
import shutil
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
DEFAULT_PATH = DATA_DIR / "concordance.json"

# ── Helpers ────────────────────────────────────────────────────────────


def normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def name_similarity(a: str, b: str) -> float:
    """Normalized Levenshtein similarity (0-1)."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    dist = levenshtein(na, nb)
    return 1.0 - dist / max(len(na), len(nb))


def longest_common_prefix(a: str, b: str) -> int:
    """Length of the longest common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — Heuristic pre-filter
# ═══════════════════════════════════════════════════════════════════════


def find_suspicious_clusters(clusters: list[dict]) -> list[dict]:
    """Find clusters likely to contain wrong members.

    Strategy: be selective. Only flag members where the name is genuinely
    unrelated — not just a cross-language translation, compound form, or
    plural variant.
    """
    flagged = []

    for c in clusters:
        if len(c["members"]) < 2:
            continue

        canonical = c["canonical_name"]
        canonical_n = normalize(canonical)
        gt = c.get("ground_truth") or {}
        modern = normalize(gt.get("modern_name") or "")
        linnaean = normalize(gt.get("linnaean") or "")

        # Collect all normalized member names for cross-checks
        all_member_names = [normalize(m["name"]) for m in c["members"]]

        suspicious_members = []

        for m in c["members"]:
            member_n = normalize(m["name"])

            # Skip very short member names — too ambiguous to flag
            if len(member_n) <= 2:
                continue

            sim_canonical = name_similarity(member_n, canonical_n)
            sim_modern = name_similarity(member_n, modern) if modern else 0.0
            sim_linnaean = name_similarity(member_n, linnaean) if linnaean else 0.0

            # Check if member name CONTAINS or IS CONTAINED in canonical/modern
            # This catches compound terms like "canela fina" ⊃ "canela"
            is_substring = (
                canonical_n in member_n
                or member_n in canonical_n
                or (modern and (modern in member_n or member_n in modern))
            )
            if is_substring:
                continue

            # Check similarity to best matching other member
            best_sim_to_others = 0.0
            for other_n in all_member_names:
                if other_n == member_n:
                    continue
                sim = name_similarity(member_n, other_n)
                best_sim_to_others = max(best_sim_to_others, sim)
                # Also check substring with other members
                if other_n in member_n or member_n in other_n:
                    best_sim_to_others = max(best_sim_to_others, 0.8)

            # ── Flag condition 1: Name is genuinely different from everything ──
            # Very strict: low similarity to canonical, modern name, linnaean,
            # AND all other members
            name_is_alien = (
                sim_canonical < 0.40
                and sim_modern < 0.40
                and sim_linnaean < 0.40
                and best_sim_to_others < 0.45
                and len(member_n) > 2
            )

            # ── Flag condition 2: Partial name match but context is wrong ──
            # The name looks similar but the context describes something different.
            # Only flag if context clearly contradicts the cluster type.
            contexts = " ".join(m.get("contexts", [])).lower()
            context_strong_mismatch = False

            if c["category"] == "PLANT" and any(
                kw in contexts
                for kw in [
                    "a stone", "precious stone", "mineral substance",
                    "an animal", "animal species", "metal",
                ]
            ):
                context_strong_mismatch = True
            if c["category"] == "ANIMAL" and any(
                kw in contexts for kw in ["plant species", "a herb", "herbal"]
            ):
                context_strong_mismatch = True
            if c["category"] == "PERSON" and any(
                kw in contexts for kw in ["plant species", "a herb", "herbal", "mineral"]
            ):
                context_strong_mismatch = True
            if c["category"] == "PLACE" and any(
                kw in contexts for kw in ["plant species", "a herb", "herbal", "disease"]
            ):
                context_strong_mismatch = True

            # ── Flag condition 3: Moderate name divergence + low count ──
            # Member has moderate name difference AND is low-frequency
            # (single-mention members with different names are often noise)
            moderate_name_divergence = (
                sim_canonical < 0.50
                and sim_modern < 0.50
                and best_sim_to_others < 0.50
                and m["count"] <= 2
                and len(member_n) > 3
            )

            # Combine: flag if alien name, or strong context mismatch,
            # or moderate name divergence with low mentions
            should_flag = (
                name_is_alien
                or context_strong_mismatch
                or (moderate_name_divergence and not is_substring)
            )

            if should_flag:
                reasons = [
                    r
                    for r, v in [
                        ("alien_name", name_is_alien),
                        ("context_mismatch", context_strong_mismatch),
                        ("low_freq_divergent", moderate_name_divergence),
                    ]
                    if v
                ]
                suspicious_members.append(
                    {
                        "member": m,
                        "sim_canonical": sim_canonical,
                        "sim_modern": sim_modern,
                        "best_sim_others": best_sim_to_others,
                        "reasons": reasons,
                    }
                )

        if suspicious_members:
            flagged.append(
                {
                    "cluster": c,
                    "suspicious": suspicious_members,
                }
            )

    return flagged


# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — LLM validation
# ═══════════════════════════════════════════════════════════════════════


def build_validation_prompt(flagged_items: list[dict]) -> str:
    """Build a Gemini prompt to validate suspicious members."""
    blocks = []

    for item in flagged_items:
        c = item["cluster"]
        gt = c.get("ground_truth") or {}
        suspicious_ids = {
            (s["member"]["entity_id"], s["member"]["book_id"])
            for s in item["suspicious"]
        }

        # Describe the cluster identity
        identity_parts = [f"'{c['canonical_name']}'"]
        if gt.get("modern_name"):
            identity_parts.append(f"(modern: {gt['modern_name']})")
        if gt.get("linnaean"):
            identity_parts.append(f"[{gt['linnaean']}]")
        identity_parts.append(f"— {c['category']}")
        if gt.get("description"):
            identity_parts.append(f"— {gt['description']}")

        identity = " ".join(identity_parts)

        # List all members with contexts
        member_lines = []
        for i, m in enumerate(c["members"], 1):
            key = (m["entity_id"], m["book_id"])
            flag = " ⚑" if key in suspicious_ids else ""
            ctx = "; ".join(m.get("contexts", [])[:3])
            ctx_str = f' — "{ctx}"' if ctx else ""
            member_lines.append(
                f"  {i}. \"{m['name']}\" from {m['book_id']} "
                f"({m['count']}x){ctx_str}{flag}"
            )

        blocks.append(
            f"CLUSTER {c['id']}: {identity}\n"
            f"Members:\n" + "\n".join(member_lines)
        )

    clusters_text = "\n\n---\n\n".join(blocks)

    return f"""You are validating entity clusters from a cross-linguistic concordance of early modern texts (1500–1800) in English, Portuguese, Spanish, French, Italian, and Latin.

Each cluster groups references to the SAME entity across books in DIFFERENT LANGUAGES. Members marked ⚑ are suspected of being wrong.

{clusters_text}

For each cluster, return a JSON object:
- "cluster_id": the cluster ID number
- "reject": array of objects for members that DON'T belong, each with:
  - "name": the member name exactly as shown
  - "book_id": the book ID exactly as shown
  - "reason": brief explanation (10 words max)
  - "suggested_identity": what this member actually is
- If all members are correct, return "reject": []

CRITICAL RULES — read these carefully:

1. KEEP cross-language translations. These texts are in 6 languages. "eau" IS water in French, "corpo" IS body in Portuguese, "raiz" IS root in Portuguese, "semilla" IS seed in Spanish, "Grèce" IS Greece in French. These MUST stay.

2. KEEP qualified/compound forms of the base concept. "canela fina" (fine cinnamon) belongs in the Cinnamon cluster. "fièvres épidémiques" belongs in the Fever cluster. "gota coral" belongs in Gout. "agua fria" belongs in Water.

3. KEEP members where the context describes the SAME thing even if the name looks different. "Windiness" IS flatulence. "Stones" ARE calculi. "warm" IS heat.

4. "Context is too general" is NOT a valid reason to reject. Many members have brief or vague contexts — that doesn't mean they're wrong.

5. ONLY reject a member if it refers to a COMPLETELY DIFFERENT thing. Examples of valid rejections:
   - "tabaxir" (bamboo sugar) in a Tobacco cluster — completely different substance
   - "oolithes" (limestone) in an Oil cluster — completely different thing
   - "Commerson" (a naturalist) in a Merchants cluster — different type of person
   - "camemali" (chamomile) in a Cinnamon cluster — different plant entirely

6. When in doubt, KEEP the member. False rejections are worse than false keeps.

Return ONLY the JSON array, no other text."""


def validate_with_llm(
    flagged: list[dict], client, model: str, batch_size: int
) -> dict[int, list[dict]]:
    """Send flagged clusters to Gemini for validation. Returns cluster_id → rejections."""
    rejections: dict[int, list[dict]] = {}

    num_batches = (len(flagged) + batch_size - 1) // batch_size
    print(f"\n  Validating {len(flagged)} clusters in {num_batches} batches...")

    for batch_idx in range(0, len(flagged), batch_size):
        batch = flagged[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        print(f"\n  Batch {batch_num}/{num_batches} ({len(batch)} clusters)...", flush=True)

        prompt = build_validation_prompt(batch)

        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = response.text.strip()

            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("```", 1)[0]
                text = text.strip()

            results = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"    JSON parse error: {e}")
            time.sleep(2)
            continue
        except Exception as e:
            print(f"    API error: {e}")
            time.sleep(2)
            continue

        for r in results:
            cid = r.get("cluster_id")
            rejects = r.get("reject", [])
            if cid is not None and rejects:
                rejections[cid] = rejects
                for rej in rejects:
                    print(
                        f"    ✗ Cluster {cid}: '{rej['name']}' ({rej['book_id']}) "
                        f"→ {rej.get('reason', '?')}"
                    )

        time.sleep(1)

    return rejections


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — Auto-split
# ═══════════════════════════════════════════════════════════════════════


def apply_splits(
    clusters: list[dict], rejections: dict[int, list[dict]]
) -> list[dict]:
    """Extract rejected members into new standalone clusters."""
    max_id = max(c["id"] for c in clusters)
    new_clusters = []
    total_splits = 0

    cluster_map = {c["id"]: c for c in clusters}

    for cid, rejects in rejections.items():
        c = cluster_map.get(cid)
        if not c:
            continue

        for rej in rejects:
            rej_name = rej["name"].lower()
            rej_book = rej.get("book_id", "")

            # Find matching member(s)
            to_extract = []
            to_keep = []
            for m in c["members"]:
                if m["name"].lower() == rej_name and (
                    not rej_book or m["book_id"] == rej_book
                ):
                    to_extract.append(m)
                else:
                    to_keep.append(m)

            if not to_extract:
                # Try fuzzy match on name
                for m in c["members"]:
                    if name_similarity(m["name"], rej["name"]) > 0.8 and (
                        not rej_book or m["book_id"] == rej_book
                    ):
                        to_extract.append(m)
                        to_keep = [x for x in c["members"] if x not in to_extract]

            if not to_extract:
                continue

            # Don't split if it would empty the original cluster
            if not to_keep:
                continue

            # Update original cluster
            c["members"] = to_keep
            c["edges"] = [
                e
                for e in c["edges"]
                if e["source_name"].lower() != rej_name
                and e["target_name"].lower() != rej_name
            ]
            c["book_count"] = len({m["book_id"] for m in c["members"]})
            c["total_mentions"] = sum(m["count"] for m in c["members"])

            # Create new cluster for the extracted member(s)
            max_id += 1
            new_cluster = {
                "id": max_id,
                "canonical_name": to_extract[0]["name"],
                "category": to_extract[0]["category"],
                "subcategory": to_extract[0].get("subcategory", ""),
                "book_count": len({m["book_id"] for m in to_extract}),
                "total_mentions": sum(m["count"] for m in to_extract),
                "members": to_extract,
                "edges": [],
                "ground_truth": {
                    "modern_name": rej.get("suggested_identity", to_extract[0]["name"]),
                    "confidence": "low",
                    "type": to_extract[0]["category"].lower(),
                    "note": f"Split from '{c['canonical_name']}' cluster — {rej.get('reason', 'different entity')}",
                },
            }
            new_clusters.append(new_cluster)
            total_splits += 1

    clusters.extend(new_clusters)
    print(f"\n  Splits applied: {total_splits}")
    print(f"  New clusters created: {len(new_clusters)}")
    return clusters


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Validate cluster members")
    parser.add_argument(
        "--concordance", default=str(DEFAULT_PATH), help="Concordance JSON"
    )
    parser.add_argument("--output", default=None, help="Output path")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--phase",
        nargs="+",
        type=int,
        default=[1, 2, 3],
        help="Steps to run (1=filter, 2=validate, 3=split)",
    )
    parser.add_argument(
        "--model", default="gemini-2.5-flash-lite", help="Gemini model"
    )
    parser.add_argument("--batch-size", type=int, default=6, help="Clusters per batch")
    args = parser.parse_args()

    load_dotenv(Path(__file__).parent.parent / ".env.local")

    concordance_path = Path(args.concordance)
    print(f"Loading: {concordance_path}")

    with open(concordance_path) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Loaded {len(clusters)} clusters\n")

    # ── Step 1: Heuristic pre-filter ──────────────────────────────────
    print("=" * 60)
    print("STEP 1 — Heuristic pre-filter")
    print("=" * 60)

    flagged = find_suspicious_clusters(clusters)
    total_suspicious = sum(len(f["suspicious"]) for f in flagged)

    print(f"\n  Flagged: {len(flagged)} clusters with {total_suspicious} suspicious members\n")

    for f in flagged[:30]:
        c = f["cluster"]
        gt = c.get("ground_truth") or {}
        print(f"  [{c['id']}] {c['canonical_name']} ({c['category']}, {gt.get('modern_name', '?')})")
        for s in f["suspicious"]:
            m = s["member"]
            ctx = "; ".join(m.get("contexts", [])[:2])[:60]
            print(
                f"       ⚑ '{m['name']}' ({m['book_id']}, {m['count']}x) "
                f"sim={s['sim_canonical']:.2f} [{', '.join(s['reasons'])}]"
            )
            if ctx:
                print(f"         ctx: {ctx}")
    if len(flagged) > 30:
        print(f"\n  ... and {len(flagged) - 30} more clusters")

    if 1 not in args.phase or 2 not in args.phase:
        return

    # ── Step 2: LLM validation ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2 — LLM validation")
    print("=" * 60)

    try:
        from google import genai
    except ImportError:
        print("  Error: google-genai not installed")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  Error: GEMINI_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)
    rejections = validate_with_llm(flagged, client, args.model, args.batch_size)

    total_rejected = sum(len(r) for r in rejections.values())
    print(f"\n  Total rejections: {total_rejected} members across {len(rejections)} clusters")

    if not rejections:
        print("  No members to split — data looks clean!")
        return

    if 3 not in args.phase:
        return

    # ── Step 3: Apply splits ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3 — Apply splits")
    print("=" * 60)

    if args.dry_run:
        print("\n  DRY RUN — would split these members:")
        for cid, rejects in rejections.items():
            c_name = next(
                (c["canonical_name"] for c in clusters if c["id"] == cid), f"#{cid}"
            )
            for rej in rejects:
                print(
                    f"    '{rej['name']}' out of '{c_name}' "
                    f"→ new cluster ({rej.get('suggested_identity', '?')})"
                )
        print(f"\n  Total: {total_rejected} splits pending")
        return

    # Backup
    backup_path = concordance_path.with_suffix(".json.bak2")
    shutil.copy2(concordance_path, backup_path)
    print(f"  Backup: {backup_path}")

    clusters = apply_splits(clusters, rejections)

    # Reassign IDs
    for i, c in enumerate(clusters, 1):
        c["id"] = i

    data["clusters"] = clusters
    data["stats"]["total_clusters"] = len(clusters)
    data["stats"]["entities_matched"] = sum(len(c["members"]) for c in clusters)

    by_cat: dict[str, int] = defaultdict(int)
    for c in clusters:
        by_cat[c["category"]] += 1
    data["stats"]["by_category"] = dict(sorted(by_cat.items()))

    data["metadata"]["member_validation_applied"] = True

    output_path = Path(args.output) if args.output else concordance_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size_mb = output_path.stat().st_size / (1024 * 1024)

    print(f"\n{'=' * 60}")
    print(f"Saved: {output_path} ({size_mb:.1f} MB, {len(clusters)} clusters)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Verify concordance clusters using LLM to catch false matches.

Automatically detects suspicious clusters (e.g., entities that share surface
string similarity but are semantically different), sends them to Gemini for
verification, and splits or removes false groupings.

Usage:
    python verify_concordance.py
    python verify_concordance.py --dry-run          # show suspicious clusters only
    python verify_concordance.py --concordance web/public/data/concordance.json
"""

import argparse
import json
import os
import time
from pathlib import Path
from collections import Counter

from google import genai

DEFAULT_PATH = Path(__file__).parent.parent / "web" / "public" / "data" / "concordance.json"


def string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity based on shared characters and prefix."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    min_len = min(len(s1), len(s2))
    if min_len == 0:
        return 0.0
    common_prefix = 0
    for i in range(min_len):
        if s1[i] == s2[i]:
            common_prefix += 1
        else:
            break
    set1, set2 = set(s1), set(s2)
    shared = len(set1 & set2)
    total = len(set1 | set2)
    char_ratio = shared / total if total > 0 else 0
    len_ratio = min_len / max(len(s1), len(s2))
    prefix_score = common_prefix / min_len
    return 0.5 * prefix_score + 0.3 * char_ratio + 0.2 * len_ratio


def is_suspicious(cluster: dict) -> tuple[bool, list[str]]:
    """Detect if a concordance cluster likely contains false matches.

    Returns (is_suspicious, list_of_reasons).
    """
    reasons = []
    members = cluster["members"]
    canonical = cluster["canonical_name"].lower()

    # 1. Multiple entities from the same book (dedup already ran,
    #    so multiples likely means different things)
    book_counts = Counter(m["book_id"] for m in members)
    max_same_book = max(book_counts.values())
    if max_same_book >= 3:
        reasons.append(f"{max_same_book} entities from same book")

    # 2. Low average string similarity to canonical name (excluding self-match)
    sims = [string_similarity(canonical, m["name"]) for m in members]
    other_sims = [s for s in sims if s < 0.99]  # exclude exact self-match
    avg_sim = sum(other_sims) / len(other_sims) if other_sims else 1.0
    if avg_sim < 0.4:
        reasons.append(f"low avg string similarity ({avg_sim:.2f})")

    # 3. Very low minimum string similarity (indicates an outlier)
    min_sim = min(sims)
    if min_sim < 0.15 and len(members) > 2:
        reasons.append(f"outlier member (min sim {min_sim:.2f})")

    # 4. Large cluster with diverse members
    if len(members) >= 6:
        reasons.append(f"large cluster ({len(members)} members)")

    # 5. Context divergence: check if contexts mention very different things
    contexts = []
    for m in members:
        contexts.extend(m.get("contexts", []))
    if len(contexts) >= 3:
        # Simple heuristic: count unique significant words across contexts
        all_words = set()
        for ctx in contexts:
            words = {w.lower() for w in ctx.split() if len(w) > 4}
            all_words.update(words)
        if len(all_words) > len(contexts) * 4:
            reasons.append("divergent contexts")

    # 6. Short names with low pairwise similarity — likely surface-level matches
    #    (e.g., tres/Trine/terço — all short, share "tr-" but are different things)
    all_names = [m["name"] for m in members]
    avg_name_len = sum(len(n) for n in all_names) / len(all_names)
    if avg_name_len < 7 and avg_sim < 0.5:
        reasons.append(f"short names with low similarity (avg len {avg_name_len:.0f})")

    # 7. Low-frequency cluster with names that don't look like translations
    #    This catches cases like tres/Trine/terço where short common words
    #    from different languages get falsely matched.
    #    Valid translations (açucar/sugar, vinagre/Vinegar) have high string
    #    similarity or one name contains the other — false matches don't.
    if cluster["total_mentions"] <= 20 and len(members) <= 4 and avg_sim < 0.55:
        # Check if any pair of names looks like a real translation/variant
        looks_like_translation = False
        for mi in range(len(members)):
            for mj in range(mi + 1, len(members)):
                n1 = members[mi]["name"].lower()
                n2 = members[mj]["name"].lower()
                # Substring check (e.g., "Gout" in "Hip-gout")
                if n1 in n2 or n2 in n1:
                    looks_like_translation = True
                    break
                # High pairwise similarity (e.g., açucar/azucar)
                if string_similarity(n1, n2) > 0.65:
                    looks_like_translation = True
                    break
            if looks_like_translation:
                break
        if not looks_like_translation:
            reasons.append(f"low-freq cluster, names not translations (avg sim {avg_sim:.2f})")

    return len(reasons) >= 2, reasons


def build_verification_prompt(cluster: dict) -> str:
    """Build a prompt for LLM verification of a concordance cluster."""
    lines = [
        "You are verifying a concordance of early modern medical and scientific texts.",
        "The following entities were grouped together by an embedding model as potentially",
        "referring to the same concept, person, substance, or thing.",
        "",
        f"Cluster category: {cluster['category']}",
        f"Canonical name: {cluster['canonical_name']}",
        "",
        "Members:",
    ]

    for i, member in enumerate(cluster["members"]):
        book_label = member["book_id"]
        ctx = member.get("contexts", [])
        ctx_str = f' — "{ctx[0]}"' if ctx else ""
        variants = member.get("variants", [])
        var_str = f" (variants: {', '.join(variants[:5])})" if len(variants) > 1 else ""
        lines.append(f"  {i+1}. \"{member['name']}\" [{book_label}, {member['count']}x]{var_str}{ctx_str}")

    lines.extend([
        "",
        "TASK: Which of these members actually refer to the same real-world entity?",
        "Return a JSON object with:",
        '  "keep": [list of member numbers (1-indexed) that belong together with the canonical name]',
        '  "remove": [list of member numbers that are FALSE matches and should be removed]',
        '  "reason": "brief explanation"',
        "",
        "Rules:",
        "- Spelling variants across languages ARE valid matches (e.g., Galeno/Galen, vinagre/Vinegar)",
        "- Same concept in different languages IS a valid match (e.g., sangue/Blood, febre/Fever)",
        "- Different concepts that happen to look similar are NOT valid (e.g., tristeza/Trine, terço/tres)",
        "- When in doubt, keep the match — we prefer false positives over missing real connections",
        "",
        "Return ONLY the JSON object, no other text.",
    ])

    return "\n".join(lines)


def verify_cluster(cluster: dict, client, model: str) -> dict | None:
    """Send a cluster to Gemini for verification. Returns the parsed response."""
    prompt = build_verification_prompt(cluster)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        print(f"    Warning: {e}")
        return None


def apply_verification(cluster: dict, result: dict) -> list[dict] | None:
    """Apply verification result to a cluster.

    Returns a list of clusters (may be 0 if all removed, 1 if cleaned,
    or potentially multiple if split). Returns None to keep unchanged.
    """
    if not result:
        return None

    keep_indices = result.get("keep", [])
    remove_indices = result.get("remove", [])

    if not remove_indices:
        return None  # Nothing to change

    # Convert 1-indexed to 0-indexed
    keep_set = {i - 1 for i in keep_indices if 1 <= i <= len(cluster["members"])}
    remove_set = {i - 1 for i in remove_indices if 1 <= i <= len(cluster["members"])}

    if not remove_set:
        return None

    # Build cleaned cluster with only kept members
    kept_members = [m for i, m in enumerate(cluster["members"]) if i not in remove_set]

    if len(kept_members) < 2:
        return []  # Cluster dissolved

    # Check it still spans multiple books
    books = set(m["book_id"] for m in kept_members)
    if len(books) < 2:
        return []  # No longer cross-book

    cleaned = dict(cluster)
    cleaned["members"] = kept_members
    cleaned["total_mentions"] = sum(m["count"] for m in kept_members)
    cleaned["book_count"] = len(books)

    # Filter edges to only include kept members' books
    kept_names = {(m["book_id"], m["name"]) for m in kept_members}
    cleaned["edges"] = [
        e for e in cluster.get("edges", [])
        if (e["source_book"], e["source_name"]) in kept_names
        and (e["target_book"], e["target_name"]) in kept_names
    ]

    return [cleaned]


def main():
    parser = argparse.ArgumentParser(description="Verify concordance clusters with LLM")
    parser.add_argument("--concordance", default=str(DEFAULT_PATH), help="Concordance JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Show suspicious clusters without verifying")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model to use")
    parser.add_argument("--output", help="Output file (default: overwrites input)")
    args = parser.parse_args()

    # Load concordance
    concordance_path = Path(args.concordance)
    with open(concordance_path) as f:
        data = json.load(f)

    clusters = data["clusters"]
    print(f"Loaded {len(clusters)} clusters from concordance")

    # Detect suspicious clusters
    suspicious = []
    clean = []
    for cluster in clusters:
        is_sus, reasons = is_suspicious(cluster)
        if is_sus:
            suspicious.append((cluster, reasons))
        else:
            clean.append(cluster)

    print(f"\nSuspicious clusters: {len(suspicious)} / {len(clusters)} ({len(suspicious)*100//len(clusters)}%)")
    print(f"Clean clusters: {len(clean)}")

    if args.dry_run:
        print(f"\nSuspicious clusters (top 30):")
        for cluster, reasons in suspicious[:30]:
            member_names = [m["name"] for m in cluster["members"]]
            print(f"  [{cluster['category']}] {cluster['canonical_name']} ({cluster['total_mentions']}x, {cluster['book_count']} books)")
            print(f"    Members: {', '.join(member_names[:6])}")
            print(f"    Reasons: {'; '.join(reasons)}")
        if len(suspicious) > 30:
            print(f"  ... and {len(suspicious) - 30} more")
        return

    # Initialize Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found. Set it with: export GEMINI_API_KEY=...")

    client = genai.Client(api_key=api_key)
    print(f"Using model: {args.model}")

    # Verify suspicious clusters
    verified_clusters = list(clean)  # Start with clean clusters
    removed_count = 0
    fixed_count = 0
    dissolved_count = 0

    print(f"\nVerifying {len(suspicious)} suspicious clusters...")
    for i, (cluster, reasons) in enumerate(suspicious):
        print(f"  [{i+1}/{len(suspicious)}] {cluster['canonical_name']} ({', '.join(reasons)})...", end=" ", flush=True)

        result = verify_cluster(cluster, client, args.model)

        if result is None:
            # Verification failed, keep as-is
            verified_clusters.append(cluster)
            print("kept (error)")
            continue

        applied = apply_verification(cluster, result)

        if applied is None:
            # No changes needed
            verified_clusters.append(cluster)
            print("confirmed")
        elif len(applied) == 0:
            dissolved_count += 1
            print(f"dissolved — {result.get('reason', '')}")
        else:
            orig_count = len(cluster["members"])
            new_count = sum(len(c["members"]) for c in applied)
            removed = orig_count - new_count
            if removed > 0:
                removed_count += removed
                fixed_count += 1
                print(f"fixed (removed {removed}) — {result.get('reason', '')}")
            else:
                print("confirmed")
            verified_clusters.extend(applied)

        # Rate limiting
        if (i + 1) % 10 == 0:
            time.sleep(1)

    # Sort by book_count desc, then total_mentions desc
    verified_clusters.sort(key=lambda c: (-c["book_count"], -c["total_mentions"]))

    # Reassign IDs
    for i, cluster in enumerate(verified_clusters):
        cluster["id"] = i + 1

    # Update stats
    by_category = Counter(c["category"] for c in verified_clusters)
    all_books_count = sum(1 for c in verified_clusters if c["book_count"] >= len(data["books"]))
    entities_matched = sum(len(c["members"]) for c in verified_clusters)

    data["clusters"] = verified_clusters
    data["stats"] = {
        "total_clusters": len(verified_clusters),
        "entities_matched": entities_matched,
        "clusters_all_books": all_books_count,
        "by_category": dict(by_category),
    }
    data["metadata"]["verified"] = True
    data["metadata"]["verified_model"] = args.model

    print(f"\nVerification Results:")
    print(f"  Before: {len(clusters)} clusters")
    print(f"  After:  {len(verified_clusters)} clusters")
    print(f"  Fixed: {fixed_count} clusters ({removed_count} false members removed)")
    print(f"  Dissolved: {dissolved_count} clusters (entirely false)")
    print(f"  Entities matched: {entities_matched}")
    print(f"  Clusters in all books: {all_books_count}")

    # Save
    output_path = Path(args.output) if args.output else concordance_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nSaved to: {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build a knowledge graph from entity pairs and analyze historical patterns.
Outputs:
  - graph.json: Node/edge data for visualization
  - findings.txt: Automatically detected historical patterns
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Build knowledge graph from entity pairs")
    parser.add_argument("--pairs", default="pilot/test_pairs.csv", help="Input CSV")
    parser.add_argument("--results", default="pilot/embedding_results.csv", help="Embedding results (optional)")
    parser.add_argument("--graph-out", default="pilot/graph.json", help="Output graph JSON")
    parser.add_argument("--findings-out", default="pilot/findings.txt", help="Output findings")
    args = parser.parse_args()

    df = pd.read_csv(args.pairs)

    # Try to load similarity scores if available
    try:
        results_df = pd.read_csv(args.results)
        sim_lookup = {
            (row["term_a"], row["term_b"]): row["similarity"]
            for _, row in results_df.iterrows()
        }
    except FileNotFoundError:
        sim_lookup = {}

    # Build graph structure
    nodes = {}
    edges = []

    for _, row in df.iterrows():
        # Add nodes
        for term, lang, source in [
            (row["term_a"], row["lang_a"], row["source_a"]),
            (row["term_b"], row["lang_b"], row["source_b"]),
        ]:
            if term not in nodes:
                nodes[term] = {
                    "id": term,
                    "language": lang,
                    "sources": [source],
                    "modern_id": row.get("modern_id", ""),
                }
            elif source not in nodes[term]["sources"]:
                nodes[term]["sources"].append(source)

        # Add edge
        sim = sim_lookup.get((row["term_a"], row["term_b"]), None)
        edges.append({
            "source": row["term_a"],
            "target": row["term_b"],
            "link_type": row["link_type"],
            "similarity": sim,
            "modern_id": row.get("modern_id", ""),
            "notes": row.get("notes", ""),
        })

    graph = {"nodes": list(nodes.values()), "edges": edges}
    Path(args.graph_out).write_text(json.dumps(graph, indent=2))
    print(f"Wrote graph to {args.graph_out}")

    # Analyze patterns for historical findings
    findings = []
    findings.append("=" * 60)
    findings.append("AUTOMATICALLY DETECTED HISTORICAL PATTERNS")
    findings.append("=" * 60)
    findings.append("")

    # 1. Language distribution in knowledge circulation
    findings.append("## 1. Language Distribution in Corpus")
    lang_counts = defaultdict(int)
    for node in nodes.values():
        lang_counts[node["language"]] += 1
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        findings.append(f"   {lang}: {count} terms")
    findings.append("")

    # 2. Cross-linguistic links (knowledge transfer pathways)
    findings.append("## 2. Cross-Linguistic Knowledge Transfer")
    cross_ling = defaultdict(list)
    for edge in edges:
        lang_a = nodes[edge["source"]]["language"]
        lang_b = nodes[edge["target"]]["language"]
        if lang_a != lang_b and edge["link_type"] in ("same_referent", "orthographic_variant"):
            key = tuple(sorted([lang_a, lang_b]))
            cross_ling[key].append((edge["source"], edge["target"]))

    for (lang_a, lang_b), pairs in sorted(cross_ling.items(), key=lambda x: -len(x[1])):
        findings.append(f"   {lang_a} ↔ {lang_b}: {len(pairs)} links")
        for a, b in pairs[:3]:
            findings.append(f"      • {a} ↔ {b}")
        if len(pairs) > 3:
            findings.append(f"      ... and {len(pairs) - 3} more")
    findings.append("")

    # 3. Contested identities (zones of epistemic uncertainty)
    findings.append("## 3. Zones of Epistemic Uncertainty (contested_identity)")
    contested = [e for e in edges if e["link_type"] == "contested_identity"]
    for edge in contested:
        findings.append(f"   • {edge['source']} / {edge['target']}")
        if edge["notes"]:
            findings.append(f"     Note: {edge['notes']}")
    findings.append("")

    # 4. Terminological archaeology (derivation chains)
    findings.append("## 4. Derivation Chains (terminological evolution)")
    derivations = [e for e in edges if e["link_type"] == "derivation"]
    for edge in derivations:
        findings.append(f"   {edge['source']} → {edge['target']}")
        if edge["notes"]:
            findings.append(f"     ({edge['notes']})")
    findings.append("")

    # 5. Extinction documentation
    findings.append("## 5. Extinct Species in Corpus")
    extinct_terms = set()
    for edge in edges:
        if "extinct" in str(edge.get("notes", "")).lower():
            extinct_terms.add(edge["source"])
            extinct_terms.add(edge["target"])
    for node_id in sorted(extinct_terms):
        node = nodes.get(node_id, {})
        findings.append(f"   • {node_id} ({node.get('language', '?')})")
        findings.append(f"     Sources: {', '.join(node.get('sources', []))}")
    findings.append("")

    # 6. Non-European terminology in European sources
    findings.append("## 6. Non-European Terminology Adopted by European Sources")
    non_euro_langs = {"Chinese", "Arabic", "Sanskrit", "Nahuatl", "Quechua"}
    euro_langs = {"English", "Latin", "French", "Spanish", "Portuguese", "Dutch", "German", "Italian"}

    adoptions = []
    for edge in edges:
        if edge["link_type"] in ("same_referent", "orthographic_variant", "derivation"):
            lang_a = nodes[edge["source"]]["language"]
            lang_b = nodes[edge["target"]]["language"]
            if lang_a in non_euro_langs and lang_b in euro_langs:
                adoptions.append((edge["target"], lang_b, edge["source"], lang_a))
            elif lang_b in non_euro_langs and lang_a in euro_langs:
                adoptions.append((edge["source"], lang_a, edge["target"], lang_b))

    if adoptions:
        for euro_term, euro_lang, source_term, source_lang in adoptions:
            findings.append(f"   • {euro_term} ({euro_lang}) ← {source_term} ({source_lang})")
    else:
        findings.append("   (No direct adoptions detected in current dataset)")
    findings.append("")

    # 7. Potential new historical claims
    findings.append("## 7. Potential Historical Claims from This Data")
    findings.append("")
    findings.append("   Based on the cross-linguistic links, we can make claims like:")
    findings.append("")

    # Count Chinese-English links
    chinese_english = [e for e in edges
                       if e["link_type"] == "same_referent"
                       and {nodes[e["source"]]["language"], nodes[e["target"]]["language"]} == {"Chinese", "English"}]
    if chinese_english:
        findings.append(f"   CLAIM: At least {len(chinese_english)} substances in the English pharmacopoeia")
        findings.append(f"          correspond to documented Chinese materia medica:")
        for e in chinese_english[:5]:
            findings.append(f"          • {e['source']} = {e['target']}")

    findings.append("")
    findings.append("=" * 60)

    Path(args.findings_out).write_text("\n".join(findings))
    print(f"Wrote findings to {args.findings_out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
import migrate_ground_truth as mg


def make_cluster(cluster_id: int, category: str, members: list[tuple[str, int, str]], with_gt: bool = True) -> dict:
    cluster = {
        "id": cluster_id,
        "category": category,
        "canonical_name": members[0][2],
        "total_mentions": sum(count for _, count, _ in members),
        "members": [
            {
                "book_id": book_id,
                "entity_id": entity_id,
                "name": name,
                "variants": [name],
            }
            for book_id, entity_id, name in members
        ],
    }
    if with_gt:
        cluster["ground_truth"] = {"modern_name": members[0][2]}
    return cluster


class MigrateGroundTruthTests(unittest.TestCase):
    def test_propose_match_includes_member_overlap_evidence_fields(self):
        old_clusters = [
            make_cluster(
                1,
                "PERSON",
                [("book_a", 100, "Galen"), ("book_b", 200, "Galeno")],
                with_gt=True,
            )
        ]
        indices = mg.build_indices(old_clusters)
        new_cluster = make_cluster(
            2,
            "PERSON",
            [("book_a", 100, "Galen"), ("book_c", 300, "Galenus")],
            with_gt=False,
        )

        proposal = mg.propose_match(new_cluster, old_clusters, indices)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["strategy"], "member_overlap")
        self.assertGreaterEqual(proposal["id_hits"], 1)
        self.assertIn("evidence_ratio", proposal)
        self.assertGreater(proposal["evidence_ratio"], 0.0)

    def test_resolve_mappings_allows_split_aware_member_overlap(self):
        new_clusters = [
            {"id": 1, "total_mentions": 50},
            {"id": 2, "total_mentions": 40},
            {"id": 3, "total_mentions": 30},
        ]
        proposals = [
            {
                "strategy": "member_overlap",
                "new_idx": 0,
                "old_idx": 0,
                "score": 7.0,
                "weighted_score": 7.0,
                "id_hits": 2,
                "name_hits": 2,
                "evidence_ratio": 1.0,
            },
            {
                "strategy": "member_overlap",
                "new_idx": 1,
                "old_idx": 0,
                "score": 5.0,
                "weighted_score": 5.0,
                "id_hits": 1,
                "name_hits": 1,
                "evidence_ratio": 0.5,
            },
            {
                "strategy": "modern_name",
                "new_idx": 2,
                "old_idx": 1,
                "score": 51.0,
            },
        ]

        mappings, strategy_counts, assigned_new = mg.resolve_mappings(proposals, new_clusters)
        mapped_pairs = {(m["new_idx"], m["old_idx"], m["strategy"]) for m in mappings}

        self.assertIn((0, 0, "member_overlap"), mapped_pairs)
        self.assertIn((1, 0, "member_overlap_split"), mapped_pairs)
        self.assertIn((2, 1, "modern_name"), mapped_pairs)
        self.assertEqual(strategy_counts["member_overlap_split"], 1)
        self.assertEqual(assigned_new, {0, 1, 2})


if __name__ == "__main__":
    unittest.main()

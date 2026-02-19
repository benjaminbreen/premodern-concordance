#!/usr/bin/env python3
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent))
import build_concordance as bc


def make_entity(entity_id: int, name: str, category: str, count: int = 1) -> dict:
    return {
        "id": entity_id,
        "name": name,
        "category": category,
        "subcategory": "OTHER_CONCEPT" if category == "CONCEPT" else "",
        "count": count,
        "variants": [name],
        "contexts": [],
    }


class BuildConcordanceRegressionTests(unittest.TestCase):
    def test_normalize_entity_schema_maps_extended_taxonomy_to_8_categories(self):
        entity = {
            "id": 10,
            "name": "Brain",
            "category": "ANATOMY",
            "subcategory": "ORGAN",
            "count": 3,
            "variants": ["Brain"],
            "contexts": [],
        }
        changed = bc.normalize_entity_schema(entity)
        self.assertTrue(changed)
        self.assertEqual(entity["category"], "SUBSTANCE")
        self.assertEqual(entity["subcategory"], "ANATOMY")

        org = {
            "id": 11,
            "name": "Royal Society",
            "category": "ORGANIZATION",
            "subcategory": "",
            "count": 2,
            "variants": ["Royal Society"],
            "contexts": [],
        }
        changed = bc.normalize_entity_schema(org)
        self.assertTrue(changed)
        self.assertEqual(org["category"], "CONCEPT")
        self.assertEqual(org["subcategory"], "OTHER_CONCEPT")

    def test_mutual_topk_pruning_suppresses_hub_chaining(self):
        edge_data = {
            (0, 1): {"similarity": 0.95, "exact_seed": False, "concept_family": False},
            (0, 2): {"similarity": 0.91, "exact_seed": False, "concept_family": False},
            (0, 3): {"similarity": 0.90, "exact_seed": False, "concept_family": False},
            (0, 4): {"similarity": 0.89, "exact_seed": False, "concept_family": False},
        }
        neighbors, pruned = bc.prune_edges_mutual_topk(edge_data, top_k=1)
        self.assertEqual(len(pruned), 1)
        self.assertIn((0, 1), pruned)
        self.assertEqual(neighbors[0], {1})

    def test_exact_lexical_seed_keeps_cross_book_match(self):
        book_a = [make_entity(1, "Aqua", "SUBSTANCE")]
        book_b = [make_entity(2, "aqua", "SUBSTANCE")]

        emb_a = np.array([[1.0, 0.0]], dtype=np.float32)
        emb_b = np.array([[0.0, 1.0]], dtype=np.float32)  # sim = 0.0

        matches = bc.find_cross_book_matches(
            book_a,
            emb_a,
            "a",
            book_b,
            emb_b,
            "b",
            threshold=0.90,
        )

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0]["exact_seed"])
        self.assertEqual(matches[0]["category"], "SUBSTANCE")

    def test_concept_family_requires_similarity_floor(self):
        book_a = [make_entity(1, "habit", "CONCEPT")]
        book_b = [make_entity(2, "habitual", "CONCEPT")]

        sim = 0.83
        emb_a = np.array([[1.0, 0.0]], dtype=np.float32)
        emb_b = np.array([[sim, math.sqrt(1 - sim * sim)]], dtype=np.float32)

        matches = bc.find_cross_book_matches(
            book_a,
            emb_a,
            "a",
            book_b,
            emb_b,
            "b",
            threshold=0.90,
        )

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0]["concept_family"])

    def test_concept_family_does_not_force_unrelated_prefix_terms(self):
        book_a = [make_entity(1, "habit", "CONCEPT")]
        book_b = [make_entity(2, "habitat", "CONCEPT")]

        sim = 0.83
        emb_a = np.array([[1.0, 0.0]], dtype=np.float32)
        emb_b = np.array([[sim, math.sqrt(1 - sim * sim)]], dtype=np.float32)

        matches = bc.find_cross_book_matches(
            book_a,
            emb_a,
            "a",
            book_b,
            emb_b,
            "b",
            threshold=0.90,
        )

        self.assertEqual(len(matches), 0)

    def test_person_lexical_gate_blocks_semantic_attractor_pairs(self):
        book_a = [make_entity(1, "Paracelsus", "PERSON")]
        book_b = [make_entity(2, "Borda", "PERSON")]

        sim = 0.97
        emb_a = np.array([[1.0, 0.0]], dtype=np.float32)
        emb_b = np.array([[sim, math.sqrt(1 - sim * sim)]], dtype=np.float32)

        matches = bc.find_cross_book_matches(
            book_a,
            emb_a,
            "a",
            book_b,
            emb_b,
            "b",
            threshold=0.88,
        )

        self.assertEqual(len(matches), 0)

    def test_strict_duplicate_merge_does_not_fuzzily_merge_places(self):
        clusters = [
            {
                "id": 1,
                "canonical_name": "northern hemisphere",
                "category": "PLACE",
                "book_count": 2,
                "total_mentions": 8,
                "members": [
                    {"entity_id": 1, "book_id": "book_a", "name": "northern hemisphere", "count": 4},
                    {"entity_id": 2, "book_id": "book_b", "name": "North", "count": 4},
                ],
                "edges": [],
            },
            {
                "id": 2,
                "canonical_name": "southern hemisphere",
                "category": "PLACE",
                "book_count": 2,
                "total_mentions": 7,
                "members": [
                    {"entity_id": 3, "book_id": "book_a", "name": "southern hemisphere", "count": 3},
                    {"entity_id": 4, "book_id": "book_b", "name": "South", "count": 4},
                ],
                "edges": [],
            },
        ]

        merged, merge_count = bc.merge_near_duplicates(clusters, mode="strict")
        self.assertEqual(merge_count, 0)
        self.assertEqual(len(merged), 2)

    def test_build_clusters_keeps_seeded_subgroup_inside_large_component(self):
        book_entities = {
            "book_a": [
                make_entity(1, "mind", "CONCEPT", count=500),
                make_entity(2, "habit", "CONCEPT", count=40),
            ],
            "book_b": [
                make_entity(3, "consciousness", "CONCEPT", count=300),
                make_entity(4, "Habit", "CONCEPT", count=35),
            ],
        }

        all_matches = [
            {
                "a_idx": 0,
                "b_idx": 0,
                "a_book": "book_a",
                "b_book": "book_b",
                "similarity": 0.95,
                "str_sim": bc.string_similarity("mind", "consciousness"),
                "category": "CONCEPT",
                "exact_seed": False,
                "concept_family": False,
            },
            {
                "a_idx": 1,
                "b_idx": 1,
                "a_book": "book_a",
                "b_book": "book_b",
                "similarity": 0.97,
                "str_sim": bc.string_similarity("habit", "Habit"),
                "category": "CONCEPT",
                "exact_seed": True,
                "concept_family": False,
            },
            {
                "a_idx": 1,
                "b_idx": 0,
                "a_book": "book_a",
                "b_book": "book_b",
                "similarity": 0.85,
                "str_sim": bc.string_similarity("habit", "consciousness"),
                "category": "CONCEPT",
                "exact_seed": False,
                "concept_family": False,
            },
        ]

        clusters = bc.build_clusters(all_matches, book_entities)
        self.assertGreaterEqual(len(clusters), 1)

        names = set()
        for cluster in clusters:
            for member in cluster["members"]:
                names.add(member["name"])

        self.assertIn("habit", names)
        self.assertIn("Habit", names)


if __name__ == "__main__":
    unittest.main()

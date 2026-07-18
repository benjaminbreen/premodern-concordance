from __future__ import annotations

import unittest

from premodern.retrieval import (
    EntryQuery,
    LexicalIndex,
    PassageRecord,
    reciprocal_rank_fusion,
)


def passage(identifier: str, text: str) -> PassageRecord:
    return PassageRecord(
        id=identifier,
        source_id="source-a",
        source_title="Work A",
        source_author="Author",
        publication_year=1700,
        language_label="English",
        sequence=0,
        display_text=text,
        search_text=text,
        printed_page="1",
        printed_page_end=None,
        scan_leaf=2,
        scan_leaf_end=2,
        scan_url="https://example.test/page/n2",
    )


class RetrievalTest(unittest.TestCase):
    def test_lexical_index_uses_historical_forms_and_ocr_fuzz(self) -> None:
        passages = [
            passage("a", "The quina bark reliably cures intermittent fevers."),
            passage("b", "The qvina arrived from Peru in chests."),
            passage("c", "A discussion of mechanical motion."),
            passage("d", "He prescribed aguade Inglaterra for the fever."),
        ]
        entry = EntryQuery(
            id="entry-a",
            slug="cinchona",
            preferred_label="Cinchona bark",
            scope_note="The febrifuge bark complex.",
            forms=("Cinchona bark", "quina", "qvina"),
        )
        ranked = LexicalIndex(passages).rank(entry)
        ranked_indices = [index for index, _ in ranked]
        self.assertIn(0, ranked_indices)
        self.assertIn(1, ranked_indices)
        self.assertNotIn(2, ranked_indices)

        preparation = EntryQuery(
            id="entry-b",
            slug="agua-inglaterra",
            preferred_label="Água de Inglaterra",
            scope_note="A proprietary febrifuge.",
            forms=("Água de Inglaterra",),
        )
        preparation_indices = [index for index, _ in LexicalIndex(passages).rank(preparation)]
        self.assertIn(3, preparation_indices)

    def test_rrf_rewards_agreement_without_hiding_unique_candidates(self) -> None:
        fused = reciprocal_rank_fusion(
            lexical=[(0, 100.0), (1, 90.0)],
            dense=[(1, 0.9), (2, 0.8)],
        )
        self.assertEqual(fused[0][0], 1)
        self.assertEqual({item[0] for item in fused}, {0, 1, 2})
        shared = fused[0]
        self.assertEqual(shared[2:], (2, 1))


if __name__ == "__main__":
    unittest.main()

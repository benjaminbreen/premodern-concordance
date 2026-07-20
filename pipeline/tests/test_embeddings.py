from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from premodern.db import apply_migrations, connect
from premodern.embeddings import DIMENSIONS, embedding_items, prepare_embedding_batch


class EmbeddingPreparationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.connection = connect(self.root / "authoring.sqlite")
        migrations = Path(__file__).parents[1] / "migrations" / "authoring"
        apply_migrations(self.connection, migrations)
        self.connection.execute(
            "INSERT INTO works (id, preferred_title) VALUES ('work-a', 'Work A')"
        )
        self.connection.execute(
            """
            INSERT INTO sources (
              id, work_id, title, author, publication_year, language_code,
              language_label, citation_text, archive_url, status
            ) VALUES (
              'source-a', 'work-a', 'Work A', 'Author', 1700, 'la',
              'Latin', 'Author, Work A', 'https://example.test', 'READY'
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO passages (
              id, source_id, sequence, display_text, search_text, scan_url, status
            ) VALUES (
              'passage-a', 'source-a', 0, 'Quina febrem curat.',
              'Quina febrem curat.', 'https://example.test/page/1', 'PRIVATE'
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO entries (id, slug, preferred_label, kind, scope_note, status)
            VALUES (
              'entry-a', 'cinchona', 'Cinchona bark', 'SUBSTANCE_MATERIAL',
              'The historical febrifuge bark complex.', 'CORE'
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO term_forms (id, display_form, normalized_form)
            VALUES ('term-a', 'quina', 'quina')
            """
        )
        self.connection.execute(
            """
            INSERT INTO entry_term_links (
              id, entry_id, term_form_id, relation_type, status
            ) VALUES ('link-a', 'entry-a', 'term-a', 'HISTORICAL_LABEL', 'CORE')
            """
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_items_use_asymmetric_retrieval_prefixes(self) -> None:
        items = embedding_items(self.connection)
        self.assertEqual([item.kind for item in items], ["passage", "query"])
        self.assertTrue(items[0].text.startswith("title: Work A"))
        self.assertIn("| text: Quina febrem curat.", items[0].text)
        self.assertTrue(items[1].text.startswith("task: search result | query:"))
        self.assertIn("Historical forms: quina", items[1].text)

    def test_batch_is_stable_and_dimensioned(self) -> None:
        output = self.root / "embeddings"
        first = prepare_embedding_batch(self.connection, output_dir=output)
        second = prepare_embedding_batch(self.connection, output_dir=output)
        self.assertEqual(first["requests_sha256"], second["requests_sha256"])
        self.assertEqual(first["counts"], {"passage": 1, "query": 1})

        lines = (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()
        requests = [json.loads(line) for line in lines]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["request"]["output_dimensionality"], DIMENSIONS)


if __name__ == "__main__":
    unittest.main()

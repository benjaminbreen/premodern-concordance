from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from premodern.config import Paths
from premodern.db import apply_migrations, connect
from premodern.publication import (
    PublicationError,
    audit_public_database,
    build_release,
    promote_release,
)


class PublicationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        pipeline = Path(__file__).resolve().parents[1]
        self.paths = Paths(
            repository=root,
            pipeline=pipeline,
            var=root / "var",
            authoring_db=root / "var" / "authoring.sqlite",
            public_db=root / "var" / "public.sqlite",
            releases=root / "var" / "releases",
            authoring_migrations=pipeline / "migrations" / "authoring",
            public_migrations=pipeline / "migrations" / "public",
        )
        self.authoring = connect(self.paths.authoring_db)
        apply_migrations(self.authoring, self.paths.authoring_migrations)

    def tearDown(self) -> None:
        self.authoring.close()
        self.temporary.cleanup()

    def seed_minimal_release(self) -> None:
        self.authoring.execute(
            "INSERT INTO works(id, preferred_title, original_year) VALUES ('work-1', 'A Work', 1800)"
        )
        self.authoring.execute(
            """
            INSERT INTO sources(
              id, work_id, title, publication_year, language_code, language_label,
              citation_text, archive_url, status
            ) VALUES ('source-1', 'work-1', 'A Work', 1800, 'en', 'English',
                      'Author. A Work. 1800.', 'https://example.test/source', 'PUBLISHED')
            """
        )
        self.authoring.execute(
            """
            INSERT INTO passages(
              id, source_id, sequence, display_text, search_text, scan_url, status
            ) VALUES ('passage-1', 'source-1', 1, 'A passage about electricity.',
                      'a passage about electricity.', 'https://example.test/scan', 'CORE')
            """
        )
        self.authoring.execute(
            """
            INSERT INTO entries(id, slug, preferred_label, kind, scope_note, status)
            VALUES ('entry-1', 'electricity', 'Electricity', 'PHENOMENON_PROCESS',
                    'Electrical phenomena.', 'CORE')
            """
        )
        self.authoring.execute(
            """
            INSERT INTO term_forms(id, display_form, normalized_form)
            VALUES ('term-1', 'electricity', 'electricity')
            """
        )
        self.authoring.execute(
            """
            INSERT INTO entry_term_links(
              id, entry_id, term_form_id, relation_type, status
            ) VALUES ('link-1', 'entry-1', 'term-1', 'PREFERRED_LABEL', 'CORE')
            """
        )
        self.authoring.execute(
            """
            INSERT INTO occurrences(
              id, passage_id, entry_id, term_form_id, surface_form,
              resolution_method, status
            ) VALUES ('occurrence-1', 'passage-1', 'entry-1', 'term-1',
                      'electricity', 'EDITORIAL', 'CORE')
            """
        )
        self.authoring.commit()

    def test_release_is_allowlisted_and_auditable(self) -> None:
        self.seed_minimal_release()
        manifest = build_release(self.paths, "test-release")
        promoted = promote_release(self.paths, manifest.release_id)
        audit = audit_public_database(promoted)

        self.assertEqual(audit["entry_count"], 1)
        self.assertEqual(audit["passage_count"], 1)
        public = sqlite3.connect(promoted)
        public_schema = "\n".join(
            row[0] or "" for row in public.execute("SELECT sql FROM sqlite_schema")
        )
        public.close()
        self.assertNotIn("review_decisions", public_schema)
        self.assertNotIn("model_runs", public_schema)

    def test_public_entry_without_evidence_blocks_release(self) -> None:
        self.authoring.execute(
            """
            INSERT INTO entries(id, slug, preferred_label, kind, scope_note, status)
            VALUES ('entry-1', 'empty', 'Empty', 'CONCEPT_THEORY',
                    'An unevidenced public entry.', 'CORE')
            """
        )
        self.authoring.commit()
        with self.assertRaisesRegex(PublicationError, "lack evidenced occurrences"):
            build_release(self.paths, "invalid-release")

    def test_invalid_occurrence_span_blocks_release(self) -> None:
        self.seed_minimal_release()
        self.authoring.execute(
            """
            UPDATE occurrences
            SET start_in_passage = 3, end_in_passage = 14
            WHERE id = 'occurrence-1'
            """
        )
        self.authoring.commit()
        with self.assertRaisesRegex(PublicationError, "invalid evidence spans"):
            build_release(self.paths, "invalid-span-release")


if __name__ == "__main__":
    unittest.main()

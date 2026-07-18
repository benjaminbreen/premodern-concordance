from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from premodern.analysis import (
    RESPONSE_SCHEMA,
    locate_evidence,
    prepare_analysis_batch,
    validate_analysis,
)
from premodern.db import apply_migrations, connect
from premodern.retrieval import RETRIEVAL_VERSION


class AnalysisTest(unittest.TestCase):
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
              'source-a', 'work-a', 'Work A', 'Author', 1700, 'la', 'Latin',
              'Author, Work A', 'https://example.test', 'READY'
            )
            """
        )
        for sequence, text in enumerate(
            [
                "The preceding paragraph introduces the medicine.",
                "The quina bark, brought from Peru, cures intermittent fevers.",
                "The following paragraph describes its preparation.",
            ]
        ):
            self.connection.execute(
                """
                INSERT INTO passages (
                  id, source_id, sequence, display_text, search_text, scan_url, status
                ) VALUES (?, 'source-a', ?, ?, ?, 'https://example.test/page/1', 'PRIVATE')
                """,
                (f"passage-{sequence}", sequence, text, text),
            )
        self.connection.execute(
            """
            INSERT INTO entries (id, slug, preferred_label, kind, scope_note, status)
            VALUES ('entry-a', 'cinchona', 'Cinchona bark', 'SUBSTANCE_MATERIAL',
                    'The historical febrifuge bark complex.', 'CORE')
            """
        )
        self.connection.execute(
            "INSERT INTO term_forms (id, display_form, normalized_form) VALUES ('term-a', 'quina', 'quina')"
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

    def test_evidence_locator_preserves_target_offsets(self) -> None:
        target = "The quina bark,\nbrought from Peru, cures intermittent fevers."
        self.assertEqual(locate_evidence(target, "quina bark,"), (4, 15))
        start, end = locate_evidence(
            target, "quina bark, brought from Peru, cures intermittent fevers."
        ) or (-1, -1)
        self.assertEqual(target[start:end], "quina bark,\nbrought from Peru, cures intermittent fevers.")
        self.assertIsNone(locate_evidence(target, "Jesuit's bark"))

        ocr = "les  caymans  ou    alligalors   à  museau  obtus"
        start, end = locate_evidence(
            ocr, "les caymans ou alligators à museau obtus"
        ) or (-1, -1)
        self.assertEqual(ocr[start:end], ocr)
        self.assertIsNone(
            locate_evidence(ocr, "alligators are indigenous to the Mississippi")
        )

    def test_validation_distinguishes_usage_and_grounded_claim(self) -> None:
        target = "The quina bark, brought from Peru, cures intermittent fevers."
        usage, claims, warnings = validate_analysis(
            {
                "mention_type": "NAMED",
                "resolution": "SAME_ENTRY",
                "relation_type": "NONE",
                "evidence_quote": "quina bark",
                "sense_gloss": "Peruvian bark used against intermittent fever",
                "rationale": "Quina bark directly names the historical material.",
                "confidence": 0.98,
                "claims": [
                    {
                        "claim_type": "CAUSAL_EFFECT",
                        "summary": "Quina bark cures intermittent fevers.",
                        "subject_text": "quina bark",
                        "object_text": "intermittent fevers",
                        "stance": "ASSERTS",
                        "evidence_basis": "UNSTATED",
                        "attributed_authority": "",
                        "evidence_quote": "The quina bark, brought from Peru, cures intermittent fevers.",
                        "confidence": 0.95,
                    }
                ],
            },
            target_text=target,
        )
        self.assertEqual(usage["resolution"], "SAME_ENTRY")
        self.assertEqual(usage["evidence_text"], "quina bark")
        self.assertEqual(claims[0]["evidence_text"], target)
        self.assertEqual(warnings, [])

        with self.assertRaisesRegex(ValueError, "verbatim TARGET"):
            validate_analysis(
                {
                    "mention_type": "DESCRIBED",
                    "resolution": "SAME_ENTRY",
                    "relation_type": "NONE",
                    "evidence_quote": "Jesuit's bark",
                    "sense_gloss": "A bark",
                    "rationale": "Unsupported quote.",
                    "confidence": 0.5,
                    "claims": [],
                },
                target_text=target,
            )

    def test_preparation_uses_adjacent_context_but_target_only_evidence_contract(self) -> None:
        candidate_dir = self.root / "retrieval" / RETRIEVAL_VERSION / "hybrid"
        candidate_dir.mkdir(parents=True)
        candidate = {
            "entry_id": "entry-a",
            "entry_label": "Cinchona bark",
            "rank": 1,
            "passage_id": "passage-1",
            "rrf_score": 0.03,
            "lexical_rank": 1,
            "dense_rank": 2,
        }
        (candidate_dir / "candidates.jsonl").write_text(
            json.dumps(candidate) + "\n", encoding="utf-8"
        )
        manifest = prepare_analysis_batch(self.connection, var_dir=self.root, top_k=1)
        self.assertEqual(manifest["request_count"], 1)
        item = json.loads(
            (self.root / "analysis" / "usage-claims-v1" / "items.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        self.assertIn("The preceding paragraph", item["prompt"])
        self.assertIn("The following paragraph", item["prompt"])
        self.assertIn("neither may supply an evidence quote", item["prompt"])
        request = json.loads(
            (self.root / "analysis" / "usage-claims-v1" / "requests.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        self.assertEqual(
            request["request"]["generation_config"]["response_json_schema"],
            RESPONSE_SCHEMA,
        )


if __name__ == "__main__":
    unittest.main()

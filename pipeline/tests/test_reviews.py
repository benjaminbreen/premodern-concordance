from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from premodern.reviews import export_historian_reviews


class HistorianReviewExportTest(unittest.TestCase):
    def test_export_keeps_latest_snapshot_and_generation_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_db = root / "reviews.sqlite"
            authoring_db = root / "authoring.sqlite"
            output = root / "reviews.jsonl"
            review = sqlite3.connect(review_db)
            review.executescript(
                """
                CREATE TABLE finding_review_events (
                  id TEXT PRIMARY KEY, finding_id TEXT, release_id TEXT,
                  snapshot_sha256 TEXT, snapshot_json TEXT, review_state TEXT,
                  evidence_support TEXT, research_value TEXT,
                  failure_modes_json TEXT, claim_verdicts_json TEXT,
                  note TEXT, corrected_summary TEXT, reviewer TEXT, created_at TEXT
                );
                """
            )
            snapshot = json.dumps({
                "entry": {"preferredLabel": "Machine"},
                "finding": {"id": "finding-a", "title": "A finding"},
            })
            review.executemany(
                "INSERT INTO finding_review_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("old", "finding-a", "release-1", "hash-1", snapshot, "ASSESSED",
                     "UNSUPPORTED", "BANAL", "[]", "{}", "old", "", "Historian", "2026-01-01T00:00:00Z"),
                    ("new", "finding-a", "release-1", "hash-1", snapshot, "ASSESSED",
                     "PARTLY_SUPPORTED", "PROMISING_LEAD", '["OVERSTATED_SUMMARY"]',
                     '{"claim-a":"ACCURATE"}', "new", "Better summary", "Historian", "2026-01-02T00:00:00Z"),
                ],
            )
            review.commit()
            review.close()

            authoring = sqlite3.connect(authoring_db)
            authoring.executescript(
                """
                CREATE TABLE model_runs (
                  id TEXT PRIMARY KEY, provider TEXT, model_snapshot TEXT,
                  prompt_version TEXT, schema_version TEXT, input_sha256 TEXT,
                  output_sha256 TEXT
                );
                CREATE TABLE research_findings (id TEXT PRIMARY KEY, model_run_id TEXT);
                INSERT INTO model_runs VALUES (
                  'run-a', 'GOOGLE', 'gemini-test', 'prompt-v1', 'schema-v1', 'input', 'output'
                );
                INSERT INTO research_findings VALUES ('finding-a', 'run-a');
                """
            )
            authoring.commit()
            authoring.close()

            result = export_historian_reviews(
                review_db=review_db,
                authoring_db=authoring_db,
                output_path=output,
            )
            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(records[0]["assessmentId"], "new")
            self.assertEqual(records[0]["judgment"]["researchValue"], "PROMISING_LEAD")
            self.assertEqual(records[0]["generation"]["modelRunId"], "run-a")
            self.assertTrue(output.with_suffix(".summary.json").exists())


if __name__ == "__main__":
    unittest.main()

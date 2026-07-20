from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from premodern.adapters.jamesiana import JamesianaImportError, import_public_release
from premodern.db import apply_migrations, connect


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class JamesianaAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        pipeline = Path(__file__).resolve().parents[1]
        self.connection = connect(self.root / "authoring.sqlite")
        apply_migrations(self.connection, pipeline / "migrations" / "authoring")
        self.connection.executemany(
            """
            INSERT INTO entries(id, slug, preferred_label, kind, scope_note, status)
            VALUES (?, ?, ?, 'CONCEPT_THEORY', ?, 'DRAFT')
            """,
            (
                ("entry-genius", "genius", "Genius", "Exceptional capacity."),
                ("entry-eugenics", "eugenics", "Eugenics", "A reproductive program."),
            ),
        )
        self.release_root = self.root / "public-release"
        release_dir = self.release_root / "releases" / "release-1"
        data_dir = release_dir / "data"
        data_dir.mkdir(parents=True)
        (self.release_root / "current.json").write_text(
            json.dumps({"releaseId": "release-1"}), encoding="utf-8"
        )
        sources = {
            "sources": [
                {
                    "id": "public-book",
                    "collectionStatus": "public",
                    "collectionTitle": "Public corpus",
                    "source_type": "book",
                    "title": "A Public Book",
                    "creator": "An Author",
                    "date_label": "1890",
                    "original_url": "https://archive.org/details/publicbook",
                    "metadata": {"year": 1890},
                },
                {
                    "id": "no-url-book",
                    "collectionStatus": "public",
                    "source_type": "book",
                    "title": "No Stable Edition",
                    "creator": "An Author",
                    "date_label": "1880",
                    "metadata": {"year": 1880},
                },
                {
                    "id": "private-book",
                    "collectionStatus": "private",
                    "source_type": "book",
                    "title": "Private Book",
                    "creator": "An Author",
                    "date_label": "1880",
                    "original_url": "https://example.test/private",
                    "metadata": {"year": 1880},
                },
            ]
        }
        sources_path = data_dir / "public-sources.json"
        sources_path.write_text(json.dumps(sources), encoding="utf-8")
        chunks = [
            {
                "id": 1,
                "passageId": "chunk-1",
                "sourceId": "public-book",
                "text": "Natural genius was discussed here, but eugenics was kept distinct.",
                "page": 12,
                "iaId": "publicbook",
                "leaf": 20,
            },
            {
                "id": 2,
                "passageId": "chunk-2",
                "sourceId": "no-url-book",
                "text": "Genius appears, but this witness has no public edition.",
            },
            {
                "id": 3,
                "passageId": "chunk-3",
                "sourceId": "private-book",
                "text": "Genius appears in private material.",
            },
        ]
        index_path = data_dir / "index.from-db.json.gz"
        with gzip.open(index_path, "wt", encoding="utf-8") as handle:
            json.dump(chunks, handle)
        manifest = {
            "releaseId": "release-1",
            "artifacts": [
                {"path": sources_path.name, "sha256": sha256(sources_path)},
                {"path": index_path.name, "sha256": sha256(index_path)},
                {
                    "path": "embeddings.f32",
                    "sha256": "not-read-by-the-adapter",
                },
            ],
        }
        (release_dir / "release-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_import_uses_only_citable_public_sources(self) -> None:
        result = import_public_release(
            self.connection, public_release_root=self.release_root
        )

        self.assertEqual(result["release_id"], "release-1")
        self.assertEqual(result["eligible_sources"], 1)
        self.assertEqual(result["sources_imported"], 1)
        self.assertEqual(result["passages_imported"], 1)
        self.assertEqual(result["occurrences_imported"], 2)
        source = self.connection.execute(
            "SELECT * FROM sources WHERE origin_system = 'william-jamesiana'"
        ).fetchone()
        self.assertEqual(source["origin_release_id"], "release-1")
        self.assertEqual(
            source["archive_url"], "https://archive.org/details/publicbook"
        )
        statuses = {
            row["status"]
            for row in self.connection.execute("SELECT status FROM occurrences")
        }
        self.assertEqual(statuses, {"SUGGESTED"})
        scan_url = self.connection.execute(
            "SELECT scan_url FROM passages"
        ).fetchone()["scan_url"]
        self.assertEqual(
            scan_url,
            "https://archive.org/details/publicbook/page/n20/mode/1up",
        )

    def test_hash_mismatch_blocks_import(self) -> None:
        sources_path = (
            self.release_root
            / "releases"
            / "release-1"
            / "data"
            / "public-sources.json"
        )
        sources_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(JamesianaImportError, "hash differs"):
            import_public_release(
                self.connection, public_release_root=self.release_root
            )


if __name__ == "__main__":
    unittest.main()

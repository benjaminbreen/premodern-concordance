from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Paths
from .db import apply_migrations, connect


PUBLIC_STATUSES = ("CORE", "SUGGESTED")
SCHEMA_VERSION = "6"


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    schema_version: str
    created_at: str
    public_db_sha256: str
    source_count: int
    passage_count: int
    entry_count: int
    occurrence_count: int
    usage_count: int
    claim_count: int


class PublicationError(RuntimeError):
    pass


def _copy_rows(
    authoring: sqlite3.Connection,
    public: sqlite3.Connection,
    *,
    select_sql: str,
    insert_sql: str,
    parameters: tuple[object, ...] = PUBLIC_STATUSES,
) -> int:
    rows = authoring.execute(select_sql, parameters).fetchall()
    if rows:
        public.executemany(insert_sql, [tuple(row) for row in rows])
    return len(rows)


def _validate_authoring(authoring: sqlite3.Connection) -> None:
    problems: list[str] = []
    bad_occurrences = authoring.execute(
        """
        SELECT o.id
        FROM occurrences o
        JOIN passages p ON p.id = o.passage_id
        JOIN entries e ON e.id = o.entry_id
        JOIN sources s ON s.id = p.source_id
        WHERE o.status IN ('CORE', 'SUGGESTED')
          AND (p.status NOT IN ('CORE', 'SUGGESTED')
               OR e.status NOT IN ('CORE', 'SUGGESTED')
               OR s.status <> 'PUBLISHED')
        """
    ).fetchall()
    if bad_occurrences:
        problems.append(f"{len(bad_occurrences)} public occurrences depend on private records")

    invalid_spans = authoring.execute(
        """
        SELECT o.id
        FROM occurrences o
        JOIN passages p ON p.id = o.passage_id
        WHERE o.status IN ('CORE', 'SUGGESTED')
          AND (
            (o.start_in_passage IS NULL) <> (o.end_in_passage IS NULL)
            OR o.start_in_passage < 0
            OR o.end_in_passage <= o.start_in_passage
            OR o.end_in_passage > length(p.display_text)
            OR substr(
                 p.display_text,
                 o.start_in_passage + 1,
                 o.end_in_passage - o.start_in_passage
               ) <> o.surface_form
          )
        """
    ).fetchall()
    if invalid_spans:
        problems.append(f"{len(invalid_spans)} public occurrences have invalid evidence spans")

    bad_usages = authoring.execute(
        """
        SELECT u.id
        FROM contextual_usages u
        JOIN passages p ON p.id = u.passage_id
        JOIN entries e ON e.id = u.entry_id
        JOIN sources s ON s.id = p.source_id
        WHERE u.status IN ('CORE', 'SUGGESTED')
          AND (p.status NOT IN ('CORE', 'SUGGESTED')
               OR e.status NOT IN ('CORE', 'SUGGESTED')
               OR s.status <> 'PUBLISHED')
        """
    ).fetchall()
    if bad_usages:
        problems.append(f"{len(bad_usages)} public usages depend on private records")

    invalid_usage_spans = authoring.execute(
        """
        SELECT u.id
        FROM contextual_usages u
        JOIN passages p ON p.id = u.passage_id
        WHERE u.status IN ('CORE', 'SUGGESTED')
          AND (
            u.evidence_start IS NULL OR u.evidence_end IS NULL OR u.evidence_text IS NULL
            OR u.evidence_start < 0 OR u.evidence_end <= u.evidence_start
            OR u.evidence_end > length(p.display_text)
            OR substr(p.display_text, u.evidence_start + 1,
                      u.evidence_end - u.evidence_start) <> u.evidence_text
          )
        """
    ).fetchall()
    if invalid_usage_spans:
        problems.append(f"{len(invalid_usage_spans)} public usages have invalid evidence spans")

    invalid_claim_spans = authoring.execute(
        """
        SELECT c.id
        FROM usage_claims c
        JOIN contextual_usages u ON u.id = c.usage_id
        JOIN passages p ON p.id = u.passage_id
        WHERE c.status IN ('CORE', 'SUGGESTED')
          AND (
            u.status NOT IN ('CORE', 'SUGGESTED')
            OR c.evidence_start < 0 OR c.evidence_end <= c.evidence_start
            OR c.evidence_end > length(p.display_text)
            OR substr(p.display_text, c.evidence_start + 1,
                      c.evidence_end - c.evidence_start) <> c.evidence_text
          )
        """
    ).fetchall()
    if invalid_claim_spans:
        problems.append(f"{len(invalid_claim_spans)} public claims have invalid evidence spans")

    empty_senses = authoring.execute(
        """
        SELECT s.id
        FROM sense_clusters s
        LEFT JOIN sense_memberships m
          ON m.sense_id = s.id AND m.status IN ('CORE', 'SUGGESTED')
        WHERE s.status IN ('CORE', 'SUGGESTED')
        GROUP BY s.id
        HAVING COUNT(m.usage_id) = 0
        """
    ).fetchall()
    if empty_senses:
        problems.append(f"{len(empty_senses)} public sense clusters lack usages")

    unsupported_findings = authoring.execute(
        """
        SELECT f.id
        FROM research_findings f
        LEFT JOIN finding_claims fc
          ON fc.finding_id = f.id AND fc.status IN ('CORE', 'SUGGESTED')
        WHERE f.status IN ('CORE', 'SUGGESTED')
        GROUP BY f.id
        HAVING COUNT(fc.claim_id) < 2
        """
    ).fetchall()
    if unsupported_findings:
        problems.append(f"{len(unsupported_findings)} public findings lack two claim links")

    missing_evidence = authoring.execute(
        """
        SELECT r.id
        FROM entry_relations r
        LEFT JOIN relation_evidence re ON re.relation_id = r.id
        WHERE r.status IN ('CORE', 'SUGGESTED')
        GROUP BY r.id
        HAVING COUNT(re.passage_id) = 0
        """
    ).fetchall()
    if missing_evidence:
        problems.append(f"{len(missing_evidence)} public relations lack evidence")

    unlinked_entries = authoring.execute(
        """
        SELECT e.id
        FROM entries e
        LEFT JOIN occurrences o
          ON o.entry_id = e.id AND o.status IN ('CORE', 'SUGGESTED')
        WHERE e.status IN ('CORE', 'SUGGESTED')
        GROUP BY e.id
        HAVING COUNT(o.id) = 0 AND NOT EXISTS (
          SELECT 1 FROM contextual_usages u
          WHERE u.entry_id = e.id AND u.status IN ('CORE', 'SUGGESTED')
        )
        """
    ).fetchall()
    if unlinked_entries:
        problems.append(f"{len(unlinked_entries)} public entries lack evidenced occurrences")

    if problems:
        raise PublicationError("; ".join(problems))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_source_objects(
    authoring: sqlite3.Connection,
    release_dir: Path,
) -> None:
    for row in authoring.execute(
        """
        SELECT id, text_path, text_sha256, public_text_object_key
        FROM sources s
        WHERE s.status = 'PUBLISHED' AND s.public_text_object_key IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM passages p
            WHERE p.source_id = s.id AND p.status IN ('CORE', 'SUGGESTED')
          )
        """
    ):
        source_path = Path(row["text_path"] or "")
        if not source_path.is_file():
            raise PublicationError(f"source text is missing for {row['id']}")
        actual_hash = _sha256(source_path)
        if row["text_sha256"] and row["text_sha256"] != actual_hash:
            raise PublicationError(f"source text hash differs for {row['id']}")
        destination = release_dir / "objects" / row["public_text_object_key"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)


def build_release(paths: Paths, release_id: str | None = None) -> ReleaseManifest:
    release_id = release_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    release_dir = paths.releases / release_id
    if release_dir.exists():
        raise PublicationError(f"release already exists: {release_id}")
    release_dir.mkdir(parents=True)
    staging_db = release_dir / "public.sqlite"

    authoring = connect(paths.authoring_db)
    apply_migrations(authoring, paths.authoring_migrations)
    _validate_authoring(authoring)
    _stage_source_objects(authoring, release_dir)
    public = connect(staging_db)
    apply_migrations(public, paths.public_migrations)

    try:
        public.execute("BEGIN")
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT id, preferred_title, original_year
              FROM works
              WHERE id IN (
                SELECT s.work_id FROM sources s
                WHERE s.status = 'PUBLISHED'
                  AND EXISTS (
                    SELECT 1 FROM passages p
                    WHERE p.source_id = s.id AND p.status IN ('CORE', 'SUGGESTED')
                  )
              )
            """,
            insert_sql="INSERT INTO works VALUES (?, ?, ?)",
            parameters=(),
        )
        source_count = _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT id, work_id, title, author, publication_year, original_year,
                     language_code, language_label, edition_statement, citation_text,
                     archive_provider, archive_url, word_count, origin_system,
                     origin_id, origin_release_id, public_text_object_key, text_sha256
              FROM sources s
              WHERE s.status = 'PUBLISHED'
                AND EXISTS (
                  SELECT 1 FROM passages p
                  WHERE p.source_id = s.id AND p.status IN ('CORE', 'SUGGESTED')
                )
            """,
            insert_sql="INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            parameters=(),
        )
        passage_count = _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT p.id, p.source_id, p.sequence, p.start_offset, p.end_offset,
                     p.printed_page, p.scan_leaf, p.display_text, p.scan_url, p.status,
                     p.heading, p.printed_page_end, p.scan_leaf_end, p.alignment_method
              FROM passages p JOIN sources s ON s.id = p.source_id
              WHERE p.status IN (?, ?) AND s.status = 'PUBLISHED'
            """,
            insert_sql="""
              INSERT INTO passages (
                id, source_id, sequence, start_offset, end_offset, printed_page,
                scan_leaf, display_text, scan_url, status, heading,
                printed_page_end, scan_leaf_end, alignment_method
              ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
        )

        entry_rows = authoring.execute(
            """
            SELECT e.id, e.slug, e.preferred_label, e.kind, e.scope_note,
                   e.exclusions_note, e.external_ids_json, e.status,
                   COUNT(DISTINCT evidence.source_id), COUNT(DISTINCT evidence.passage_id),
                   MIN(evidence.publication_year), MAX(evidence.publication_year)
            FROM entries e
            JOIN (
              SELECT o.entry_id, p.id AS passage_id, s.id AS source_id,
                     s.publication_year
              FROM occurrences o
              JOIN passages p ON p.id = o.passage_id
                AND p.status IN ('CORE', 'SUGGESTED')
              JOIN sources s ON s.id = p.source_id AND s.status = 'PUBLISHED'
              WHERE o.status IN (?, ?)
              UNION
              SELECT u.entry_id, p.id AS passage_id, s.id AS source_id,
                     s.publication_year
              FROM contextual_usages u
              JOIN passages p ON p.id = u.passage_id
                AND p.status IN ('CORE', 'SUGGESTED')
              JOIN sources s ON s.id = p.source_id AND s.status = 'PUBLISHED'
              WHERE u.status IN (?, ?)
            ) evidence ON evidence.entry_id = e.id
            WHERE e.status IN ('CORE', 'SUGGESTED')
            GROUP BY e.id
            """,
            (*PUBLIC_STATUSES, *PUBLIC_STATUSES),
        ).fetchall()
        public.executemany(
            "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(row) for row in entry_rows],
        )
        entry_count = len(entry_rows)

        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT DISTINCT t.id, t.display_form, t.normalized_form, t.language_code,
                              t.earliest_year, t.latest_year, t.notes
              FROM term_forms t
              JOIN entry_term_links l ON l.term_form_id = t.id
              JOIN entries e ON e.id = l.entry_id
              WHERE l.status IN (?, ?) AND e.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO term_forms VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT l.id, l.entry_id, l.term_form_id, l.relation_type, l.rationale,
                     l.status, l.confidence
              FROM entry_term_links l
              JOIN entries e ON e.id = l.entry_id
              WHERE l.status IN (?, ?) AND e.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO entry_term_links VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        occurrence_count = _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT o.id, o.passage_id, o.entry_id, o.term_form_id, o.surface_form,
                     o.start_in_passage, o.end_in_passage, o.resolution_method,
                     o.confidence, o.status
              FROM occurrences o
              JOIN passages p ON p.id = o.passage_id
              JOIN entries e ON e.id = o.entry_id
              WHERE o.status IN (?, ?) AND p.status IN ('CORE', 'SUGGESTED')
                AND e.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        usage_count = _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT u.id, u.entry_id, u.passage_id, u.mention_type, u.resolution,
                     u.relation_type, u.evidence_start, u.evidence_end,
                     u.evidence_text, u.sense_gloss, u.rationale, u.confidence,
                     u.retrieval_method, u.retrieval_rank, u.status
              FROM contextual_usages u
              JOIN passages p ON p.id = u.passage_id
              JOIN entries e ON e.id = u.entry_id
              WHERE u.status IN (?, ?) AND p.status IN ('CORE', 'SUGGESTED')
                AND e.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO contextual_usages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        claim_count = _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT c.id, c.usage_id, c.claim_index, c.claim_type, c.summary,
                     c.subject_text, c.object_text, c.stance, c.evidence_basis,
                     c.attributed_authority, c.evidence_start, c.evidence_end,
                     c.evidence_text, c.confidence, c.status
              FROM usage_claims c
              JOIN contextual_usages u ON u.id = c.usage_id
              WHERE c.status IN (?, ?) AND u.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO usage_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT s.id, s.entry_id, s.label, s.definition, s.sort_order,
                     s.confidence, s.status
              FROM sense_clusters s
              JOIN entries e ON e.id = s.entry_id
              WHERE s.status IN (?, ?) AND e.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO sense_clusters VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT m.sense_id, m.usage_id, m.status
              FROM sense_memberships m
              JOIN sense_clusters s ON s.id = m.sense_id
              JOIN contextual_usages u ON u.id = m.usage_id
              WHERE m.status IN (?, ?) AND s.status IN ('CORE', 'SUGGESTED')
                AND u.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO sense_memberships VALUES (?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT f.id, f.entry_id, f.finding_type, f.title, f.summary,
                     f.sort_order, f.confidence, f.status
              FROM research_findings f
              JOIN entries e ON e.id = f.entry_id
              WHERE f.status IN (?, ?) AND e.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO research_findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT fc.finding_id, fc.claim_id, fc.role, fc.status
              FROM finding_claims fc
              JOIN research_findings f ON f.id = fc.finding_id
              JOIN usage_claims c ON c.id = fc.claim_id
              WHERE fc.status IN (?, ?) AND f.status IN ('CORE', 'SUGGESTED')
                AND c.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO finding_claims VALUES (?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT r.id, r.source_entry_id, r.target_entry_id, r.layer,
                     r.relation_type, r.rationale, r.non_claim, r.confidence, r.status
              FROM entry_relations r
              JOIN entries se ON se.id = r.source_entry_id
              JOIN entries te ON te.id = r.target_entry_id
              WHERE r.status IN (?, ?) AND se.status IN ('CORE', 'SUGGESTED')
                AND te.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO entry_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT re.relation_id, re.passage_id, re.note
              FROM relation_evidence re
              JOIN entry_relations r ON r.id = re.relation_id
              JOIN passages p ON p.id = re.passage_id
              WHERE r.status IN (?, ?)
                AND p.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO relation_evidence VALUES (?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT id, slug, preferred_label, kind, description,
                     external_ids_json, status
              FROM supporting_entities WHERE status IN (?, ?)
            """,
            insert_sql="INSERT INTO supporting_entities VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        _copy_rows(
            authoring,
            public,
            select_sql="""
              SELECT m.id, m.supporting_entity_id, m.passage_id, m.surface_form, m.status
              FROM supporting_mentions m
              JOIN supporting_entities e ON e.id = m.supporting_entity_id
              JOIN passages p ON p.id = m.passage_id
              WHERE m.status IN (?, ?) AND e.status IN ('CORE', 'SUGGESTED')
                AND p.status IN ('CORE', 'SUGGESTED')
            """,
            insert_sql="INSERT INTO supporting_mentions VALUES (?, ?, ?, ?, ?)",
        )

        public.execute(
            """
            INSERT INTO entry_search(entry_id, slug, preferred_label, term_label, scope_note)
            SELECT e.id, e.slug, e.preferred_label, COALESCE(t.display_form, ''), e.scope_note
            FROM entries e
            LEFT JOIN entry_term_links l ON l.entry_id = e.id
            LEFT JOIN term_forms t ON t.id = l.term_form_id
            """
        )
        created_at = datetime.now(UTC).isoformat()
        public.execute(
            """
            INSERT INTO release_metadata (
              id, schema_version, created_at, source_count, passage_count,
              entry_count, occurrence_count, usage_count, claim_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                release_id,
                SCHEMA_VERSION,
                created_at,
                source_count,
                passage_count,
                entry_count,
                occurrence_count,
                usage_count,
                claim_count,
            ),
        )
        public.commit()
        public.execute("PRAGMA optimize")
        public.execute("VACUUM")
    finally:
        public.close()

    database_hash = _sha256(staging_db)
    manifest = ReleaseManifest(
        release_id=release_id,
        schema_version=SCHEMA_VERSION,
        created_at=created_at,
        public_db_sha256=database_hash,
        source_count=source_count,
        passage_count=passage_count,
        entry_count=entry_count,
        occurrence_count=occurrence_count,
        usage_count=usage_count,
        claim_count=claim_count,
    )
    manifest_path = release_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    authoring.execute(
        """
        INSERT INTO releases (
          id, schema_version, manifest_path, public_db_sha256, source_count,
          passage_count, entry_count, occurrence_count, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'VALIDATED')
        """,
        (
            release_id,
            SCHEMA_VERSION,
            str(manifest_path),
            database_hash,
            source_count,
            passage_count,
            entry_count,
            occurrence_count,
        ),
    )
    authoring.commit()
    authoring.close()
    return manifest


def promote_release(paths: Paths, release_id: str) -> Path:
    release_dir = paths.releases / release_id
    source = release_dir / "public.sqlite"
    manifest_path = release_dir / "manifest.json"
    if not source.exists() or not manifest_path.exists():
        raise PublicationError(f"validated release is incomplete: {release_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(source) != manifest["public_db_sha256"]:
        raise PublicationError("public database hash differs from release manifest")

    paths.public_db.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=paths.public_db.parent, prefix="public-", suffix=".sqlite", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, paths.public_db)
    finally:
        temporary_path.unlink(missing_ok=True)

    promoted_objects = paths.var / "objects"
    staged_objects = release_dir / "objects"
    if staged_objects.exists():
        replacement = paths.var / f"objects-{release_id}.tmp"
        shutil.rmtree(replacement, ignore_errors=True)
        shutil.copytree(staged_objects, replacement)
        shutil.rmtree(promoted_objects, ignore_errors=True)
        os.replace(replacement, promoted_objects)

    authoring = connect(paths.authoring_db)
    authoring.execute(
        "UPDATE releases SET status = 'PROMOTED', promoted_at = CURRENT_TIMESTAMP WHERE id = ?",
        (release_id,),
    )
    authoring.commit()
    authoring.close()
    return paths.public_db


def audit_public_database(path: Path) -> dict[str, int | str]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    metadata = connection.execute("SELECT * FROM release_metadata").fetchone()
    if metadata is None:
        raise PublicationError("public database has no release metadata")
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise PublicationError(f"SQLite integrity check failed: {integrity}")

    actual = {
        "source_count": connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "passage_count": connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0],
        "entry_count": connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
        "occurrence_count": connection.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0],
        "usage_count": connection.execute("SELECT COUNT(*) FROM contextual_usages").fetchone()[0],
        "claim_count": connection.execute("SELECT COUNT(*) FROM usage_claims").fetchone()[0],
    }
    for key, value in actual.items():
        if value != metadata[key]:
            raise PublicationError(f"{key} drift: metadata={metadata[key]}, actual={value}")

    leaks = connection.execute(
        "SELECT COUNT(*) FROM sqlite_schema WHERE sql LIKE '%model_run%' OR sql LIKE '%review_decision%'"
    ).fetchone()[0]
    if leaks:
        raise PublicationError("private authoring fields leaked into public schema")
    connection.close()
    return {"release_id": metadata["id"], **actual}

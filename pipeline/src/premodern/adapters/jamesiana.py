from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .legacy import normalize, stable_id


ALLOWED_SOURCE_TYPES = {"book", "article", "essay", "lecture"}
YEAR_MINIMUM = 1500
YEAR_MAXIMUM = 1950


@dataclass(frozen=True)
class TermRule:
    entry_id: str
    relation_type: str
    pattern: re.Pattern[str]


TERM_RULES = (
    TermRule("entry-alligator", "PREFERRED_LABEL", re.compile(r"\balligators?\b", re.I)),
    TermRule("entry-cinchona-bark", "HISTORICAL_LABEL", re.compile(r"\bcinchona(?:\s+bark)?\b", re.I)),
    TermRule("entry-agua-inglaterra", "PREFERRED_LABEL", re.compile(r"\b[aá]gua\s+de\s+inglaterra\b", re.I)),
    TermRule("entry-engineer", "PREFERRED_LABEL", re.compile(r"\bengineers?\b", re.I)),
    TermRule("entry-machine", "PREFERRED_LABEL", re.compile(r"\bmachines?\b", re.I)),
    TermRule("entry-consciousness", "PREFERRED_LABEL", re.compile(r"\bconsciousness\b", re.I)),
    TermRule("entry-cosmos", "PREFERRED_LABEL", re.compile(r"\bcosmos\b", re.I)),
    TermRule("entry-homo-sapiens", "PREFERRED_LABEL", re.compile(r"\bhomo\s+sapiens\b", re.I)),
    TermRule("entry-human-species", "PREFERRED_LABEL", re.compile(r"\bhuman\s+species\b", re.I)),
    TermRule("entry-evolution", "PREFERRED_LABEL", re.compile(r"\bevolution\b", re.I)),
    TermRule(
        "entry-transmutation-species",
        "PREFERRED_LABEL",
        re.compile(r"\btransmutation\s+of\s+(?:the\s+)?species\b", re.I),
    ),
    TermRule("entry-genius", "PREFERRED_LABEL", re.compile(r"\bgenius(?:es)?\b", re.I)),
    TermRule("entry-intelligence", "PREFERRED_LABEL", re.compile(r"\bintelligence\b", re.I)),
    TermRule(
        "entry-mental-measurement",
        "PREFERRED_LABEL",
        re.compile(
            r"\b(?:mental\s+(?:measurement|measurements|tests?)|measurement\s+of\s+(?:the\s+)?(?:mind|mental\s+(?:capacity|faculties)))\b",
            re.I,
        ),
    ),
    TermRule("entry-eugenics", "DERIVED_FORM", re.compile(r"\beugenics?\b|\beugenic\b", re.I)),
    TermRule("entry-melancholy", "PREFERRED_LABEL", re.compile(r"\bmelancholy\b", re.I)),
    TermRule("entry-contagion", "PREFERRED_LABEL", re.compile(r"\bcontagion\b", re.I)),
    TermRule("entry-electricity", "PREFERRED_LABEL", re.compile(r"\belectricity\b", re.I)),
)


class JamesianaImportError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(release_dir: Path, relative_path: str) -> Path:
    direct = release_dir / relative_path
    nested = release_dir / "data" / relative_path
    if direct.is_file():
        return direct
    if nested.is_file():
        return nested
    raise JamesianaImportError(f"public release artifact is missing: {relative_path}")


def _verified_public_release(public_release_root: Path) -> tuple[str, Path, Path, Path]:
    pointer_path = public_release_root / "current.json"
    if not pointer_path.is_file():
        raise JamesianaImportError(f"Jamesiana public release pointer is missing: {pointer_path}")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    release_id = str(pointer.get("releaseId") or "")
    if not release_id or not re.fullmatch(r"[a-zA-Z0-9._-]+", release_id):
        raise JamesianaImportError("Jamesiana current.json has an invalid releaseId")

    release_dir = public_release_root / "releases" / release_id
    manifest_path = release_dir / "release-manifest.json"
    if not manifest_path.is_file():
        raise JamesianaImportError(f"Jamesiana release manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("releaseId")) != release_id:
        raise JamesianaImportError("Jamesiana pointer and manifest release IDs differ")

    artifacts = {
        str(item.get("path")): str(item.get("sha256"))
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    required = ("public-sources.json", "index.from-db.json.gz")
    verified: list[Path] = []
    for relative_path in required:
        expected_hash = artifacts.get(relative_path)
        if not expected_hash:
            raise JamesianaImportError(
                f"Jamesiana manifest does not hash required artifact: {relative_path}"
            )
        path = _artifact_path(release_dir, relative_path)
        if _sha256(path) != expected_hash:
            raise JamesianaImportError(f"Jamesiana artifact hash differs: {relative_path}")
        verified.append(path)
    return release_id, release_dir, verified[0], verified[1]


def _year(source: dict[str, Any]) -> int | None:
    candidates = (source.get("metadata", {}).get("year"), source.get("date_label"))
    for candidate in candidates:
        match = re.search(r"\b(1[5-9]\d{2})\b", str(candidate or ""))
        if match:
            return int(match.group(1))
    return None


def _stable_public_url(source: dict[str, Any]) -> str | None:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    candidate = source.get("original_url") or metadata.get("sourceUrl")
    if not isinstance(candidate, str):
        return None
    parsed = urlparse(candidate)
    return candidate if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _eligible_sources(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    eligible: dict[str, dict[str, Any]] = {}
    for source in payload.get("sources", []):
        if not isinstance(source, dict) or source.get("collectionStatus") != "public":
            continue
        if str(source.get("source_type") or "").casefold() not in ALLOWED_SOURCE_TYPES:
            continue
        year = _year(source)
        url = _stable_public_url(source)
        if year is None or not YEAR_MINIMUM <= year <= YEAR_MAXIMUM or url is None:
            continue
        eligible[str(source["id"])] = source
    return eligible


def _archive_fields(url: str) -> tuple[str, str | None]:
    match = re.search(r"archive\.org/details/([^/?#]+)", url)
    if match:
        return "Internet Archive", match.group(1)
    if "gutenberg.org" in url:
        return "Project Gutenberg", None
    return "External digital edition", None


def _language(source: dict[str, Any]) -> tuple[str, str]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    language = str(metadata.get("language") or "English")
    codes = {
        "english": "en",
        "french": "fr",
        "german": "de",
        "italian": "it",
        "latin": "la",
        "portuguese": "pt",
        "spanish": "es",
    }
    return codes.get(language.casefold(), "und"), language


def _citation(source: dict[str, Any], year: int) -> str:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    creator = str(source.get("creator") or metadata.get("authorName") or "Anonymous")
    title = str(source.get("title") or "Untitled")
    publication = str(metadata.get("originalPublication") or "").strip()
    suffix = f" {publication}" if publication else ""
    title_punctuation = "" if title.endswith((".", "?", "!")) else "."
    return f"{creator}. {title}{title_punctuation} {year}.{suffix}".strip()


def _source_and_work_ids(
    connection: sqlite3.Connection, source: dict[str, Any], url: str
) -> tuple[str, str]:
    existing_url = connection.execute(
        "SELECT id, work_id FROM sources WHERE archive_url = ?", (url,)
    ).fetchone()
    if existing_url:
        return str(existing_url["id"]), str(existing_url["work_id"])

    title = str(source.get("title") or "Untitled")
    author = str(source.get("creator") or source.get("metadata", {}).get("authorName") or "")
    same_work = connection.execute(
        """
        SELECT work_id
        FROM sources
        WHERE lower(title) = lower(?) AND lower(coalesce(author, '')) = lower(?)
        ORDER BY publication_year
        LIMIT 1
        """,
        (title, author),
    ).fetchone()
    work_id = (
        str(same_work["work_id"])
        if same_work
        else stable_id("work", "william-jamesiana", source.get("id"))
    )
    return stable_id("source", "william-jamesiana", source.get("id"), url), work_id


def _upsert_source(
    connection: sqlite3.Connection,
    source: dict[str, Any],
    release_id: str,
) -> tuple[str, str]:
    url = _stable_public_url(source)
    year = _year(source)
    if url is None or year is None:
        raise JamesianaImportError("ineligible Jamesiana source reached insertion")
    source_id, work_id = _source_and_work_ids(connection, source, url)
    title = str(source.get("title") or "Untitled")
    author = str(source.get("creator") or source.get("metadata", {}).get("authorName") or "Anonymous")
    language_code, language_label = _language(source)
    provider, item_id = _archive_fields(url)
    connection.execute(
        """
        INSERT INTO works (id, preferred_title, original_year)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          preferred_title = excluded.preferred_title,
          original_year = coalesce(works.original_year, excluded.original_year)
        """,
        (work_id, title, year),
    )
    connection.execute(
        """
        INSERT INTO sources (
          id, work_id, title, author, publication_year, original_year,
          language_code, language_label, citation_text, archive_provider,
          archive_item_id, archive_url, rights_status, origin_system, origin_id,
          origin_release_id, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PUBLIC_DOMAIN',
                  'william-jamesiana', ?, ?, 'PUBLISHED')
        ON CONFLICT(id) DO UPDATE SET
          citation_text = excluded.citation_text,
          archive_url = excluded.archive_url,
          origin_release_id = excluded.origin_release_id,
          status = 'PUBLISHED'
        """,
        (
            source_id,
            work_id,
            title,
            author,
            year,
            year,
            language_code,
            language_label,
            _citation(source, year),
            provider,
            item_id,
            url,
            str(source["id"]),
            release_id,
        ),
    )
    return source_id, work_id


def _scan_url(source_url: str, chunk: dict[str, Any]) -> str:
    archive_id = chunk.get("iaId")
    leaf = chunk.get("leaf")
    if archive_id and isinstance(leaf, int) and leaf >= 0:
        return f"https://archive.org/details/{archive_id}/page/n{leaf}/mode/1up"
    return source_url


def _chunks(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise JamesianaImportError("Jamesiana public index is not an array")
    for chunk in payload:
        if isinstance(chunk, dict):
            yield chunk


def _first_contextual_match(rule: TermRule, text: str) -> re.Match[str] | None:
    for match in rule.pattern.finditer(text):
        if rule.entry_id != "entry-genius":
            return match
        if normalize(match.group(0)) == "geniuses":
            return match
        before = text[max(0, match.start() - 90) : match.start()]
        after = text[match.end() : min(len(text), match.end() + 90)]
        context = f"{before} {match.group(0)} {after}"
        collective_sense = re.match(
            r"\s+of\s+(?:an?\s+|the\s+)?(?:age|century|christianity|country|democracy|institution|language|nation|people|place|race|religion|republic|time)",
            after,
            flags=re.I,
        )
        capacity_sense = re.search(
            r"\b(?:artist|author|child|creative|exceptional|gift|individual|intellect|intellectual|inventor|man|men|mind|natural|original|person|poet|talent)\b",
            context,
            flags=re.I,
        )
        if not collective_sense and capacity_sense:
            return match
    return None


def import_public_release(
    connection: sqlite3.Connection,
    *,
    public_release_root: Path,
    max_passages_per_source_entry: int = 2,
) -> dict[str, int | str]:
    """Import suggestions from Jamesiana's signed public boundary only.

    This adapter intentionally reads exactly two release artifacts: public source
    metadata and passage text. It never opens Jamesiana's authoring database or
    its embeddings artifact.
    """

    release_id, _, sources_path, index_path = _verified_public_release(public_release_root)
    source_payload = json.loads(sources_path.read_text(encoding="utf-8"))
    eligible = _eligible_sources(source_payload)
    known_entries = {
        str(row["id"]): str(row["preferred_label"])
        for row in connection.execute("SELECT id, preferred_label FROM entries")
    }
    rules = tuple(rule for rule in TERM_RULES if rule.entry_id in known_entries)

    imported_sources: set[str] = set()
    imported_passages: set[str] = set()
    imported_occurrences = 0
    evidenced_entries: set[str] = set()
    per_source_entry: dict[tuple[str, str], int] = {}

    for chunk in _chunks(index_path):
        origin_source_id = str(chunk.get("sourceId") or "")
        source = eligible.get(origin_source_id)
        text = str(chunk.get("text") or "").strip()
        if source is None or not text:
            continue
        source_url = _stable_public_url(source)
        if source_url is None:
            continue

        matches: list[tuple[TermRule, re.Match[str]]] = []
        for rule in rules:
            key = (origin_source_id, rule.entry_id)
            if per_source_entry.get(key, 0) >= max_passages_per_source_entry:
                continue
            match = _first_contextual_match(rule, text)
            if match:
                matches.append((rule, match))
        if not matches:
            continue

        source_id, _ = _upsert_source(connection, source, release_id)
        imported_sources.add(source_id)
        sequence_value = chunk.get("id")
        if not isinstance(sequence_value, int) or sequence_value < 0:
            sequence_value = int(
                hashlib.sha1(str(chunk.get("passageId") or text[:80]).encode("utf-8")).hexdigest()[:12],
                16,
            )
        passage_id = stable_id(
            "passage", "william-jamesiana", origin_source_id, chunk.get("passageId"), sequence_value
        )
        connection.execute(
            """
            INSERT INTO passages (
              id, source_id, sequence, printed_page, scan_leaf, display_text,
              search_text, scan_url, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUGGESTED')
            ON CONFLICT(id) DO UPDATE SET
              display_text = excluded.display_text,
              search_text = excluded.search_text,
              scan_url = excluded.scan_url,
              status = 'SUGGESTED'
            """,
            (
                passage_id,
                source_id,
                sequence_value,
                str(chunk["page"]) if chunk.get("page") is not None else None,
                chunk.get("leaf") if isinstance(chunk.get("leaf"), int) else None,
                text,
                normalize(text),
                _scan_url(source_url, chunk),
            ),
        )
        imported_passages.add(passage_id)

        for rule, match in matches:
            key = (origin_source_id, rule.entry_id)
            if per_source_entry.get(key, 0) >= max_passages_per_source_entry:
                continue
            surface = match.group(0)
            normalized_surface = normalize(surface)
            existing_term = connection.execute(
                """
                SELECT t.id
                FROM term_forms t
                JOIN entry_term_links l ON l.term_form_id = t.id
                WHERE l.entry_id = ? AND t.normalized_form = ?
                ORDER BY
                  CASE l.status WHEN 'CORE' THEN 0 WHEN 'SUGGESTED' THEN 1 ELSE 2 END,
                  CASE l.relation_type WHEN 'PREFERRED_LABEL' THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (rule.entry_id, normalized_surface),
            ).fetchone()
            term_id = (
                str(existing_term["id"])
                if existing_term
                else stable_id("term", normalized_surface, "en")
            )
            if not existing_term:
                connection.execute(
                    """
                    INSERT INTO term_forms (
                      id, display_form, normalized_form, language_code,
                      earliest_year, latest_year
                    ) VALUES (?, ?, ?, 'en', ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      earliest_year = min(coalesce(term_forms.earliest_year, excluded.earliest_year), excluded.earliest_year),
                      latest_year = max(coalesce(term_forms.latest_year, excluded.latest_year), excluded.latest_year)
                    """,
                    (term_id, surface, normalized_surface, _year(source), _year(source)),
                )
            relation_type = rule.relation_type
            if (
                relation_type == "PREFERRED_LABEL"
                and normalized_surface != normalize(known_entries[rule.entry_id])
            ):
                relation_type = "ORTHOGRAPHIC_VARIANT"
            connection.execute(
                """
                INSERT INTO entry_term_links (
                  id, entry_id, term_form_id, relation_type, rationale,
                  status, confidence
                ) VALUES (?, ?, ?, ?, ?, 'SUGGESTED', 0.75)
                ON CONFLICT(id) DO UPDATE SET
                  status = CASE
                    WHEN entry_term_links.status = 'CORE' THEN 'CORE'
                    ELSE 'SUGGESTED'
                  END,
                  rationale = excluded.rationale
                """,
                (
                    stable_id("link", rule.entry_id, term_id, relation_type),
                    rule.entry_id,
                    term_id,
                    relation_type,
                    "Exact lexical candidate imported from a verified William Jamesiana public release; contextual review remains advisable.",
                ),
            )
            occurrence_id = stable_id(
                "occurrence", rule.entry_id, passage_id, match.start(), surface
            )
            before = connection.total_changes
            connection.execute(
                """
                INSERT OR IGNORE INTO occurrences (
                  id, passage_id, entry_id, term_form_id, surface_form,
                  start_in_passage, end_in_passage, resolution_method,
                  confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'EXACT', 0.75, 'SUGGESTED')
                """,
                (
                    occurrence_id,
                    passage_id,
                    rule.entry_id,
                    term_id,
                    surface,
                    match.start(),
                    match.end(),
                ),
            )
            if connection.total_changes > before:
                imported_occurrences += 1
            per_source_entry[key] = per_source_entry.get(key, 0) + 1
            evidenced_entries.add(rule.entry_id)

    for entry_id in evidenced_entries:
        connection.execute(
            """
            UPDATE entries
            SET status = CASE WHEN status = 'CORE' THEN 'CORE' ELSE 'SUGGESTED' END
            WHERE id = ?
            """,
            (entry_id,),
        )
    connection.execute(
        """
        UPDATE entry_term_links
        SET status = (SELECT status FROM entries WHERE entries.id = entry_term_links.entry_id)
        WHERE relation_type = 'PREFERRED_LABEL'
          AND status = 'PRIVATE'
          AND (SELECT status FROM entries WHERE entries.id = entry_term_links.entry_id)
              IN ('CORE', 'SUGGESTED')
        """
    )
    connection.commit()
    return {
        "release_id": release_id,
        "eligible_sources": len(eligible),
        "sources_imported": len(imported_sources),
        "passages_imported": len(imported_passages),
        "occurrences_imported": imported_occurrences,
        "entries_evidenced": len(evidenced_entries),
    }

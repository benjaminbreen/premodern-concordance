from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ſ", "s")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def stable_id(prefix: str, *parts: object) -> str:
    content = "\x1f".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(content.encode('utf-8')).hexdigest()[:20]}"


def _legacy_books(data_dir: Path) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
    books: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for path in sorted(data_dir.glob("*_entities.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        book = payload.get("book")
        entities = payload.get("entities")
        if not isinstance(book, dict) or not isinstance(entities, list):
            continue
        books[str(book["id"])] = (book, entities)
    return books


def _language(language: str) -> tuple[str, str]:
    codes = {
        "english": "en",
        "french": "fr",
        "german": "de",
        "latin": "la",
        "portuguese": "pt",
        "spanish": "es",
        "italian": "it",
        "dutch": "nl",
    }
    return codes.get(language.casefold(), "und"), language


def _insert_entry(connection: sqlite3.Connection, spec: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO entries (
          id, slug, preferred_label, kind, scope_note, exclusions_note,
          external_ids_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT')
        ON CONFLICT(id) DO UPDATE SET
          slug = excluded.slug,
          preferred_label = excluded.preferred_label,
          kind = excluded.kind,
          scope_note = excluded.scope_note,
          exclusions_note = excluded.exclusions_note,
          external_ids_json = excluded.external_ids_json
        """,
        (
            spec["id"],
            spec["slug"],
            spec["preferred_label"],
            spec["kind"],
            spec["scope_note"],
            spec.get("exclusions_note"),
            json.dumps(spec.get("external_ids", {}), ensure_ascii=False, sort_keys=True),
        ),
    )


def _insert_source(
    connection: sqlite3.Connection,
    book: dict[str, Any],
    page_map: dict[str, Any],
    repository: Path,
) -> None:
    source_id = str(book["id"])
    work_id = f"work-{source_id}"
    language_code, language_label = _language(str(book.get("language", "Unknown")))
    author = str(book.get("author") or "Anonymous")
    title = str(book["title"])
    year = int(book["year"])
    archive_id = str(page_map["ia_id"])
    archive_url = f"https://archive.org/details/{archive_id}"
    citation = f"{author}. {title}. {year}."
    text_candidates = [
        repository / "web" / "public" / "texts" / f"{source_id}.txt",
        repository / "books" / f"{source_id}.txt",
    ]
    text_path = next((path for path in text_candidates if path.exists()), None)
    text_sha256 = None
    word_count = None
    object_key = None
    if text_path:
        text_bytes = text_path.read_bytes()
        text_sha256 = hashlib.sha256(text_bytes).hexdigest()
        word_count = len(text_bytes.decode("utf-8", errors="replace").split())
        object_key = f"sources/{source_id}.txt"
    connection.execute(
        "INSERT OR IGNORE INTO works (id, preferred_title, original_year) VALUES (?, ?, ?)",
        (work_id, title, year),
    )
    connection.execute(
        """
        INSERT INTO sources (
          id, work_id, title, author, publication_year, original_year,
          language_code, language_label, citation_text, archive_provider,
          archive_item_id, archive_url, rights_status, text_path, text_sha256,
          word_count, public_text_object_key, origin_system, origin_id, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Internet Archive', ?, ?,
                  'PUBLIC_DOMAIN', ?, ?, ?, ?, 'legacy-concordance', ?, 'PUBLISHED')
        ON CONFLICT(id) DO UPDATE SET
          citation_text = excluded.citation_text,
          archive_url = excluded.archive_url,
          text_path = excluded.text_path,
          text_sha256 = excluded.text_sha256,
          word_count = excluded.word_count,
          public_text_object_key = excluded.public_text_object_key,
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
            citation,
            archive_id,
            archive_url,
            str(text_path) if text_path else None,
            text_sha256,
            word_count,
            object_key,
            source_id,
        ),
    )


def seed_acceptance_entries(
    connection: sqlite3.Connection,
    *,
    repository: Path,
    fixture_path: Path,
    max_passages_per_source: int = 2,
) -> dict[str, int]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    specs = fixture["entries"]
    data_dir = repository / "web" / "public" / "data"
    page_map_dir = data_dir / "page_maps"
    books = _legacy_books(data_dir)

    for spec in specs:
        _insert_entry(connection, spec)

    imported_passages = 0
    imported_occurrences = 0
    public_entries: set[str] = set()
    suggested_entries: set[str] = set()

    for spec in specs:
        entry_id = spec["id"]
        preferred_term_id = stable_id("term", spec["preferred_label"], "und")
        connection.execute(
            "INSERT OR IGNORE INTO term_forms (id, display_form, normalized_form) VALUES (?, ?, ?)",
            (preferred_term_id, spec["preferred_label"], normalize(spec["preferred_label"])),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO entry_term_links (
              id, entry_id, term_form_id, relation_type, status
            ) VALUES (?, ?, ?, 'PREFERRED_LABEL', 'PRIVATE')
            """,
            (stable_id("link", entry_id, preferred_term_id, "PREFERRED_LABEL"), entry_id, preferred_term_id),
        )

        for term in spec.get("legacy_terms", []):
            wanted_names = {normalize(name) for name in term["names"]}
            term_status = term["status"]
            term_id = (
                preferred_term_id
                if normalize(term["form"]) == normalize(spec["preferred_label"])
                else stable_id("term", term["form"], "und")
            )
            connection.execute(
                "INSERT OR IGNORE INTO term_forms (id, display_form, normalized_form) VALUES (?, ?, ?)",
                (term_id, term["form"], normalize(term["form"])),
            )

            term_has_occurrence = False
            for source_id, (book, entities) in books.items():
                page_map_path = page_map_dir / f"{source_id}.json"
                if not page_map_path.exists():
                    continue
                matches = [entity for entity in entities if normalize(str(entity.get("name", ""))) in wanted_names]
                if not matches:
                    continue
                page_map = json.loads(page_map_path.read_text(encoding="utf-8"))
                _insert_source(connection, book, page_map, repository)
                selected = 0
                for entity in matches:
                    preferred_phrases = [normalize(item) for item in term.get("prefer", [])]
                    mentions = list(entity.get("mentions", []))
                    def preference_rank(mention: dict[str, Any]) -> int:
                        excerpt_value = normalize(str(mention.get("excerpt") or ""))
                        for index, phrase in enumerate(preferred_phrases):
                            if phrase in excerpt_value:
                                return index
                        return len(preferred_phrases)

                    mentions.sort(
                        key=preference_rank
                    )
                    for mention in mentions:
                        if selected >= max_passages_per_source:
                            break
                        offset = int(mention["offset"])
                        if offset < int(term.get("minimum_offset", 0)):
                            continue
                        excerpt = str(mention.get("excerpt") or "").strip()
                        excerpt_normalized = normalize(excerpt)
                        if not excerpt or any(normalize(item) in excerpt_normalized for item in term.get("exclude", [])):
                            continue
                        surface = str(mention.get("matched_term") or term["form"])
                        surface_match = re.search(re.escape(surface), excerpt, flags=re.IGNORECASE)
                        if surface_match is None:
                            continue
                        surface = surface_match.group(0)
                        surface_position = surface_match.start()
                        leaf = page_map.get("leaves", {}).get(str(offset))
                        printed_page = page_map.get("pages", {}).get(str(offset))
                        archive_id = page_map["ia_id"]
                        scan_url = (
                            f"https://archive.org/details/{archive_id}/page/n{leaf}/mode/1up"
                            if leaf is not None
                            else f"https://archive.org/details/{archive_id}"
                        )
                        passage_id = stable_id("passage", source_id, offset)
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO passages (
                              id, source_id, sequence, start_offset, end_offset,
                              printed_page, scan_leaf, display_text, search_text,
                              scan_url, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                passage_id,
                                source_id,
                                offset,
                                max(0, offset - surface_position),
                                offset - surface_position + len(excerpt),
                                printed_page,
                                leaf,
                                excerpt,
                                excerpt_normalized,
                                scan_url,
                                term_status,
                            ),
                        )
                        occurrence_id = stable_id("occurrence", entry_id, source_id, offset, surface)
                        before = connection.total_changes
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO occurrences (
                              id, passage_id, entry_id, term_form_id, surface_form,
                              start_in_passage, end_in_passage, resolution_method,
                              confidence, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'LEGACY_IMPORT', ?, ?)
                            """,
                            (
                                occurrence_id,
                                passage_id,
                                entry_id,
                                term_id,
                                surface,
                                surface_position,
                                surface_position + len(surface),
                                1.0 if term_status == "CORE" else 0.7,
                                term_status,
                            ),
                        )
                        if connection.total_changes > before:
                            imported_occurrences += 1
                            imported_passages += 1
                        selected += 1
                        term_has_occurrence = True
                        if term_status == "CORE":
                            public_entries.add(entry_id)
                        else:
                            suggested_entries.add(entry_id)

            link_status = term_status if term_has_occurrence else "PRIVATE"
            connection.execute(
                """
                INSERT INTO entry_term_links (
                  id, entry_id, term_form_id, relation_type, status,
                  confidence, rationale
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status = excluded.status
                """,
                (
                    stable_id("link", entry_id, term_id, term["relation"]),
                    entry_id,
                    term_id,
                    term["relation"],
                    link_status,
                    1.0 if term_status == "CORE" else 0.7,
                    "Imported from a legacy passage as candidate evidence for the V2 acceptance set.",
                ),
            )

    preparation_passage = connection.execute(
        """
        SELECT p.id, p.display_text
        FROM passages p
        JOIN occurrences o ON o.passage_id = p.id
        WHERE o.entry_id = 'entry-cinchona-bark'
          AND lower(p.display_text) LIKE '%inglaterra%'
          AND lower(p.display_text) LIKE '%prepara%'
        ORDER BY p.sequence
        LIMIT 1
        """
    ).fetchone()
    if preparation_passage:
        match = re.search(
            r"a?agua\s*de\s*Inglaterra",
            preparation_passage["display_text"],
            flags=re.IGNORECASE,
        )
        if match:
            agua_entry = "entry-agua-inglaterra"
            agua_term = stable_id("term", "Água de Inglaterra", "und")
            connection.execute(
                "UPDATE entries SET status = 'CORE' WHERE id = ?", (agua_entry,)
            )
            connection.execute(
                "UPDATE entry_term_links SET status = 'CORE', confidence = 1.0 WHERE entry_id = ? AND term_form_id = ?",
                (agua_entry, agua_term),
            )
            before = connection.total_changes
            connection.execute(
                """
                INSERT OR IGNORE INTO occurrences (
                  id, passage_id, entry_id, term_form_id, surface_form,
                  start_in_passage, end_in_passage, resolution_method,
                  confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'EDITORIAL', 1.0, 'CORE')
                """,
                (
                    stable_id("occurrence", agua_entry, preparation_passage["id"]),
                    preparation_passage["id"],
                    agua_entry,
                    agua_term,
                    match.group(0),
                    match.start(),
                    match.end(),
                ),
            )
            if connection.total_changes > before:
                imported_occurrences += 1
            relation_id = "relation-agua-preparation-of-cinchona-bark"
            connection.execute(
                """
                INSERT OR REPLACE INTO entry_relations (
                  id, source_entry_id, target_entry_id, layer, relation_type,
                  rationale, non_claim, confidence, status
                ) VALUES (?, ?, 'entry-cinchona-bark', 'PRECISE', 'PREPARATION_OF',
                  ?, ?, 1.0, 'CORE')
                """,
                (
                    relation_id,
                    agua_entry,
                    "Semedo describes genuine Água de Inglaterra as made and prepared with true Quinaquina.",
                    "This supports one historical preparation; it does not make the names interchangeable or establish a universal recipe.",
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO relation_evidence (relation_id, passage_id, note) VALUES (?, ?, ?)",
                (
                    relation_id,
                    preparation_passage["id"],
                    "The passage explicitly describes the preparation as made with Quinaquina.",
                ),
            )
            public_entries.add(agua_entry)

    for entry_id in public_entries:
        connection.execute("UPDATE entries SET status = 'CORE' WHERE id = ?", (entry_id,))
    for entry_id in suggested_entries - public_entries:
        connection.execute("UPDATE entries SET status = 'SUGGESTED' WHERE id = ?", (entry_id,))
    connection.execute(
        """
        UPDATE entry_term_links
        SET status = (SELECT status FROM entries WHERE entries.id = entry_term_links.entry_id)
        WHERE relation_type = 'PREFERRED_LABEL'
          AND (SELECT status FROM entries WHERE entries.id = entry_term_links.entry_id)
              IN ('CORE', 'SUGGESTED')
        """
    )
    connection.commit()
    return {
        "entries_defined": len(specs),
        "entries_public": len(public_entries | suggested_entries),
        "passages_imported": imported_passages,
        "occurrences_imported": imported_occurrences,
    }

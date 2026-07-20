from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LANGUAGE_CODES = {
    "dutch": "nl",
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "latin": "la",
    "portuguese": "pt",
    "spanish": "es",
}


@dataclass(frozen=True)
class SourceSpec:
    id: str
    title: str
    author: str
    year: int
    language_code: str
    language_label: str
    text_path: Path
    archive_item_id: str
    archive_url: str
    djvu_xml_path: Path | None
    page_numbers_path: Path | None

    @property
    def work_id(self) -> str:
        return f"work-{self.id}"

    @property
    def citation_text(self) -> str:
        return f"{self.author}. {self.title}. {self.year}."

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text_path.read_bytes()).hexdigest()


def language(language: str) -> tuple[str, str]:
    return LANGUAGE_CODES.get(language.casefold(), "und"), language


def _legacy_book_metadata(data_dir: Path) -> dict[str, dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for path in sorted(data_dir.glob("*_entities.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        book = payload.get("book")
        if isinstance(book, dict) and book.get("id"):
            books[str(book["id"])] = book
    return books


def discover_legacy_sources(repository: Path) -> list[SourceSpec]:
    """Discover complete legacy texts with enough metadata to cite an edition."""
    data_dir = repository / "web" / "public" / "data"
    text_dir = repository / "web" / "public" / "texts"
    cache_dir = repository / "data" / "page_maps"
    books = _legacy_book_metadata(data_dir)
    sources: list[SourceSpec] = []

    for text_path in sorted(text_dir.glob("*.txt")):
        source_id = text_path.stem
        book = books.get(source_id)
        page_map_path = data_dir / "page_maps" / f"{source_id}.json"
        if not book or not page_map_path.exists():
            continue
        page_map = json.loads(page_map_path.read_text(encoding="utf-8"))
        archive_item_id = str(page_map.get("ia_id") or "").strip()
        if not archive_item_id:
            continue
        language_code, language_label = language(str(book.get("language") or "Unknown"))
        page_numbers_path = cache_dir / f"{archive_item_id}_page_numbers.json"
        djvu_xml_path = cache_dir / f"{archive_item_id}_djvu.xml"
        sources.append(
            SourceSpec(
                id=source_id,
                title=str(book["title"]),
                author=str(book.get("author") or "Anonymous"),
                year=int(book["year"]),
                language_code=language_code,
                language_label=language_label,
                text_path=text_path.resolve(),
                archive_item_id=archive_item_id,
                archive_url=f"https://archive.org/details/{archive_item_id}",
                djvu_xml_path=djvu_xml_path if djvu_xml_path.exists() else None,
                page_numbers_path=page_numbers_path if page_numbers_path.exists() else None,
            )
        )
    return sources


def upsert_source(connection: sqlite3.Connection, spec: SourceSpec) -> None:
    text_bytes = spec.text_path.read_bytes()
    connection.execute(
        """
        INSERT INTO works (id, preferred_title, original_year)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          preferred_title = excluded.preferred_title,
          original_year = excluded.original_year,
          updated_at = CURRENT_TIMESTAMP
        """,
        (spec.work_id, spec.title, spec.year),
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
          work_id = excluded.work_id,
          title = excluded.title,
          author = excluded.author,
          publication_year = excluded.publication_year,
          original_year = excluded.original_year,
          language_code = excluded.language_code,
          language_label = excluded.language_label,
          citation_text = excluded.citation_text,
          archive_provider = excluded.archive_provider,
          archive_item_id = excluded.archive_item_id,
          archive_url = excluded.archive_url,
          rights_status = excluded.rights_status,
          text_path = excluded.text_path,
          text_sha256 = excluded.text_sha256,
          word_count = excluded.word_count,
          public_text_object_key = excluded.public_text_object_key,
          status = excluded.status,
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            spec.id,
            spec.work_id,
            spec.title,
            spec.author,
            spec.year,
            spec.year,
            spec.language_code,
            spec.language_label,
            spec.citation_text,
            spec.archive_item_id,
            spec.archive_url,
            str(spec.text_path),
            hashlib.sha256(text_bytes).hexdigest(),
            len(text_bytes.decode("utf-8", errors="replace").split()),
            f"sources/{spec.id}.txt",
            spec.id,
        ),
    )

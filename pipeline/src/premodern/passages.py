from __future__ import annotations

import hashlib
import html
import json
import math
import re
import sqlite3
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping

from .sources import SourceSpec, discover_legacy_sources, upsert_source


CHUNKER_VERSION = "paragraph-words-v1"
MIN_WORDS = 80
TARGET_WORDS = 200
MAX_WORDS = 320
MIN_ALIGNMENT_SCORE = 2
SEQUENCE_STAGING_OFFSET = 1_000_000


@dataclass(frozen=True)
class PassageDraft:
    id: str
    source_id: str
    sequence: int
    start_offset: int
    end_offset: int
    raw_text: str
    display_text: str
    search_text: str
    heading: str | None = None
    printed_page: str | None = None
    printed_page_end: str | None = None
    scan_leaf: int | None = None
    scan_leaf_end: int | None = None
    scan_url: str = ""
    alignment_method: str = "UNALIGNED"
    alignment_score: float | None = None
    status: str = "PRIVATE"

    @property
    def word_count(self) -> int:
        return count_words(self.raw_text)

    @property
    def midpoint(self) -> float:
        return (self.start_offset + self.end_offset) / 2


@dataclass(frozen=True)
class PageRecord:
    leaf: int
    text: str
    grams: frozenset[str]
    long_s_grams: frozenset[str]


@dataclass(frozen=True)
class AlignmentSummary:
    passage_count: int
    directly_aligned_count: int
    inferred_count: int
    unaligned_count: int
    median_score: float | None
    inversion_count: int


def stable_id(prefix: str, *parts: object) -> str:
    content = "\x1f".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(content.encode('utf-8')).hexdigest()[:20]}"


def count_words(value: str) -> int:
    return len(re.findall(r"\w+", value, flags=re.UNICODE))


def normalize_search_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("ſ", "s").replace("ﬁ", "fi").replace("ﬂ", "fl")
    value = value.replace("æ", "ae").replace("Æ", "Ae")
    value = value.replace("œ", "oe").replace("Œ", "Oe")
    value = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_alignment_text(value: str, *, long_s_ocr: bool = False) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = value.replace("ſ", "s").replace("ﬁ", "fi").replace("ﬂ", "fl")
    value = value.replace("æ", "ae").replace("œ", "oe")
    value = "".join(character for character in value if not unicodedata.combining(character))
    if long_s_ocr:
        value = value.replace("f", "s")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def four_grams(value: str, *, long_s_ocr: bool = False) -> frozenset[str]:
    words = normalize_alignment_text(value, long_s_ocr=long_s_ocr).split()
    return frozenset(" ".join(words[index : index + 4]) for index in range(len(words) - 3))


def _trim_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for separator in re.finditer(r"\n[ \t]*\n+", text):
        trimmed = _trim_span(text, cursor, separator.start())
        if trimmed:
            spans.append(trimmed)
        cursor = separator.end()
    trimmed = _trim_span(text, cursor, len(text))
    if trimmed:
        spans.append(trimmed)
    return spans


def _word_matches(text: str, start: int, end: int) -> list[re.Match[str]]:
    return list(re.finditer(r"\w+", text[start:end], flags=re.UNICODE))


def _sentence_break_after(text: str, word: re.Match[str], next_word: re.Match[str]) -> bool:
    return bool(re.search(r"[.!?][\]\[\)\(\"'’”»]*\s*$", text[word.end() : next_word.start()]))


def split_long_span(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split a long paragraph near sentence boundaries while retaining offsets."""
    result: list[tuple[int, int]] = []
    cursor = start
    while count_words(text[cursor:end]) > MAX_WORDS:
        words = _word_matches(text, cursor, end)
        minimum_index = min(MIN_WORDS - 1, len(words) - 2)
        maximum_index = min(MAX_WORDS - 1, len(words) - 2)
        target_index = min(TARGET_WORDS - 1, maximum_index)
        candidates = [
            index
            for index in range(minimum_index, maximum_index + 1)
            if _sentence_break_after(text[cursor:end], words[index], words[index + 1])
        ]
        chosen = min(candidates, key=lambda index: abs(index - target_index)) if candidates else target_index
        cut = cursor + words[chosen + 1].start()
        trimmed = _trim_span(text, cursor, cut)
        if not trimmed or cut <= cursor:
            break
        result.append(trimmed)
        cursor = cut
        while cursor < end and text[cursor].isspace():
            cursor += 1
    trimmed = _trim_span(text, cursor, end)
    if trimmed:
        result.append(trimmed)
    return result


def _atomic_spans(text: str) -> list[tuple[int, int]]:
    atoms: list[tuple[int, int]] = []
    for start, end in paragraph_spans(text):
        if count_words(text[start:end]) > MAX_WORDS:
            atoms.extend(split_long_span(text, start, end))
        else:
            atoms.append((start, end))
    return atoms


def passageize_text(source_id: str, text: str) -> list[PassageDraft]:
    atoms = _atomic_spans(text)
    groups: list[list[tuple[int, int]]] = []
    buffer: list[tuple[int, int]] = []
    buffer_words = 0

    for index, atom in enumerate(atoms):
        atom_words = count_words(text[atom[0] : atom[1]])
        if buffer and buffer_words + atom_words > MAX_WORDS:
            groups.append(buffer)
            buffer = []
            buffer_words = 0
        buffer.append(atom)
        buffer_words += atom_words
        next_words = (
            count_words(text[atoms[index + 1][0] : atoms[index + 1][1]])
            if index + 1 < len(atoms)
            else 0
        )
        projected = buffer_words + next_words
        should_flush = (
            index + 1 == len(atoms)
            or buffer_words >= MAX_WORDS
            or (
                buffer_words >= MIN_WORDS
                and (
                    projected > MAX_WORDS
                    or abs(buffer_words - TARGET_WORDS) <= abs(projected - TARGET_WORDS)
                )
            )
        )
        if should_flush:
            groups.append(buffer)
            buffer = []
            buffer_words = 0

    if buffer:
        groups.append(buffer)

    if len(groups) > 1:
        last = groups[-1]
        last_words = sum(count_words(text[start:end]) for start, end in last)
        previous = groups[-2]
        previous_words = sum(count_words(text[start:end]) for start, end in previous)
        if last_words < MIN_WORDS and previous_words + last_words <= MAX_WORDS:
            groups[-2] = previous + last
            groups.pop()

    passages: list[PassageDraft] = []
    for sequence, group in enumerate(groups):
        start = group[0][0]
        end = group[-1][1]
        raw_text = text[start:end]
        passages.append(
            PassageDraft(
                id=stable_id("passage", source_id, start, end),
                source_id=source_id,
                sequence=sequence,
                start_offset=start,
                end_offset=end,
                raw_text=raw_text,
                display_text=raw_text,
                search_text=normalize_search_text(raw_text),
            )
        )
    return passages


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def parse_djvu_pages(path: Path) -> list[PageRecord]:
    pages: list[PageRecord] = []
    object_index = 0
    for _, element in ET.iterparse(path, events=("end",)):
        if _local_name(element) != "OBJECT":
            continue
        leaf = object_index
        for child in element.iter():
            if _local_name(child) != "PARAM":
                continue
            if str(child.attrib.get("name", "")).casefold() != "page":
                continue
            match = re.search(r"_(\d+)\.djvu$", str(child.attrib.get("value", "")), re.IGNORECASE)
            if match:
                leaf = int(match.group(1)) - 1
                break
        words = [
            html.unescape("".join(child.itertext())).strip()
            for child in element.iter()
            if _local_name(child) == "WORD"
        ]
        page_text = " ".join(word for word in words if word)
        pages.append(
            PageRecord(
                leaf=leaf,
                text=page_text,
                grams=four_grams(page_text),
                long_s_grams=four_grams(page_text, long_s_ocr=True),
            )
        )
        object_index += 1
        element.clear()
    return pages


def page_number_lookup(path: Path | None):
    exact: dict[int, str] = {}
    numeric_anchors: list[tuple[int, int]] = []
    if path and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("pages", []):
            label = str(record.get("pageNumber") or "").strip()
            leaf_value = record.get("leafNum")
            if not label or not isinstance(leaf_value, int):
                continue
            leaf = leaf_value - 1
            exact[leaf] = label
            if label.isdigit() and int(label) > 0:
                numeric_anchors.append((leaf, int(label)))
    numeric_anchors.sort()
    page_one_leaf = (
        numeric_anchors[0][0] - numeric_anchors[0][1] + 1
        if numeric_anchors
        else None
    )

    def lookup(leaf: int | None) -> str | None:
        if leaf is None:
            return None
        if leaf in exact:
            return exact[leaf]
        if page_one_leaf is None:
            return None
        if leaf < page_one_leaf:
            return "front matter"
        return str(leaf - page_one_leaf + 1)

    return lookup


def _gram_index(pages: Iterable[PageRecord], *, long_s_ocr: bool = False) -> dict[str, list[int]]:
    index: dict[str, list[int]] = defaultdict(list)
    for page in pages:
        for gram in page.long_s_grams if long_s_ocr else page.grams:
            index[gram].append(page.leaf)
    return index


def _score_grams(grams: Iterable[str], index: dict[str, list[int]]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for gram in grams:
        for leaf in index.get(gram, []):
            counts[leaf] += 1
    return dict(counts)


def _median_chars_per_leaf(records: list[dict], text_length: int, page_count: int) -> float:
    rates: list[float] = []
    direct = [record for record in records if record["direct"]]
    for left, right in zip(direct, direct[1:]):
        leaf_delta = right["leaf"] - left["leaf"]
        offset_delta = right["passage"].midpoint - left["passage"].midpoint
        if leaf_delta > 0 and offset_delta > 0:
            rates.append(offset_delta / leaf_delta)
    return statistics.median(rates) if rates else text_length / max(page_count, 1)


def align_passages(
    passages: list[PassageDraft],
    pages: list[PageRecord],
    *,
    archive_item_id: str,
    page_numbers_path: Path | None,
) -> tuple[list[PassageDraft], AlignmentSummary]:
    if not pages:
        return passages, AlignmentSummary(len(passages), 0, 0, len(passages), None, 0)

    base_index = _gram_index(pages)
    long_s_index = _gram_index(pages, long_s_ocr=True)
    cursor = -1
    records: list[dict] = []
    inversion_count = 0
    previous_direct_leaf = -1

    for passage in passages:
        base_counts = _score_grams(four_grams(passage.raw_text), base_index)
        long_s_counts = _score_grams(
            four_grams(passage.raw_text, long_s_ocr=True), long_s_index
        )
        base_best = max(base_counts.values(), default=0)
        long_s_best = max(long_s_counts.values(), default=0)
        counts = long_s_counts if long_s_best > base_best else base_counts
        candidates = [
            (leaf, score) for leaf, score in counts.items() if score >= MIN_ALIGNMENT_SCORE
        ]
        local = [
            item
            for item in candidates
            if cursor < 0 or max(0, cursor - 3) <= item[0] <= cursor + 18
        ]
        choices = local or candidates
        choices.sort(key=lambda item: (-item[1], item[0]))
        if choices:
            leaf, score = choices[0]
            direct = True
            if previous_direct_leaf >= 0 and leaf < previous_direct_leaf - 2:
                inversion_count += 1
            previous_direct_leaf = max(previous_direct_leaf, leaf)
            cursor = max(cursor, leaf)
        else:
            leaf, score, direct = -1, 0, False
        records.append(
            {
                "passage": passage,
                "leaf": leaf,
                "score": score,
                "counts": counts,
                "direct": direct,
                "inferred": False,
            }
        )

    chars_per_leaf = _median_chars_per_leaf(
        records,
        passages[-1].end_offset if passages else 0,
        max(page.leaf for page in pages) + 1,
    )
    direct_indices = [index for index, record in enumerate(records) if record["direct"]]
    max_leaf = max(page.leaf for page in pages)
    for index, record in enumerate(records):
        if record["direct"]:
            continue
        before_indices = [item for item in direct_indices if item < index]
        after_indices = [item for item in direct_indices if item > index]
        before = records[before_indices[-1]] if before_indices else None
        after = records[after_indices[0]] if after_indices else None
        midpoint = record["passage"].midpoint
        inferred_leaf: int | None = None
        if before and after and after["passage"].midpoint > before["passage"].midpoint:
            ratio = (midpoint - before["passage"].midpoint) / (
                after["passage"].midpoint - before["passage"].midpoint
            )
            inferred_leaf = round(before["leaf"] + ratio * (after["leaf"] - before["leaf"]))
        elif before:
            inferred_leaf = before["leaf"] + round(
                (midpoint - before["passage"].midpoint) / max(chars_per_leaf, 1)
            )
        elif after:
            inferred_leaf = after["leaf"] - round(
                (after["passage"].midpoint - midpoint) / max(chars_per_leaf, 1)
            )
        if inferred_leaf is not None:
            record["leaf"] = min(max(0, inferred_leaf), max_leaf)
            record["inferred"] = True

    page_for_leaf = page_number_lookup(page_numbers_path)
    aligned: list[PassageDraft] = []
    for record in records:
        passage = record["passage"]
        if record["leaf"] < 0:
            aligned.append(replace(passage, scan_url=f"https://archive.org/details/{archive_item_id}"))
            continue
        best_leaf = int(record["leaf"])
        if record["direct"]:
            meaningful = max(MIN_ALIGNMENT_SCORE, float(record["score"]) * 0.08)
            nearby = [
                leaf
                for leaf, score in record["counts"].items()
                if abs(leaf - best_leaf) <= 4 and score >= meaningful
            ]
            leaf_start = min(nearby) if nearby else best_leaf
            leaf_end = max(nearby) if nearby else best_leaf
            method = "FOUR_GRAM"
            score_value: float | None = float(record["score"])
        else:
            leaf_start = leaf_end = best_leaf
            method = "INFERRED"
            score_value = None
        aligned.append(
            replace(
                passage,
                printed_page=page_for_leaf(leaf_start),
                printed_page_end=page_for_leaf(leaf_end),
                scan_leaf=leaf_start,
                scan_leaf_end=leaf_end,
                scan_url=(
                    f"https://archive.org/details/{archive_item_id}/page/n{leaf_start}/mode/1up"
                ),
                alignment_method=method,
                alignment_score=score_value,
            )
        )

    direct_scores = [float(record["score"]) for record in records if record["direct"]]
    summary = AlignmentSummary(
        passage_count=len(records),
        directly_aligned_count=sum(1 for record in records if record["direct"]),
        inferred_count=sum(1 for record in records if record["inferred"]),
        unaligned_count=sum(1 for record in records if record["leaf"] < 0),
        median_score=statistics.median(direct_scores) if direct_scores else None,
        inversion_count=inversion_count,
    )
    return aligned, summary


def _absolute_occurrence_span(row: Mapping[str, object]) -> tuple[int, int]:
    start = int(row["start_offset"] or 0) + int(row["start_in_passage"] or 0)
    end = int(row["start_offset"] or 0) + int(row["end_in_passage"] or 0)
    return start, end


def _containing_passage(
    passages: list[PassageDraft], start: int, end: int
) -> PassageDraft | None:
    for passage in passages:
        if passage.start_offset <= start and passage.end_offset >= end:
            return passage
    return None


def _remap_legacy_evidence(
    connection: sqlite3.Connection,
    source_id: str,
    passages: list[PassageDraft],
) -> int:
    old_rows = connection.execute(
        """
        SELECT id, start_offset, end_offset, status
        FROM passages
        WHERE source_id = ? AND chunker_version IS NULL
        """,
        (source_id,),
    ).fetchall()
    remapped = 0
    for old in old_rows:
        occurrences = connection.execute(
            """
            SELECT id, start_in_passage, end_in_passage
            FROM occurrences WHERE passage_id = ?
            """,
            (old["id"],),
        ).fetchall()
        target: PassageDraft | None = None
        for occurrence in occurrences:
            combined = dict(old)
            combined.update(dict(occurrence))
            absolute_start, absolute_end = _absolute_occurrence_span(combined)
            target = _containing_passage(passages, absolute_start, absolute_end)
            if target is None:
                continue
            connection.execute(
                """
                UPDATE occurrences
                SET passage_id = ?, start_in_passage = ?, end_in_passage = ?
                WHERE id = ?
                """,
                (
                    target.id,
                    absolute_start - target.start_offset,
                    absolute_end - target.start_offset,
                    occurrence["id"],
                ),
            )
            remapped += 1
        if target is None and old["start_offset"] is not None:
            target = _containing_passage(
                passages,
                int(old["start_offset"]),
                int(old["end_offset"] or old["start_offset"]),
            )
        if target:
            if old["status"] == "CORE":
                connection.execute("UPDATE passages SET status = 'CORE' WHERE id = ?", (target.id,))
            elif old["status"] == "SUGGESTED":
                connection.execute(
                    """
                    UPDATE passages SET status = 'SUGGESTED'
                    WHERE id = ? AND status = 'PRIVATE'
                    """,
                    (target.id,),
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO relation_evidence (relation_id, passage_id, note)
                SELECT relation_id, ?, note FROM relation_evidence WHERE passage_id = ?
                """,
                (target.id, old["id"]),
            )
            connection.execute(
                "UPDATE supporting_mentions SET passage_id = ? WHERE passage_id = ?",
                (target.id, old["id"]),
            )
        connection.execute("DELETE FROM passages WHERE id = ?", (old["id"],))
    return remapped


def ingest_passages(
    connection: sqlite3.Connection,
    spec: SourceSpec,
    passages: list[PassageDraft],
    summary: AlignmentSummary,
    *,
    page_map_path: Path,
) -> dict[str, int | str | float | None]:
    upsert_source(connection, spec)
    connection.commit()
    build_id = stable_id("passage-build", spec.id, spec.text_sha256, CHUNKER_VERSION)
    existing = connection.execute(
        "SELECT id FROM passage_builds WHERE id = ?", (build_id,)
    ).fetchone()
    if existing:
        return {"source_id": spec.id, "status": "unchanged", "passage_count": len(passages)}

    connection.execute("BEGIN")
    try:
        for passage in passages:
            connection.execute(
                """
                INSERT INTO passages (
                  id, source_id, sequence, start_offset, end_offset,
                  printed_page, scan_leaf, display_text, search_text, scan_url,
                  status, raw_text, heading, printed_page_end, scan_leaf_end,
                  alignment_method, alignment_score, chunker_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    passage.id,
                    passage.source_id,
                    passage.sequence + SEQUENCE_STAGING_OFFSET,
                    passage.start_offset,
                    passage.end_offset,
                    passage.printed_page,
                    passage.scan_leaf,
                    passage.display_text,
                    passage.search_text,
                    passage.scan_url or spec.archive_url,
                    passage.status,
                    passage.raw_text,
                    passage.heading,
                    passage.printed_page_end,
                    passage.scan_leaf_end,
                    passage.alignment_method,
                    passage.alignment_score,
                    CHUNKER_VERSION,
                ),
            )
        remapped = _remap_legacy_evidence(connection, spec.id, passages)
        connection.execute(
            """
            UPDATE passages SET sequence = sequence - ?
            WHERE source_id = ? AND chunker_version = ?
            """,
            (SEQUENCE_STAGING_OFFSET, spec.id, CHUNKER_VERSION),
        )
        connection.execute(
            """
            INSERT INTO passage_builds (
              id, source_id, source_text_sha256, chunker_version, passage_count,
              directly_aligned_count, inferred_count, unaligned_count,
              median_alignment_score, page_map_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_id,
                spec.id,
                spec.text_sha256,
                CHUNKER_VERSION,
                summary.passage_count,
                summary.directly_aligned_count,
                summary.inferred_count,
                summary.unaligned_count,
                summary.median_score,
                str(page_map_path),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "source_id": spec.id,
        "status": "built",
        "passage_count": len(passages),
        "directly_aligned": summary.directly_aligned_count,
        "inferred": summary.inferred_count,
        "unaligned": summary.unaligned_count,
        "median_score": summary.median_score,
        "remapped_occurrences": remapped,
    }


def passageize_source(spec: SourceSpec) -> tuple[list[PassageDraft], AlignmentSummary]:
    text = spec.text_path.read_text(encoding="utf-8", errors="replace")
    passages = passageize_text(spec.id, text)
    pages = parse_djvu_pages(spec.djvu_xml_path) if spec.djvu_xml_path else []
    return align_passages(
        passages,
        pages,
        archive_item_id=spec.archive_item_id,
        page_numbers_path=spec.page_numbers_path,
    )


def passageize_legacy_corpus(
    connection: sqlite3.Connection,
    *,
    repository: Path,
    output_dir: Path,
    source_id: str | None = None,
) -> list[dict[str, int | str | float | None]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = discover_legacy_sources(repository)
    if source_id:
        sources = [source for source in sources if source.id == source_id]
        if not sources:
            raise ValueError(f"unknown complete legacy source: {source_id}")
    results = []
    for spec in sources:
        passages, summary = passageize_source(spec)
        page_map_path = output_dir / f"{spec.id}.json"
        page_map_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_id": spec.id,
                    "archive_item_id": spec.archive_item_id,
                    "chunker_version": CHUNKER_VERSION,
                    "alignment": summary.__dict__,
                    "passages": {
                        passage.id: {
                            "start_offset": passage.start_offset,
                            "end_offset": passage.end_offset,
                            "printed_page": passage.printed_page,
                            "printed_page_end": passage.printed_page_end,
                            "scan_leaf": passage.scan_leaf,
                            "scan_leaf_end": passage.scan_leaf_end,
                            "method": passage.alignment_method,
                            "score": passage.alignment_score,
                        }
                        for passage in passages
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        results.append(
            ingest_passages(
                connection,
                spec,
                passages,
                summary,
                page_map_path=page_map_path,
            )
        )
    return results


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    index = min(len(values) - 1, max(0, math.ceil(len(values) * fraction) - 1))
    return sorted(values)[index]


def audit_passages(connection: sqlite3.Connection) -> dict[str, object]:
    sources = connection.execute(
        """
        SELECT s.id, s.text_path, s.text_sha256, COUNT(p.id) AS passage_count
        FROM sources s
        JOIN passages p ON p.source_id = s.id
        WHERE p.chunker_version = ?
        GROUP BY s.id
        ORDER BY s.id
        """,
        (CHUNKER_VERSION,),
    ).fetchall()
    errors: list[str] = []
    words: list[int] = []
    source_reports: list[dict[str, object]] = []
    for source in sources:
        path = Path(source["text_path"] or "")
        if not path.is_file():
            errors.append(f"{source['id']}: source text missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if source["text_sha256"] != actual_hash:
            errors.append(f"{source['id']}: source checksum drift")
        rows = connection.execute(
            """
            SELECT * FROM passages
            WHERE source_id = ? AND chunker_version = ?
            ORDER BY sequence
            """,
            (source["id"], CHUNKER_VERSION),
        ).fetchall()
        previous_end = -1
        for expected_sequence, passage in enumerate(rows):
            start = int(passage["start_offset"])
            end = int(passage["end_offset"])
            if passage["sequence"] != expected_sequence:
                errors.append(f"{source['id']}: non-contiguous sequence at {passage['id']}")
            if start < previous_end:
                errors.append(f"{source['id']}: overlapping passage at {passage['id']}")
            if start < 0 or end <= start or end > len(text):
                errors.append(f"{source['id']}: invalid offsets at {passage['id']}")
            elif passage["raw_text"] != text[start:end] or passage["display_text"] != text[start:end]:
                errors.append(f"{source['id']}: source slice drift at {passage['id']}")
            if passage["scan_leaf"] is not None and (
                passage["scan_leaf_end"] is None
                or int(passage["scan_leaf_end"]) < int(passage["scan_leaf"])
            ):
                errors.append(f"{source['id']}: invalid scan range at {passage['id']}")
            previous_end = end
            words.append(count_words(passage["raw_text"]))
        methods = dict(
            connection.execute(
                """
                SELECT alignment_method, COUNT(*) FROM passages
                WHERE source_id = ? AND chunker_version = ?
                GROUP BY alignment_method
                """,
                (source["id"], CHUNKER_VERSION),
            ).fetchall()
        )
        source_reports.append(
            {
                "source_id": source["id"],
                "passages": len(rows),
                "alignment_methods": methods,
            }
        )
    return {
        "chunker_version": CHUNKER_VERSION,
        "source_count": len(sources),
        "passage_count": sum(int(source["passage_count"]) for source in sources),
        "word_count": {
            "min": min(words, default=0),
            "median": int(statistics.median(words)) if words else 0,
            "p90": _percentile(words, 0.90),
            "p99": _percentile(words, 0.99),
            "max": max(words, default=0),
        },
        "errors": errors,
        "sources": source_reports,
    }

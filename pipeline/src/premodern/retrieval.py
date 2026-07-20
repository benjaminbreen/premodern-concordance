from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .embeddings import artifact_dir
from .passages import normalize_alignment_text


RETRIEVAL_VERSION = "hybrid-rrf-v1"
RRF_CONSTANT = 60
DEFAULT_CANDIDATES = 100
FUZZY_FORM_CUTOFF = 0.82


@dataclass(frozen=True)
class PassageRecord:
    id: str
    source_id: str
    source_title: str
    source_author: str | None
    publication_year: int
    language_label: str
    sequence: int
    display_text: str
    search_text: str
    printed_page: str | None
    printed_page_end: str | None
    scan_leaf: int | None
    scan_leaf_end: int | None
    scan_url: str


@dataclass(frozen=True)
class EntryQuery:
    id: str
    slug: str
    preferred_label: str
    scope_note: str
    forms: tuple[str, ...]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_passages(connection: sqlite3.Connection) -> list[PassageRecord]:
    return [
        PassageRecord(
            id=str(row[0]),
            source_id=str(row[1]),
            source_title=str(row[2]),
            source_author=str(row[3]) if row[3] else None,
            publication_year=int(row[4]),
            language_label=str(row[5]),
            sequence=int(row[6]),
            display_text=str(row[7]),
            search_text=str(row[8]),
            printed_page=str(row[9]) if row[9] else None,
            printed_page_end=str(row[10]) if row[10] else None,
            scan_leaf=int(row[11]) if row[11] is not None else None,
            scan_leaf_end=int(row[12]) if row[12] is not None else None,
            scan_url=str(row[13]),
        )
        for row in connection.execute(
            """
            SELECT passages.id, passages.source_id, sources.title, sources.author,
                   sources.publication_year, sources.language_label, passages.sequence,
                   passages.display_text, passages.search_text,
                   passages.printed_page, passages.printed_page_end,
                   passages.scan_leaf, passages.scan_leaf_end, passages.scan_url
            FROM passages
            JOIN sources ON sources.id = passages.source_id
            WHERE passages.status != 'REJECTED'
              AND sources.status != 'REJECTED'
              AND trim(passages.search_text) != ''
            ORDER BY passages.source_id, passages.sequence
            """
        )
    ]


def load_entries(connection: sqlite3.Connection) -> list[EntryQuery]:
    entries: list[EntryQuery] = []
    for row in connection.execute(
        """
        SELECT id, slug, preferred_label, scope_note
        FROM entries
        WHERE status != 'REJECTED'
        ORDER BY preferred_label COLLATE NOCASE
        """
    ):
        forms = [str(row[2])]
        forms.extend(
            str(term[0])
            for term in connection.execute(
                """
                SELECT DISTINCT term_forms.display_form
                FROM entry_term_links
                JOIN term_forms ON term_forms.id = entry_term_links.term_form_id
                WHERE entry_term_links.entry_id = ?
                  AND entry_term_links.status != 'REJECTED'
                ORDER BY term_forms.display_form COLLATE NOCASE
                """,
                (row[0],),
            )
        )
        unique_forms = tuple(dict.fromkeys(form.strip() for form in forms if form.strip()))
        entries.append(
            EntryQuery(
                id=str(row[0]),
                slug=str(row[1]),
                preferred_label=str(row[2]),
                scope_note=str(row[3]),
                forms=unique_forms,
            )
        )
    return entries


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


class LexicalIndex:
    def __init__(self, passages: list[PassageRecord]) -> None:
        self.normalized = [normalize_alignment_text(item.search_text) for item in passages]
        self.long_s = [
            normalize_alignment_text(item.search_text, long_s_ocr=True) for item in passages
        ]
        locations: dict[str, set[int]] = defaultdict(set)
        for index, text in enumerate(self.normalized):
            for token in set(text.split()):
                if len(token) >= 4:
                    locations[token].add(index)
        self.token_locations = locations
        self.vocabulary = tuple(locations)

    def rank(self, entry: EntryQuery, *, limit: int = DEFAULT_CANDIDATES) -> list[tuple[int, float]]:
        normalized_forms = tuple(
            dict.fromkeys(
                form
                for form in (normalize_alignment_text(value) for value in entry.forms)
                if form
            )
        )
        long_s_forms = tuple(
            dict.fromkeys(
                form
                for form in (
                    normalize_alignment_text(value, long_s_ocr=True) for value in entry.forms
                )
                if form
            )
        )
        scores: dict[int, float] = defaultdict(float)
        for index, text in enumerate(self.normalized):
            best = 0.0
            for form in normalized_forms:
                if _contains_phrase(text, form):
                    best = max(best, 100.0 + 4.0 * len(form.split()) + min(len(form), 30) / 30)
            if best:
                scores[index] = best

        for index, text in enumerate(self.long_s):
            best = scores.get(index, 0.0)
            for form in long_s_forms:
                if _contains_phrase(text, form):
                    best = max(best, 88.0 + 3.0 * len(form.split()))
            if best:
                scores[index] = best

        compact_forms = tuple(
            form.replace(" ", "") for form in normalized_forms if " " in form and len(form) >= 8
        )
        if compact_forms:
            for index, text in enumerate(self.normalized):
                compact_text = text.replace(" ", "")
                for form in compact_forms:
                    if form in compact_text:
                        scores[index] = max(scores.get(index, 0.0), 82.0)

        for form in normalized_forms:
            if " " in form or len(form) < 5:
                continue
            for match in difflib.get_close_matches(
                form,
                self.vocabulary,
                n=24,
                cutoff=FUZZY_FORM_CUTOFF,
            ):
                similarity = difflib.SequenceMatcher(a=form, b=match).ratio()
                for index in self.token_locations[match]:
                    scores[index] = max(scores.get(index, 0.0), 55.0 + 25.0 * similarity)

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]


def load_embedding_matrix(output_dir: Path) -> tuple[list[str], np.ndarray]:
    keys_path = output_dir / "keys.json"
    vectors_path = output_dir / "vectors.npy"
    if not keys_path.exists() or not vectors_path.exists():
        raise RuntimeError("Embedding keys/vectors are unavailable; fetch the completed batch first")
    keys = json.loads(keys_path.read_text(encoding="utf-8"))
    matrix = np.load(vectors_path, mmap_mode="r", allow_pickle=False)
    if matrix.ndim != 2 or matrix.shape[0] != len(keys):
        raise RuntimeError("Embedding key and vector counts do not agree")
    return [str(key) for key in keys], matrix


def dense_rankings(
    entries: list[EntryQuery],
    passages: list[PassageRecord],
    *,
    embedding_output_dir: Path,
    limit: int = DEFAULT_CANDIDATES,
) -> dict[str, list[tuple[int, float]]]:
    keys, matrix = load_embedding_matrix(embedding_output_dir)
    key_index = {key: index for index, key in enumerate(keys)}
    passage_rows: list[int] = []
    passage_indices: list[int] = []
    for passage_index, passage in enumerate(passages):
        row = key_index.get(f"passage:{passage.id}")
        if row is not None:
            passage_rows.append(row)
            passage_indices.append(passage_index)
    if not passage_rows:
        raise RuntimeError("Embedding artifact contains no current passage IDs")
    passage_matrix = np.asarray(matrix[passage_rows], dtype=np.float32)

    result: dict[str, list[tuple[int, float]]] = {}
    for entry in entries:
        query_row = key_index.get(f"query:{entry.id}")
        if query_row is None:
            result[entry.id] = []
            continue
        query = np.asarray(matrix[query_row], dtype=np.float32)
        scores = passage_matrix @ query
        count = min(limit, len(scores))
        candidate_rows = np.argpartition(scores, -count)[-count:]
        ordered = candidate_rows[np.argsort(scores[candidate_rows])[::-1]]
        result[entry.id] = [
            (passage_indices[int(row)], float(scores[int(row)])) for row in ordered
        ]
    return result


def reciprocal_rank_fusion(
    lexical: list[tuple[int, float]],
    dense: list[tuple[int, float]],
    *,
    limit: int = DEFAULT_CANDIDATES,
) -> list[tuple[int, float, int | None, int | None]]:
    scores: dict[int, float] = defaultdict(float)
    lexical_rank = {index: rank for rank, (index, _) in enumerate(lexical, start=1)}
    dense_rank = {index: rank for rank, (index, _) in enumerate(dense, start=1)}
    lexical_scores = dict(lexical)
    for index, rank in lexical_rank.items():
        lexical_score = lexical_scores[index]
        quality_weight = 2.0 if lexical_score >= 100 else 1.5 if lexical_score >= 82 else 1.0
        scores[index] += quality_weight / (RRF_CONSTANT + rank)
    for index, rank in dense_rank.items():
        scores[index] += 1.0 / (RRF_CONSTANT + rank)
    ordered = sorted(scores, key=lambda index: (-scores[index], index))[:limit]
    return [
        (index, scores[index], lexical_rank.get(index), dense_rank.get(index))
        for index in ordered
    ]


def gold_passages(connection: sqlite3.Connection) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in connection.execute(
        """
        SELECT entry_id, passage_id
        FROM occurrences
        WHERE status IN ('CORE', 'SUGGESTED')
        ORDER BY entry_id, passage_id
        """
    ):
        result[str(row[0])].add(str(row[1]))
    return result


def _citation(passage: PassageRecord) -> str:
    author = f"{passage.source_author}, " if passage.source_author else ""
    page = passage.printed_page
    if passage.printed_page_end and passage.printed_page_end != page:
        page = f"{page}–{passage.printed_page_end}" if page else passage.printed_page_end
    location = f", p. {page}" if page else ""
    return f"{author}{passage.source_title} ({passage.publication_year}){location}"


def build_retrieval(
    connection: sqlite3.Connection,
    *,
    var_dir: Path,
    mode: str = "hybrid",
    limit: int = DEFAULT_CANDIDATES,
) -> dict[str, object]:
    if mode not in {"lexical", "dense", "hybrid"}:
        raise ValueError("mode must be lexical, dense, or hybrid")
    passages = load_passages(connection)
    entries = load_entries(connection)
    lexical_index = LexicalIndex(passages)
    embedding_output_dir = artifact_dir(var_dir)
    dense = (
        {entry.id: [] for entry in entries}
        if mode == "lexical"
        else dense_rankings(
            entries,
            passages,
            embedding_output_dir=embedding_output_dir,
            limit=limit,
        )
    )
    gold = gold_passages(connection)
    output_dir = var_dir / "retrieval" / RETRIEVAL_VERSION / mode
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = output_dir / "candidates.jsonl"
    packet_path = output_dir / "historian-packet.md"

    entry_reports: list[dict[str, object]] = []
    packet: list[str] = [
        "# Premodern Concordance retrieval packet",
        "",
        f"Built {datetime.now(timezone.utc).isoformat()} with `{RETRIEVAL_VERSION}`.",
        "",
    ]
    with candidates_path.open("w", encoding="utf-8") as candidates:
        for entry in entries:
            lexical = lexical_index.rank(entry, limit=limit) if mode != "dense" else []
            fused = reciprocal_rank_fusion(lexical, dense[entry.id], limit=limit)
            lexical_scores = dict(lexical)
            dense_scores = dict(dense[entry.id])
            ranked_ids = [passages[index].id for index, _, _, _ in fused]
            known = gold.get(entry.id, set())
            ranks = [ranked_ids.index(item) + 1 for item in known if item in ranked_ids]
            report = {
                "entry_id": entry.id,
                "entry_label": entry.preferred_label,
                "gold_count": len(known),
                "gold_found": len(ranks),
                "best_gold_rank": min(ranks) if ranks else None,
                "recall_at_20": sum(rank <= 20 for rank in ranks) / len(known) if known else None,
                "recall_at_50": sum(rank <= 50 for rank in ranks) / len(known) if known else None,
                "hit_at_20": any(rank <= 20 for rank in ranks) if known else None,
                "hit_at_50": any(rank <= 50 for rank in ranks) if known else None,
            }
            entry_reports.append(report)
            packet.extend([f"## {entry.preferred_label}", ""])
            if known:
                packet.append(
                    f"Known evidence recovered: {len(ranks)}/{len(known)}; best rank: "
                    f"{min(ranks) if ranks else 'not in top ' + str(limit)}."
                )
                packet.append("")
            for rank, (index, score, lexical_rank, dense_rank) in enumerate(fused, start=1):
                passage = passages[index]
                record = {
                    "entry_id": entry.id,
                    "entry_label": entry.preferred_label,
                    "rank": rank,
                    "passage_id": passage.id,
                    "source_id": passage.source_id,
                    "citation": _citation(passage),
                    "language": passage.language_label,
                    "printed_page": passage.printed_page,
                    "printed_page_end": passage.printed_page_end,
                    "scan_leaf": passage.scan_leaf,
                    "scan_leaf_end": passage.scan_leaf_end,
                    "scan_url": passage.scan_url,
                    "rrf_score": score,
                    "lexical_rank": lexical_rank,
                    "lexical_score": lexical_scores.get(index),
                    "dense_rank": dense_rank,
                    "dense_score": dense_scores.get(index),
                    "known_evidence": passage.id in known,
                    "text": passage.display_text,
                }
                candidates.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                if rank <= 10:
                    known_marker = " **[KNOWN EVIDENCE]**" if passage.id in known else ""
                    packet.extend(
                        [
                            f"{rank}. **{_citation(passage)}**{known_marker}",
                            f"   - retrieval: lexical {lexical_rank or '—'}; dense {dense_rank or '—'}",
                            f"   - {passage.display_text.replace(chr(10), ' ')[:700]}",
                            f"   - [scan]({passage.scan_url})" if passage.scan_url else "",
                            "",
                        ]
                    )

    evaluated = [item for item in entry_reports if item["gold_count"]]
    report = {
        "retrieval_version": RETRIEVAL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "passage_count": len(passages),
        "entry_count": len(entries),
        "candidate_limit": limit,
        "entries_with_gold": len(evaluated),
        "macro_recall_at_20": (
            sum(float(item["recall_at_20"]) for item in evaluated) / len(evaluated)
            if evaluated
            else None
        ),
        "macro_recall_at_50": (
            sum(float(item["recall_at_50"]) for item in evaluated) / len(evaluated)
            if evaluated
            else None
        ),
        "known_entry_hit_rate_at_20": (
            sum(bool(item["hit_at_20"]) for item in evaluated) / len(evaluated)
            if evaluated
            else None
        ),
        "known_entry_hit_rate_at_50": (
            sum(bool(item["hit_at_50"]) for item in evaluated) / len(evaluated)
            if evaluated
            else None
        ),
        "micro_recall_at_20": (
            sum(
                int(item["gold_count"]) * float(item["recall_at_20"])
                for item in evaluated
            )
            / sum(int(item["gold_count"]) for item in evaluated)
            if evaluated
            else None
        ),
        "micro_recall_at_50": (
            sum(
                int(item["gold_count"]) * float(item["recall_at_50"])
                for item in evaluated
            )
            / sum(int(item["gold_count"]) for item in evaluated)
            if evaluated
            else None
        ),
        "entries": entry_reports,
        "candidates_sha256": _sha256_file(candidates_path),
    }
    packet_path.write_text("\n".join(line for line in packet if line is not None), encoding="utf-8")
    report["historian_packet_sha256"] = _sha256_file(packet_path)
    _write_json(output_dir / "report.json", report)
    return report

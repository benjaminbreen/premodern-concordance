from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import unicodedata
from difflib import SequenceMatcher
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .embeddings import gemini_api_key
from .retrieval import RETRIEVAL_VERSION, load_entries


MODEL = "gemini-3.1-flash-lite"
ANALYSIS_VERSION = "usage-claims-v1"
PROMPT_VERSION = "historical-usage-v1"
SCHEMA_VERSION = "contextual-usage-v1"
DEFAULT_TOP_K = 20
BATCH_INPUT_PRICE_PER_MILLION = 0.125
BATCH_OUTPUT_PRICE_PER_MILLION = 0.75

MENTION_TYPES = {"NAMED", "DESCRIBED", "IMPLIED", "ABSENT"}
RESOLUTIONS = {"SAME_ENTRY", "RELATED_DISTINCT", "AMBIGUOUS", "NOT_RELEVANT"}
RELATION_TYPES = {
    "BROADER",
    "NARROWER",
    "PART_OF",
    "PREPARATION_OF",
    "DERIVED_FROM",
    "CONCEPTUAL_OVERLAP",
    "FUNCTIONAL_ANALOGY",
    "CONTESTED_IDENTITY",
    "LATER_REFRAMING",
    "SHARED_PROBLEM",
    "OTHER",
}
CLAIM_TYPES = {
    "DEFINITION",
    "IDENTITY",
    "CAUSAL_EFFECT",
    "PROPERTY",
    "FUNCTION_USE",
    "ORIGIN_DISTRIBUTION",
    "CLASSIFICATION",
    "MECHANISM",
    "EVALUATION",
    "METHOD",
    "OTHER",
}
STANCES = {"ASSERTS", "DENIES", "QUALIFIES", "UNCERTAIN", "ATTRIBUTES", "REPORTS"}
EVIDENCE_BASES = {
    "OBSERVATION",
    "EXPERIMENT",
    "CASE_REPORT",
    "AUTHORITY_CITATION",
    "REASONING",
    "HEARSAY",
    "RECIPE_OR_INSTRUCTION",
    "UNSTATED",
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "mention_type": {"type": "string", "enum": sorted(MENTION_TYPES)},
        "resolution": {"type": "string", "enum": sorted(RESOLUTIONS)},
        "relation_type": {
            "type": "string",
            "enum": ["NONE", *sorted(RELATION_TYPES)],
        },
        "evidence_quote": {"type": "string"},
        "sense_gloss": {"type": "string"},
        "rationale": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "claims": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "claim_type": {"type": "string", "enum": sorted(CLAIM_TYPES)},
                    "summary": {"type": "string"},
                    "subject_text": {"type": "string"},
                    "object_text": {"type": "string"},
                    "stance": {"type": "string", "enum": sorted(STANCES)},
                    "evidence_basis": {
                        "type": "string",
                        "enum": sorted(EVIDENCE_BASES),
                    },
                    "attributed_authority": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "claim_type",
                    "summary",
                    "subject_text",
                    "object_text",
                    "stance",
                    "evidence_basis",
                    "attributed_authority",
                    "evidence_quote",
                    "confidence",
                ],
            },
        },
    },
    "required": [
        "mention_type",
        "resolution",
        "relation_type",
        "evidence_quote",
        "sense_gloss",
        "rationale",
        "confidence",
        "claims",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_dir(var_dir: Path) -> Path:
    return var_dir / "analysis" / ANALYSIS_VERSION


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> Iterable[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Invalid JSONL on line {line_number}: {path}") from error
            if not isinstance(value, dict):
                raise RuntimeError(f"JSONL line {line_number} is not an object: {path}")
            yield value


def _prompt(
    *,
    entry_label: str,
    scope_note: str,
    forms: tuple[str, ...],
    source_title: str,
    source_author: str | None,
    publication_year: int,
    language_label: str,
    previous_text: str,
    target_text: str,
    next_text: str,
) -> str:
    return f"""You are analyzing one passage for a cross-lingual concordance of historical scientific and medical writing. Classify what this passage does; do not decide from vocabulary or embedding similarity alone.

ENTRY
Preferred label: {entry_label}
Scope: {scope_note}
Known names/forms: {', '.join(forms)}

SOURCE
{source_author or 'Unknown author'}, {source_title} ({publication_year}); language: {language_label}

DECISION RULES
- SAME_ENTRY: the TARGET names or describes the entry's referent or intended historical sense. A genuine periphrasis or translation can be SAME_ENTRY.
- RELATED_DISTINCT: the TARGET concerns a distinct thing or concept that matters to the entry's history. Choose one relation_type.
- AMBIGUOUS: the evidence does not support either judgment securely.
- NOT_RELEVANT: the candidate is a retrieval false positive, incidental association, or unrelated homonym.
- relation_type must be NONE unless resolution is RELATED_DISTINCT.
- Do not collapse neighboring ideas. Breeding is not eugenics; transmutation is not automatically evolution; a Cinchona species is not identical to bark or a preparation; an engineer is not simply a man of science. These may be RELATED_DISTINCT when the passage supports the connection.
- Mention types: NAMED uses an explicit term; DESCRIBED uses a clear periphrasis; IMPLIED is present only by strong context; ABSENT means the entry is not present.
- evidence_quote must be copied VERBATIM from TARGET and kept under 240 characters. Use an empty string only for NOT_RELEVANT.
- sense_gloss is a concrete description of this passage's local sense, no more than 18 words.
- Give at most two claims. A claim is a historically comparable assertion about this entry or the related entity—not merely any sentence in the passage.
- Claim summaries paraphrase; each claim evidence_quote must be copied VERBATIM from TARGET and kept under 300 characters.
- Treat the passage as historical evidence. Report what it asserts, denies, qualifies, attributes, or reports without correcting it to modern truth.
- PREVIOUS and NEXT may disambiguate the TARGET, but neither may supply an evidence quote.

PREVIOUS CONTEXT
{previous_text or '[none]'}

TARGET PASSAGE
{target_text}

NEXT CONTEXT
{next_text or '[none]'}
"""


def _passage_context(connection: sqlite3.Connection, passage_id: str) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT passages.id, passages.source_id, passages.sequence, passages.display_text,
               sources.title, sources.author, sources.publication_year, sources.language_label
        FROM passages
        JOIN sources ON sources.id = passages.source_id
        WHERE passages.id = ?
        """,
        (passage_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Retrieval candidate references missing passage {passage_id}")
    adjacent = {
        int(item[0]): str(item[1])
        for item in connection.execute(
            """
            SELECT sequence, display_text
            FROM passages
            WHERE source_id = ? AND sequence BETWEEN ? AND ?
              AND status != 'REJECTED'
            """,
            (row["source_id"], int(row["sequence"]) - 1, int(row["sequence"]) + 1),
        )
    }
    sequence = int(row["sequence"])
    return {
        "passage_id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "sequence": sequence,
        "target_text": str(row["display_text"]),
        "previous_text": adjacent.get(sequence - 1, ""),
        "next_text": adjacent.get(sequence + 1, ""),
        "source_title": str(row["title"]),
        "source_author": str(row["author"]) if row["author"] else None,
        "publication_year": int(row["publication_year"]),
        "language_label": str(row["language_label"]),
    }


def prepare_analysis_batch(
    connection: sqlite3.Connection,
    *,
    var_dir: Path,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, object]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    candidates_path = (
        var_dir / "retrieval" / RETRIEVAL_VERSION / "hybrid" / "candidates.jsonl"
    )
    if not candidates_path.exists():
        raise RuntimeError("Build hybrid retrieval before preparing candidate analysis")

    entries = {entry.id: entry for entry in load_entries(connection)}
    selected = [
        record
        for record in _read_jsonl(candidates_path)
        if int(record.get("rank", top_k + 1)) <= top_k
    ]
    if not selected:
        raise RuntimeError("Hybrid retrieval contains no candidates at the requested cutoff")

    output_dir = artifact_dir(var_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "items.jsonl"
    requests_path = output_dir / "requests.jsonl"
    estimated_input_tokens = 0
    seen: set[str] = set()
    with items_path.open("w", encoding="utf-8") as items, requests_path.open(
        "w", encoding="utf-8"
    ) as requests:
        for candidate in selected:
            entry_id = str(candidate["entry_id"])
            passage_id = str(candidate["passage_id"])
            entry = entries.get(entry_id)
            if entry is None:
                raise RuntimeError(f"Retrieval candidate references missing entry {entry_id}")
            context = _passage_context(connection, passage_id)
            prompt = _prompt(
                entry_label=entry.preferred_label,
                scope_note=entry.scope_note,
                forms=entry.forms,
                source_title=str(context["source_title"]),
                source_author=context["source_author"],
                publication_year=int(context["publication_year"]),
                language_label=str(context["language_label"]),
                previous_text=str(context["previous_text"]),
                target_text=str(context["target_text"]),
                next_text=str(context["next_text"]),
            )
            digest = _sha256_bytes(
                f"{ANALYSIS_VERSION}\0{entry_id}\0{passage_id}\0{prompt}".encode("utf-8")
            )
            key = f"usage-{digest[:24]}"
            if key in seen:
                raise RuntimeError(f"Duplicate analysis request key {key}")
            seen.add(key)
            estimated_input_tokens += max(1, round(len(prompt) / 4))
            item = {
                "key": key,
                "entry_id": entry_id,
                "entry_label": entry.preferred_label,
                "passage_id": passage_id,
                "source_id": context["source_id"],
                "retrieval_method": RETRIEVAL_VERSION,
                "retrieval_rank": int(candidate["rank"]),
                "rrf_score": candidate.get("rrf_score"),
                "lexical_rank": candidate.get("lexical_rank"),
                "dense_rank": candidate.get("dense_rank"),
                "target_text": context["target_text"],
                "input_sha256": _sha256_bytes(prompt.encode("utf-8")),
                "prompt": prompt,
            }
            items.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            request = {
                "key": key,
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generation_config": {
                        "temperature": 0,
                        "max_output_tokens": 1200,
                        "response_mime_type": "application/json",
                        "response_json_schema": RESPONSE_SCHEMA,
                        "thinking_config": {
                            "thinking_level": "MINIMAL",
                            "include_thoughts": False,
                        },
                    },
                },
            }
            requests.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")

    requests_hash = _sha256_file(requests_path)
    run_id = f"run-{ANALYSIS_VERSION}-{requests_hash[:16]}"
    entry_counts = Counter(str(record["entry_id"]) for record in selected)
    manifest = {
        "analysis_version": ANALYSIS_VERSION,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "model": MODEL,
        "model_run_id": run_id,
        "retrieval_version": RETRIEVAL_VERSION,
        "top_k": top_k,
        "request_count": len(selected),
        "entry_count": len(entry_counts),
        "entry_candidate_counts": dict(sorted(entry_counts.items())),
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_batch_input_cost_usd": round(
            estimated_input_tokens / 1_000_000 * BATCH_INPUT_PRICE_PER_MILLION, 4
        ),
        "items_sha256": _sha256_file(items_path),
        "requests_sha256": requests_hash,
        "requests_bytes": requests_path.stat().st_size,
        "retrieval_candidates_sha256": _sha256_file(candidates_path),
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _client(repository: Path):
    from google import genai

    return genai.Client(api_key=gemini_api_key(repository))


def submit_analysis_batch(*, repository: Path, output_dir: Path) -> dict[str, object]:
    from google.genai import types

    requests_path = output_dir / "requests.jsonl"
    manifest_path = output_dir / "manifest.json"
    if not requests_path.exists() or not manifest_path.exists():
        raise RuntimeError("Run prepare-analysis before submitting a batch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["requests_sha256"] != _sha256_file(requests_path):
        raise RuntimeError("Analysis request file changed after its manifest was written")

    client = _client(repository)
    upload_path = output_dir / "upload.json"
    upload_record = (
        json.loads(upload_path.read_text(encoding="utf-8")) if upload_path.exists() else {}
    )
    if upload_record.get("input_file_sha256") == manifest["requests_sha256"]:
        uploaded_name = str(upload_record["input_file_name"])
    else:
        uploaded = client.files.upload(
            file=requests_path,
            config=types.UploadFileConfig(mime_type="jsonl", display_name=requests_path.name),
        )
        uploaded_name = str(uploaded.name)
        upload_record = {
            "input_file_name": uploaded_name,
            "input_file_sha256": manifest["requests_sha256"],
            "uploaded_at": utc_now(),
        }
        _write_json(upload_path, upload_record)

    job = client.batches.create(
        model=MODEL,
        src=types.BatchJobSource(file_name=uploaded_name),
        config={"display_name": f"Premodern usage analysis {manifest['requests_sha256'][:12]}"},
    )
    record = {
        "job_name": job.name,
        "state": job.state.name if job.state else None,
        "model": MODEL,
        "model_run_id": manifest["model_run_id"],
        "input_file_name": uploaded_name,
        "input_file_sha256": manifest["requests_sha256"],
        "submitted_at": utc_now(),
    }
    _write_json(output_dir / "batch.json", record)
    return record


def _batch_job(repository: Path, output_dir: Path):
    record_path = output_dir / "batch.json"
    if not record_path.exists():
        raise RuntimeError("No candidate-analysis batch has been submitted")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    client = _client(repository)
    return client, client.batches.get(name=record["job_name"]), record


def analysis_batch_status(*, repository: Path, output_dir: Path) -> dict[str, object]:
    _, job, record = _batch_job(repository, output_dir)
    status = {
        **record,
        "state": job.state.name if job.state else None,
        "updated_at": job.update_time.isoformat() if job.update_time else None,
        "output_file_name": job.dest.file_name if job.dest and job.dest.file_name else None,
        "error": str(job.error) if job.error else None,
    }
    _write_json(output_dir / "batch.json", status)
    return status


def _alignment_stream(value: str) -> tuple[str, list[int], list[int]]:
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for index, original in enumerate(value.replace("ſ", "s")):
        for character in unicodedata.normalize("NFKD", original):
            if unicodedata.category(character) == "Mn" or not character.isalnum():
                continue
            for folded in character.casefold():
                characters.append(folded)
                starts.append(index)
                ends.append(index + 1)
    return "".join(characters), starts, ends


def _locate_evidence_details(
    text: str,
    quote: str,
) -> tuple[int, int, str, float] | None:
    quote = quote.strip()
    if not quote:
        return None
    exact = text.find(quote)
    if exact >= 0:
        return exact, exact + len(quote), "EXACT", 1.0
    tokens = re.findall(r"\S+", quote)
    if tokens:
        pattern = r"\s+".join(re.escape(token) for token in tokens)
        match = re.search(pattern, text)
        if match is not None:
            return match.start(), match.end(), "WHITESPACE", 1.0

    normalized_quote, _, _ = _alignment_stream(quote)
    normalized_text, starts, ends = _alignment_stream(text)
    if not normalized_quote or not normalized_text:
        return None
    normalized_start = normalized_text.find(normalized_quote)
    if normalized_start >= 0:
        normalized_end = normalized_start + len(normalized_quote)
        return (
            starts[normalized_start],
            ends[normalized_end - 1],
            "OCR_NORMALIZED",
            1.0,
        )

    # Models often regularize long-s, hyphenation, or a few damaged OCR
    # characters even when explicitly asked to quote. Align only substantial
    # quotes and require high character agreement; the stored evidence remains
    # the exact source slice, never the model's cleaned rendering.
    if len(normalized_quote) < 24:
        return None
    matcher = SequenceMatcher(None, normalized_quote, normalized_text, autojunk=False)
    candidate_starts: set[int] = set()
    for quote_start, text_start, size in matcher.get_matching_blocks():
        if size < 4:
            continue
        inferred = text_start - quote_start
        candidate_starts.update(
            range(max(0, inferred - 6), min(len(normalized_text), inferred + 7))
        )
    best_ratio = 0.0
    best_span: tuple[int, int] | None = None
    delta = max(4, len(normalized_quote) // 10)
    for candidate_start in candidate_starts:
        for length_delta in range(-delta, delta + 1, 2):
            candidate_end = min(
                len(normalized_text),
                candidate_start + len(normalized_quote) + length_delta,
            )
            if candidate_end <= candidate_start:
                continue
            ratio = SequenceMatcher(
                None,
                normalized_quote,
                normalized_text[candidate_start:candidate_end],
                autojunk=False,
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_span = (candidate_start, candidate_end)
    if best_span is None or best_ratio < 0.82:
        return None
    return (
        starts[best_span[0]],
        ends[best_span[1] - 1],
        "OCR_FUZZY",
        best_ratio,
    )


def locate_evidence(text: str, quote: str) -> tuple[int, int] | None:
    details = _locate_evidence_details(text, quote)
    return (details[0], details[1]) if details else None


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    result = value.strip()
    if not allow_empty and not result:
        raise ValueError(f"{field} must not be empty")
    return result


def _enum(value: object, field: str, allowed: set[str]) -> str:
    result = _string(value, field)
    if result not in allowed:
        raise ValueError(f"{field} has unsupported value {result}")
    return result


def _confidence(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return result


def validate_analysis(
    value: object,
    *,
    target_text: str,
) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    if not isinstance(value, dict):
        raise ValueError("response must be an object")
    mention_type = _enum(value.get("mention_type"), "mention_type", MENTION_TYPES)
    resolution = _enum(value.get("resolution"), "resolution", RESOLUTIONS)
    relation_raw = _string(value.get("relation_type"), "relation_type")
    if resolution == "RELATED_DISTINCT":
        if relation_raw not in RELATION_TYPES:
            raise ValueError("RELATED_DISTINCT requires a supported relation_type")
        relation_type: str | None = relation_raw
    else:
        if relation_raw != "NONE":
            raise ValueError("relation_type must be NONE unless resolution is RELATED_DISTINCT")
        relation_type = None

    evidence_quote = _string(value.get("evidence_quote"), "evidence_quote", allow_empty=True)
    evidence_details = _locate_evidence_details(target_text, evidence_quote)
    if resolution != "NOT_RELEVANT" and evidence_details is None:
        raise ValueError("a relevant or ambiguous usage requires a verbatim TARGET evidence quote")
    if resolution == "NOT_RELEVANT" and evidence_details is None:
        evidence_quote = ""
    evidence_span = (evidence_details[0], evidence_details[1]) if evidence_details else None

    sense_gloss = _string(value.get("sense_gloss"), "sense_gloss", allow_empty=True)
    if resolution != "NOT_RELEVANT" and not sense_gloss:
        raise ValueError("a relevant or ambiguous usage requires a sense_gloss")
    usage = {
        "mention_type": mention_type,
        "resolution": resolution,
        "relation_type": relation_type,
        "evidence_start": evidence_span[0] if evidence_span else None,
        "evidence_end": evidence_span[1] if evidence_span else None,
        "evidence_text": target_text[evidence_span[0] : evidence_span[1]] if evidence_span else None,
        "sense_gloss": sense_gloss or None,
        "rationale": _string(value.get("rationale"), "rationale"),
        "confidence": _confidence(value.get("confidence"), "confidence"),
    }

    claims_value = value.get("claims")
    if not isinstance(claims_value, list) or len(claims_value) > 2:
        raise ValueError("claims must be a list containing at most two items")
    claims: list[dict[str, object]] = []
    warnings: list[str] = []
    if evidence_details and evidence_details[2] == "OCR_FUZZY":
        warnings.append(f"usage evidence OCR-aligned at {evidence_details[3]:.3f}")
    if resolution == "NOT_RELEVANT" and claims_value:
        warnings.append("discarded claims attached to NOT_RELEVANT response")
        claims_value = []
    for index, claim_value in enumerate(claims_value):
        try:
            if not isinstance(claim_value, dict):
                raise ValueError("claim must be an object")
            claim_quote = _string(
                claim_value.get("evidence_quote"),
                f"claims[{index}].evidence_quote",
            )
            claim_details = _locate_evidence_details(target_text, claim_quote)
            if claim_details is None:
                raise ValueError("claim evidence is not a verbatim TARGET quote")
            claim_span = (claim_details[0], claim_details[1])
            claims.append(
                {
                    "claim_index": index,
                    "claim_type": _enum(
                        claim_value.get("claim_type"),
                        f"claims[{index}].claim_type",
                        CLAIM_TYPES,
                    ),
                    "summary": _string(claim_value.get("summary"), f"claims[{index}].summary"),
                    "subject_text": _string(
                        claim_value.get("subject_text"), f"claims[{index}].subject_text"
                    ),
                    "object_text": _string(
                        claim_value.get("object_text"),
                        f"claims[{index}].object_text",
                        allow_empty=True,
                    )
                    or None,
                    "stance": _enum(
                        claim_value.get("stance"), f"claims[{index}].stance", STANCES
                    ),
                    "evidence_basis": _enum(
                        claim_value.get("evidence_basis"),
                        f"claims[{index}].evidence_basis",
                        EVIDENCE_BASES,
                    ),
                    "attributed_authority": _string(
                        claim_value.get("attributed_authority"),
                        f"claims[{index}].attributed_authority",
                        allow_empty=True,
                    )
                    or None,
                    "evidence_start": claim_span[0],
                    "evidence_end": claim_span[1],
                    "evidence_text": target_text[claim_span[0] : claim_span[1]],
                    "confidence": _confidence(
                        claim_value.get("confidence"), f"claims[{index}].confidence"
                    ),
                }
            )
            if claim_details[2] == "OCR_FUZZY":
                warnings.append(
                    f"claim {index} evidence OCR-aligned at {claim_details[3]:.3f}"
                )
        except ValueError as error:
            warnings.append(f"claim {index} discarded: {error}")
    return usage, claims, warnings


def _response_text(result: dict[str, object]) -> str:
    response = result.get("response")
    if not isinstance(response, dict):
        raise ValueError(str(result.get("error", "missing response")))
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("response has no candidates")
    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise ValueError("response candidate has no content parts")
    text_parts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
    if not text_parts:
        raise ValueError("response candidate has no text")
    return "".join(str(part) for part in text_parts)


def _token_usage(result: dict[str, object]) -> tuple[int, int]:
    response = result.get("response")
    metadata = response.get("usageMetadata", {}) if isinstance(response, dict) else {}
    if not isinstance(metadata, dict):
        return 0, 0
    input_tokens = int(metadata.get("promptTokenCount", 0) or 0)
    output_tokens = int(metadata.get("candidatesTokenCount", 0) or 0) + int(
        metadata.get("thoughtsTokenCount", 0) or 0
    )
    return input_tokens, output_tokens


def fetch_analysis_batch(
    connection: sqlite3.Connection,
    *,
    repository: Path,
    output_dir: Path,
) -> dict[str, object]:
    client, job, record = _batch_job(repository, output_dir)
    state = job.state.name if job.state else None
    if state != "JOB_STATE_SUCCEEDED":
        return analysis_batch_status(repository=repository, output_dir=output_dir)
    if not job.dest or not job.dest.file_name:
        raise RuntimeError("Succeeded analysis batch has no output file")

    content = client.files.download(file=job.dest.file_name)
    raw_path = output_dir / "responses.jsonl.gz"
    with gzip.open(raw_path, "wb") as handle:
        handle.write(content)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    items = {str(item["key"]): item for item in _read_jsonl(output_dir / "items.jsonl")}

    usages: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    input_tokens = 0
    output_tokens = 0
    seen_keys: set[str] = set()
    for result in _result_lines(content):
        key = str(result.get("key", ""))
        item = items.get(key)
        if item is None:
            failures.append({"key": key, "error": "response key not found in prepared items"})
            continue
        seen_keys.add(key)
        request_input, request_output = _token_usage(result)
        input_tokens += request_input
        output_tokens += request_output
        try:
            response_text = _response_text(result)
            response_value = json.loads(response_text)
            usage, item_claims, item_warnings = validate_analysis(
                response_value,
                target_text=str(item["target_text"]),
            )
        except (ValueError, json.JSONDecodeError) as error:
            failures.append({"key": key, "error": str(error)})
            continue
        usage_key = f"{manifest['model_run_id']}\0{key}".encode("utf-8")
        usage_id = f"usage-{_sha256_bytes(usage_key)[:24]}"
        status = (
            "SUGGESTED"
            if usage["resolution"] in {"SAME_ENTRY", "RELATED_DISTINCT"}
            else "PRIVATE"
        )
        usage_record = {
            **item,
            **usage,
            "usage_id": usage_id,
            "status": status,
        }
        usage_record.pop("prompt", None)
        usage_record.pop("target_text", None)
        usages.append(usage_record)
        for claim in item_claims:
            claim_key = f"{usage_id}\0{claim['claim_index']}".encode("utf-8")
            claims.append(
                {
                    **claim,
                    "claim_id": f"claim-{_sha256_bytes(claim_key)[:24]}",
                    "usage_id": usage_id,
                    "status": status,
                }
            )
        warnings.extend({"key": key, "warning": warning} for warning in item_warnings)

    for key in sorted(set(items) - seen_keys):
        failures.append({"key": key, "error": "batch output omitted prepared request"})

    output_sha256 = _sha256_bytes(content)
    cost_usd = input_tokens / 1_000_000 * BATCH_INPUT_PRICE_PER_MILLION + (
        output_tokens / 1_000_000 * BATCH_OUTPUT_PRICE_PER_MILLION
    )
    run_id = str(manifest["model_run_id"])
    with connection:
        connection.execute(
            """
            INSERT INTO model_runs (
              id, operation, provider, model_snapshot, prompt_version, schema_version,
              input_sha256, output_sha256, input_tokens, output_tokens, cost_usd,
              status, started_at, completed_at
            ) VALUES (?, 'CANDIDATE_ANALYSIS', 'GOOGLE', ?, ?, ?, ?, ?, ?, ?, ?,
                      'COMPLETE', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              output_sha256 = excluded.output_sha256,
              input_tokens = excluded.input_tokens,
              output_tokens = excluded.output_tokens,
              cost_usd = excluded.cost_usd,
              status = excluded.status,
              completed_at = excluded.completed_at
            """,
            (
                run_id,
                MODEL,
                PROMPT_VERSION,
                SCHEMA_VERSION,
                manifest["requests_sha256"],
                output_sha256,
                input_tokens,
                output_tokens,
                cost_usd,
                record.get("submitted_at", manifest["created_at"]),
                utc_now(),
            ),
        )
        connection.execute("DELETE FROM contextual_usages WHERE model_run_id = ?", (run_id,))
        for usage in usages:
            connection.execute(
                """
                INSERT INTO contextual_usages (
                  id, entry_id, passage_id, mention_type, resolution, relation_type,
                  evidence_start, evidence_end, evidence_text, sense_gloss, rationale,
                  confidence, retrieval_method, retrieval_rank, model_run_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage["usage_id"],
                    usage["entry_id"],
                    usage["passage_id"],
                    usage["mention_type"],
                    usage["resolution"],
                    usage["relation_type"],
                    usage["evidence_start"],
                    usage["evidence_end"],
                    usage["evidence_text"],
                    usage["sense_gloss"],
                    usage["rationale"],
                    usage["confidence"],
                    usage["retrieval_method"],
                    usage["retrieval_rank"],
                    run_id,
                    usage["status"],
                ),
            )
        for claim in claims:
            connection.execute(
                """
                INSERT INTO usage_claims (
                  id, usage_id, claim_index, claim_type, summary, subject_text,
                  object_text, stance, evidence_basis, attributed_authority,
                  evidence_start, evidence_end, evidence_text, confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim["claim_id"],
                    claim["usage_id"],
                    claim["claim_index"],
                    claim["claim_type"],
                    claim["summary"],
                    claim["subject_text"],
                    claim["object_text"],
                    claim["stance"],
                    claim["evidence_basis"],
                    claim["attributed_authority"],
                    claim["evidence_start"],
                    claim["evidence_end"],
                    claim["evidence_text"],
                    claim["confidence"],
                    claim["status"],
                ),
            )
        # This is an internal research release: a grounded model suggestion is
        # enough to make its entry, form, and passage eligible for the next
        # allowlisted projection. It remains visibly SUGGESTED rather than CORE.
        connection.execute(
            """
            UPDATE passages
            SET status = 'SUGGESTED', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'PRIVATE'
              AND id IN (
                SELECT passage_id FROM contextual_usages
                WHERE model_run_id = ? AND status = 'SUGGESTED'
              )
            """,
            (run_id,),
        )
        connection.execute(
            """
            UPDATE entries
            SET status = 'SUGGESTED', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'DRAFT'
              AND id IN (
                SELECT entry_id FROM contextual_usages
                WHERE model_run_id = ? AND status = 'SUGGESTED'
              )
            """,
            (run_id,),
        )
        connection.execute(
            """
            UPDATE entry_term_links
            SET status = 'SUGGESTED'
            WHERE status = 'PRIVATE'
              AND entry_id IN (
                SELECT entry_id FROM contextual_usages
                WHERE model_run_id = ? AND status = 'SUGGESTED'
              )
            """,
            (run_id,),
        )

    results_path = output_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as handle:
        for usage in usages:
            item_claims = [claim for claim in claims if claim["usage_id"] == usage["usage_id"]]
            handle.write(
                json.dumps(
                    {"usage": usage, "claims": item_claims},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    _write_json(output_dir / "failures.json", failures)
    _write_json(output_dir / "warnings.json", warnings)
    summary = {
        **record,
        "state": state,
        "model_run_id": run_id,
        "request_count": len(items),
        "usage_count": len(usages),
        "claim_count": len(claims),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "resolution_counts": dict(Counter(str(item["resolution"]) for item in usages)),
        "relation_counts": dict(
            Counter(str(item["relation_type"]) for item in usages if item["relation_type"])
        ),
        "mention_counts": dict(Counter(str(item["mention_type"]) for item in usages)),
        "claim_type_counts": dict(Counter(str(item["claim_type"]) for item in claims)),
        "stance_counts": dict(Counter(str(item["stance"]) for item in claims)),
        "evidence_basis_counts": dict(
            Counter(str(item["evidence_basis"]) for item in claims)
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "responses_sha256": output_sha256,
        "results_sha256": _sha256_file(results_path),
        "completed_at": utc_now(),
    }
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "batch.json", {**record, "state": state})
    return summary


def _result_lines(content: bytes) -> Iterable[dict[str, object]]:
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            result = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid analysis response JSON on line {line_number}") from error
        if not isinstance(result, dict):
            raise RuntimeError(f"Analysis response line {line_number} is not an object")
        yield result

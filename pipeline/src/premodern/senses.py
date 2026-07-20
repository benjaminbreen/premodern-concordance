from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .analysis import (
    BATCH_INPUT_PRICE_PER_MILLION,
    BATCH_OUTPUT_PRICE_PER_MILLION,
    MODEL,
)
from .embeddings import gemini_api_key


SENSE_VERSION = "sense-clusters-v1"
PROMPT_VERSION = "entry-local-senses-v1"
SCHEMA_VERSION = "sense-clusters-v1"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "senses": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "definition": {"type": "string"},
                    "usage_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["label", "definition", "usage_ids", "confidence"],
            },
        }
    },
    "required": ["senses"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_dir(var_dir: Path) -> Path:
    return var_dir / "analysis" / SENSE_VERSION


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


def _prompt(entry: dict[str, object], usages: list[dict[str, object]]) -> str:
    rows = []
    for usage in usages:
        quote = str(usage["evidence_text"]).replace("\n", " ")[:700]
        rows.append(
            f"- {usage['usage_id']} | {usage['publication_year']} | "
            f"{usage['language_label']} | {usage['sense_gloss']} | QUOTE: {quote}"
        )
    return f"""Group the grounded passage usages below into a small set of historically meaningful, entry-local senses.

ENTRY: {entry['preferred_label']}
SCOPE: {entry['scope_note']}

RULES
- This is closed-set clustering. Use only the supplied usage IDs.
- Assign every usage ID exactly once and do not invent IDs.
- A sense is a distinguishable local meaning or referential function, not merely a language, source, date, author, or wording difference.
- Prefer a few useful senses. Split only when a historian would learn something from the distinction.
- Do not merge distinct material, taxonomic, metaphorical, technical, and conceptual functions merely because they share a word.
- Labels should be concrete and no more than six words. Definitions should be one concise sentence grounded in the supplied usages.
- This operation clusters SAME_ENTRY usages only. It does not create links to other concordance entries.

USAGES
{chr(10).join(rows)}
"""


def prepare_sense_batch(
    connection: sqlite3.Connection,
    *,
    var_dir: Path,
    minimum_usages: int = 2,
) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    entries: dict[str, dict[str, object]] = {}
    for row in connection.execute(
        """
        SELECT u.id, u.entry_id, u.sense_gloss, u.evidence_text, u.retrieval_rank,
               e.preferred_label, e.scope_note, s.publication_year, s.language_label
        FROM contextual_usages u
        JOIN entries e ON e.id = u.entry_id
        JOIN passages p ON p.id = u.passage_id
        JOIN sources s ON s.id = p.source_id
        WHERE u.status IN ('CORE', 'SUGGESTED') AND u.resolution = 'SAME_ENTRY'
        ORDER BY e.preferred_label COLLATE NOCASE, s.publication_year, u.retrieval_rank
        """
    ):
        entry_id = str(row["entry_id"])
        entries[entry_id] = {
            "entry_id": entry_id,
            "preferred_label": str(row["preferred_label"]),
            "scope_note": str(row["scope_note"]),
        }
        grouped[entry_id].append(
            {
                "usage_id": str(row["id"]),
                "sense_gloss": str(row["sense_gloss"] or ""),
                "evidence_text": str(row["evidence_text"] or ""),
                "retrieval_rank": int(row["retrieval_rank"]),
                "publication_year": int(row["publication_year"]),
                "language_label": str(row["language_label"]),
            }
        )

    output_dir = artifact_dir(var_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "items.jsonl"
    requests_path = output_dir / "requests.jsonl"
    request_count = 0
    usage_count = 0
    estimated_input_tokens = 0
    with items_path.open("w", encoding="utf-8") as items, requests_path.open(
        "w", encoding="utf-8"
    ) as requests:
        for entry_id in sorted(grouped, key=lambda value: str(entries[value]["preferred_label"])):
            usages = grouped[entry_id]
            if len(usages) < minimum_usages:
                continue
            prompt = _prompt(entries[entry_id], usages)
            digest = _sha256_bytes(
                f"{SENSE_VERSION}\0{entry_id}\0{prompt}".encode("utf-8")
            )
            key = f"senses-{digest[:24]}"
            usage_ids = [str(usage["usage_id"]) for usage in usages]
            item = {
                "key": key,
                **entries[entry_id],
                "usage_ids": usage_ids,
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
                        "max_output_tokens": 1800,
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
            request_count += 1
            usage_count += len(usage_ids)
            estimated_input_tokens += max(1, round(len(prompt) / 4))
    if not request_count:
        raise RuntimeError("No entries have enough grounded usages for sense induction")

    requests_hash = _sha256_file(requests_path)
    manifest = {
        "sense_version": SENSE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "model": MODEL,
        "model_run_id": f"run-{SENSE_VERSION}-{requests_hash[:16]}",
        "created_at": utc_now(),
        "minimum_usages": minimum_usages,
        "request_count": request_count,
        "usage_count": usage_count,
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_batch_input_cost_usd": round(
            estimated_input_tokens / 1_000_000 * BATCH_INPUT_PRICE_PER_MILLION, 4
        ),
        "items_sha256": _sha256_file(items_path),
        "requests_sha256": requests_hash,
        "requests_bytes": requests_path.stat().st_size,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _client(repository: Path):
    from google import genai

    return genai.Client(api_key=gemini_api_key(repository))


def submit_sense_batch(*, repository: Path, output_dir: Path) -> dict[str, object]:
    from google.genai import types

    requests_path = output_dir / "requests.jsonl"
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["requests_sha256"] != _sha256_file(requests_path):
        raise RuntimeError("Sense request file changed after its manifest was written")
    client = _client(repository)
    uploaded = client.files.upload(
        file=requests_path,
        config=types.UploadFileConfig(mime_type="jsonl", display_name=requests_path.name),
    )
    job = client.batches.create(
        model=MODEL,
        src=types.BatchJobSource(file_name=str(uploaded.name)),
        config={"display_name": f"Premodern senses {manifest['requests_sha256'][:12]}"},
    )
    record = {
        "job_name": job.name,
        "state": job.state.name if job.state else None,
        "model": MODEL,
        "model_run_id": manifest["model_run_id"],
        "input_file_name": uploaded.name,
        "input_file_sha256": manifest["requests_sha256"],
        "submitted_at": utc_now(),
    }
    _write_json(output_dir / "batch.json", record)
    return record


def _batch_job(repository: Path, output_dir: Path):
    record = json.loads((output_dir / "batch.json").read_text(encoding="utf-8"))
    client = _client(repository)
    return client, client.batches.get(name=record["job_name"]), record


def sense_batch_status(*, repository: Path, output_dir: Path) -> dict[str, object]:
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


def validate_senses(value: object, expected_ids: list[str]) -> list[dict[str, object]]:
    if not isinstance(value, dict) or not isinstance(value.get("senses"), list):
        raise ValueError("response must contain a senses array")
    raw_senses = value["senses"]
    if not 1 <= len(raw_senses) <= 8:
        raise ValueError("response must contain one to eight senses")
    expected = set(expected_ids)
    assigned: list[str] = []
    labels: set[str] = set()
    senses: list[dict[str, object]] = []
    for index, raw in enumerate(raw_senses):
        if not isinstance(raw, dict):
            raise ValueError(f"sense {index} must be an object")
        label = str(raw.get("label", "")).strip()
        definition = str(raw.get("definition", "")).strip()
        usage_ids = raw.get("usage_ids")
        confidence = raw.get("confidence")
        if not label or not definition:
            raise ValueError(f"sense {index} needs a label and definition")
        normalized_label = label.casefold()
        if normalized_label in labels:
            raise ValueError(f"duplicate sense label {label}")
        labels.add(normalized_label)
        if not isinstance(usage_ids, list) or not usage_ids:
            raise ValueError(f"sense {index} has no usage IDs")
        ids = [str(identifier) for identifier in usage_ids]
        if len(ids) != len(set(ids)):
            raise ValueError(f"sense {index} repeats a usage ID")
        if any(identifier not in expected for identifier in ids):
            raise ValueError(f"sense {index} contains an unknown usage ID")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f"sense {index} confidence must be numeric")
        confidence_value = float(confidence)
        if not 0 <= confidence_value <= 1:
            raise ValueError(f"sense {index} confidence must be between 0 and 1")
        assigned.extend(ids)
        senses.append(
            {
                "label": label,
                "definition": definition,
                "usage_ids": ids,
                "confidence": confidence_value,
            }
        )
    if len(assigned) != len(set(assigned)):
        raise ValueError("a usage ID was assigned to more than one sense")
    missing = expected - set(assigned)
    if missing:
        raise ValueError(f"{len(missing)} expected usage IDs were not assigned")
    return senses


def repair_duplicate_assignments(value: object) -> object:
    """Keep the first sense assignment when a model repeats an otherwise valid ID."""
    if not isinstance(value, dict) or not isinstance(value.get("senses"), list):
        return value
    seen: set[str] = set()
    repaired_senses: list[object] = []
    for raw in value["senses"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("usage_ids"), list):
            repaired_senses.append(raw)
            continue
        usage_ids = []
        for identifier in raw["usage_ids"]:
            normalized = str(identifier)
            if normalized in seen:
                continue
            seen.add(normalized)
            usage_ids.append(identifier)
        if usage_ids:
            repaired_senses.append({**raw, "usage_ids": usage_ids})
    return {**value, "senses": repaired_senses}


def _response_text(result: dict[str, object]) -> str:
    response = result.get("response")
    candidates = response.get("candidates") if isinstance(response, dict) else None
    candidate = candidates[0] if isinstance(candidates, list) and candidates else None
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    values = [part.get("text") for part in parts or [] if isinstance(part, dict) and part.get("text")]
    if not values:
        raise ValueError(str(result.get("error", "response has no text")))
    return "".join(str(value) for value in values)


def _token_usage(result: dict[str, object]) -> tuple[int, int]:
    response = result.get("response")
    metadata = response.get("usageMetadata", {}) if isinstance(response, dict) else {}
    if not isinstance(metadata, dict):
        return 0, 0
    return (
        int(metadata.get("promptTokenCount", 0) or 0),
        int(metadata.get("candidatesTokenCount", 0) or 0)
        + int(metadata.get("thoughtsTokenCount", 0) or 0),
    )


def fetch_sense_batch(
    connection: sqlite3.Connection,
    *,
    repository: Path,
    output_dir: Path,
) -> dict[str, object]:
    client, job, record = _batch_job(repository, output_dir)
    state = job.state.name if job.state else None
    if state != "JOB_STATE_SUCCEEDED":
        return sense_batch_status(repository=repository, output_dir=output_dir)
    if not job.dest or not job.dest.file_name:
        raise RuntimeError("Succeeded sense batch has no output file")
    content = client.files.download(file=job.dest.file_name)
    with gzip.open(output_dir / "responses.jsonl.gz", "wb") as handle:
        handle.write(content)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    items = {str(item["key"]): item for item in _read_jsonl(output_dir / "items.jsonl")}

    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    input_tokens = 0
    output_tokens = 0
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid sense response JSON on line {line_number}") from error
        key = str(response.get("key", ""))
        item = items.get(key)
        if item is None:
            failures.append({"key": key, "error": "unknown response key"})
            continue
        request_input, request_output = _token_usage(response)
        input_tokens += request_input
        output_tokens += request_output
        try:
            response_value = json.loads(_response_text(response))
            expected_ids = [str(identifier) for identifier in item["usage_ids"]]
            try:
                senses = validate_senses(response_value, expected_ids)
            except ValueError as initial_error:
                if "more than one sense" not in str(initial_error):
                    raise
                senses = validate_senses(
                    repair_duplicate_assignments(response_value),
                    expected_ids,
                )
                warnings.append(
                    {
                        "key": key,
                        "entry_id": item["entry_id"],
                        "warning": "duplicate usage assignment kept in the first returned sense",
                    }
                )
        except (ValueError, json.JSONDecodeError) as error:
            failures.append({"key": key, "entry_id": item["entry_id"], "error": str(error)})
            continue
        results.append({"key": key, "entry_id": item["entry_id"], "senses": senses})

    run_id = str(manifest["model_run_id"])
    output_sha = _sha256_bytes(content)
    cost = input_tokens / 1_000_000 * BATCH_INPUT_PRICE_PER_MILLION + (
        output_tokens / 1_000_000 * BATCH_OUTPUT_PRICE_PER_MILLION
    )
    with connection:
        connection.execute(
            """
            INSERT INTO model_runs (
              id, operation, provider, model_snapshot, prompt_version, schema_version,
              input_sha256, output_sha256, input_tokens, output_tokens, cost_usd,
              status, started_at, completed_at
            ) VALUES (?, 'SENSE_INDUCTION', 'GOOGLE', ?, ?, ?, ?, ?, ?, ?, ?,
                      'COMPLETE', ?, ?)
            ON CONFLICT(id) DO UPDATE SET output_sha256=excluded.output_sha256,
              input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
              cost_usd=excluded.cost_usd, status='COMPLETE', completed_at=excluded.completed_at
            """,
            (
                run_id,
                MODEL,
                PROMPT_VERSION,
                SCHEMA_VERSION,
                manifest["requests_sha256"],
                output_sha,
                input_tokens,
                output_tokens,
                cost,
                record.get("submitted_at", manifest["created_at"]),
                utc_now(),
            ),
        )
        for result in results:
            entry_id = str(result["entry_id"])
            connection.execute(
                """
                UPDATE sense_memberships SET status='PRIVATE'
                WHERE sense_id IN (SELECT id FROM sense_clusters WHERE entry_id = ?)
                """,
                (entry_id,),
            )
            connection.execute(
                "UPDATE sense_clusters SET status='PRIVATE' WHERE entry_id = ?",
                (entry_id,),
            )
            for index, sense in enumerate(result["senses"]):
                sense_key = f"{run_id}\0{entry_id}\0{index}\0{sense['label']}".encode("utf-8")
                sense_id = f"sense-{_sha256_bytes(sense_key)[:24]}"
                connection.execute(
                    """
                    INSERT OR REPLACE INTO sense_clusters (
                      id, entry_id, label, definition, sort_order, confidence,
                      model_run_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SUGGESTED')
                    """,
                    (
                        sense_id,
                        entry_id,
                        sense["label"],
                        sense["definition"],
                        index,
                        sense["confidence"],
                        run_id,
                    ),
                )
                for usage_id in sense["usage_ids"]:
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO sense_memberships
                          (sense_id, usage_id, status)
                        VALUES (?, ?, 'SUGGESTED')
                        """,
                        (sense_id, usage_id),
                    )

    results_path = output_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    _write_json(output_dir / "failures.json", failures)
    _write_json(output_dir / "warnings.json", warnings)
    summary = {
        **record,
        "state": state,
        "request_count": len(items),
        "successful_entries": len(results),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "sense_count": sum(len(result["senses"]) for result in results),
        "membership_count": sum(
            len(sense["usage_ids"])
            for result in results
            for sense in result["senses"]
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "responses_sha256": output_sha,
        "results_sha256": _sha256_file(results_path),
        "completed_at": utc_now(),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary

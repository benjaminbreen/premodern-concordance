from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np


MODEL = "gemini-embedding-2"
DIMENSIONS = 768
ARTIFACT_VERSION = "gemini-embedding-2-retrieval-v1"
BATCH_PRICE_PER_MILLION_TOKENS = 0.10
STANDARD_PRICE_PER_MILLION_TOKENS = 0.20


@dataclass(frozen=True)
class EmbeddingItem:
    key: str
    kind: str
    subject_id: str
    text: str


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


def _read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("\"'") or None
    return None


def gemini_api_key(repository: Path) -> str:
    value = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    value = value or _read_env_value(repository / ".env.local", "GEMINI_API_KEY")
    value = value or _read_env_value(repository / ".env.local", "GOOGLE_API_KEY")
    if not value:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment or repository .env.local")
    return value


def artifact_dir(var_dir: Path) -> Path:
    return var_dir / "embeddings" / f"{MODEL}-{DIMENSIONS}"


def _term_forms(connection: sqlite3.Connection, entry_id: str) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT DISTINCT term_forms.display_form
            FROM entry_term_links
            JOIN term_forms ON term_forms.id = entry_term_links.term_form_id
            WHERE entry_term_links.entry_id = ?
              AND entry_term_links.status != 'REJECTED'
            ORDER BY term_forms.display_form COLLATE NOCASE
            """,
            (entry_id,),
        )
    ]


def embedding_items(connection: sqlite3.Connection) -> list[EmbeddingItem]:
    items: list[EmbeddingItem] = []
    for row in connection.execute(
        """
        SELECT passages.id, passages.search_text, passages.heading, sources.title
        FROM passages
        JOIN sources ON sources.id = passages.source_id
        WHERE passages.status != 'REJECTED'
          AND sources.status != 'REJECTED'
          AND trim(passages.search_text) != ''
        ORDER BY passages.source_id, passages.sequence
        """
    ):
        title_parts = [str(row[3])]
        if row[2]:
            title_parts.append(str(row[2]))
        title = " — ".join(title_parts)
        items.append(
            EmbeddingItem(
                key=f"passage:{row[0]}",
                kind="passage",
                subject_id=str(row[0]),
                text=f"title: {title} | text: {row[1]}",
            )
        )

    for row in connection.execute(
        """
        SELECT id, preferred_label, scope_note
        FROM entries
        WHERE status != 'REJECTED'
        ORDER BY id
        """
    ):
        forms = _term_forms(connection, str(row[0]))
        form_clause = f" Historical forms: {', '.join(forms)}." if forms else ""
        query = f"{row[1]}. {row[2]}{form_clause}"
        items.append(
            EmbeddingItem(
                key=f"query:{row[0]}",
                kind="query",
                subject_id=str(row[0]),
                text=f"task: search result | query: {query}",
            )
        )
    return items


def prepare_embedding_batch(
    connection: sqlite3.Connection,
    *,
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    items = embedding_items(connection)
    if not items:
        raise RuntimeError("No passages or entries are available for embedding")

    metadata_path = output_dir / "items.jsonl"
    requests_path = output_dir / "requests.jsonl"
    estimated_tokens = 0
    with metadata_path.open("w", encoding="utf-8") as metadata, requests_path.open(
        "w", encoding="utf-8"
    ) as requests:
        for item in items:
            encoded = item.text.encode("utf-8")
            estimated_tokens += max(1, round(len(item.text) / 4))
            metadata.write(
                json.dumps(
                    {
                        "key": item.key,
                        "kind": item.kind,
                        "subject_id": item.subject_id,
                        "input_sha256": _sha256_bytes(encoded),
                        "text": item.text,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
            requests.write(
                json.dumps(
                    {
                        "key": item.key,
                        "request": {
                            "output_dimensionality": DIMENSIONS,
                            "content": {"parts": [{"text": item.text}]},
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

    counts = {
        kind: sum(item.kind == kind for item in items) for kind in ("passage", "query")
    }
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "document_prefix": "title: {title} | text: {passage}",
        "query_prefix": "task: search result | query: {entry}",
        "item_count": len(items),
        "counts": counts,
        "estimated_tokens": estimated_tokens,
        "estimated_batch_cost_usd": round(
            estimated_tokens / 1_000_000 * BATCH_PRICE_PER_MILLION_TOKENS, 4
        ),
        "items_sha256": _sha256_file(metadata_path),
        "requests_sha256": _sha256_file(requests_path),
        "requests_bytes": requests_path.stat().st_size,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _client(repository: Path):
    from google import genai

    return genai.Client(api_key=gemini_api_key(repository))


def submit_embedding_batch(*, repository: Path, output_dir: Path) -> dict[str, object]:
    from google.genai import types

    requests_path = output_dir / "requests.jsonl"
    manifest_path = output_dir / "manifest.json"
    if not requests_path.exists() or not manifest_path.exists():
        raise RuntimeError("Run prepare-embeddings before submitting a batch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["requests_sha256"] != _sha256_file(requests_path):
        raise RuntimeError("Embedding request file changed after its manifest was written")

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
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(upload_path, upload_record)
    job = client.batches.create_embeddings(
        model=MODEL,
        src=types.EmbeddingsBatchJobSource(file_name=uploaded_name),
        config={"display_name": f"Premodern passages {manifest['requests_sha256'][:12]}"},
    )
    record = {
        "job_name": job.name,
        "state": job.state.name if job.state else None,
        "model": MODEL,
        "input_file_name": uploaded_name,
        "input_file_sha256": manifest["requests_sha256"],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(output_dir / "batch.json", record)
    return record


def _batch_job(repository: Path, output_dir: Path):
    record_path = output_dir / "batch.json"
    if not record_path.exists():
        raise RuntimeError("No embedding batch has been submitted")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    client = _client(repository)
    return client, client.batches.get(name=record["job_name"]), record


def embedding_batch_status(*, repository: Path, output_dir: Path) -> dict[str, object]:
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


def _result_lines(content: bytes) -> Iterable[dict[str, object]]:
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid embedding response JSON on line {line_number}") from error


def fetch_embedding_batch(*, repository: Path, output_dir: Path) -> dict[str, object]:
    client, job, record = _batch_job(repository, output_dir)
    state = job.state.name if job.state else None
    if state != "JOB_STATE_SUCCEEDED":
        return embedding_batch_status(repository=repository, output_dir=output_dir)
    if not job.dest or not job.dest.file_name:
        raise RuntimeError("Succeeded embedding batch has no output file")

    content = client.files.download(file=job.dest.file_name)
    raw_path = output_dir / "responses.jsonl.gz"
    with gzip.open(raw_path, "wb") as handle:
        handle.write(content)

    vectors: list[list[float]] = []
    keys: list[str] = []
    failures: list[dict[str, object]] = []
    token_count = 0
    for result in _result_lines(content):
        key = str(result.get("key", ""))
        response = result.get("response")
        if not isinstance(response, dict):
            failures.append({"key": key, "error": result.get("error", "missing response")})
            continue
        embedding = response.get("embedding")
        values = embedding.get("values") if isinstance(embedding, dict) else None
        if not isinstance(values, list) or len(values) != DIMENSIONS:
            failures.append({"key": key, "error": "missing or invalid vector"})
            continue
        keys.append(key)
        vectors.append([float(value) for value in values])
        token_count += int(response.get("tokenCount", 0))

    if not vectors:
        raise RuntimeError("Embedding batch returned no valid vectors")
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.maximum(norms, np.finfo(np.float32).eps)
    np.save(output_dir / "vectors.npy", matrix, allow_pickle=False)
    _write_json(output_dir / "keys.json", keys)
    _write_json(output_dir / "failures.json", failures)

    result_manifest = {
        **record,
        "state": state,
        "output_file_name": job.dest.file_name,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "vector_count": len(keys),
        "failure_count": len(failures),
        "dimensions": int(matrix.shape[1]),
        "token_count": token_count,
        "actual_batch_cost_usd": round(
            token_count / 1_000_000 * BATCH_PRICE_PER_MILLION_TOKENS, 4
        ),
        "keys_sha256": _sha256_file(output_dir / "keys.json"),
        "vectors_sha256": _sha256_file(output_dir / "vectors.npy"),
        "responses_sha256": _sha256_file(raw_path),
    }
    _write_json(output_dir / "batch.json", result_manifest)
    return result_manifest


def embed_standard(
    *,
    repository: Path,
    output_dir: Path,
    batch_size: int = 100,
    minimum_interval_seconds: float = 2.1,
) -> dict[str, object]:
    """Embed prepared items through the standard endpoint with resumable checkpoints."""
    from google.genai import types

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    manifest_path = output_dir / "manifest.json"
    items_path = output_dir / "items.jsonl"
    if not manifest_path.exists() or not items_path.exists():
        raise RuntimeError("Run prepare-embeddings before standard embedding")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["items_sha256"] != _sha256_file(items_path):
        raise RuntimeError("Embedding item file changed after its manifest was written")
    items = [json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines()]
    if len(items) != int(manifest["item_count"]):
        raise RuntimeError("Embedding item count does not match its manifest")

    state_path = output_dir / "standard.json"
    raw_vectors_path = output_dir / "vectors.raw.npy"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state and state.get("items_sha256") != manifest["items_sha256"]:
        raise RuntimeError(
            "Prepared inputs changed after standard embedding began; remove the stale standard artifacts"
        )
    completed = int(state.get("completed", 0))
    token_count = int(state.get("token_count", 0))
    billable_characters = int(state.get("billable_character_count", 0))
    if raw_vectors_path.exists():
        raw_vectors = np.lib.format.open_memmap(raw_vectors_path, mode="r+")
        if raw_vectors.shape != (len(items), DIMENSIONS):
            raise RuntimeError("Standard embedding checkpoint has an unexpected matrix shape")
    else:
        raw_vectors = np.lib.format.open_memmap(
            raw_vectors_path,
            mode="w+",
            dtype=np.float32,
            shape=(len(items), DIMENSIONS),
        )
        completed = 0
        token_count = 0
        billable_characters = 0

    client = _client(repository)
    started_at = state.get("started_at") or datetime.now(timezone.utc).isoformat()
    for start in range(completed, len(items), batch_size):
        end = min(start + batch_size, len(items))
        contents = [
            types.Content(parts=[types.Part(text=str(item["text"]))]) for item in items[start:end]
        ]
        while True:
            try:
                response = client.models.embed_content(
                    model=MODEL,
                    contents=contents,
                    config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
                )
                break
            except Exception as error:
                if getattr(error, "status_code", None) != 429:
                    raise
                print(
                    json.dumps(
                        {
                            "throttled_at": start,
                            "retry_in_seconds": 58,
                            "message": "Gemini per-minute embedding quota reached",
                        }
                    ),
                    flush=True,
                )
                time.sleep(58)
        embeddings = response.embeddings or []
        if len(embeddings) != end - start:
            raise RuntimeError(
                f"Standard embedding returned {len(embeddings)} vectors for {end - start} inputs"
            )
        for offset, embedding in enumerate(embeddings):
            values = embedding.values or []
            if len(values) != DIMENSIONS:
                raise RuntimeError(f"Invalid vector dimension at item {start + offset}")
            if embedding.statistics:
                token_count += round(float(embedding.statistics.token_count or 0))
            raw_vectors[start + offset] = np.asarray(values, dtype=np.float32)
        if response.metadata:
            billable_characters += int(response.metadata.billable_character_count or 0)
        raw_vectors.flush()
        completed = end
        estimated_tokens = round(
            int(manifest["estimated_tokens"]) * completed / max(1, len(items))
        )
        state = {
            "mode": "standard",
            "model": MODEL,
            "dimensions": DIMENSIONS,
            "items_sha256": manifest["items_sha256"],
            "started_at": started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed": completed,
            "item_count": len(items),
            "token_count": token_count,
            "billable_character_count": billable_characters,
            "estimated_input_tokens": estimated_tokens,
            "estimated_cost_usd": round(
                estimated_tokens / 1_000_000 * STANDARD_PRICE_PER_MILLION_TOKENS, 4
            ),
        }
        _write_json(state_path, state)
        print(
            json.dumps(
                {
                    "embedded": completed,
                    "total": len(items),
                    "tokens": token_count,
                    "estimated_cost_usd": state["estimated_cost_usd"],
                }
            ),
            flush=True,
        )
        if end < len(items) and minimum_interval_seconds > 0:
            time.sleep(minimum_interval_seconds)

    matrix = np.asarray(raw_vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = matrix / np.maximum(norms, np.finfo(np.float32).eps)
    np.save(output_dir / "vectors.npy", normalized, allow_pickle=False)
    keys = [str(item["key"]) for item in items]
    _write_json(output_dir / "keys.json", keys)
    result = {
        **state,
        "state": "COMPLETE",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "estimated_total_cost_usd": round(
            int(manifest["estimated_tokens"])
            / 1_000_000
            * STANDARD_PRICE_PER_MILLION_TOKENS,
            4,
        ),
        "keys_sha256": _sha256_file(output_dir / "keys.json"),
        "raw_vectors_sha256": _sha256_file(raw_vectors_path),
        "vectors_sha256": _sha256_file(output_dir / "vectors.npy"),
    }
    _write_json(state_path, result)
    return result

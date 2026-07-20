from __future__ import annotations

import gzip
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from .analysis import (
    BATCH_INPUT_PRICE_PER_MILLION,
    BATCH_OUTPUT_PRICE_PER_MILLION,
    MODEL,
)
from .senses import (
    _client,
    _read_jsonl,
    _response_text,
    _sha256_bytes,
    _sha256_file,
    _token_usage,
    _write_json,
    utc_now,
)


FINDING_VERSION = "research-findings-v1"
PROMPT_VERSION = "closed-claim-findings-v1"
SCHEMA_VERSION = "research-findings-v1"
FINDING_TYPES = {
    "RECURRENCE",
    "DISAGREEMENT",
    "QUALIFICATION",
    "SENSE_SHIFT",
    "METHOD_SHIFT",
    "TRANSMISSION_CANDIDATE",
    "ANOMALY",
}
CLAIM_ROLES = {"SUPPORTS", "CONTRADICTS", "QUALIFIES", "EXAMPLE"}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "finding_type": {"type": "string", "enum": sorted(FINDING_TYPES)},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "claim_links": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim_id": {"type": "string"},
                                "role": {"type": "string", "enum": sorted(CLAIM_ROLES)},
                            },
                            "required": ["claim_id", "role"],
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "finding_type",
                    "title",
                    "summary",
                    "claim_links",
                    "confidence",
                ],
            },
        }
    },
    "required": ["findings"],
}


def artifact_dir(var_dir: Path) -> Path:
    return var_dir / "analysis" / FINDING_VERSION


def _prompt(entry: dict[str, object], claims: list[dict[str, object]]) -> str:
    rows = []
    for claim in claims:
        authority = f" | attributed: {claim['attributed_authority']}" if claim["attributed_authority"] else ""
        sense = f" | sense: {claim['sense_label']}" if claim["sense_label"] else ""
        quote = str(claim["evidence_text"]).replace("\n", " ")[:450]
        rows.append(
            f"- {claim['claim_id']} | {claim['publication_year']} | {claim['language_label']} | "
            f"{claim['source_title']} | {claim['stance']} | {claim['evidence_basis']}"
            f"{authority}{sense} | CLAIM: {claim['summary']} | QUOTE: {quote}"
        )
    return f"""Identify up to five historically substantive findings supported by the closed set of passage-grounded claims below.

ENTRY: {entry['preferred_label']}
SCOPE: {entry['scope_note']}

FINDING TYPES
- RECURRENCE: substantially the same assertion recurs in distinct passages or sources.
- DISAGREEMENT: claims genuinely conflict; include SUPPORTS and CONTRADICTS roles.
- QUALIFICATION: one claim materially limits or modifies another; use QUALIFIES.
- SENSE_SHIFT: the entry is used in meaningfully different historical senses over time.
- METHOD_SHIFT: the evidence basis or mode of warrant changes in a meaningful way.
- TRANSMISSION_CANDIDATE: a distinctive claim may have traveled across sources, languages, or periods. This label is a hypothesis, never proof of influence.
- ANOMALY: a claim is a notable outlier relative to the others.

RULES
- Use only supplied claim IDs. Every finding needs at least two different claims.
- Do not manufacture a disagreement from different emphases or a transmission path from generic similarity.
- Prefer fewer, stronger findings. Return an empty list if the claims do not support something a historian might investigate or footnote.
- The title should state the pattern, not advertise it. The summary should explain the comparison in no more than two sentences.
- Claims all come from usages already resolved as the same concordance entry. Do not add outside knowledge.
- Distinct passages from one author can show internal variation but cannot prove circulation between authors.

CLAIMS
{chr(10).join(rows)}
"""


def prepare_findings_batch(
    connection: sqlite3.Connection,
    *,
    var_dir: Path,
    minimum_sources: int = 2,
    minimum_claims: int = 4,
) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    entries: dict[str, dict[str, object]] = {}
    for row in connection.execute(
        """
        SELECT c.id, c.summary, c.stance, c.evidence_basis,
               c.attributed_authority, c.evidence_text,
               u.entry_id, e.preferred_label, e.scope_note,
               s.id AS source_id, s.title, s.publication_year, s.language_label,
               sc.label AS sense_label
        FROM usage_claims c
        JOIN contextual_usages u ON u.id = c.usage_id
        JOIN entries e ON e.id = u.entry_id
        JOIN passages p ON p.id = u.passage_id
        JOIN sources s ON s.id = p.source_id
        LEFT JOIN sense_memberships sm
          ON sm.usage_id = u.id AND sm.status IN ('CORE', 'SUGGESTED')
        LEFT JOIN sense_clusters sc
          ON sc.id = sm.sense_id AND sc.status IN ('CORE', 'SUGGESTED')
        WHERE c.status IN ('CORE', 'SUGGESTED')
          AND u.status IN ('CORE', 'SUGGESTED')
          AND u.resolution = 'SAME_ENTRY'
        ORDER BY e.preferred_label COLLATE NOCASE, s.publication_year, c.id
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
                "claim_id": str(row["id"]),
                "summary": str(row["summary"]),
                "stance": str(row["stance"]),
                "evidence_basis": str(row["evidence_basis"]),
                "attributed_authority": str(row["attributed_authority"] or ""),
                "evidence_text": str(row["evidence_text"]),
                "source_id": str(row["source_id"]),
                "source_title": str(row["title"]),
                "publication_year": int(row["publication_year"]),
                "language_label": str(row["language_label"]),
                "sense_label": str(row["sense_label"] or ""),
            }
        )

    output_dir = artifact_dir(var_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "items.jsonl"
    requests_path = output_dir / "requests.jsonl"
    request_count = 0
    claim_count = 0
    estimated_input_tokens = 0
    with items_path.open("w", encoding="utf-8") as items, requests_path.open(
        "w", encoding="utf-8"
    ) as requests:
        for entry_id in sorted(grouped, key=lambda value: str(entries[value]["preferred_label"])):
            claims = grouped[entry_id]
            source_count = len({str(claim["source_id"]) for claim in claims})
            if len(claims) < minimum_claims or source_count < minimum_sources:
                continue
            prompt = _prompt(entries[entry_id], claims)
            digest = _sha256_bytes(
                f"{FINDING_VERSION}\0{entry_id}\0{prompt}".encode("utf-8")
            )
            key = f"findings-{digest[:24]}"
            claim_ids = [str(claim["claim_id"]) for claim in claims]
            item = {
                "key": key,
                **entries[entry_id],
                "claim_ids": claim_ids,
                "source_count": source_count,
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
                        "max_output_tokens": 2200,
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
            claim_count += len(claim_ids)
            estimated_input_tokens += max(1, round(len(prompt) / 4))
    if not request_count:
        raise RuntimeError("No entries meet the source and claim thresholds for findings")

    requests_hash = _sha256_file(requests_path)
    manifest = {
        "finding_version": FINDING_VERSION,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "model": MODEL,
        "model_run_id": f"run-{FINDING_VERSION}-{requests_hash[:16]}",
        "created_at": utc_now(),
        "minimum_sources": minimum_sources,
        "minimum_claims": minimum_claims,
        "request_count": request_count,
        "claim_count": claim_count,
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


def submit_findings_batch(*, repository: Path, output_dir: Path) -> dict[str, object]:
    from google.genai import types

    requests_path = output_dir / "requests.jsonl"
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["requests_sha256"] != _sha256_file(requests_path):
        raise RuntimeError("Finding request file changed after its manifest was written")
    client = _client(repository)
    uploaded = client.files.upload(
        file=requests_path,
        config=types.UploadFileConfig(mime_type="jsonl", display_name=requests_path.name),
    )
    job = client.batches.create(
        model=MODEL,
        src=types.BatchJobSource(file_name=str(uploaded.name)),
        config={"display_name": f"Premodern findings {manifest['requests_sha256'][:12]}"},
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


def findings_batch_status(*, repository: Path, output_dir: Path) -> dict[str, object]:
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


def validate_findings(value: object, expected_claim_ids: list[str]) -> list[dict[str, object]]:
    if not isinstance(value, dict) or not isinstance(value.get("findings"), list):
        raise ValueError("response must contain a findings array")
    raw_findings = value["findings"]
    if len(raw_findings) > 5:
        raise ValueError("response contains more than five findings")
    expected = set(expected_claim_ids)
    titles: set[str] = set()
    findings: list[dict[str, object]] = []
    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, dict):
            raise ValueError(f"finding {index} must be an object")
        finding_type = str(raw.get("finding_type", ""))
        title = str(raw.get("title", "")).strip()
        summary = str(raw.get("summary", "")).strip()
        links = raw.get("claim_links")
        confidence = raw.get("confidence")
        if finding_type not in FINDING_TYPES or not title or not summary:
            raise ValueError(f"finding {index} has invalid type, title, or summary")
        if title.casefold() in titles:
            raise ValueError(f"duplicate finding title {title}")
        titles.add(title.casefold())
        if not isinstance(links, list) or len(links) < 2:
            raise ValueError(f"finding {index} needs at least two claim links")
        claim_links: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_link in links:
            if not isinstance(raw_link, dict):
                raise ValueError(f"finding {index} has an invalid claim link")
            claim_id = str(raw_link.get("claim_id", ""))
            role = str(raw_link.get("role", ""))
            if claim_id not in expected or role not in CLAIM_ROLES:
                raise ValueError(f"finding {index} references an unknown claim or role")
            if claim_id in seen:
                raise ValueError(f"finding {index} repeats claim {claim_id}")
            seen.add(claim_id)
            claim_links.append({"claim_id": claim_id, "role": role})
        roles = {link["role"] for link in claim_links}
        if finding_type == "DISAGREEMENT" and not {"SUPPORTS", "CONTRADICTS"} <= roles:
            raise ValueError("a disagreement requires supporting and contradicting claims")
        if finding_type == "QUALIFICATION" and "QUALIFIES" not in roles:
            raise ValueError("a qualification requires a qualifying claim")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f"finding {index} confidence must be numeric")
        confidence_value = float(confidence)
        if not 0 <= confidence_value <= 1:
            raise ValueError(f"finding {index} confidence must be between 0 and 1")
        findings.append(
            {
                "finding_type": finding_type,
                "title": title,
                "summary": summary,
                "claim_links": claim_links,
                "confidence": confidence_value,
            }
        )
    return findings


def fetch_findings_batch(
    connection: sqlite3.Connection,
    *,
    repository: Path,
    output_dir: Path,
) -> dict[str, object]:
    client, job, record = _batch_job(repository, output_dir)
    state = job.state.name if job.state else None
    if state != "JOB_STATE_SUCCEEDED":
        return findings_batch_status(repository=repository, output_dir=output_dir)
    if not job.dest or not job.dest.file_name:
        raise RuntimeError("Succeeded findings batch has no output file")
    content = client.files.download(file=job.dest.file_name)
    with gzip.open(output_dir / "responses.jsonl.gz", "wb") as handle:
        handle.write(content)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    items = {str(item["key"]): item for item in _read_jsonl(output_dir / "items.jsonl")}

    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    input_tokens = 0
    output_tokens = 0
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid finding response JSON on line {line_number}") from error
        key = str(response.get("key", ""))
        item = items.get(key)
        if item is None:
            failures.append({"key": key, "error": "unknown response key"})
            continue
        request_input, request_output = _token_usage(response)
        input_tokens += request_input
        output_tokens += request_output
        try:
            findings = validate_findings(
                json.loads(_response_text(response)),
                [str(identifier) for identifier in item["claim_ids"]],
            )
        except (ValueError, json.JSONDecodeError) as error:
            failures.append({"key": key, "entry_id": item["entry_id"], "error": str(error)})
            continue
        results.append({"key": key, "entry_id": item["entry_id"], "findings": findings})

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
            ) VALUES (?, 'FINDING_SYNTHESIS', 'GOOGLE', ?, ?, ?, ?, ?, ?, ?, ?,
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
                UPDATE finding_claims SET status='PRIVATE'
                WHERE finding_id IN (SELECT id FROM research_findings WHERE entry_id = ?)
                """,
                (entry_id,),
            )
            connection.execute(
                "UPDATE research_findings SET status='PRIVATE' WHERE entry_id = ?",
                (entry_id,),
            )
            for index, finding in enumerate(result["findings"]):
                finding_key = (
                    f"{run_id}\0{entry_id}\0{index}\0{finding['title']}".encode("utf-8")
                )
                finding_id = f"finding-{_sha256_bytes(finding_key)[:24]}"
                connection.execute(
                    """
                    INSERT OR REPLACE INTO research_findings (
                      id, entry_id, finding_type, title, summary, sort_order,
                      confidence, model_run_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUGGESTED')
                    """,
                    (
                        finding_id,
                        entry_id,
                        finding["finding_type"],
                        finding["title"],
                        finding["summary"],
                        index,
                        finding["confidence"],
                        run_id,
                    ),
                )
                for link in finding["claim_links"]:
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO finding_claims
                          (finding_id, claim_id, role, status)
                        VALUES (?, ?, ?, 'SUGGESTED')
                        """,
                        (finding_id, link["claim_id"], link["role"]),
                    )

    results_path = output_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    _write_json(output_dir / "failures.json", failures)
    summary = {
        **record,
        "state": state,
        "request_count": len(items),
        "successful_entries": len(results),
        "failure_count": len(failures),
        "finding_count": sum(len(result["findings"]) for result in results),
        "claim_link_count": sum(
            len(finding["claim_links"])
            for result in results
            for finding in result["findings"]
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

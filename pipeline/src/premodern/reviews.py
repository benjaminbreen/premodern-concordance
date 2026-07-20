from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


REVIEW_SCHEMA_VERSION = "historian-assessment-v1"


def _latest_reviews(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    return list(
        connection.execute(
            """
            WITH ranked AS (
              SELECT *, row_number() OVER (
                PARTITION BY finding_id ORDER BY created_at DESC, id DESC
              ) AS rank
              FROM finding_review_events
            )
            SELECT * FROM ranked WHERE rank = 1
            ORDER BY json_extract(snapshot_json, '$.entry.preferredLabel') COLLATE NOCASE,
                     json_extract(snapshot_json, '$.finding.title') COLLATE NOCASE
            """
        )
    )


def export_historian_reviews(
    *,
    review_db: Path,
    authoring_db: Path,
    output_path: Path,
) -> dict[str, object]:
    if not review_db.exists():
        raise FileNotFoundError(f"Historian review database does not exist: {review_db}")
    review_connection = sqlite3.connect(review_db)
    try:
        rows = _latest_reviews(review_connection)
    finally:
        review_connection.close()

    generation: dict[str, dict[str, object]] = {}
    if authoring_db.exists():
        authoring_connection = sqlite3.connect(authoring_db)
        authoring_connection.row_factory = sqlite3.Row
        try:
            for row in authoring_connection.execute(
                """
                SELECT f.id AS finding_id, f.model_run_id,
                       r.provider, r.model_snapshot, r.prompt_version,
                       r.schema_version, r.input_sha256, r.output_sha256
                FROM research_findings f
                JOIN model_runs r ON r.id = f.model_run_id
                """
            ):
                generation[str(row["finding_id"])] = {
                    "modelRunId": str(row["model_run_id"]),
                    "provider": str(row["provider"]),
                    "model": str(row["model_snapshot"]),
                    "promptVersion": str(row["prompt_version"]),
                    "schemaVersion": str(row["schema_version"]),
                    "inputSha256": str(row["input_sha256"]),
                    "outputSha256": str(row["output_sha256"] or ""),
                }
        finally:
            authoring_connection.close()

    records: list[dict[str, object]] = []
    evidence_counts: Counter[str] = Counter()
    value_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    for row in rows:
        snapshot = json.loads(str(row["snapshot_json"]))
        finding_id = str(row["finding_id"])
        failure_modes = json.loads(str(row["failure_modes_json"]))
        judgment = {
            "reviewState": str(row["review_state"]),
            "evidenceSupport": row["evidence_support"],
            "researchValue": row["research_value"],
            "failureModes": failure_modes,
            "claimVerdicts": json.loads(str(row["claim_verdicts_json"])),
            "note": str(row["note"]),
            "correctedSummary": str(row["corrected_summary"]),
        }
        record = {
            "schemaVersion": REVIEW_SCHEMA_VERSION,
            "assessmentId": str(row["id"]),
            "reviewer": str(row["reviewer"]),
            "createdAt": str(row["created_at"]),
            "releaseId": str(row["release_id"]),
            "snapshotSha256": str(row["snapshot_sha256"]),
            "target": snapshot,
            "generation": generation.get(finding_id),
            "judgment": judgment,
        }
        records.append(record)
        state_counts[str(row["review_state"])] += 1
        if row["evidence_support"]:
            evidence_counts[str(row["evidence_support"])] += 1
        if row["research_value"]:
            value_counts[str(row["research_value"])] += 1
        failure_counts.update(str(value) for value in failure_modes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(output_path)

    summary = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "record_count": len(records),
        "review_state": dict(sorted(state_counts.items())),
        "evidence_support": dict(sorted(evidence_counts.items())),
        "research_value": dict(sorted(value_counts.items())),
        "failure_modes": dict(sorted(failure_counts.items())),
        "output": str(output_path),
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {**summary, "summary": str(summary_path)}

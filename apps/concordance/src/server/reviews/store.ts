import "server-only";

import { createHash, randomUUID } from "node:crypto";
import {
  claimVerdictSchema,
  evidenceSupportSchema,
  failureModeSchema,
  researchValueSchema,
  reviewStateSchema,
  type FindingReviewItem,
  type FindingReviewSubmission,
  type SavedFindingReview
} from "@/contracts/review";
import { reviewDb } from "@/server/db/client";
import { nullableText, text } from "@/server/repositories/rows";
import { reviewModeReviewer } from "./config";

let schemaPromise: Promise<void> | null = null;

async function ensureSchema(): Promise<void> {
  if (!schemaPromise) {
    schemaPromise = reviewDb().batch([
      `CREATE TABLE IF NOT EXISTS review_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      ) STRICT`,
      `INSERT OR IGNORE INTO review_metadata (key, value)
       VALUES ('schema_version', 'historian-assessment-v1')`,
      `CREATE TABLE IF NOT EXISTS finding_review_events (
        id TEXT PRIMARY KEY,
        finding_id TEXT NOT NULL,
        release_id TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        review_state TEXT NOT NULL CHECK (review_state IN ('ASSESSED', 'DEFERRED')),
        evidence_support TEXT,
        research_value TEXT,
        failure_modes_json TEXT NOT NULL,
        claim_verdicts_json TEXT NOT NULL,
        note TEXT NOT NULL,
        corrected_summary TEXT NOT NULL,
        reviewer TEXT NOT NULL,
        created_at TEXT NOT NULL
      ) STRICT`,
      `CREATE INDEX IF NOT EXISTS idx_finding_review_events_latest
       ON finding_review_events(finding_id, created_at DESC, id DESC)`
    ], "write").then(() => undefined).catch((error) => {
      schemaPromise = null;
      throw error;
    });
  }
  return schemaPromise;
}

function parseReview(row: Parameters<typeof text>[0]): SavedFindingReview {
  const support = nullableText(row, "evidence_support");
  const value = nullableText(row, "research_value");
  return {
    id: text(row, "id"),
    findingId: text(row, "finding_id"),
    releaseId: text(row, "release_id"),
    snapshotSha256: text(row, "snapshot_sha256"),
    reviewState: reviewStateSchema.parse(text(row, "review_state")),
    evidenceSupport: support ? evidenceSupportSchema.parse(support) : null,
    researchValue: value ? researchValueSchema.parse(value) : null,
    failureModes: failureModeSchema.array().parse(JSON.parse(text(row, "failure_modes_json"))),
    claimVerdicts: Object.fromEntries(
      Object.entries(JSON.parse(text(row, "claim_verdicts_json"))).map(([key, verdict]) => [
        key,
        claimVerdictSchema.parse(verdict)
      ])
    ),
    note: text(row, "note"),
    correctedSummary: text(row, "corrected_summary"),
    reviewer: text(row, "reviewer"),
    createdAt: text(row, "created_at")
  };
}

export async function listLatestFindingReviews(): Promise<SavedFindingReview[]> {
  await ensureSchema();
  const result = await reviewDb().execute(`
    WITH ranked AS (
      SELECT *, row_number() OVER (
        PARTITION BY finding_id ORDER BY created_at DESC, id DESC
      ) AS rank
      FROM finding_review_events
    )
    SELECT * FROM ranked WHERE rank = 1 ORDER BY finding_id
  `);
  return result.rows.map(parseReview);
}

export async function saveFindingReview(
  item: FindingReviewItem,
  submission: FindingReviewSubmission
): Promise<SavedFindingReview> {
  await ensureSchema();
  const validClaimIds = new Set(item.finding.evidence.map((evidence) => evidence.claimId));
  for (const claimId of Object.keys(submission.claimVerdicts)) {
    if (!validClaimIds.has(claimId)) {
      throw new Error(`Claim ${claimId} is not evidence for finding ${item.finding.id}`);
    }
  }
  const snapshotJson = JSON.stringify(item);
  const snapshotSha256 = createHash("sha256").update(snapshotJson).digest("hex");
  const id = `review-${randomUUID()}`;
  const createdAt = new Date().toISOString();
  const reviewer = reviewModeReviewer();
  await reviewDb().execute({
    sql: `INSERT INTO finding_review_events (
      id, finding_id, release_id, snapshot_sha256, snapshot_json,
      review_state, evidence_support, research_value,
      failure_modes_json, claim_verdicts_json, note, corrected_summary,
      reviewer, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      id,
      item.finding.id,
      item.releaseId,
      snapshotSha256,
      snapshotJson,
      submission.reviewState,
      submission.evidenceSupport,
      submission.researchValue,
      JSON.stringify([...new Set(submission.failureModes)].sort()),
      JSON.stringify(submission.claimVerdicts),
      submission.note.trim(),
      submission.correctedSummary.trim(),
      reviewer,
      createdAt
    ]
  });
  return {
    id,
    findingId: item.finding.id,
    releaseId: item.releaseId,
    snapshotSha256,
    reviewState: submission.reviewState,
    evidenceSupport: submission.evidenceSupport,
    researchValue: submission.researchValue,
    failureModes: [...new Set(submission.failureModes)].sort() as SavedFindingReview["failureModes"],
    claimVerdicts: submission.claimVerdicts,
    note: submission.note.trim(),
    correctedSummary: submission.correctedSummary.trim(),
    reviewer,
    createdAt
  };
}

export async function latestReviewExportJsonl(): Promise<string> {
  await ensureSchema();
  const result = await reviewDb().execute(`
    WITH ranked AS (
      SELECT *, row_number() OVER (
        PARTITION BY finding_id ORDER BY created_at DESC, id DESC
      ) AS rank
      FROM finding_review_events
    )
    SELECT * FROM ranked WHERE rank = 1
    ORDER BY json_extract(snapshot_json, '$.entry.preferredLabel') COLLATE NOCASE,
             json_extract(snapshot_json, '$.finding.title') COLLATE NOCASE
  `);
  return result.rows.map((row) => JSON.stringify({
    schemaVersion: "historian-assessment-v1",
    assessmentId: text(row, "id"),
    reviewer: text(row, "reviewer"),
    createdAt: text(row, "created_at"),
    releaseId: text(row, "release_id"),
    snapshotSha256: text(row, "snapshot_sha256"),
    target: JSON.parse(text(row, "snapshot_json")),
    judgment: {
      reviewState: text(row, "review_state"),
      evidenceSupport: nullableText(row, "evidence_support"),
      researchValue: nullableText(row, "research_value"),
      failureModes: JSON.parse(text(row, "failure_modes_json")),
      claimVerdicts: JSON.parse(text(row, "claim_verdicts_json")),
      note: text(row, "note"),
      correctedSummary: text(row, "corrected_summary")
    }
  })).join("\n") + (result.rows.length ? "\n" : "");
}

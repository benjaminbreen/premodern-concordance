import "server-only";

import {
  claimStanceSchema,
  evidenceBasisSchema,
  findingClaimRoleSchema,
  findingTypeSchema,
  publicationStatusSchema,
  type ResearchFinding
} from "@/contracts/domain";
import type { FindingReviewItem } from "@/contracts/review";
import { db } from "@/server/db/client";
import { nullableText, number, text } from "@/server/repositories/rows";

export async function listFindingReviewItems(): Promise<FindingReviewItem[]> {
  const [releaseResult, findingResult, evidenceResult] = await Promise.all([
    db().execute("SELECT id FROM release_metadata ORDER BY created_at DESC LIMIT 1"),
    db().execute(`
      SELECT f.id, f.finding_type, f.title, f.summary, f.confidence, f.status,
             e.id AS entry_id, e.slug AS entry_slug,
             e.preferred_label AS entry_preferred_label,
             e.scope_note AS entry_scope_note
      FROM research_findings f
      JOIN entries e ON e.id = f.entry_id
      ORDER BY e.preferred_label COLLATE NOCASE, f.sort_order, f.title
    `),
    db().execute(`
      SELECT fc.finding_id, fc.claim_id, fc.role, c.summary,
             c.evidence_text, c.stance, c.evidence_basis,
             p.id AS passage_id, p.scan_url,
             s.title AS source_title, s.author AS source_author,
             s.publication_year
      FROM finding_claims fc
      JOIN usage_claims c ON c.id = fc.claim_id
      JOIN contextual_usages u ON u.id = c.usage_id
      JOIN passages p ON p.id = u.passage_id
      JOIN sources s ON s.id = p.source_id
      ORDER BY fc.finding_id, s.publication_year, fc.claim_id
    `)
  ]);
  const releaseRow = releaseResult.rows[0];
  if (!releaseRow) throw new Error("The public concordance release has no metadata");
  const releaseId = text(releaseRow, "id");

  const evidence = new Map<string, ResearchFinding["evidence"]>();
  for (const row of evidenceResult.rows) {
    const findingId = text(row, "finding_id");
    const collection = evidence.get(findingId) ?? [];
    collection.push({
      claimId: text(row, "claim_id"),
      role: findingClaimRoleSchema.parse(text(row, "role")),
      summary: text(row, "summary"),
      evidenceText: text(row, "evidence_text"),
      stance: claimStanceSchema.parse(text(row, "stance")),
      evidenceBasis: evidenceBasisSchema.parse(text(row, "evidence_basis")),
      sourceTitle: text(row, "source_title"),
      sourceAuthor: nullableText(row, "source_author"),
      publicationYear: number(row, "publication_year"),
      passageId: text(row, "passage_id"),
      scanUrl: text(row, "scan_url")
    });
    evidence.set(findingId, collection);
  }

  return findingResult.rows.map((row) => {
    const findingId = text(row, "id");
    return {
      releaseId,
      entry: {
        id: text(row, "entry_id"),
        slug: text(row, "entry_slug"),
        preferredLabel: text(row, "entry_preferred_label"),
        scopeNote: text(row, "entry_scope_note")
      },
      finding: {
        id: findingId,
        findingType: findingTypeSchema.parse(text(row, "finding_type")),
        title: text(row, "title"),
        summary: text(row, "summary"),
        confidence: number(row, "confidence"),
        status: publicationStatusSchema.parse(text(row, "status")),
        evidence: evidence.get(findingId) ?? []
      }
    };
  });
}

export async function getFindingReviewItem(findingId: string): Promise<FindingReviewItem | null> {
  const items = await listFindingReviewItems();
  return items.find((item) => item.finding.id === findingId) ?? null;
}

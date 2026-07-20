import "server-only";

import {
  claimStanceSchema,
  claimTypeSchema,
  evidenceBasisSchema,
  entryRelationTypeSchema,
  findingClaimRoleSchema,
  findingTypeSchema,
  mentionTypeSchema,
  publicationStatusSchema,
  relationLayerSchema,
  termRelationSchema,
  usageRelationTypeSchema,
  usageResolutionSchema,
  type ContextualUsage,
  type EntryDetail,
  type EntrySummary,
  type Passage,
  type ResearchFinding,
  type SenseCluster
} from "@/contracts/domain";
import { db } from "@/server/db/client";
import { entrySummary, sourceSummary } from "./mappers";
import { nullableNumber, nullableText, number, text } from "./rows";

const entryColumns = `
  id, slug, preferred_label, kind, scope_note, exclusions_note, status,
  source_count, passage_count, earliest_year, latest_year
`;

export async function listEntries(limit = 50, offset = 0): Promise<EntrySummary[]> {
  const result = await db().execute({
    sql: `SELECT ${entryColumns} FROM entries ORDER BY preferred_label LIMIT ? OFFSET ?`,
    args: [Math.min(Math.max(limit, 1), 100), Math.max(offset, 0)]
  });
  return result.rows.map((row) => entrySummary(row));
}

export async function getEntryBySlug(slug: string): Promise<EntryDetail | null> {
  const result = await db().execute({
    sql: `SELECT ${entryColumns} FROM entries WHERE slug = ? LIMIT 1`,
    args: [slug]
  });
  const row = result.rows[0];
  if (!row) return null;
  const base = entrySummary(row);

  const [termsResult, relationsResult] = await Promise.all([
    db().execute({
      sql: `
        SELECT t.id, t.display_form, t.language_code, l.relation_type,
               l.rationale, l.status, l.confidence
        FROM entry_term_links l
        JOIN term_forms t ON t.id = l.term_form_id
        WHERE l.entry_id = ?
        ORDER BY CASE l.relation_type WHEN 'PREFERRED_LABEL' THEN 0 ELSE 1 END,
                 COALESCE(t.earliest_year, 9999), t.display_form
      `,
      args: [base.id]
    }),
    db().execute({
      sql: `
        SELECT r.id AS relation_id, r.layer, r.relation_type, r.rationale,
               r.non_claim, r.confidence, r.status AS relation_status,
               (SELECT group_concat(re.passage_id, char(31))
                FROM relation_evidence re WHERE re.relation_id = r.id) AS evidence_passage_ids,
               CASE WHEN r.source_entry_id = ? THEN 'OUTGOING' ELSE 'INCOMING' END AS direction,
               t.id AS target_id, t.slug AS target_slug,
               t.preferred_label AS target_preferred_label,
               t.kind AS target_kind, t.scope_note AS target_scope_note,
               t.exclusions_note AS target_exclusions_note,
               t.status AS target_status, t.source_count AS target_source_count,
               t.passage_count AS target_passage_count,
               t.earliest_year AS target_earliest_year,
               t.latest_year AS target_latest_year
        FROM entry_relations r
        JOIN entries t ON t.id = CASE
          WHEN r.source_entry_id = ? THEN r.target_entry_id ELSE r.source_entry_id END
        WHERE r.source_entry_id = ? OR r.target_entry_id = ?
        ORDER BY r.layer, r.relation_type, t.preferred_label
      `,
      args: [base.id, base.id, base.id, base.id]
    })
  ]);

  return {
    ...base,
    terms: termsResult.rows.map((term) => ({
      id: text(term, "id"),
      displayForm: text(term, "display_form"),
      languageCode: nullableText(term, "language_code"),
      relationType: termRelationSchema.parse(text(term, "relation_type")),
      rationale: nullableText(term, "rationale"),
      status: publicationStatusSchema.parse(text(term, "status")),
      confidence: nullableNumber(term, "confidence")
    })),
    relations: relationsResult.rows.map((relation) => ({
      id: text(relation, "relation_id"),
      direction: text(relation, "direction") as "OUTGOING" | "INCOMING",
      layer: relationLayerSchema.parse(text(relation, "layer")),
      relationType: entryRelationTypeSchema.parse(text(relation, "relation_type")),
      rationale: text(relation, "rationale"),
      nonClaim: nullableText(relation, "non_claim"),
      confidence: nullableNumber(relation, "confidence"),
      status: publicationStatusSchema.parse(text(relation, "relation_status")),
      evidencePassageIds: (nullableText(relation, "evidence_passage_ids") ?? "").split("\u001f").filter(Boolean),
      target: entrySummary(relation, "target_")
    }))
  };
}

export async function getEntryPassages(slug: string, limit = 20, offset = 0): Promise<Passage[]> {
  const result = await db().execute({
    sql: `
      WITH evidence AS (
        SELECT o.passage_id, o.status, o.surface_form,
               o.start_in_passage, o.end_in_passage,
               o.resolution_method, o.confidence, 0 AS priority
        FROM occurrences o
        JOIN entries e ON e.id = o.entry_id
        WHERE e.slug = ?
        UNION ALL
        SELECT u.passage_id, u.status, u.evidence_text AS surface_form,
               u.evidence_start AS start_in_passage,
               u.evidence_end AS end_in_passage,
               'MODEL' AS resolution_method, u.confidence, 1 AS priority
        FROM contextual_usages u
        JOIN entries e ON e.id = u.entry_id
        WHERE e.slug = ?
      ), chosen AS (
        SELECT *, row_number() OVER (
          PARTITION BY passage_id
          ORDER BY priority, CASE status WHEN 'CORE' THEN 0 ELSE 1 END
        ) AS choice
        FROM evidence
      )
      SELECT p.id, p.sequence, p.start_offset, p.end_offset, p.printed_page,
             p.scan_leaf, p.display_text, p.scan_url,
             COALESCE(chosen.status, p.status) AS status,
             chosen.surface_form, chosen.start_in_passage, chosen.end_in_passage,
             chosen.resolution_method, chosen.confidence,
             s.id AS source_id, s.title AS source_title, s.author AS source_author,
             s.publication_year AS source_publication_year,
             s.original_year AS source_original_year,
             s.language_code AS source_language_code,
             s.language_label AS source_language_label,
             s.citation_text AS source_citation_text,
             s.archive_provider AS source_archive_provider,
             s.archive_url AS source_archive_url,
             (SELECT COUNT(*) FROM passages sp WHERE sp.source_id = s.id) AS source_passage_count
      FROM chosen
      JOIN passages p ON p.id = chosen.passage_id
      JOIN sources s ON s.id = p.source_id
      WHERE chosen.choice = 1
      ORDER BY s.publication_year, s.title, p.sequence
      LIMIT ? OFFSET ?
    `,
    args: [slug, slug, Math.min(Math.max(limit, 1), 100), Math.max(offset, 0)]
  });
  return result.rows.map((row) => ({
    id: text(row, "id"),
    source: sourceSummary(row, "source_"),
    sequence: number(row, "sequence"),
    startOffset: nullableNumber(row, "start_offset"),
    endOffset: nullableNumber(row, "end_offset"),
    printedPage: nullableText(row, "printed_page"),
    scanLeaf: nullableNumber(row, "scan_leaf"),
    displayText: text(row, "display_text"),
    scanUrl: text(row, "scan_url"),
    status: publicationStatusSchema.parse(text(row, "status")),
    surfaceForm: nullableText(row, "surface_form"),
    matchStart: nullableNumber(row, "start_in_passage"),
    matchEnd: nullableNumber(row, "end_in_passage"),
    resolutionMethod: nullableText(row, "resolution_method"),
    confidence: nullableNumber(row, "confidence")
  }));
}

export async function getEntryUsages(slug: string, limit = 100): Promise<ContextualUsage[]> {
  const boundedLimit = Math.min(Math.max(limit, 1), 100);
  const [usageResult, claimResult] = await Promise.all([
    db().execute({
      sql: `
        SELECT u.id AS usage_id, u.mention_type, u.resolution, u.relation_type,
               u.sense_gloss, u.rationale, u.confidence AS usage_confidence,
               u.retrieval_rank, u.status AS usage_status,
               u.evidence_start, u.evidence_end, u.evidence_text,
               p.id, p.sequence, p.start_offset, p.end_offset, p.printed_page,
               p.scan_leaf, p.display_text, p.scan_url, p.status,
               s.id AS source_id, s.title AS source_title, s.author AS source_author,
               s.publication_year AS source_publication_year,
               s.original_year AS source_original_year,
               s.language_code AS source_language_code,
               s.language_label AS source_language_label,
               s.citation_text AS source_citation_text,
               s.archive_provider AS source_archive_provider,
               s.archive_url AS source_archive_url,
               (SELECT COUNT(*) FROM passages sp WHERE sp.source_id = s.id) AS source_passage_count
        FROM contextual_usages u
        JOIN entries e ON e.id = u.entry_id
        JOIN passages p ON p.id = u.passage_id
        JOIN sources s ON s.id = p.source_id
        WHERE e.slug = ?
        ORDER BY s.publication_year, s.title, p.sequence, u.retrieval_rank
        LIMIT ?
      `,
      args: [slug, boundedLimit]
    }),
    db().execute({
      sql: `
        SELECT c.id, c.usage_id, c.claim_type, c.summary, c.subject_text,
               c.object_text, c.stance, c.evidence_basis,
               c.attributed_authority, c.evidence_text, c.confidence, c.status
        FROM usage_claims c
        JOIN contextual_usages u ON u.id = c.usage_id
        JOIN entries e ON e.id = u.entry_id
        WHERE e.slug = ?
        ORDER BY c.usage_id, c.claim_index
      `,
      args: [slug]
    })
  ]);

  const claims = new Map<string, ContextualUsage["claims"]>();
  for (const row of claimResult.rows) {
    const usageId = text(row, "usage_id");
    const collection = claims.get(usageId) ?? [];
    collection.push({
      id: text(row, "id"),
      claimType: claimTypeSchema.parse(text(row, "claim_type")),
      summary: text(row, "summary"),
      subjectText: text(row, "subject_text"),
      objectText: nullableText(row, "object_text"),
      stance: claimStanceSchema.parse(text(row, "stance")),
      evidenceBasis: evidenceBasisSchema.parse(text(row, "evidence_basis")),
      attributedAuthority: nullableText(row, "attributed_authority"),
      evidenceText: text(row, "evidence_text"),
      confidence: number(row, "confidence"),
      status: publicationStatusSchema.parse(text(row, "status"))
    });
    claims.set(usageId, collection);
  }

  return usageResult.rows.map((row) => {
    const usageId = text(row, "usage_id");
    const evidenceText = text(row, "evidence_text");
    return {
      id: usageId,
      mentionType: mentionTypeSchema.parse(text(row, "mention_type")),
      resolution: usageResolutionSchema.parse(text(row, "resolution")),
      relationType: nullableText(row, "relation_type")
        ? usageRelationTypeSchema.parse(text(row, "relation_type"))
        : null,
      senseGloss: nullableText(row, "sense_gloss"),
      rationale: text(row, "rationale"),
      confidence: number(row, "usage_confidence"),
      retrievalRank: number(row, "retrieval_rank"),
      status: publicationStatusSchema.parse(text(row, "usage_status")),
      evidenceText,
      passage: {
        id: text(row, "id"),
        source: sourceSummary(row, "source_"),
        sequence: number(row, "sequence"),
        startOffset: nullableNumber(row, "start_offset"),
        endOffset: nullableNumber(row, "end_offset"),
        printedPage: nullableText(row, "printed_page"),
        scanLeaf: nullableNumber(row, "scan_leaf"),
        displayText: text(row, "display_text"),
        scanUrl: text(row, "scan_url"),
        status: publicationStatusSchema.parse(text(row, "status")),
        surfaceForm: evidenceText,
        matchStart: nullableNumber(row, "evidence_start"),
        matchEnd: nullableNumber(row, "evidence_end"),
        resolutionMethod: "MODEL",
        confidence: number(row, "usage_confidence")
      },
      claims: claims.get(usageId) ?? []
    };
  });
}

export async function getEntrySenses(slug: string): Promise<SenseCluster[]> {
  const result = await db().execute({
    sql: `
      SELECT s.id, s.label, s.definition, s.confidence, s.status,
             group_concat(m.usage_id, char(31)) AS usage_ids
      FROM sense_clusters s
      JOIN entries e ON e.id = s.entry_id
      JOIN sense_memberships m ON m.sense_id = s.id
      WHERE e.slug = ?
      GROUP BY s.id
      ORDER BY s.sort_order, s.label
    `,
    args: [slug]
  });
  return result.rows.map((row) => ({
    id: text(row, "id"),
    label: text(row, "label"),
    definition: text(row, "definition"),
    confidence: number(row, "confidence"),
    status: publicationStatusSchema.parse(text(row, "status")),
    usageIds: (nullableText(row, "usage_ids") ?? "").split("\u001f").filter(Boolean)
  }));
}

export async function getEntryFindings(slug: string): Promise<ResearchFinding[]> {
  const [findingResult, evidenceResult] = await Promise.all([
    db().execute({
      sql: `
        SELECT f.id, f.finding_type, f.title, f.summary, f.confidence, f.status
        FROM research_findings f
        JOIN entries e ON e.id = f.entry_id
        WHERE e.slug = ?
        ORDER BY f.sort_order, f.title
      `,
      args: [slug]
    }),
    db().execute({
      sql: `
        SELECT fc.finding_id, fc.claim_id, fc.role, c.summary,
               c.evidence_text, c.stance, c.evidence_basis,
               p.id AS passage_id, p.scan_url,
               s.title AS source_title, s.author AS source_author,
               s.publication_year
        FROM finding_claims fc
        JOIN research_findings f ON f.id = fc.finding_id
        JOIN entries e ON e.id = f.entry_id
        JOIN usage_claims c ON c.id = fc.claim_id
        JOIN contextual_usages u ON u.id = c.usage_id
        JOIN passages p ON p.id = u.passage_id
        JOIN sources s ON s.id = p.source_id
        WHERE e.slug = ?
        ORDER BY fc.finding_id, s.publication_year, fc.claim_id
      `,
      args: [slug]
    })
  ]);

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
    const id = text(row, "id");
    return {
      id,
      findingType: findingTypeSchema.parse(text(row, "finding_type")),
      title: text(row, "title"),
      summary: text(row, "summary"),
      confidence: number(row, "confidence"),
      status: publicationStatusSchema.parse(text(row, "status")),
      evidence: evidence.get(id) ?? []
    };
  });
}

export async function getEntryPassageCount(slug: string): Promise<number | null> {
  const result = await db().execute({
    sql: "SELECT passage_count FROM entries WHERE slug = ? LIMIT 1",
    args: [slug]
  });
  return result.rows[0] ? number(result.rows[0], "passage_count") : null;
}

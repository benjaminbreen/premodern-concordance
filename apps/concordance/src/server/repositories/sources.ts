import "server-only";

import { publicationStatusSchema, type Passage, type SourceSummary } from "@/contracts/domain";
import { db } from "@/server/db/client";
import { sourceSummary } from "./mappers";
import { nullableNumber, nullableText, number, text } from "./rows";

const sourceColumns = `
  s.id, s.title, s.author, s.publication_year, s.original_year,
  s.language_code, s.language_label, s.citation_text, s.archive_provider,
  s.archive_url, COUNT(p.id) AS passage_count
`;

export async function listSources(): Promise<SourceSummary[]> {
  const result = await db().execute(`
    SELECT ${sourceColumns}
    FROM sources s LEFT JOIN passages p ON p.source_id = s.id
    GROUP BY s.id
    ORDER BY s.publication_year, s.title
  `);
  return result.rows.map((row) => sourceSummary(row));
}

export async function getSource(id: string): Promise<SourceSummary | null> {
  const result = await db().execute({
    sql: `
      SELECT ${sourceColumns}
      FROM sources s LEFT JOIN passages p ON p.source_id = s.id
      WHERE s.id = ? GROUP BY s.id LIMIT 1
    `,
    args: [id]
  });
  return result.rows[0] ? sourceSummary(result.rows[0]) : null;
}

export async function getSourcePassages(id: string, limit = 20, offset = 0): Promise<Passage[]> {
  const result = await db().execute({
    sql: `
      SELECT p.id, p.sequence, p.start_offset, p.end_offset, p.printed_page,
             p.scan_leaf, p.display_text, p.scan_url,
             COALESCE(o.status, p.status) AS status,
             o.surface_form, o.start_in_passage, o.end_in_passage,
             o.resolution_method, o.confidence,
             s.id AS source_id, s.title AS source_title, s.author AS source_author,
             s.publication_year AS source_publication_year,
             s.original_year AS source_original_year,
             s.language_code AS source_language_code,
             s.language_label AS source_language_label,
             s.citation_text AS source_citation_text,
             s.archive_provider AS source_archive_provider,
             s.archive_url AS source_archive_url,
             (SELECT COUNT(*) FROM passages sp WHERE sp.source_id = s.id) AS source_passage_count
      FROM passages p JOIN sources s ON s.id = p.source_id
      LEFT JOIN occurrences o ON o.id = (
        SELECT candidate.id
        FROM occurrences candidate
        WHERE candidate.passage_id = p.id
        ORDER BY CASE candidate.status WHEN 'CORE' THEN 0 ELSE 1 END, candidate.id
        LIMIT 1
      )
      WHERE s.id = ? ORDER BY p.sequence LIMIT ? OFFSET ?
    `,
    args: [id, Math.min(Math.max(limit, 1), 100), Math.max(offset, 0)]
  });
  return result.rows.map((row) => ({
    id: text(row, "id"), source: sourceSummary(row, "source_"),
    sequence: number(row, "sequence"), startOffset: nullableNumber(row, "start_offset"),
    endOffset: nullableNumber(row, "end_offset"), printedPage: nullableText(row, "printed_page"),
    scanLeaf: nullableNumber(row, "scan_leaf"), displayText: text(row, "display_text"),
    scanUrl: text(row, "scan_url"), status: publicationStatusSchema.parse(text(row, "status")),
    surfaceForm: nullableText(row, "surface_form"), matchStart: nullableNumber(row, "start_in_passage"),
    matchEnd: nullableNumber(row, "end_in_passage"), resolutionMethod: nullableText(row, "resolution_method"),
    confidence: nullableNumber(row, "confidence")
  }));
}

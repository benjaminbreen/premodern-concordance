import "server-only";

import { publicationStatusSchema, type Passage } from "@/contracts/domain";
import { db } from "@/server/db/client";
import { readSourceText } from "@/server/text/source-text";
import { sourceSummary } from "./mappers";
import { nullableNumber, nullableText, number, text } from "./rows";

export async function getPassage(id: string, entrySlug?: string): Promise<Passage | null> {
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
      FROM passages p
      JOIN sources s ON s.id = p.source_id
      LEFT JOIN occurrences o ON o.id = (
        SELECT candidate.id
        FROM occurrences candidate
        JOIN entries candidate_entry ON candidate_entry.id = candidate.entry_id
        WHERE candidate.passage_id = p.id
          AND (? IS NULL OR candidate_entry.slug = ?)
        ORDER BY CASE candidate.status WHEN 'CORE' THEN 0 ELSE 1 END, candidate.id
        LIMIT 1
      )
      WHERE p.id = ?
      LIMIT 1
    `,
    args: [entrySlug ?? null, entrySlug ?? null, id]
  });
  const row = result.rows[0];
  if (!row) return null;
  return {
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
  };
}

export async function getExpandedPassageContext(id: string, window: number) {
  const result = await db().execute({
    sql: `
      SELECT p.start_offset, p.end_offset, s.text_object_key
      FROM passages p JOIN sources s ON s.id = p.source_id
      WHERE p.id = ? LIMIT 1
    `,
    args: [id]
  });
  const row = result.rows[0];
  if (!row) return null;
  const objectKey = nullableText(row, "text_object_key");
  const passageStart = nullableNumber(row, "start_offset");
  const passageEnd = nullableNumber(row, "end_offset");
  if (!objectKey || passageStart === null || passageEnd === null) return null;

  const sourceCharacters = Array.from(await readSourceText(objectKey));
  const boundedWindow = Math.min(Math.max(window, 200), 5000);
  const start = Math.max(0, passageStart - boundedWindow);
  const end = Math.min(sourceCharacters.length, passageEnd + boundedWindow);
  return { passageId: id, excerpt: sourceCharacters.slice(start, end).join(""), start, end, expanded: true };
}

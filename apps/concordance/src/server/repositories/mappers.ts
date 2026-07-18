import type { Row } from "@libsql/client";
import { entryKindSchema, publicationStatusSchema, type EntrySummary, type SourceSummary } from "@/contracts/domain";
import { nullableNumber, nullableText, number, text } from "./rows";

export function entrySummary(row: Row, prefix = ""): EntrySummary {
  return {
    id: text(row, `${prefix}id`),
    slug: text(row, `${prefix}slug`),
    preferredLabel: text(row, `${prefix}preferred_label`),
    kind: entryKindSchema.parse(text(row, `${prefix}kind`)),
    scopeNote: text(row, `${prefix}scope_note`),
    exclusionsNote: nullableText(row, `${prefix}exclusions_note`),
    status: publicationStatusSchema.parse(text(row, `${prefix}status`)),
    sourceCount: number(row, `${prefix}source_count`),
    passageCount: number(row, `${prefix}passage_count`),
    earliestYear: nullableNumber(row, `${prefix}earliest_year`),
    latestYear: nullableNumber(row, `${prefix}latest_year`)
  };
}

export function sourceSummary(row: Row, prefix = ""): SourceSummary {
  return {
    id: text(row, `${prefix}id`),
    title: text(row, `${prefix}title`),
    author: nullableText(row, `${prefix}author`),
    publicationYear: number(row, `${prefix}publication_year`),
    originalYear: nullableNumber(row, `${prefix}original_year`),
    languageCode: text(row, `${prefix}language_code`),
    languageLabel: text(row, `${prefix}language_label`),
    citationText: text(row, `${prefix}citation_text`),
    archiveProvider: nullableText(row, `${prefix}archive_provider`),
    archiveUrl: text(row, `${prefix}archive_url`),
    passageCount: number(row, `${prefix}passage_count`)
  };
}

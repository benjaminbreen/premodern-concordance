import "server-only";

import { entryKindSchema, publicationStatusSchema, type SearchResult } from "@/contracts/domain";
import { db } from "@/server/db/client";
import { number, text } from "./rows";

function tokens(query: string) {
  return query
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/ſ/g, "s")
    .match(/[\p{L}\p{N}]+/gu)
    ?.slice(0, 8) ?? [];
}

function ftsQuery(query: string) {
  return tokens(query).map((token) => `"${token.replaceAll('"', '""')}"*`).join(" AND ");
}

export async function searchEntries(query: string, limit = 20): Promise<SearchResult[]> {
  const boundedLimit = Math.min(Math.max(limit, 1), 50);
  const normalizedTokens = tokens(query);
  if (!normalizedTokens.length) return [];

  const result = await db().execute({
    sql: `
      SELECT es.entry_id, es.term_label, e.slug, e.preferred_label, e.kind,
             e.scope_note, e.status, e.source_count, e.passage_count,
             bm25(entry_search) AS rank
      FROM entry_search es
      JOIN entries e ON e.id = es.entry_id
      WHERE entry_search MATCH ?
      ORDER BY rank, e.source_count DESC, e.preferred_label
      LIMIT ?
    `,
    args: [ftsQuery(query), boundedLimit * 4]
  });

  const seen = new Set<string>();
  const matches: SearchResult[] = [];
  for (const row of result.rows) {
    const id = text(row, "entry_id");
    if (seen.has(id)) continue;
    seen.add(id);
    const termLabel = text(row, "term_label");
    matches.push({
      id,
      slug: text(row, "slug"),
      preferredLabel: text(row, "preferred_label"),
      matchedLabel: termLabel || text(row, "preferred_label"),
      kind: entryKindSchema.parse(text(row, "kind")),
      scopeNote: text(row, "scope_note"),
      status: publicationStatusSchema.parse(text(row, "status")),
      sourceCount: number(row, "source_count"),
      passageCount: number(row, "passage_count")
    });
    if (matches.length >= boundedLimit) break;
  }
  return matches;
}

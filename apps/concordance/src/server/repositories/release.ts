import "server-only";

import { db } from "@/server/db/client";
import { number, text } from "./rows";

export interface ReleaseStats {
  releaseId: string;
  sourceCount: number;
  entryCount: number;
  passageCount: number;
}

export async function getReleaseStats(): Promise<ReleaseStats> {
  const result = await db().execute(
    `SELECT id, source_count, entry_count,
      (SELECT COUNT(*) FROM passages) AS passage_count
     FROM release_metadata ORDER BY created_at DESC LIMIT 1`
  );
  const row = result.rows[0];
  if (!row) throw new Error("The public concordance release has no metadata");
  return {
    releaseId: text(row, "id"),
    sourceCount: number(row, "source_count"),
    entryCount: number(row, "entry_count"),
    passageCount: number(row, "passage_count")
  };
}

import "server-only";

import { createClient, type Client } from "@libsql/client";
import { resolve } from "node:path";

const globalDatabase = globalThis as typeof globalThis & {
  premodernDb?: Client;
  premodernReviewDb?: Client;
};

function databaseUrl() {
  if (process.env.TURSO_DATABASE_URL) return process.env.TURSO_DATABASE_URL;
  return `file:${resolve(process.cwd(), "../../var/public.sqlite")}`;
}

export function db(): Client {
  if (!globalDatabase.premodernDb) {
    globalDatabase.premodernDb = createClient({
      url: databaseUrl(),
      authToken: process.env.TURSO_AUTH_TOKEN
    });
  }
  return globalDatabase.premodernDb;
}

export function reviewDb(): Client {
  if (!globalDatabase.premodernReviewDb) {
    const url = process.env.PREMODERN_REVIEW_DB_URL
      ?? `file:${resolve(process.cwd(), "../../var/historian-reviews.sqlite")}`;
    globalDatabase.premodernReviewDb = createClient({ url });
  }
  return globalDatabase.premodernReviewDb;
}

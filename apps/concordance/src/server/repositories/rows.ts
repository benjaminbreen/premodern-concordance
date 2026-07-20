import type { Row } from "@libsql/client";

export function text(row: Row, key: string): string {
  const value = row[key];
  if (typeof value !== "string") throw new TypeError(`Expected ${key} to be text`);
  return value;
}

export function nullableText(row: Row, key: string): string | null {
  const value = row[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new TypeError(`Expected ${key} to be nullable text`);
  return value;
}

export function number(row: Row, key: string): number {
  const value = row[key];
  if (typeof value === "bigint") return Number(value);
  if (typeof value !== "number") throw new TypeError(`Expected ${key} to be numeric`);
  return value;
}

export function nullableNumber(row: Row, key: string): number | null {
  const value = row[key];
  if (value === null || value === undefined) return null;
  if (typeof value === "bigint") return Number(value);
  if (typeof value !== "number") throw new TypeError(`Expected ${key} to be nullable numeric`);
  return value;
}

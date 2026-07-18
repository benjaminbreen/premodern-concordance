export type QueryValue = string | string[] | undefined;

export function firstQueryValue(value: QueryValue, fallback = ""): string {
  if (Array.isArray(value)) return value[0] ?? fallback;
  return value ?? fallback;
}

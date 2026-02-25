import { join } from "path";

/** Resolve a filename inside `public/data/` at runtime. */
export function dataPath(filename: string): string {
  return join(process.cwd(), "public", "data", filename);
}

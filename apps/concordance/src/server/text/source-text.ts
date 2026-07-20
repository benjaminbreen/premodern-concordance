import "server-only";

import { resolve, sep } from "node:path";

function safeLocalPath(key: string) {
  const root = resolve(process.cwd(), "../../var/objects");
  const path = resolve(root, key);
  if (path !== root && !path.startsWith(`${root}${sep}`)) {
    throw new Error("Source object key escaped the configured object directory");
  }
  return path;
}

export async function readSourceText(key: string): Promise<string> {
  const baseUrl = process.env.R2_PUBLIC_BASE_URL?.replace(/\/$/, "");
  if (baseUrl) {
    const response = await fetch(`${baseUrl}/${key.split("/").map(encodeURIComponent).join("/")}`, {
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`Source object returned ${response.status}`);
    return response.text();
  }

  const { readFile } = await import("node:fs/promises");
  return readFile(safeLocalPath(key), "utf8");
}

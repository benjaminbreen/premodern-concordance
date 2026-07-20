import { readdir, readFile, stat } from "node:fs/promises";
import { extname, join, relative, resolve } from "node:path";

const appRoot = resolve(import.meta.dirname, "..");
const srcRoot = join(appRoot, "src");
const publicRoot = join(appRoot, "public");
const codeExtensions = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs"]);
const forbiddenEverywhere = [
  /from\s+["'][^"']*\/web\//,
  /from\s+["'][^"']*\/pipeline\//,
  /from\s+["'](?:openai|@google\/generative-ai)["']/
];

async function filesUnder(directory) {
  const found = [];
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") return found;
    throw error;
  }
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...(await filesUnder(path)));
    else found.push(path);
  }
  return found;
}

const violations = [];
for (const path of await filesUnder(srcRoot)) {
  if (!codeExtensions.has(extname(path))) continue;
  const source = await readFile(path, "utf8");
  const label = relative(appRoot, path);
  for (const pattern of forbiddenEverywhere) {
    if (pattern.test(source)) violations.push(`${label}: forbidden import ${pattern}`);
  }
  if (/^["']use client["'];?/m.test(source)) {
    if (/from\s+["']@\/server\//.test(source)) {
      violations.push(`${label}: client component imports server code`);
    }
    if (/process\.env\./.test(source)) {
      violations.push(`${label}: client component reads environment variables`);
    }
  }
  if (/createClient\s*\(/.test(source) && label !== "src/server/db/client.ts") {
    violations.push(`${label}: database clients may only be created in src/server/db/client.ts`);
  }
}

for (const path of await filesUnder(publicRoot)) {
  const info = await stat(path);
  if (extname(path) === ".json" && info.size > 1_000_000) {
    violations.push(`${relative(appRoot, path)}: public JSON exceeds 1 MB`);
  }
}

if (violations.length) {
  console.error("Architecture check failed:\n" + violations.map((item) => `- ${item}`).join("\n"));
  process.exit(1);
}

console.log("Architecture check passed.");

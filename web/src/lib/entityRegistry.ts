import { readFileSync } from "fs";
import { join } from "path";

export interface RegistryBook {
  id: string;
  title: string;
  author: string;
  year: number;
  language: string;
  description?: string;
}

export interface RegistryAttestation {
  book_id: string;
  book_title: string;
  book_author: string;
  book_year: number;
  book_language: string;
  local_entity_id: string;
  local_name: string;
  category: string;
  subcategory: string;
  count: number;
  variants: string[];
  contexts: string[];
  mention_count: number;
  excerpt_samples: string[];
  entity_page_path: string;
}

export interface RegistryEntity {
  id: string;
  slug: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  is_concordance: boolean;
  concordance_cluster_id: number | null;
  concordance_slug: string | null;
  ground_truth: Record<string, unknown>;
  books: string[];
  names: string[];
  attestations: RegistryAttestation[];
}

export interface EntityRegistry {
  metadata: {
    built_at: string;
    version: string;
    counts: {
      books: number;
      entities_total: number;
      entities_concordance: number;
      entities_singleton: number;
      attestations_total: number;
      mentions_total: number;
    };
    by_category: Record<string, number>;
  };
  books: RegistryBook[];
  entities: RegistryEntity[];
}

let cached: EntityRegistry | null = null;

export function getEntityRegistry(): EntityRegistry {
  if (cached) return cached;
  const registryPath = join(process.cwd(), "public", "data", "entity_registry.json");
  const raw = readFileSync(registryPath, "utf-8");
  cached = JSON.parse(raw) as EntityRegistry;
  return cached;
}

export function clearEntityRegistryCache() {
  cached = null;
}

function foldSpecialLatin(text: string): string {
  return text
    .replace(/Æ/g, "AE")
    .replace(/æ/g, "ae")
    .replace(/Œ/g, "OE")
    .replace(/œ/g, "oe")
    .replace(/ß/g, "ss")
    .replace(/Ø/g, "O")
    .replace(/ø/g, "o")
    .replace(/Ð/g, "D")
    .replace(/ð/g, "d")
    .replace(/Þ/g, "Th")
    .replace(/þ/g, "th");
}

function normalize(text: string): string {
  return foldSpecialLatin(text)
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const OCR_NOISE_CHARS_RE = /[»«^§|{}†‡¶•☉♀♈〈〉]/u;
const BIBLIO_REFS_RE = /\b(fol\.|lib\.|cap\.|timoth\b|regum\b)\b/i;
const DATE_TEXT_RE =
  /\b(janeiro|fevereiro|marco|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|january|february|march|april|may|june|july|august|september|october|november|december)\b/i;

export function isLikelyNoiseEntityName(name: string, totalMentions = 0): boolean {
  const raw = (name || "").trim();
  if (!raw) return true;
  if (OCR_NOISE_CHARS_RE.test(raw)) return true;

  const folded = normalize(raw);
  if (!folded) return true;
  if (BIBLIO_REFS_RE.test(raw)) return true;

  const letters = (raw.match(/\p{L}/gu) || []).length;
  const digits = (raw.match(/\p{N}/gu) || []).length;
  const punct = (raw.match(/[^\p{L}\p{N}\s]/gu) || []).length;
  const len = raw.length;
  const hasLatin = /[\p{Script=Latin}]/u.test(raw);

  if (len <= 2 && totalMentions < 10) return true;
  if (/^[0-9]{3,4}[a-z]?$/i.test(raw)) return true; // likely year/page token
  if (DATE_TEXT_RE.test(raw) && digits >= 1) return true;
  if (/[/\\]/.test(raw) && totalMentions < 100) return true;
  if (/[£€<>]/.test(raw)) return true;
  if (/^[_'".()[\]{}]+|[_'".()[\]{}]+$/.test(raw)) return true;
  if (letters === 0 && digits > 0) return true;
  if (letters === 0 && punct >= 2) return true;
  if (!hasLatin && totalMentions < 20) return true;
  if (letters > 0 && punct / Math.max(1, len) >= 0.35) return true;
  if (digits >= 4 && digits / Math.max(1, len) > 0.45) return true;
  if (/^[\W_].*[\W_]$/.test(raw) && letters < 3) return true;

  return false;
}

function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

export function lexicalEntityScore(query: string, entity: RegistryEntity): number {
  const q = normalize(query);
  if (!q) return 0;

  const names = [entity.canonical_name, ...entity.names].map(normalize).filter(Boolean);
  let best = 0;

  for (const name of names) {
    if (name === q) return 1;
    if (name.startsWith(q)) {
      best = Math.max(best, 0.95);
      continue;
    }
    if (name.includes(q) || q.includes(name)) {
      const overlap = Math.min(name.length, q.length) / Math.max(name.length, q.length);
      best = Math.max(best, 0.75 + 0.2 * overlap);
      continue;
    }
    const dist = levenshtein(q, name);
    const maxLen = Math.max(q.length, name.length);
    if (maxLen > 0) {
      const sim = 1 - dist / maxLen;
      if (sim >= 0.65) {
        best = Math.max(best, sim * 0.8);
      }
    }
  }

  if (normalize(entity.category).includes(q)) {
    best = Math.max(best, 0.25);
  }

  return best;
}

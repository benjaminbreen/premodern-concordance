import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { readFileSync } from "fs";
import { join } from "path";
import { BOOK_YEARS } from "@/lib/books";

// ── Types ──────────────────────────────────────────────────────────────

interface MemberDetail {
  book_id: string;
  entity_id: string;
  name: string;
  count: number;
  context: string;
}

interface SearchEntry {
  embedding: number[];
  metadata: {
    id: string;
    stable_key?: string;
    display_name?: string;
    canonical_name: string;
    category: string;
    subcategory: string;
    book_count: number;
    total_mentions: number;
    books: string[];
    modern_name: string;
    linnaean: string;
    wikidata_id: string;
    wikidata_description: string;
    wikipedia_url: string;
    confidence: string;
    note: string;
    family: string;
    semantic_gloss: string;
    portrait_url: string;
    wikipedia_extract: string;
    names: string[];
    members?: MemberDetail[];
  };
}

interface SearchIndex {
  model: string;
  dimensions: number;
  count: number;
  entries: SearchEntry[];
}

interface SearchResult {
  metadata: SearchEntry["metadata"];
  score: number;
  semantic_score: number;
  lexical_score: number;
}

// ── Cached index + concordance ────────────────────────────────────────

let cachedIndex: SearchIndex | null = null;

function getIndex(): SearchIndex {
  if (cachedIndex) return cachedIndex;
  const indexPath = join(process.cwd(), "public", "data", "search_index.json");
  const raw = readFileSync(indexPath, "utf-8");
  cachedIndex = JSON.parse(raw);
  return cachedIndex!;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let cachedConcordance: any = null;
let clusterMemberMap: Map<string, MemberDetail[]> | null = null;
let clusterContextText: Map<string, string> | null = null;

function getClusterMemberMap(): Map<string, MemberDetail[]> {
  if (clusterMemberMap) return clusterMemberMap;
  loadConcordanceMaps();
  return clusterMemberMap!;
}

function getClusterContextText(): Map<string, string> {
  if (clusterContextText) return clusterContextText;
  loadConcordanceMaps();
  return clusterContextText!;
}

function loadConcordanceMaps(): void {
  if (!cachedConcordance) {
    const cPath = join(process.cwd(), "public", "data", "concordance.json");
    cachedConcordance = JSON.parse(readFileSync(cPath, "utf-8"));
  }

  clusterMemberMap = new Map();
  clusterContextText = new Map();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  for (const cluster of cachedConcordance.clusters) {
    const id = String(cluster.id);
    // Aggregate members by book_id (a cluster can have multiple members from the same book)
    const byBook = new Map<string, { entity_id: string; name: string; count: number; context: string }>();
    const allContexts: string[] = [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    for (const m of cluster.members || []) {
      // Collect all contexts for lexical search
      for (const ctx of m.contexts || []) {
        if (ctx) allContexts.push(ctx);
      }

      const existing = byBook.get(m.book_id);
      if (existing) {
        existing.count += m.count || 0;
      } else {
        const ctx = (m.contexts && m.contexts[0]) || "";
        byBook.set(m.book_id, {
          entity_id: m.entity_id || m.name,
          name: m.name || m.entity_id,
          count: m.count || 0,
          context: ctx.length > 120 ? ctx.slice(0, 117) + "..." : ctx,
        });
      }
    }

    // Sort by book year (chronological)
    const members = Array.from(byBook.entries())
      .map(([book_id, data]) => ({ book_id, ...data }))
      .sort((a, b) => (BOOK_YEARS[a.book_id] || 0) - (BOOK_YEARS[b.book_id] || 0));

    clusterMemberMap.set(id, members);
    clusterContextText.set(id, allContexts.join(" ").toLowerCase());
  }
}

// ── Math helpers ───────────────────────────────────────────────────────

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0,
    normA = 0,
    normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) + 1e-10);
}

// ── Lexical scoring ────────────────────────────────────────────────────

function levenshtein(a: string, b: string): number {
  const m = a.length,
    n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0)
  );
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

function lexicalScore(query: string, entry: SearchEntry, memberContexts?: string): number {
  const q = query.toLowerCase().trim();
  const names = (entry.metadata.names || []).filter(Boolean).map((n) => n.toLowerCase());
  const modernName = (entry.metadata.modern_name || "").toLowerCase();
  const linnaean = (entry.metadata.linnaean || "").toLowerCase();
  const category = (entry.metadata.category || "").toLowerCase();
  const description = (entry.metadata.wikidata_description || "").toLowerCase();

  let best = 0;

  // Exact match on any name → perfect score
  if (
    names.includes(q) ||
    modernName === q ||
    linnaean === q
  ) {
    return 1.0;
  }

  // Substring match — require name to be at least 2 chars to avoid empty-string matches
  for (const name of [modernName, linnaean, ...names]) {
    if (name.length < 2) continue;
    if (name.includes(q) || (name.length >= 3 && q.includes(name))) {
      const overlap = Math.min(q.length, name.length) / Math.max(q.length, name.length);
      best = Math.max(best, 0.7 + 0.3 * overlap);
    }
  }

  // Category match bonus
  if (q.length >= 3 && (category.includes(q) || q.includes(category))) {
    best = Math.max(best, 0.3);
  }

  // Description match — boost higher since these are genuinely relevant
  if (description.includes(q)) {
    best = Math.max(best, 0.55);
  }

  // Semantic gloss match
  const gloss = (entry.metadata.semantic_gloss || "").toLowerCase();
  if (gloss.includes(q)) {
    best = Math.max(best, 0.55);
  }

  // Wikipedia extract match — rich keyword-dense text from Wikipedia articles
  const wikiExtract = (entry.metadata.wikipedia_extract || "").toLowerCase();
  if (q.length >= 3 && wikiExtract.includes(q)) {
    best = Math.max(best, 0.5);
  }

  // Member context match — check if the query appears in any member's context descriptions
  if (memberContexts && q.length >= 3 && memberContexts.includes(q)) {
    best = Math.max(best, 0.45);
  }

  // Fuzzy match (Levenshtein) on top names
  const fuzzyTargets = [
    entry.metadata.canonical_name,
    entry.metadata.modern_name,
    entry.metadata.linnaean,
    ...(entry.metadata.names || []).slice(0, 10),
  ].filter(Boolean);

  for (const target of fuzzyTargets) {
    const t = target.toLowerCase();
    const dist = levenshtein(q, t);
    const maxLen = Math.max(q.length, t.length);
    if (maxLen > 0) {
      const similarity = 1 - dist / maxLen;
      if (similarity > 0.6) {
        best = Math.max(best, similarity * 0.8);
      }
    }
  }

  return best;
}

// ── API handler ────────────────────────────────────────────────────────

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.trim();
  const limitParam = request.nextUrl.searchParams.get("limit");
  const limit = limitParam ? parseInt(limitParam, 10) : 20;
  const categoryFilter = request.nextUrl.searchParams.get("category");

  if (!query || query.length < 2) {
    return NextResponse.json({ results: [], query: "" });
  }

  const apiKey = process.env.OPENAI_API_KEY;
  let index: SearchIndex;

  try {
    index = getIndex();
  } catch {
    return NextResponse.json(
      { error: "Search index not built. Run: python scripts/build_search_index.py" },
      { status: 500 }
    );
  }

  let queryEmbedding: number[] | null = null;

  // Try to get semantic embedding
  if (apiKey) {
    try {
      const openai = new OpenAI({ apiKey });
      const response = await openai.embeddings.create({
        model: index.model,
        input: query,
        dimensions: index.dimensions,
      });
      queryEmbedding = response.data[0].embedding;
    } catch {
      // Fall back to lexical-only
    }
  }

  // Load cluster member map for per-book details
  let memberMap: Map<string, MemberDetail[]>;
  let contextMap: Map<string, string>;
  try {
    memberMap = getClusterMemberMap();
    contextMap = getClusterContextText();
  } catch {
    memberMap = new Map();
    contextMap = new Map();
  }

  // Score all entries
  const scored: SearchResult[] = index.entries.map((entry) => {
    const semantic = queryEmbedding
      ? cosineSimilarity(queryEmbedding, entry.embedding)
      : 0;
    const contexts = contextMap.get(String(entry.metadata.id)) || "";
    const lexical = lexicalScore(query, entry, contexts);

    // Adaptive weighting: if we have a strong lexical match, weight it more
    let score: number;
    if (!queryEmbedding) {
      score = lexical;
    } else if (lexical >= 0.9) {
      // Near-exact match — trust lexical
      score = 0.3 * semantic + 0.7 * lexical;
    } else if (lexical >= 0.6) {
      // Good lexical match
      score = 0.5 * semantic + 0.5 * lexical;
    } else {
      // Rely more on semantic
      score = 0.65 * semantic + 0.35 * lexical;
    }

    // Attach per-book member details
    const members = memberMap.get(String(entry.metadata.id)) || [];

    return {
      metadata: { ...entry.metadata, members },
      score,
      semantic_score: semantic,
      lexical_score: lexical,
    };
  });

  // Filter by category if requested
  const filtered = categoryFilter
    ? scored.filter((r) => r.metadata.category === categoryFilter)
    : scored;

  // Sort by score descending
  filtered.sort((a, b) => b.score - a.score);

  // Return top results
  const results = filtered.slice(0, limit);

  return NextResponse.json({
    query,
    results,
    total_candidates: filtered.length,
    mode: queryEmbedding ? "hybrid" : "lexical",
  });
}

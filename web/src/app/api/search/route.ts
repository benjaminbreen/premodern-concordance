import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { readFileSync } from "fs";
import { join } from "path";

// ── Types ──────────────────────────────────────────────────────────────

interface SearchEntry {
  embedding: number[];
  metadata: {
    id: string;
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
    names: string[];
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

// ── Cached index ───────────────────────────────────────────────────────

let cachedIndex: SearchIndex | null = null;

function getIndex(): SearchIndex {
  if (cachedIndex) return cachedIndex;
  const indexPath = join(process.cwd(), "public", "data", "search_index.json");
  const raw = readFileSync(indexPath, "utf-8");
  cachedIndex = JSON.parse(raw);
  return cachedIndex!;
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

function lexicalScore(query: string, entry: SearchEntry): number {
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

  // Substring match
  for (const name of [modernName, linnaean, ...names]) {
    if (name.includes(q) || q.includes(name)) {
      const overlap = Math.min(q.length, name.length) / Math.max(q.length, name.length);
      best = Math.max(best, 0.7 + 0.3 * overlap);
    }
  }

  // Category match bonus
  if (category.includes(q) || q.includes(category)) {
    best = Math.max(best, 0.3);
  }

  // Description match
  if (description.includes(q)) {
    best = Math.max(best, 0.4);
  }

  // Semantic gloss match
  const gloss = (entry.metadata.semantic_gloss || "").toLowerCase();
  if (gloss.includes(q)) {
    best = Math.max(best, 0.4);
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

  // Score all entries
  const scored: SearchResult[] = index.entries.map((entry) => {
    const semantic = queryEmbedding
      ? cosineSimilarity(queryEmbedding, entry.embedding)
      : 0;
    const lexical = lexicalScore(query, entry);

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

    return {
      metadata: entry.metadata,
      score,
      semantic_score: semantic,
      lexical_score: lexical,
    };
  });

  // Filter by category if requested
  let filtered = categoryFilter
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

import { NextRequest, NextResponse } from "next/server";
import {
  getEntityRegistry,
  isLikelyNoiseEntityName,
  lexicalEntityScore,
  type RegistryEntity,
} from "@/lib/entityRegistry";

interface EntitiesResult {
  id: string;
  slug: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  is_concordance: boolean;
  books: string[];
  names: string[];
  ground_truth: Record<string, unknown>;
}

interface EntitiesCompactResult {
  id: string;
  slug: string;
  canonical_name: string;
  category: string;
  book_count: number;
  total_mentions: number;
  is_concordance: boolean;
  books: string[];
}

function initialFromName(name: string): string {
  const folded = name
    .trim()
    .replace(/^Æ/i, "A")
    .replace(/^æ/i, "a")
    .replace(/^Œ/i, "O")
    .replace(/^œ/i, "o");
  const first = folded.charAt(0);
  const normalized = first
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase();
  return /^[A-Z]$/.test(normalized) ? normalized : "#";
}

function toResult(entity: RegistryEntity): EntitiesResult {
  return {
    id: entity.id,
    slug: entity.slug,
    canonical_name: entity.canonical_name,
    category: entity.category,
    subcategory: entity.subcategory,
    book_count: entity.book_count,
    total_mentions: entity.total_mentions,
    is_concordance: entity.is_concordance,
    books: entity.books,
    names: entity.names.slice(0, 20),
    ground_truth: entity.ground_truth || {},
  };
}

function toCompactResult(entity: RegistryEntity): EntitiesCompactResult {
  return {
    id: entity.id,
    slug: entity.slug,
    canonical_name: entity.canonical_name,
    category: entity.category,
    book_count: entity.book_count,
    total_mentions: entity.total_mentions,
    is_concordance: entity.is_concordance,
    books: entity.books.slice(0, 5),
  };
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const q = params.get("q")?.trim() || "";
  const category = params.get("category")?.trim() || "";
  const book = params.get("book")?.trim() || "";
  const crossBook = params.get("cross_book")?.trim() || "all"; // all|only|exclude
  const includeNoise = params.get("include_noise") === "1";
  const initial = (params.get("initial") || "ALL").trim().toUpperCase();
  const sort = params.get("sort")?.trim() || ""; // alpha|mentions
  const compact = params.get("compact") === "1";
  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  const maxLimit = compact ? 5000 : 100;
  const limit = Math.min(maxLimit, Math.max(1, Number.parseInt(params.get("limit") || "40", 10) || 40));

  const registry = getEntityRegistry();
  let entities = registry.entities;

  if (category && category !== "ALL") {
    entities = entities.filter((e) => e.category === category);
  }

  if (book && book !== "ALL") {
    entities = entities.filter((e) => e.books.includes(book));
  }

  if (crossBook === "only") {
    entities = entities.filter((e) => e.book_count >= 2);
  } else if (crossBook === "exclude") {
    entities = entities.filter((e) => e.book_count < 2);
  }

  if (!includeNoise) {
    entities = entities.filter(
      (e) => !isLikelyNoiseEntityName(e.canonical_name, e.total_mentions)
    );
  }

  if (initial !== "ALL") {
    entities = entities.filter((e) => initialFromName(e.canonical_name) === initial);
  }

  let scored: Array<{ entity: RegistryEntity; score: number }> = entities.map((entity) => ({
    entity,
    score: q ? lexicalEntityScore(q, entity) : 0,
  }));

  if (q.length >= 1) {
    scored = scored.filter((x) => x.score > 0.2);
    scored.sort(
      (a, b) =>
        b.score - a.score ||
        b.entity.total_mentions - a.entity.total_mentions ||
        a.entity.canonical_name.localeCompare(b.entity.canonical_name)
    );
  } else {
    if (sort === "alpha") {
      scored.sort((a, b) => a.entity.canonical_name.localeCompare(b.entity.canonical_name));
    } else {
      scored.sort(
        (a, b) =>
          Number(b.entity.is_concordance) - Number(a.entity.is_concordance) ||
          b.entity.book_count - a.entity.book_count ||
          b.entity.total_mentions - a.entity.total_mentions ||
          a.entity.canonical_name.localeCompare(b.entity.canonical_name)
      );
    }
  }

  const total = scored.length;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = (page - 1) * limit;
  const slice = scored.slice(start, start + limit);

  const results = compact
    ? slice.map(({ entity }) => toCompactResult(entity))
    : slice.map(({ entity, score }) => ({
        ...toResult(entity),
        score: q ? score : undefined,
      }));

  return NextResponse.json({
    query: q,
    page,
    limit,
    total,
    total_pages: totalPages,
    results,
    facets: {
      categories: registry.metadata.by_category,
      books: registry.books,
      counts: registry.metadata.counts,
    },
  });
}

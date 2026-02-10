import { NextRequest, NextResponse } from "next/server";
import { getEntityRegistry } from "@/lib/entityRegistry";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ slug: string }> }
) {
  const { slug } = await context.params;
  const params = request.nextUrl.searchParams;
  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  const limit = Math.min(100, Math.max(1, Number.parseInt(params.get("limit") || "20", 10) || 20));

  const registry = getEntityRegistry();
  const entity = registry.entities.find((e) => e.slug === slug);
  if (!entity) {
    return NextResponse.json({ error: "Entity not found" }, { status: 404 });
  }

  const ordered = [...entity.attestations].sort(
    (a, b) =>
      b.count - a.count ||
      a.book_year - b.book_year ||
      a.book_id.localeCompare(b.book_id)
  );
  const total = ordered.length;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = (page - 1) * limit;

  return NextResponse.json({
    entity_slug: slug,
    page,
    limit,
    total,
    total_pages: totalPages,
    attestations: ordered.slice(start, start + limit),
  });
}


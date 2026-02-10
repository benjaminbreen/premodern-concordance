import { NextResponse } from "next/server";
import { getEntityRegistry } from "@/lib/entityRegistry";

export async function GET(
  _request: Request,
  context: { params: Promise<{ slug: string }> }
) {
  const { slug } = await context.params;
  const registry = getEntityRegistry();
  const entity = registry.entities.find((e) => e.slug === slug);

  if (!entity) {
    return NextResponse.json({ error: "Entity not found" }, { status: 404 });
  }

  return NextResponse.json({
    entity,
    book_details: registry.books.filter((b) => entity.books.includes(b.id)),
  });
}


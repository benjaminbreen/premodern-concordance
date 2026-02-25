import { NextResponse } from "next/server";
import { getEntityRegistry } from "@/lib/entityRegistry";

export async function GET() {
  const registry = getEntityRegistry();
  return NextResponse.json({
    books: registry.books,
    total: registry.books.length,
  });
}

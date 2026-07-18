import { NextRequest, NextResponse } from "next/server";
import { passageSchema } from "@/contracts/domain";
import { getEntryPassageCount, getEntryPassages } from "@/server/repositories/entries";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const requestedLimit = Number.parseInt(request.nextUrl.searchParams.get("limit") ?? "10", 10);
  const requestedOffset = Number.parseInt(request.nextUrl.searchParams.get("offset") ?? "0", 10);
  const limit = Math.min(Math.max(Number.isFinite(requestedLimit) ? requestedLimit : 10, 1), 100);
  const offset = Math.max(Number.isFinite(requestedOffset) ? requestedOffset : 0, 0);
  const [passages, total] = await Promise.all([
    getEntryPassages(slug, limit, offset),
    getEntryPassageCount(slug)
  ]);
  if (total === null) return NextResponse.json({ error: "Not found" }, { status: 404 });
  const nextOffset = offset + passages.length < total ? offset + passages.length : null;
  return NextResponse.json({ passages: passageSchema.array().parse(passages), nextOffset, total });
}

import { NextRequest, NextResponse } from "next/server";
import { getExpandedPassageContext, getPassage } from "@/server/repositories/passages";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const requestedWindow = Number.parseInt(request.nextUrl.searchParams.get("window") ?? "1000", 10);
  const expanded = await getExpandedPassageContext(id, Number.isFinite(requestedWindow) ? requestedWindow : 1000);
  if (expanded) return NextResponse.json(expanded);
  const passage = await getPassage(id);
  if (!passage) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json({ passageId: passage.id, excerpt: passage.displayText, start: passage.startOffset, end: passage.endOffset, expanded: false });
}

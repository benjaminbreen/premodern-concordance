import { NextRequest, NextResponse } from "next/server";
import { searchResultSchema } from "@/contracts/domain";
import { searchEntries } from "@/server/repositories/search";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.slice(0, 200).trim() ?? "";
  const limit = Number.parseInt(request.nextUrl.searchParams.get("limit") ?? "20", 10);
  const results = query ? await searchEntries(query, Number.isFinite(limit) ? limit : 20) : [];
  return NextResponse.json({ query, results: searchResultSchema.array().parse(results) });
}

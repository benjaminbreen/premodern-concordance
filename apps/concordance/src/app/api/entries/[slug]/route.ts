import { NextResponse } from "next/server";
import { entryDetailSchema } from "@/contracts/domain";
import { getEntryBySlug } from "@/server/repositories/entries";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const entry = await getEntryBySlug(slug);
  return entry ? NextResponse.json(entryDetailSchema.parse(entry)) : NextResponse.json({ error: "Not found" }, { status: 404 });
}

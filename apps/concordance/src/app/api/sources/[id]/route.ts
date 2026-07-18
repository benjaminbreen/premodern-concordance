import { NextResponse } from "next/server";
import { sourceSummarySchema } from "@/contracts/domain";
import { getSource } from "@/server/repositories/sources";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const source = await getSource(id);
  return source ? NextResponse.json(sourceSummarySchema.parse(source)) : NextResponse.json({ error: "Not found" }, { status: 404 });
}

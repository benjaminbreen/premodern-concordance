import { NextResponse } from "next/server";
import { passageSchema } from "@/contracts/domain";
import { getPassage } from "@/server/repositories/passages";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const passage = await getPassage(id);
  return passage ? NextResponse.json(passageSchema.parse(passage)) : NextResponse.json({ error: "Not found" }, { status: 404 });
}

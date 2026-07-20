import { reviewModeEnabled } from "@/server/reviews/config";
import { latestReviewExportJsonl } from "@/server/reviews/store";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!reviewModeEnabled()) return new Response("Not found", { status: 404 });
  const body = await latestReviewExportJsonl();
  return new Response(body, {
    headers: {
      "Cache-Control": "no-store",
      "Content-Disposition": "attachment; filename=historian-finding-assessments.jsonl",
      "Content-Type": "application/x-ndjson; charset=utf-8"
    }
  });
}

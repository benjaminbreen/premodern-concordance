import { NextResponse } from "next/server";
import { ZodError } from "zod";
import { findingReviewSubmissionSchema } from "@/contracts/review";
import { reviewModeEnabled } from "@/server/reviews/config";
import { getFindingReviewItem } from "@/server/reviews/data";
import { saveFindingReview } from "@/server/reviews/store";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!reviewModeEnabled()) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  try {
    const submission = findingReviewSubmissionSchema.parse(await request.json());
    const item = await getFindingReviewItem(submission.findingId);
    if (!item) return NextResponse.json({ error: "Finding not found" }, { status: 404 });
    const review = await saveFindingReview(item, submission);
    return NextResponse.json({ review }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof ZodError) {
      return NextResponse.json(
        { error: "Invalid assessment", issues: error.issues },
        { status: 400, headers: { "Cache-Control": "no-store" } }
      );
    }
    const message = error instanceof Error ? error.message : "Unable to save assessment";
    return NextResponse.json(
      { error: message },
      { status: 400, headers: { "Cache-Control": "no-store" } }
    );
  }
}

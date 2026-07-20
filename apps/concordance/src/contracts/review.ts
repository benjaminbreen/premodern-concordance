import { z } from "zod";
import { researchFindingSchema } from "./domain";

export const reviewStateSchema = z.enum(["ASSESSED", "DEFERRED"]);
export const evidenceSupportSchema = z.enum([
  "SUPPORTED",
  "PARTLY_SUPPORTED",
  "UNSUPPORTED",
  "UNCLEAR"
]);
export const researchValueSchema = z.enum([
  "FOOTNOTE_WORTHY",
  "PROMISING_LEAD",
  "KNOWN_OR_EXPECTED",
  "BANAL",
  "IRRELEVANT",
  "UNCLEAR"
]);
export const failureModeSchema = z.enum([
  "RETRIEVAL",
  "ENTRY_RESOLUTION",
  "CLAIM_EXTRACTION",
  "INVALID_COMPARISON",
  "OVERSTATED_SUMMARY",
  "MISSING_COUNTEREVIDENCE",
  "OCR_OR_PARATEXT_NOISE",
  "DUPLICATE_EVIDENCE"
]);
export const claimVerdictSchema = z.enum([
  "ACCURATE",
  "PARTLY_ACCURATE",
  "INACCURATE",
  "UNCLEAR"
]);

export const findingReviewItemSchema = z.object({
  releaseId: z.string(),
  entry: z.object({
    id: z.string(),
    slug: z.string(),
    preferredLabel: z.string(),
    scopeNote: z.string()
  }),
  finding: researchFindingSchema
});

const findingReviewJudgmentShape = {
  reviewState: reviewStateSchema,
  evidenceSupport: evidenceSupportSchema.nullable(),
  researchValue: researchValueSchema.nullable(),
  failureModes: z.array(failureModeSchema).max(8),
  claimVerdicts: z.record(z.string(), claimVerdictSchema),
  note: z.string().max(5000),
  correctedSummary: z.string().max(3000)
};

export const findingReviewSubmissionSchema = z.object({
  findingId: z.string().min(1),
  ...findingReviewJudgmentShape
}).superRefine((value, context) => {
  if (value.reviewState === "ASSESSED" && !value.evidenceSupport) {
    context.addIssue({ code: "custom", path: ["evidenceSupport"], message: "Choose an evidence judgment" });
  }
  if (value.reviewState === "ASSESSED" && !value.researchValue) {
    context.addIssue({ code: "custom", path: ["researchValue"], message: "Choose a research-value judgment" });
  }
});

export const savedFindingReviewSchema = z.object({
  ...findingReviewJudgmentShape,
  id: z.string(),
  findingId: z.string(),
  releaseId: z.string(),
  snapshotSha256: z.string(),
  reviewer: z.string(),
  createdAt: z.string()
});

export type FindingReviewItem = z.infer<typeof findingReviewItemSchema>;
export type FindingReviewSubmission = z.infer<typeof findingReviewSubmissionSchema>;
export type SavedFindingReview = z.infer<typeof savedFindingReviewSchema>;
export type EvidenceSupport = z.infer<typeof evidenceSupportSchema>;
export type ResearchValue = z.infer<typeof researchValueSchema>;
export type FailureMode = z.infer<typeof failureModeSchema>;
export type ClaimVerdict = z.infer<typeof claimVerdictSchema>;

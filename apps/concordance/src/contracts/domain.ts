import { z } from "zod";

export const entryKindSchema = z.enum([
  "ORGANISM_TAXON",
  "SUBSTANCE_MATERIAL",
  "DISEASE_CONDITION",
  "ANATOMY",
  "PRACTICE_METHOD",
  "ROLE_OCCUPATION",
  "CONCEPT_THEORY",
  "PHENOMENON_PROCESS",
  "OBJECT_INSTRUMENT"
]);

export const publicationStatusSchema = z.enum(["CORE", "SUGGESTED"]);

export const termRelationSchema = z.enum([
  "PREFERRED_LABEL",
  "ORTHOGRAPHIC_VARIANT",
  "TRANSLATION",
  "HISTORICAL_LABEL",
  "TAXONOMIC_SYNONYM",
  "TRADE_NAME",
  "DERIVED_FORM",
  "CONTESTED_LABEL"
]);

export const relationLayerSchema = z.enum(["PRECISE", "EXPLORATORY"]);

export const entryRelationTypeSchema = z.enum([
  "PREPARATION_OF",
  "BROADER_THAN",
  "NARROWER_THAN",
  "PART_OF",
  "CONTESTED_IDENTITY",
  "INFLUENCE",
  "SHARED_PROBLEM",
  "FUNCTIONAL_ANALOGY",
  "LATER_REFRAMING",
  "CONTRAST"
]);

export type EntryKind = z.infer<typeof entryKindSchema>;
export type PublicationStatus = z.infer<typeof publicationStatusSchema>;
export type TermRelation = z.infer<typeof termRelationSchema>;
export type RelationLayer = z.infer<typeof relationLayerSchema>;
export type EntryRelationType = z.infer<typeof entryRelationTypeSchema>;

export const mentionTypeSchema = z.enum(["NAMED", "DESCRIBED", "IMPLIED", "ABSENT"]);
export const usageResolutionSchema = z.enum([
  "SAME_ENTRY",
  "RELATED_DISTINCT",
  "AMBIGUOUS",
  "NOT_RELEVANT"
]);
export const usageRelationTypeSchema = z.enum([
  "BROADER",
  "NARROWER",
  "PART_OF",
  "PREPARATION_OF",
  "DERIVED_FROM",
  "CONCEPTUAL_OVERLAP",
  "FUNCTIONAL_ANALOGY",
  "CONTESTED_IDENTITY",
  "LATER_REFRAMING",
  "SHARED_PROBLEM",
  "OTHER"
]);
export const claimTypeSchema = z.enum([
  "DEFINITION",
  "IDENTITY",
  "CAUSAL_EFFECT",
  "PROPERTY",
  "FUNCTION_USE",
  "ORIGIN_DISTRIBUTION",
  "CLASSIFICATION",
  "MECHANISM",
  "EVALUATION",
  "METHOD",
  "OTHER"
]);
export const claimStanceSchema = z.enum([
  "ASSERTS",
  "DENIES",
  "QUALIFIES",
  "UNCERTAIN",
  "ATTRIBUTES",
  "REPORTS"
]);
export const evidenceBasisSchema = z.enum([
  "OBSERVATION",
  "EXPERIMENT",
  "CASE_REPORT",
  "AUTHORITY_CITATION",
  "REASONING",
  "HEARSAY",
  "RECIPE_OR_INSTRUCTION",
  "UNSTATED"
]);

export const searchResultSchema = z.object({
  id: z.string(),
  slug: z.string(),
  preferredLabel: z.string(),
  matchedLabel: z.string(),
  kind: entryKindSchema,
  scopeNote: z.string(),
  status: publicationStatusSchema,
  sourceCount: z.number().int().nonnegative(),
  passageCount: z.number().int().nonnegative()
});

export type SearchResult = z.infer<typeof searchResultSchema>;

export const termFormSchema = z.object({
  id: z.string(),
  displayForm: z.string(),
  languageCode: z.string().nullable(),
  relationType: termRelationSchema,
  rationale: z.string().nullable(),
  status: publicationStatusSchema,
  confidence: z.number().nullable()
});

export const entrySummarySchema = z.object({
  id: z.string(),
  slug: z.string(),
  preferredLabel: z.string(),
  kind: entryKindSchema,
  scopeNote: z.string(),
  exclusionsNote: z.string().nullable(),
  status: publicationStatusSchema,
  sourceCount: z.number().int().nonnegative(),
  passageCount: z.number().int().nonnegative(),
  earliestYear: z.number().int().nullable(),
  latestYear: z.number().int().nullable()
});

export const sourceSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  author: z.string().nullable(),
  publicationYear: z.number().int(),
  originalYear: z.number().int().nullable(),
  languageCode: z.string(),
  languageLabel: z.string(),
  citationText: z.string(),
  archiveProvider: z.string().nullable(),
  archiveUrl: z.string(),
  passageCount: z.number().int().nonnegative().default(0)
});

export const passageSchema = z.object({
  id: z.string(),
  source: sourceSummarySchema,
  sequence: z.number().int().nonnegative(),
  startOffset: z.number().int().nullable(),
  endOffset: z.number().int().nullable(),
  printedPage: z.string().nullable(),
  scanLeaf: z.number().int().nullable(),
  displayText: z.string(),
  scanUrl: z.string(),
  status: publicationStatusSchema,
  surfaceForm: z.string().nullable(),
  matchStart: z.number().int().nullable(),
  matchEnd: z.number().int().nullable(),
  resolutionMethod: z.string().nullable(),
  confidence: z.number().nullable()
});

export const entryRelationSchema = z.object({
  id: z.string(),
  direction: z.enum(["OUTGOING", "INCOMING"]),
  layer: relationLayerSchema,
  relationType: entryRelationTypeSchema,
  rationale: z.string(),
  nonClaim: z.string().nullable(),
  confidence: z.number().nullable(),
  status: publicationStatusSchema,
  evidencePassageIds: z.array(z.string()),
  target: entrySummarySchema
});

export const entryDetailSchema = entrySummarySchema.extend({
  terms: z.array(termFormSchema),
  relations: z.array(entryRelationSchema)
});

export const usageClaimSchema = z.object({
  id: z.string(),
  claimType: claimTypeSchema,
  summary: z.string(),
  subjectText: z.string(),
  objectText: z.string().nullable(),
  stance: claimStanceSchema,
  evidenceBasis: evidenceBasisSchema,
  attributedAuthority: z.string().nullable(),
  evidenceText: z.string(),
  confidence: z.number(),
  status: publicationStatusSchema
});

export const contextualUsageSchema = z.object({
  id: z.string(),
  mentionType: mentionTypeSchema,
  resolution: usageResolutionSchema,
  relationType: usageRelationTypeSchema.nullable(),
  senseGloss: z.string().nullable(),
  rationale: z.string(),
  confidence: z.number(),
  retrievalRank: z.number().int().positive(),
  status: publicationStatusSchema,
  evidenceText: z.string(),
  passage: passageSchema,
  claims: z.array(usageClaimSchema)
});

export const senseClusterSchema = z.object({
  id: z.string(),
  label: z.string(),
  definition: z.string(),
  confidence: z.number(),
  status: publicationStatusSchema,
  usageIds: z.array(z.string())
});

export const findingTypeSchema = z.enum([
  "RECURRENCE",
  "DISAGREEMENT",
  "QUALIFICATION",
  "SENSE_SHIFT",
  "METHOD_SHIFT",
  "TRANSMISSION_CANDIDATE",
  "ANOMALY"
]);
export const findingClaimRoleSchema = z.enum([
  "SUPPORTS",
  "CONTRADICTS",
  "QUALIFIES",
  "EXAMPLE"
]);
export const findingEvidenceSchema = z.object({
  claimId: z.string(),
  role: findingClaimRoleSchema,
  summary: z.string(),
  evidenceText: z.string(),
  stance: claimStanceSchema,
  evidenceBasis: evidenceBasisSchema,
  sourceTitle: z.string(),
  sourceAuthor: z.string().nullable(),
  publicationYear: z.number().int(),
  passageId: z.string(),
  scanUrl: z.string()
});
export const researchFindingSchema = z.object({
  id: z.string(),
  findingType: findingTypeSchema,
  title: z.string(),
  summary: z.string(),
  confidence: z.number(),
  status: publicationStatusSchema,
  evidence: z.array(findingEvidenceSchema)
});

export type TermForm = z.infer<typeof termFormSchema>;
export type EntrySummary = z.infer<typeof entrySummarySchema>;
export type SourceSummary = z.infer<typeof sourceSummarySchema>;
export type Passage = z.infer<typeof passageSchema>;
export type EntryRelation = z.infer<typeof entryRelationSchema>;
export type EntryDetail = z.infer<typeof entryDetailSchema>;
export type UsageClaim = z.infer<typeof usageClaimSchema>;
export type ContextualUsage = z.infer<typeof contextualUsageSchema>;
export type SenseCluster = z.infer<typeof senseClusterSchema>;
export type ResearchFinding = z.infer<typeof researchFindingSchema>;

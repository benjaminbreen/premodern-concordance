CREATE TABLE contextual_usages (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  passage_id TEXT NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
  mention_type TEXT NOT NULL CHECK (mention_type IN (
    'NAMED', 'DESCRIBED', 'IMPLIED', 'ABSENT'
  )),
  resolution TEXT NOT NULL CHECK (resolution IN (
    'SAME_ENTRY', 'RELATED_DISTINCT', 'AMBIGUOUS', 'NOT_RELEVANT'
  )),
  relation_type TEXT CHECK (relation_type IS NULL OR relation_type IN (
    'BROADER', 'NARROWER', 'PART_OF', 'PREPARATION_OF', 'DERIVED_FROM',
    'CONCEPTUAL_OVERLAP', 'FUNCTIONAL_ANALOGY', 'CONTESTED_IDENTITY',
    'LATER_REFRAMING', 'SHARED_PROBLEM', 'OTHER'
  )),
  evidence_start INTEGER CHECK (evidence_start IS NULL OR evidence_start >= 0),
  evidence_end INTEGER CHECK (evidence_end IS NULL OR evidence_end >= 0),
  evidence_text TEXT,
  sense_gloss TEXT,
  rationale TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  retrieval_method TEXT NOT NULL,
  retrieval_rank INTEGER NOT NULL CHECK (retrieval_rank > 0),
  model_run_id TEXT NOT NULL REFERENCES model_runs(id),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (entry_id, passage_id, model_run_id),
  CHECK (
    (evidence_start IS NULL AND evidence_end IS NULL AND evidence_text IS NULL)
    OR
    (evidence_start IS NOT NULL AND evidence_end IS NOT NULL
      AND evidence_text IS NOT NULL AND evidence_end > evidence_start)
  ),
  CHECK (
    (resolution = 'RELATED_DISTINCT' AND relation_type IS NOT NULL)
    OR
    (resolution != 'RELATED_DISTINCT' AND relation_type IS NULL)
  )
) STRICT;

CREATE INDEX idx_contextual_usages_entry
  ON contextual_usages(entry_id, status, resolution);
CREATE INDEX idx_contextual_usages_passage
  ON contextual_usages(passage_id, status);

CREATE TABLE usage_claims (
  id TEXT PRIMARY KEY,
  usage_id TEXT NOT NULL REFERENCES contextual_usages(id) ON DELETE CASCADE,
  claim_index INTEGER NOT NULL CHECK (claim_index BETWEEN 0 AND 1),
  claim_type TEXT NOT NULL CHECK (claim_type IN (
    'DEFINITION', 'IDENTITY', 'CAUSAL_EFFECT', 'PROPERTY', 'FUNCTION_USE',
    'ORIGIN_DISTRIBUTION', 'CLASSIFICATION', 'MECHANISM', 'EVALUATION',
    'METHOD', 'OTHER'
  )),
  summary TEXT NOT NULL,
  subject_text TEXT NOT NULL,
  object_text TEXT,
  stance TEXT NOT NULL CHECK (stance IN (
    'ASSERTS', 'DENIES', 'QUALIFIES', 'UNCERTAIN', 'ATTRIBUTES', 'REPORTS'
  )),
  evidence_basis TEXT NOT NULL CHECK (evidence_basis IN (
    'OBSERVATION', 'EXPERIMENT', 'CASE_REPORT', 'AUTHORITY_CITATION',
    'REASONING', 'HEARSAY', 'RECIPE_OR_INSTRUCTION', 'UNSTATED'
  )),
  attributed_authority TEXT,
  evidence_start INTEGER NOT NULL CHECK (evidence_start >= 0),
  evidence_end INTEGER NOT NULL CHECK (evidence_end > evidence_start),
  evidence_text TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (usage_id, claim_index)
) STRICT;

CREATE INDEX idx_usage_claims_usage ON usage_claims(usage_id, status);
CREATE INDEX idx_usage_claims_type ON usage_claims(claim_type, stance, evidence_basis);

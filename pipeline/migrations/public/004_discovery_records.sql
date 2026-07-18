ALTER TABLE release_metadata ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE release_metadata ADD COLUMN claim_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE contextual_usages (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id),
  passage_id TEXT NOT NULL REFERENCES passages(id),
  mention_type TEXT NOT NULL,
  resolution TEXT NOT NULL,
  relation_type TEXT,
  evidence_start INTEGER,
  evidence_end INTEGER,
  evidence_text TEXT,
  sense_gloss TEXT,
  rationale TEXT NOT NULL,
  confidence REAL NOT NULL,
  retrieval_method TEXT NOT NULL,
  retrieval_rank INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE INDEX idx_public_contextual_usages_entry
  ON contextual_usages(entry_id, resolution, retrieval_rank);
CREATE INDEX idx_public_contextual_usages_passage
  ON contextual_usages(passage_id);

CREATE TABLE usage_claims (
  id TEXT PRIMARY KEY,
  usage_id TEXT NOT NULL REFERENCES contextual_usages(id),
  claim_index INTEGER NOT NULL,
  claim_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  subject_text TEXT NOT NULL,
  object_text TEXT,
  stance TEXT NOT NULL,
  evidence_basis TEXT NOT NULL,
  attributed_authority TEXT,
  evidence_start INTEGER NOT NULL,
  evidence_end INTEGER NOT NULL,
  evidence_text TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED')),
  UNIQUE (usage_id, claim_index)
) STRICT;

CREATE INDEX idx_public_usage_claims_usage ON usage_claims(usage_id, claim_index);

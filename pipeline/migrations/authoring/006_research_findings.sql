CREATE TABLE research_findings (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  finding_type TEXT NOT NULL CHECK (finding_type IN (
    'RECURRENCE', 'DISAGREEMENT', 'QUALIFICATION', 'SENSE_SHIFT',
    'METHOD_SHIFT', 'TRANSMISSION_CANDIDATE', 'ANOMALY'
  )),
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  model_run_id TEXT NOT NULL REFERENCES model_runs(id),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (entry_id, title, model_run_id)
) STRICT;

CREATE INDEX idx_research_findings_entry
  ON research_findings(entry_id, status, sort_order);

CREATE TABLE finding_claims (
  finding_id TEXT NOT NULL REFERENCES research_findings(id) ON DELETE CASCADE,
  claim_id TEXT NOT NULL REFERENCES usage_claims(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN (
    'SUPPORTS', 'CONTRADICTS', 'QUALIFIES', 'EXAMPLE'
  )),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  PRIMARY KEY (finding_id, claim_id)
) WITHOUT ROWID, STRICT;

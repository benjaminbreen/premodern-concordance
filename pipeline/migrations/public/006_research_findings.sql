CREATE TABLE research_findings (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id),
  finding_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  sort_order INTEGER NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE INDEX idx_public_research_findings_entry
  ON research_findings(entry_id, sort_order);

CREATE TABLE finding_claims (
  finding_id TEXT NOT NULL REFERENCES research_findings(id),
  claim_id TEXT NOT NULL REFERENCES usage_claims(id),
  role TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED')),
  PRIMARY KEY (finding_id, claim_id)
) WITHOUT ROWID, STRICT;

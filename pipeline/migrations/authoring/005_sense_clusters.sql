CREATE TABLE sense_clusters (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  definition TEXT NOT NULL,
  sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  model_run_id TEXT NOT NULL REFERENCES model_runs(id),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (entry_id, label, model_run_id)
) STRICT;

CREATE INDEX idx_sense_clusters_entry
  ON sense_clusters(entry_id, status, sort_order);

CREATE TABLE sense_memberships (
  sense_id TEXT NOT NULL REFERENCES sense_clusters(id) ON DELETE CASCADE,
  usage_id TEXT NOT NULL REFERENCES contextual_usages(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  PRIMARY KEY (sense_id, usage_id)
) WITHOUT ROWID, STRICT;

CREATE UNIQUE INDEX idx_sense_memberships_one_active_sense
  ON sense_memberships(usage_id)
  WHERE status IN ('CORE', 'SUGGESTED');

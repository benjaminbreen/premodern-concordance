CREATE TABLE sense_clusters (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id),
  label TEXT NOT NULL,
  definition TEXT NOT NULL,
  sort_order INTEGER NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE INDEX idx_public_sense_clusters_entry
  ON sense_clusters(entry_id, sort_order);

CREATE TABLE sense_memberships (
  sense_id TEXT NOT NULL REFERENCES sense_clusters(id),
  usage_id TEXT NOT NULL REFERENCES contextual_usages(id),
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED')),
  PRIMARY KEY (sense_id, usage_id)
) WITHOUT ROWID, STRICT;

CREATE UNIQUE INDEX idx_public_sense_memberships_usage
  ON sense_memberships(usage_id);

ALTER TABLE passages ADD COLUMN raw_text TEXT;
ALTER TABLE passages ADD COLUMN heading TEXT;
ALTER TABLE passages ADD COLUMN printed_page_end TEXT;
ALTER TABLE passages ADD COLUMN scan_leaf_end INTEGER
  CHECK (scan_leaf_end IS NULL OR scan_leaf_end >= 0);
ALTER TABLE passages ADD COLUMN alignment_method TEXT
  CHECK (alignment_method IS NULL OR alignment_method IN (
    'FOUR_GRAM', 'INFERRED', 'LEGACY_OFFSET', 'SOURCE_NATIVE', 'UNALIGNED'
  ));
ALTER TABLE passages ADD COLUMN alignment_score REAL
  CHECK (alignment_score IS NULL OR alignment_score >= 0);
ALTER TABLE passages ADD COLUMN chunker_version TEXT;

CREATE INDEX idx_passages_source_offsets
  ON passages(source_id, start_offset, end_offset);

CREATE TABLE passage_builds (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  source_text_sha256 TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  passage_count INTEGER NOT NULL CHECK (passage_count >= 0),
  directly_aligned_count INTEGER NOT NULL CHECK (directly_aligned_count >= 0),
  inferred_count INTEGER NOT NULL CHECK (inferred_count >= 0),
  unaligned_count INTEGER NOT NULL CHECK (unaligned_count >= 0),
  median_alignment_score REAL CHECK (
    median_alignment_score IS NULL OR median_alignment_score >= 0
  ),
  page_map_path TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (source_id, source_text_sha256, chunker_version)
) STRICT;

CREATE INDEX idx_passage_builds_source ON passage_builds(source_id, created_at);

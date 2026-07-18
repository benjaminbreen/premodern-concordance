CREATE TABLE release_metadata (
  id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  source_count INTEGER NOT NULL,
  passage_count INTEGER NOT NULL,
  entry_count INTEGER NOT NULL,
  occurrence_count INTEGER NOT NULL
) STRICT;

CREATE TABLE works (
  id TEXT PRIMARY KEY,
  preferred_title TEXT NOT NULL,
  original_year INTEGER
) STRICT;

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  work_id TEXT NOT NULL REFERENCES works(id),
  title TEXT NOT NULL,
  author TEXT,
  publication_year INTEGER NOT NULL,
  original_year INTEGER,
  language_code TEXT NOT NULL,
  language_label TEXT NOT NULL,
  edition_statement TEXT,
  citation_text TEXT NOT NULL,
  archive_provider TEXT,
  archive_url TEXT NOT NULL,
  word_count INTEGER,
  origin_system TEXT,
  origin_id TEXT,
  origin_release_id TEXT
) STRICT;

CREATE INDEX idx_public_sources_year ON sources(publication_year);

CREATE TABLE passages (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  sequence INTEGER NOT NULL,
  start_offset INTEGER,
  end_offset INTEGER,
  printed_page TEXT,
  scan_leaf INTEGER,
  display_text TEXT NOT NULL,
  scan_url TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED')),
  UNIQUE (source_id, sequence)
) STRICT;

CREATE INDEX idx_public_passages_source ON passages(source_id, sequence);

CREATE TABLE entries (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  preferred_label TEXT NOT NULL,
  kind TEXT NOT NULL,
  scope_note TEXT NOT NULL,
  exclusions_note TEXT,
  external_ids_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED')),
  source_count INTEGER NOT NULL,
  passage_count INTEGER NOT NULL,
  earliest_year INTEGER,
  latest_year INTEGER
) STRICT;

CREATE TABLE term_forms (
  id TEXT PRIMARY KEY,
  display_form TEXT NOT NULL,
  normalized_form TEXT NOT NULL,
  language_code TEXT,
  earliest_year INTEGER,
  latest_year INTEGER,
  notes TEXT
) STRICT;

CREATE TABLE entry_term_links (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id),
  term_form_id TEXT NOT NULL REFERENCES term_forms(id),
  relation_type TEXT NOT NULL,
  rationale TEXT,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED')),
  confidence REAL
) STRICT;

CREATE INDEX idx_public_term_links_entry ON entry_term_links(entry_id);

CREATE TABLE occurrences (
  id TEXT PRIMARY KEY,
  passage_id TEXT NOT NULL REFERENCES passages(id),
  entry_id TEXT NOT NULL REFERENCES entries(id),
  term_form_id TEXT REFERENCES term_forms(id),
  surface_form TEXT NOT NULL,
  start_in_passage INTEGER,
  end_in_passage INTEGER,
  resolution_method TEXT NOT NULL,
  confidence REAL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE INDEX idx_public_occurrences_entry ON occurrences(entry_id, status);
CREATE INDEX idx_public_occurrences_passage ON occurrences(passage_id);

CREATE TABLE entry_relations (
  id TEXT PRIMARY KEY,
  source_entry_id TEXT NOT NULL REFERENCES entries(id),
  target_entry_id TEXT NOT NULL REFERENCES entries(id),
  layer TEXT NOT NULL CHECK (layer IN ('PRECISE', 'EXPLORATORY')),
  relation_type TEXT NOT NULL,
  rationale TEXT NOT NULL,
  non_claim TEXT,
  confidence REAL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE TABLE relation_evidence (
  relation_id TEXT NOT NULL REFERENCES entry_relations(id),
  passage_id TEXT NOT NULL REFERENCES passages(id),
  note TEXT,
  PRIMARY KEY (relation_id, passage_id)
) WITHOUT ROWID, STRICT;

CREATE TABLE supporting_entities (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  preferred_label TEXT NOT NULL,
  kind TEXT NOT NULL,
  description TEXT,
  external_ids_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE TABLE supporting_mentions (
  id TEXT PRIMARY KEY,
  supporting_entity_id TEXT NOT NULL REFERENCES supporting_entities(id),
  passage_id TEXT NOT NULL REFERENCES passages(id),
  surface_form TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CORE', 'SUGGESTED'))
) STRICT;

CREATE VIRTUAL TABLE entry_search USING fts5(
  entry_id UNINDEXED,
  slug UNINDEXED,
  preferred_label,
  term_label,
  scope_note,
  tokenize = 'unicode61 remove_diacritics 2'
);

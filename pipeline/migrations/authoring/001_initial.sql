CREATE TABLE works (
  id TEXT PRIMARY KEY,
  preferred_title TEXT NOT NULL,
  original_year INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
  publisher TEXT,
  publication_place TEXT,
  citation_text TEXT NOT NULL,
  archive_provider TEXT,
  archive_item_id TEXT,
  archive_url TEXT NOT NULL,
  rights_status TEXT NOT NULL DEFAULT 'UNKNOWN'
    CHECK (rights_status IN ('PUBLIC_DOMAIN', 'LICENSED', 'UNKNOWN', 'RESTRICTED')),
  text_path TEXT,
  text_sha256 TEXT,
  word_count INTEGER CHECK (word_count IS NULL OR word_count >= 0),
  origin_system TEXT,
  origin_id TEXT,
  origin_release_id TEXT,
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'READY', 'PUBLISHED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE passages (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL CHECK (sequence >= 0),
  start_offset INTEGER CHECK (start_offset IS NULL OR start_offset >= 0),
  end_offset INTEGER CHECK (end_offset IS NULL OR end_offset >= 0),
  printed_page TEXT,
  scan_leaf INTEGER CHECK (scan_leaf IS NULL OR scan_leaf >= 0),
  display_text TEXT NOT NULL,
  search_text TEXT NOT NULL,
  scan_url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (source_id, sequence)
) STRICT;

CREATE TABLE entries (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  preferred_label TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN (
    'ORGANISM_TAXON', 'SUBSTANCE_MATERIAL', 'DISEASE_CONDITION', 'ANATOMY',
    'PRACTICE_METHOD', 'ROLE_OCCUPATION', 'CONCEPT_THEORY',
    'PHENOMENON_PROCESS', 'OBJECT_INSTRUMENT'
  )),
  scope_note TEXT NOT NULL,
  exclusions_note TEXT,
  external_ids_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE term_forms (
  id TEXT PRIMARY KEY,
  display_form TEXT NOT NULL,
  normalized_form TEXT NOT NULL,
  language_code TEXT,
  earliest_year INTEGER,
  latest_year INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX idx_term_forms_normalized ON term_forms(normalized_form);

CREATE TABLE entry_term_links (
  id TEXT PRIMARY KEY,
  entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  term_form_id TEXT NOT NULL REFERENCES term_forms(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL CHECK (relation_type IN (
    'PREFERRED_LABEL', 'ORTHOGRAPHIC_VARIANT', 'TRANSLATION', 'HISTORICAL_LABEL',
    'TAXONOMIC_SYNONYM', 'TRADE_NAME', 'DERIVED_FORM', 'CONTESTED_LABEL'
  )),
  rationale TEXT,
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (entry_id, term_form_id, relation_type)
) STRICT;

CREATE TABLE model_runs (
  id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  provider TEXT NOT NULL,
  model_snapshot TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  input_sha256 TEXT NOT NULL,
  output_sha256 TEXT,
  input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens >= 0),
  cost_usd REAL CHECK (cost_usd IS NULL OR cost_usd >= 0),
  status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETE', 'FAILED')),
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
) STRICT;

CREATE TABLE occurrences (
  id TEXT PRIMARY KEY,
  passage_id TEXT NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
  entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  term_form_id TEXT REFERENCES term_forms(id),
  surface_form TEXT NOT NULL,
  start_in_passage INTEGER CHECK (start_in_passage IS NULL OR start_in_passage >= 0),
  end_in_passage INTEGER CHECK (end_in_passage IS NULL OR end_in_passage >= 0),
  resolution_method TEXT NOT NULL CHECK (resolution_method IN (
    'EDITORIAL', 'EXACT', 'NORMALIZED', 'EMBEDDING', 'MODEL', 'LEGACY_IMPORT'
  )),
  confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  model_run_id TEXT REFERENCES model_runs(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX idx_occurrences_entry ON occurrences(entry_id, status);
CREATE INDEX idx_occurrences_passage ON occurrences(passage_id);

CREATE TABLE entry_relations (
  id TEXT PRIMARY KEY,
  source_entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  target_entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  layer TEXT NOT NULL CHECK (layer IN ('PRECISE', 'EXPLORATORY')),
  relation_type TEXT NOT NULL CHECK (relation_type IN (
    'PREPARATION_OF', 'BROADER_THAN', 'NARROWER_THAN', 'PART_OF',
    'CONTESTED_IDENTITY', 'INFLUENCE', 'SHARED_PROBLEM', 'FUNCTIONAL_ANALOGY',
    'LATER_REFRAMING', 'CONTRAST'
  )),
  rationale TEXT NOT NULL,
  non_claim TEXT,
  confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED')),
  model_run_id TEXT REFERENCES model_runs(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (source_entry_id <> target_entry_id),
  UNIQUE (source_entry_id, target_entry_id, relation_type)
) STRICT;

CREATE TABLE relation_evidence (
  relation_id TEXT NOT NULL REFERENCES entry_relations(id) ON DELETE CASCADE,
  passage_id TEXT NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
  note TEXT,
  PRIMARY KEY (relation_id, passage_id)
) WITHOUT ROWID, STRICT;

CREATE TABLE supporting_entities (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  preferred_label TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('PERSON', 'PLACE', 'WORK', 'INSTITUTION')),
  description TEXT,
  external_ids_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED'))
) STRICT;

CREATE TABLE supporting_mentions (
  id TEXT PRIMARY KEY,
  supporting_entity_id TEXT NOT NULL REFERENCES supporting_entities(id) ON DELETE CASCADE,
  passage_id TEXT NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
  surface_form TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PRIVATE'
    CHECK (status IN ('CORE', 'SUGGESTED', 'PRIVATE', 'REJECTED'))
) STRICT;

CREATE TABLE review_decisions (
  id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL CHECK (subject_type IN (
    'ENTRY', 'TERM_LINK', 'OCCURRENCE', 'RELATION', 'PASSAGE', 'SOURCE'
  )),
  subject_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('ACCEPT', 'REJECT', 'RECLASSIFY', 'DEFER')),
  previous_status TEXT,
  resulting_status TEXT,
  reviewer TEXT NOT NULL,
  rationale TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE releases (
  id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  manifest_path TEXT,
  public_db_sha256 TEXT,
  source_count INTEGER NOT NULL DEFAULT 0,
  passage_count INTEGER NOT NULL DEFAULT 0,
  entry_count INTEGER NOT NULL DEFAULT 0,
  occurrence_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('BUILDING', 'VALIDATED', 'PROMOTED', 'FAILED')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  promoted_at TEXT
) STRICT;

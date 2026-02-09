# Entity Registry Schema — Draft for Review

## Design Principles

1. **Every entity is first-class from day one**, regardless of book count. Concordance = `WHERE book_count >= 2`.
2. **Stable slugs** — once assigned, never change. Name can evolve, slug stays.
3. **Extraction is stateless, resolution is separate.** Raw extraction goes into a staging area; a resolver matches against existing entities.
4. **Denormalize for reads.** `book_count` and `total_mentions` live on the entity row to avoid COUNT queries on every page load.
5. **SQLite-compatible** (Turso/libSQL). JSON columns use TEXT with JSON functions.

## Target: Turso (libSQL)

- Local dev: plain `.db` file, no server
- Production: hosted Turso with edge replicas
- Reads are free and fast; writes go through primary

---

## Core Tables (5)

### `books`

```sql
CREATE TABLE books (
  id            TEXT PRIMARY KEY,        -- 'english_physician_1652'
  title         TEXT NOT NULL,
  author        TEXT NOT NULL,
  year          INTEGER NOT NULL,
  language      TEXT NOT NULL,
  description   TEXT,
  cover_path    TEXT,                    -- '/images/covers/culpeper.png'
  text_path     TEXT,                    -- '/texts/english_physician_1652.txt'
  entity_count  INTEGER DEFAULT 0,      -- denormalized
  created_at    TEXT DEFAULT (datetime('now'))
);
```

### `entities`

The canonical global entity. One row per real-world thing (Francis Galton, mercury the element, Goa the city).

```sql
CREATE TABLE entities (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  slug            TEXT UNIQUE NOT NULL,    -- 'francis-galton' (stable, never changes)
  canonical_name  TEXT NOT NULL,           -- 'Francis Galton'
  category        TEXT NOT NULL,           -- 'PERSON'
  subcategory     TEXT,                    -- 'scholar'

  -- Profile / enrichment
  wikidata_id         TEXT,               -- 'Q180970'
  wikipedia_url       TEXT,
  wikipedia_summary   TEXT,               -- 2-3 paragraphs, cached
  thumbnail_path      TEXT,               -- local cached image path
  portrait_url        TEXT,               -- original remote URL

  -- Domain-specific ground truth
  modern_name     TEXT,                   -- resolved modern equivalent
  linnaean        TEXT,                   -- 'Cinchona officinalis' (plants/animals)
  family          TEXT,                   -- taxonomic family
  country         TEXT,                   -- for places
  birth_year      INTEGER,               -- for persons
  death_year      INTEGER,               -- for persons
  confidence      TEXT CHECK(confidence IN ('high','medium','low')),
  description     TEXT,                   -- semantic gloss

  -- Denormalized stats (updated by triggers or migration script)
  book_count      INTEGER DEFAULT 0,
  total_mentions  INTEGER DEFAULT 0,

  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);
```

**Slug generation rule:** `slugify(canonical_name)`. On collision, append category: `mercury-substance` vs `mercury-place`. On further collision, append numeric suffix.

### `attestations`

An entity's appearance in a specific book. This is where per-book names, counts, and variants live.

```sql
CREATE TABLE attestations (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  local_name      TEXT NOT NULL,          -- 'Galton' (name as it appears in this book)
  local_entity_id TEXT,                   -- original ID from *_entities.json
  count           INTEGER DEFAULT 0,      -- mention count in this book
  variants        TEXT,                   -- JSON array: ["Galton", "Mr. Galton"]
  contexts        TEXT,                   -- JSON array: ["scientist who...", ...]

  -- Resolution metadata
  match_score     REAL,                   -- confidence of the entity match (0-1)
  match_method    TEXT,                   -- 'exact', 'embedding', 'manual', 'singleton'

  UNIQUE(entity_id, book_id),            -- one attestation per entity per book
  UNIQUE(book_id, local_entity_id)       -- one global entity per local entity
);
```

### `mentions`

Individual text occurrences. Only populated for books where we have excerpt data.

```sql
CREATE TABLE mentions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  attestation_id  INTEGER NOT NULL REFERENCES attestations(id) ON DELETE CASCADE,
  offset          INTEGER,                -- character offset in source text
  matched_term    TEXT,                   -- exact string matched
  excerpt         TEXT                    -- ~200 char surrounding context
);
```

### `entity_links`

Typed relationships between entities. Replaces current `cross_references` array on concordance clusters.

```sql
CREATE TABLE entity_links (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  source_entity_id  INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  target_entity_id  INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  link_type         TEXT NOT NULL,        -- see Link Types below
  confidence        REAL,
  evidence_snippet  TEXT,                 -- short quote supporting the link
  source_book_id    TEXT REFERENCES books(id),  -- which book the link was found in

  UNIQUE(source_entity_id, target_entity_id, link_type)
);
```

**Link types** (from your existing synonym chain work):
- `same_referent` — true synonyms across languages (eau = water)
- `cross_linguistic` — same concept, different languages
- `derived_from` — Galtonian derived from Galton
- `part_of` — anatomical/compositional
- `ingredient_of` — recipe/compound relationships
- `therapeutic_for` — substance treats disease
- `associated_with` — looser thematic connection

---

## Staging Table (1) — for ingestion pipeline

### `pending_entities`

Raw extraction output before resolution. Resolver reads from here, creates entities + attestations, then deletes the row (or marks it resolved).

```sql
CREATE TABLE pending_entities (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id         TEXT NOT NULL REFERENCES books(id),
  local_entity_id TEXT NOT NULL,
  name            TEXT NOT NULL,
  category        TEXT NOT NULL,
  subcategory     TEXT,
  count           INTEGER DEFAULT 0,
  variants        TEXT,                   -- JSON array
  contexts        TEXT,                   -- JSON array
  mentions        TEXT,                   -- JSON array of {offset, matched_term, excerpt}

  -- Resolution status
  resolved_entity_id  INTEGER REFERENCES entities(id),
  status          TEXT DEFAULT 'pending'
                  CHECK(status IN ('pending', 'auto_matched', 'review', 'resolved', 'new_entity')),
  match_score     REAL,
  reviewed_at     TEXT,

  UNIQUE(book_id, local_entity_id)
);
```

---

## Indexes

```sql
-- Entity lookups
CREATE INDEX idx_entities_slug ON entities(slug);
CREATE INDEX idx_entities_category ON entities(category);
CREATE INDEX idx_entities_book_count ON entities(book_count);
CREATE INDEX idx_entities_canonical ON entities(canonical_name);

-- Attestation lookups
CREATE INDEX idx_attestations_entity ON attestations(entity_id);
CREATE INDEX idx_attestations_book ON attestations(book_id);
CREATE INDEX idx_attestations_name ON attestations(local_name);

-- Mention lookups
CREATE INDEX idx_mentions_attestation ON mentions(attestation_id);

-- Link lookups
CREATE INDEX idx_links_source ON entity_links(source_entity_id);
CREATE INDEX idx_links_target ON entity_links(target_entity_id);
CREATE INDEX idx_links_type ON entity_links(link_type);

-- Pending entity lookups
CREATE INDEX idx_pending_book ON pending_entities(book_id);
CREATE INDEX idx_pending_status ON pending_entities(status);
```

---

## Key Queries the App Needs

```sql
-- Search: find entities by name (text search, augmented by embeddings externally)
SELECT id, slug, canonical_name, category, book_count, total_mentions,
       thumbnail_path, wikipedia_summary
FROM entities
WHERE canonical_name LIKE '%galton%' OR id IN (
  SELECT entity_id FROM attestations WHERE local_name LIKE '%galton%'
)
ORDER BY total_mentions DESC;

-- Entity page: canonical info + all attestations
SELECT e.*, a.local_name, a.count, a.variants, a.contexts, b.title, b.year, b.language
FROM entities e
JOIN attestations a ON a.entity_id = e.id
JOIN books b ON b.id = a.book_id
WHERE e.slug = 'francis-galton'
ORDER BY b.year;

-- Book entity list: all entities in a book
SELECT e.slug, e.canonical_name, e.category, a.local_name, a.count
FROM attestations a
JOIN entities e ON e.id = a.entity_id
WHERE a.book_id = 'principles_of_psychology_james_1890'
ORDER BY a.count DESC;

-- Concordance view: entities in 2+ books
SELECT id, slug, canonical_name, category, book_count, total_mentions
FROM entities
WHERE book_count >= 2
ORDER BY book_count DESC, total_mentions DESC;

-- Entity links (cross-references)
SELECT el.link_type, el.confidence, el.evidence_snippet,
       t.slug, t.canonical_name, t.category
FROM entity_links el
JOIN entities t ON t.id = el.target_entity_id
WHERE el.source_entity_id = 42;
```

---

## Embeddings / Vector Search

Turso doesn't have native vector support yet. Two options:

**Option A (recommended for now):** Keep a companion `search_embeddings.json` file, generated at build time from the `entities` table. Use the existing client-side cosine similarity search. At 500 books / ~50K canonical entities this is ~100MB — still feasible as a static asset with lazy loading.

**Option B (later):** Use Turso's experimental vector extension, or add a pgvector column if you migrate to Postgres. This becomes necessary once you're past ~100K entities.

---

## Migration from Current Data

The migration script (`scripts/migrate_to_db.py`) would:

1. Read all `*_entities.json` → populate `books`, `pending_entities`
2. Read `concordance.json` → create `entities` for each cluster, `attestations` for each member, `entity_links` for cross_references
3. For entities NOT in concordance (single-book) → create singleton `entities` + `attestations`
4. Read `person_identities.json` → populate `wikidata_id`, `wikipedia_url`, `thumbnail_path` on `entities`
5. Read mention data → populate `mentions`
6. Compute `book_count` and `total_mentions` on `entities`

---

## Galton Lifecycle Example

**Day 1 (now, 8 books):**
- Migration creates `entities` row: `{id: 4201, slug: 'galton', canonical_name: 'Galton', category: 'PERSON', book_count: 1}`
- One `attestations` row: `{entity_id: 4201, book_id: 'principles_of_psychology_james_1890', local_name: 'Galton', count: 9}`
- Searchable immediately. Page at `/entity/galton`.

**Day N (book 47 added, mentions Galton):**
- Extraction creates `pending_entities` row for "Mr. Galton" in new book
- Resolver matches against existing entity 4201 (embedding + string + category)
- New `attestations` row links to same entity
- `book_count` updated to 2
- Entity now appears in concordance view automatically
- Same URL: `/entity/galton`. Nothing breaks.

---

## What This Schema Does NOT Include (defer to later)

- `slug_history` — add when you first need to rename a slug
- `review_queue` as separate table — `pending_entities.status = 'review'` covers this for now
- `entity_aliases` as separate table — `attestations.variants` covers this; extract to its own table when you need full-text alias search across books
- User/auth tables — not needed until multi-user
- Audit/provenance logging — add when you have multiple contributors

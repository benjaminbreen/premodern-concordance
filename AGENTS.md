# AGENTS.md

Project overview

This project proposes historical typed entity resolution: linking entity mentions across languages and centuries while preserving the reason for the link (orthographic variant, same referent, conceptual overlap, derivation, contested identity). The goal is to move beyond keyword search in early modern scientific and medical texts, where terminology is unstable, by building a cross‑linguistic concordance that supports historical research on knowledge circulation and also creates AI benchmarks for similarity with explicit link types.

Core objectives

1. Build a multilingual corpus and entity vocabulary from early modern sources (seeded indices, LLM extraction, and historian curation).
2. Detect entity mentions and embed them with a fine‑tuned multilingual model to retrieve candidate matches.
3. Use a two‑stage pipeline: high‑confidence auto‑accept, low‑confidence auto‑reject, and LLM review for uncertain cases.
4. Produce a typed annotation schema and benchmarks that test whether models can distinguish *why* terms are linked, and whether explanations are correct.
5. Release a cross‑linguistic concordance and associated datasets/models for humanities and AI research.

Planned deliverables

1. Cross‑linguistic concordance of early modern natural knowledge (gold‑standard set plus model‑generated extensions).
2. Fine‑tuned multilingual embedding model and evaluation scripts.
3. Benchmark datasets for typed similarity and explanation correctness.
4. Transfer pilot in a related domain (e.g., historical patents) to test generalizability.
5. Publications across humanities, NLP, and interdisciplinary venues.

Key risks and mitigation (proposed)

1. Hard negatives clustering with true matches: use hard‑negative mining, margin losses, and calibrated thresholds by link type.
2. Annotation bottlenecks: focus on high‑value entities, bootstrap with LLM extraction, and iterate with historian review.
3. Reproducibility and scale: report pipeline‑level metrics, stratified evaluation by link type, and clear release plan for derived data.

Primary value proposition

For humanities: a searchable, cross‑lingual concordance enabling new research on knowledge circulation, contested identifications, and non‑European contributions.

For AI: benchmarks and methods for typed similarity learning and explanation correctness in historically unstable terminology.

---

## Scaling Strategy

See [futureworkflow.md](futureworkflow.md) for a detailed plan on scaling from 4 books to 5,000+, covering:
- Entity convergence projections (why 5,000 books doesn't mean 5,000x entities)
- Tiered entity model (specific referents vs. domain concepts vs. generic vocabulary)
- UI redesign from browsable list to search engine with entity profile pages
- Architecture migration path (JSON → SQLite → PostgreSQL + pgvector)
- Concrete use cases for botanists, medical historians, pharmacologists, linguists
- Phased implementation roadmap

---

## Technical Architecture: Fine-Tuning vs. API Strategy

### The Economics Reality

Entity extraction costs with commercial APIs are now low enough that fine-tuning small models for this task doesn't make economic sense at typical grant scales:

| Scale | Gemini 2.5 Flash Lite cost | Fine-tune justified? |
|-------|---------------------------|----------------------|
| 500 books | ~$5-10 | No |
| 5,000 books | ~$50-100 | Marginal |
| 50,000 books | ~$500-1,000 | Maybe |

### Where Fine-Tuning Makes Sense

Fine-tuning open-source models is valuable for tasks that run frequently at runtime, require instant responses, or benefit from domain-specific optimization:

1. **Embedding model (implemented)** — Fine-tuned BGE-M3 for cross-lingual entity matching. Runs thousands of times during user searches; local inference = instant and free at runtime. Handles orthographic variants across languages (bezoar → bezoartica → pedra de porco).

2. **Query understanding (planned)** — Fine-tune a small LLM to interpret scholarly queries ("show me Iberian drug trade references" → structured search parameters). Runs on every user interaction.

3. **Relationship classification (planned)** — Given two entities + context, classify the relationship type (CITES, DISPUTES, DESCRIBES, TRADES, etc.). Simpler than full extraction; small models can handle classification tasks.

4. **OCR correction (potential)** — Fine-tune to fix common early modern OCR errors (ſ→s, ct ligatures, abbreviation marks, etc.).

### Recommended Pipeline Architecture

```
PREPROCESSING (one-time per book):
├── Gemini 2.5 Flash Lite → Entity extraction (~$0.01/book)
│   Returns: JSON array of {name, category, context} for each entity
├── Fine-tuned embeddings → Cross-lingual deduplication (free, local)
│   Clusters variant spellings, links across languages
└── Optional: Relationship extraction pass

RUNTIME (every user query):
├── Fine-tuned query model → Interpret search intent (free, local, instant)
├── Fine-tuned embeddings → Find matching entities (free, local, instant)
└── UI serves pre-computed entity data + relationships
```

### Pilot Results: Qwen3-0.6B Fine-Tuning (February 2026)

Attempted fine-tuning Qwen3-0.6B on 414 training examples (generated by Gemini 2.5 Flash Lite as teacher) for entity extraction. Results on held-out test set:

- **F1 Score: 1.74%** — Model failed to produce valid JSON for 9/10 test examples
- **Conclusion:** 0.6B parameter models lack capacity for structured entity extraction from early modern texts
- **Recommendation:** Use commercial APIs for extraction; reserve fine-tuning for simpler classification and embedding tasks

### Grant Narrative

"We use state-of-the-art commercial LLMs for complex extraction tasks where quality matters, combined with fine-tuned open-source models for runtime inference where speed and cost-at-scale matter. This hybrid approach optimizes for both accuracy in preprocessing and responsiveness in the user-facing concordance."

---

## Progress Update: Cross-Book Matching Pipeline (February 2026)

### Entity Extraction Schema

Implemented an 8-category schema with subcategories for entity extraction (updated February 2026 — PLANT and ANIMAL promoted from SUBSTANCE subcategories to top-level categories):

| Category | Subcategories |
|----------|---------------|
| PERSON | AUTHORITY, SCHOLAR, PRACTITIONER, PATRON, OTHER_PERSON |
| PLANT | HERB, TREE, ROOT, SEED, RESIN, OTHER_PLANT |
| ANIMAL | MAMMAL, BIRD, FISH, INSECT, REPTILE, PRODUCT, OTHER_ANIMAL |
| SUBSTANCE | MINERAL, PREPARATION, ANATOMY, OTHER_SUBSTANCE |
| PLACE | COUNTRY, CITY, REGION, OTHER_PLACE |
| DISEASE | ACUTE, CHRONIC, SYMPTOM, OTHER_DISEASE |
| CONCEPT | THEORY, PRACTICE, QUALITY, OTHER_CONCEPT |
| OBJECT | INSTRUMENT, VESSEL, TOOL, OTHER_OBJECT |

Scripts created:
- `scripts/extract_book_entities.py` — Extracts entities using Gemini 2.5 Flash Lite with the new schema
- `scripts/fix_categories.py` — Normalizes misplaced subcategories to correct top-level categories
- `scripts/match_cross_book_entities.py` — Cross-book entity matching using fine-tuned embeddings

### Cross-Book Matching: Test Results

Tested matching between Semedo (Portuguese, 1741) and Culpeper (English, 1652) entities.

**What works well:**
- Exact matches: Apollo ↔ Apollo (1.000)
- Cross-lingual cognates: Medicina ↔ Medicine (0.988), França ↔ France (0.988)
- OCR variants: Diofcorides ↔ Dioscorides (0.986) — long-s handling
- Semantic matches: agua ↔ Waters (0.982), enfermidade ↔ Disease (0.963)

**Failure modes identified:**

1. **"Attractor" entities** — Certain entities (Avicenna, Julips, Cornhil) match to many unrelated entities because they appear in similar contexts. The model learned "scholars citing other scholars" have similar embeddings regardless of identity.

2. **Broad subcategories** — PREPARATION lumps together bezoar antidotes, juleps, syrups, decoctions. CONCEPT lumps together unrelated abstractions.

3. **False positives at high similarity** — 90+ matches with >0.95 similarity that share no linguistic features (e.g., Caffaneo ↔ Avicenna, afucena ↔ Fennel).

**Root cause:** The embedding model was fine-tuned primarily on medical/substance terminology. It correctly clusters "Medicina/Medicine" but lacks training signal to distinguish individual scholars, places, or concepts.

### Fixes Implemented

1. **String similarity filter for PERSON** — Names must share linguistic features (threshold 0.35)
2. **Higher threshold for PREPARATION** (0.90) and OTHER_CONCEPT (0.92)
3. **One-to-one matching constraint** — Each entity only keeps its single best match, preventing "attractor" entities from matching everything

Results after fixes:
- Matches reduced from 32,246 → 82 (with one-to-one constraint)
- ~16% clearly correct, ~15% clearly incorrect, ~70% need human review
- Many "uncertain" matches are actually correct (e.g., corpo ↔ Body)

### Training Data for Re-Fine-Tuning

Created `data/training_pairs.json` with 347 positive pairs and 63 hard negatives across 6 languages:
- Latin-English (most common in medical texts)
- Portuguese-English (Semedo)
- French-English, German-English, Italian-English, Spanish-English

Coverage by category:
- PERSON: 67 positives, 10 negatives (Galeno↔Galen, Avicena↔Avicenna, etc.)
- SUBSTANCE: 132 positives, 10 negatives (agua↔water, sangue↔blood, etc.)
- PLACE: 81 positives, 9 negatives (Lisboa↔Lisbon, França↔France, etc.)
- CONCEPT: 98 positives, 9 negatives (Medicina↔Medicine, sangria↔bloodletting, etc.)
- DISEASE: 77 positives, 6 negatives (febre↔fever, peste↔plague, etc.)
- OBJECT: 50 positives, 4 negatives (alambique↔alembic, ventosa↔cupping glass, etc.)

Hard negatives include actual false positives from testing (Caffaneo↔Avicenna, vontade↔Vertue, etc.).

### Next Steps

1. ~~Convert training data to triplet format for contrastive learning~~ Done
2. ~~Re-fine-tune BGE-M3 with expanded multilingual training data~~ Done (finetuned-bge-m3-v2)
3. ~~Run full extraction on Semedo (1922 chunks) and Culpeper (409 chunks)~~ Done
4. ~~Evaluate improved model on cross-book matching~~ Done (138 matches, 50 auto-accepted on partial data)
5. Build human review interface for uncertain matches

---

## Concordance: Cluster-Based Cross-Book Entity Resolution

### Core Concept

Every entity from every book lives in a shared embedding space. Entities that refer to the same thing — across languages, centuries, and spelling conventions — cluster together. Each cluster becomes a **concordance entry**: a canonical concept with attestations across multiple books.

```
CONCORDANCE ENTRY: "Galen" (PERSON)
  Description: "Ancient Greek physician (129–216 CE), foundational authority in humoral medicine"
  Attestations:
    ├── Culpeper (English, 1652): "Galen" — 45× — SAME_REFERENT
    ├── Semedo (Portuguese, 1741): "Galeno" — 130× — SAME_REFERENT
    ├── Semedo (Portuguese, 1741): "Galenus" — 93× — ORTHOGRAPHIC_VARIANT
    ├── Semedo (Portuguese, 1741): "Galen" — 218× — SAME_REFERENT
    ├── Da Orta (Portuguese, 1563): "Galeno" — 87× — SAME_REFERENT
    └── Monardes (Spanish, 1574): "Galeno" — 52× — SAME_REFERENT
```

This replaces the pairwise book-matching approach, which doesn't scale and produces redundant entries.

### Link Types (from grant proposal)

Each attestation's relationship to the concordance entry is classified as one of five types:

1. **ORTHOGRAPHIC_VARIANT** — Different spellings of the same word (Diofcorides ↔ Dioscorides, cerebro ↔ cerebrum)
2. **SAME_REFERENT** — Different words across languages pointing to the same thing (Galeno ↔ Galen, água ↔ water)
3. **CONCEPTUAL_OVERLAP** — Related but distinct concepts (sangria ↔ bloodletting, humores ↔ humoral theory)
4. **DERIVATION** — One term derives from or gave rise to another (Latin *febris* → Portuguese *febre* → English *fever*)
5. **CONTESTED_IDENTITY** — Genuinely unclear or historically debated whether these are the same thing (is Monardes's *bálsamo del Perú* the same substance as Culpeper's *Balsam*?)

### Pipeline

#### Step 1: Embed all entities

Embed every entity from every book using the fine-tuned BGE-M3 model. The embedding input combines name, category, and first context:

```
"{entity_name} | {category} | {first_context}"
```

Store all embeddings in a FAISS index alongside entity metadata. This is computed once per entity and persisted to disk.

At current scale (4 books, ~35K entities): a few minutes on CPU.
At target scale (5,000 books, ~25M entities): FAISS handles this fine with an IVF index. Embedding computation is the bottleneck — ~50 hours on GPU, or batched over time as books are added.

#### Step 2: Cluster

For each entity, find its k nearest neighbors (k=10) in the FAISS index above a similarity threshold (0.82). Build a graph where edges connect similar entities. Apply community detection (Louvain algorithm) to find clusters.

**Constraints:**
- Entities must share a top-level category to cluster (PERSON with PERSON, SUBSTANCE with SUBSTANCE). This prevents "Galen" the person from accidentally clustering with a substance that happens to have a similar embedding.
- Within-book entities CAN cluster together — this handles deduplication naturally (Galen/Galeno/Galenus in Semedo → same cluster).
- Minimum similarity for any edge: 0.82. This is deliberately conservative — false merges are worse than false splits for scholarly credibility.

**Why Louvain over simple connected components:** Connected components suffer from "chaining" — if A~B and B~C, they all merge even if A≁C. Louvain finds denser communities and avoids long chains of tenuous connections.

#### Step 3: Classify link types (LLM pass)

For each cluster, send the member entities to Gemini 2.5 Flash Lite:

```
You are classifying relationships in a concordance of early modern scientific texts.

Concordance cluster members:
1. "Galen" (PERSON) — from The English Physician (English, 1652). Context: "Galen describes the virtues of..."
2. "Galeno" (PERSON) — from Polyanthea Medicinal (Portuguese, 1741). Context: "Galeno diz que os humores..."
3. "Galenus" (PERSON) — from Polyanthea Medicinal (Portuguese, 1741). Context: "segundo Galenus no livro..."

For each member, classify its relationship to the cluster concept:
- ORTHOGRAPHIC_VARIANT: different spelling of the same word
- SAME_REFERENT: different word, same thing
- CONCEPTUAL_OVERLAP: related but distinct
- DERIVATION: etymological descent
- CONTESTED_IDENTITY: historically debated equivalence

Return JSON:
{
  "canonical_name": "Galen",
  "description": "Ancient Greek physician...",
  "members": [
    {"index": 1, "link_type": "SAME_REFERENT", "explanation": "English form of the name"},
    {"index": 2, "link_type": "SAME_REFERENT", "explanation": "Portuguese form of Galenus"},
    {"index": 3, "link_type": "ORTHOGRAPHIC_VARIANT", "explanation": "Latin nominative form"}
  ]
}
```

Cost estimate: ~$0.01 per cluster. At 5,000 clusters across 4 books: ~$50. At 100,000 clusters across 5,000 books: ~$1,000 (but spread over years of incremental ingestion).

#### Step 4: Human review

Flag clusters for human review when:
- Any member is classified as CONTESTED_IDENTITY
- Cluster has members with low similarity to centroid (0.82-0.87)
- LLM confidence is low or explanation is uncertain
- Cluster is unusually large (>20 members) — may be over-merged

Provide a review interface where a historian can:
- Confirm or reject cluster membership
- Split over-merged clusters
- Merge under-split clusters
- Override link type classifications

### Incremental Ingestion (adding book #5,001)

When a new book is added:

1. Extract entities (Gemini Flash Lite) — same as now
2. Embed entities (fine-tuned BGE-M3)
3. For each new entity, query FAISS for nearest neighbors above threshold
4. If match found: assign to existing cluster, run LLM link typing on the new member
5. If no match: create a new single-member cluster
6. Update FAISS index with new embeddings

Adding a new book is O(n) where n = number of entities in the new book, regardless of how many books are already in the system. No re-clustering needed.

### Data Model

```sql
-- Concordance clusters
CREATE TABLE clusters (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT NOT NULL,
  category      TEXT NOT NULL,
  description   TEXT,           -- LLM-generated description
  member_count  INTEGER DEFAULT 1,
  book_count    INTEGER DEFAULT 1  -- how many distinct books
);

-- Cluster membership
CREATE TABLE cluster_members (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  cluster_id    INTEGER NOT NULL REFERENCES clusters(id),
  entity_id     TEXT NOT NULL,
  book_id       TEXT NOT NULL,
  entity_name   TEXT NOT NULL,  -- the surface form in this book
  link_type     TEXT NOT NULL,  -- ORTHOGRAPHIC_VARIANT, SAME_REFERENT, etc.
  explanation   TEXT,           -- LLM-generated explanation
  similarity    REAL,           -- cosine similarity to cluster centroid
  status        TEXT DEFAULT 'auto'  -- 'auto', 'confirmed', 'rejected'
);

-- Embeddings stored as binary blobs for FAISS rebuild
CREATE TABLE embeddings (
  entity_id     TEXT PRIMARY KEY,
  book_id       TEXT NOT NULL,
  vector        BLOB NOT NULL   -- float32 array, 1024 dims for BGE-M3
);

CREATE INDEX idx_cluster_members_cluster ON cluster_members(cluster_id);
CREATE INDEX idx_cluster_members_book ON cluster_members(book_id);
CREATE INDEX idx_cluster_members_entity ON cluster_members(entity_id);
CREATE INDEX idx_clusters_category ON clusters(category);
CREATE INDEX idx_clusters_name ON clusters(canonical_name);
```

### Concordance UI

The concordance page shows:

1. **Search bar** — find concordance entries by name, across all books and languages
2. **Filterable table** of concordance entries:
   - Canonical name, category, number of books, total attestations
   - Color-coded book badges showing which books contain this entity
   - Expand to see all attestations with link types
3. **Network view** (optional) — graph showing books as nodes, concordance entries as edges, thickness = number of shared entities
4. **Stats dashboard** — how many shared entities between each book pair, by category, by link type

### Dependencies

- `faiss-cpu` (pip) — fast approximate nearest neighbor search
- `sentence-transformers` (pip) — already installed for BGE-M3
- `python-louvain` or `networkx` (pip) — community detection
- Gemini 2.5 Flash Lite API — link type classification
- `better-sqlite3` (npm) — for serving concordance data to frontend

### File Structure

```
scripts/
  build_concordance.py      -- main pipeline: embed → cluster → classify
  add_book_to_concordance.py -- incremental: add one new book
data/
  concordance.db            -- SQLite database
  embeddings.faiss          -- FAISS index file
  embeddings_meta.json      -- entity ID → index mapping
```

---

## SQLite Migration Plan

### Why

The current architecture serves entity data as static JSON files loaded entirely by the browser. This works for 2-3 books but doesn't scale:

- Semedo's entity file is **50 MB** (105K text excerpts at ~314 chars each)
- Culpeper is 13 MB. Da Orta and Monardes will be 15-30 MB each.
- At 100 books, total JSON could reach several gigabytes
- The browser downloads and parses everything even to display one entity
- Cross-book queries (the concordance) require loading all books into memory

SQLite is the right fix: a single `.db` file, no server, instant queries, and the frontend only receives exactly what it needs.

### Schema

```sql
CREATE TABLE books (
  id          TEXT PRIMARY KEY,   -- e.g. "semedo-polyanthea-1741"
  title       TEXT NOT NULL,
  author      TEXT,
  year        INTEGER,
  language    TEXT,               -- "Portuguese", "English", "Spanish"
  source_file TEXT                -- original text filename
);

CREATE TABLE entities (
  id          TEXT PRIMARY KEY,   -- e.g. "sangue"
  book_id     TEXT NOT NULL REFERENCES books(id),
  name        TEXT NOT NULL,
  category    TEXT NOT NULL,      -- PERSON, SUBSTANCE, DISEASE, etc.
  subcategory TEXT,
  count       INTEGER DEFAULT 1,
  contexts    TEXT,               -- JSON array of description strings
  variants    TEXT                -- JSON array of spelling variants
);

CREATE TABLE mentions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  book_id     TEXT NOT NULL REFERENCES books(id),
  offset      INTEGER,           -- char offset in source text
  matched_term TEXT,
  excerpt     TEXT
);

CREATE TABLE concordance (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_a    TEXT NOT NULL,
  book_a      TEXT NOT NULL,
  entity_b    TEXT NOT NULL,
  book_b      TEXT NOT NULL,
  similarity  REAL,
  link_type   TEXT,              -- "same_referent", "orthographic_variant", etc.
  status      TEXT DEFAULT 'pending'
);

CREATE INDEX idx_entities_book ON entities(book_id);
CREATE INDEX idx_entities_category ON entities(book_id, category);
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_mentions_entity ON mentions(entity_id);
CREATE INDEX idx_mentions_book ON mentions(book_id);
CREATE INDEX idx_concordance_entity ON concordance(entity_a);
CREATE INDEX idx_concordance_books ON concordance(book_a, book_b);
```

### API Routes

Replace static JSON fetches with Next.js API routes:

- `GET /api/books` — list of all books with stats
- `GET /api/entities?book={id}&page={n}&limit={n}&category={cat}&search={term}` — paginated entity list
- `GET /api/entity/{id}?book={bookId}` — single entity (no mentions)
- `GET /api/mentions?entity={id}&book={bookId}&page={n}` — paginated mentions for one entity
- `GET /api/concordance?book={id}` or `?entity={id}` — cross-book matches
- `GET /api/search?q={term}` — cross-book entity search

### Migration Steps

1. `npm install better-sqlite3 @types/better-sqlite3`
2. Create `scripts/migrate_to_sqlite.py` — reads existing JSON, inserts into SQLite
3. Create `data/concordance.db` by running migration
4. Create API routes in `web/src/app/api/`
5. Update frontend fetch calls (minimal UI changes)
6. Move large JSON files out of `web/public/data/`

### Dependencies

- `better-sqlite3` (npm) — fast native SQLite for Node.js
- No cloud services, no accounts, no credentials

### Deployment

- **Vercel**: SQLite bundles with serverless functions (up to ~250 MB)
- **Any VPS**: Works perfectly, no size limits
- **Local dev**: Just works

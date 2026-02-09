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
- Architecture migration path (current: cluster-based JSON, planned: Turso/libSQL entity registry, optional later PostgreSQL + pgvector)
- Concrete use cases for botanists, medical historians, pharmacologists, linguists
- Phased implementation roadmap

---

## Planned Work (Later February 2026): Canonical Entity Pages + Database Registry

**Status:** Planned for later in February 2026 (not implemented yet).

### Why this was initiated (Galton example)

Current UX gap:
- Searching for "Galton" in global search returns nothing.
- "Galton" exists only as a book-local page in James (e.g. `/books/principles_of_psychology_james_1890/entity/galton`).
- Concordance/search currently prioritizes cross-book clusters, so single-book entities are hard to discover globally.

Goal:
- Make entities discoverable and stable from day one, even before they appear in multiple books.
- Add richer canonical profiles (e.g. biography panel, thumbnail, category-aware labels) above excerpts.

### Product decision for scale (500-book target)

For now:
- Keep **semantic search** focused on the concordance list (cross-book cluster layer).
- Use **lexical search** (prefix/fuzzy) for broad entity lookup (e.g. typing "GALT" finds "Galton").

This avoids immediate need for vector search across all entities while still supporting large-scale discoverability.

### Architecture plan

1. Introduce a canonical entity registry in a database with stable IDs/slugs (`/entity/[slug]`).
2. Keep existing book-local entity pages for provenance and excerpt context.
3. Model concordance as a **view over canonical entities** (entities with `book_count >= 2`), not a separate ontology.
4. Keep extraction stateless; add a resolver stage that links new local entities to existing canonical entities when confidence is high.

### Galton lifecycle under the new model

1. First mention (James only): create canonical entity "Galton" with one attestation.
2. Later mention in another book: resolver links the new local entity to the same canonical ID.
3. No URL migration or structural rewrite needed; only `book_count` increases and concordance visibility updates automatically.

### Rollout phases (later Feb 2026)

1. **Phase 1:** Core DB + migration from JSON (books, canonical entities, local attestations, mentions, memberships).
2. **Phase 2:** Canonical routes and API (`/entity/[slug]`) + category-aware top panel content.
3. **Phase 3:** Search split (semantic concordance search + lexical entity search).
4. **Phase 4:** Resolver + human review queue for uncertain links.

### Transition rule and non-goals (important)

- **Current production model remains cluster-based** until the migration phases above are completed.
- During transition, cluster pages and book-local entity pages continue to work as-is.
- **Non-goal for this phase:** full semantic vector search over all entities. Full-entity search can remain lexical (prefix/fuzzy).

### Database schema

See [`docs/entity_registry_schema.md`](docs/entity_registry_schema.md) for the full proposed schema (6 tables: `books`, `entities`, `attestations`, `mentions`, `entity_links`, `pending_entities`).

### Hosting decision (current recommendation)

- Start with **Turso/libSQL** for this phase (cost-effective and sufficient for DB-backed canonical pages + lexical entity search).
- Defer PostgreSQL/pgvector migration until/if semantic search over the full entity universe becomes a core requirement.

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

### Expert-Reviewed Membership Decisions (Training Data)

**Location:** `data/training/membership_decisions.jsonl` (491 examples) + `data/training/membership_decisions.csv`

Created by expert review (Opus 4.6 with early modern history domain knowledge) of 491 borderline cluster members — entities flagged by low string similarity to their cluster's canonical name. Each example is a labeled pair: does this member belong in this cluster?

| Verdict | Count | Description |
|---------|-------|-------------|
| KEEP (label=1) | 401 | Member correctly belongs (cross-language translation, variant spelling, descriptive phrase) |
| SPLIT (label=0) | 90 | Member is a genuinely different entity (string-similarity false positive) |

**Pattern breakdown:** 136 phrase matches, 129 cross-language translations, 127 variant spellings, 90 mismatches, 9 subtypes.

**Why this data is valuable for fine-tuning:**

This dataset captures the core challenge of cross-linguistic entity resolution in historical texts: distinguishing true semantic equivalence from superficial string similarity. Standard embedding models fail here because:

1. **String similarity is misleading.** "oolithes" (oolitic limestone) has 0.38 similarity to "olio" (oil) — higher than "azeytes" (oils, Spanish) at 0.00. But azeytes IS oil and oolithes is NOT. A fine-tuned model needs to learn that shared substrings across language boundaries carry different weight than shared substrings within a language.

2. **Context disambiguates.** "Stones" in Culpeper (1652) means kidney stones (= pedras/calculus) while "roches" in Humboldt (1825) means geological rocks. The member context field ("hard concretions in kidneys" vs. "geological formations") is the signal a model should learn to exploit.

3. **Cross-linguistic translation is asymmetric.** "eau" (French) = water is obvious to a multilingual model, but "orraca" (Konkani/Arabic) = arrack ≠ mint requires domain knowledge about early modern trade languages. These hard negatives are exactly what contrastive training needs.

**Recommended fine-tuning approach:**

- **Format:** Convert to triplet format (anchor, positive, negative) where the anchor is the cluster description, positives are KEEP members, and negatives are SPLIT members from the *same cluster* (hard negatives). Where a cluster has no SPLIT members, use SPLIT members from same-category clusters.
- **Model:** Start from BGE-M3 (already multilingual) or `intfloat/multilingual-e5-large`. These handle Latin-script languages well but need tuning for early modern orthography and OCR artifacts.
- **Loss:** MultipleNegativesRankingLoss or TripletLoss with a margin that accounts for the difficulty gradient — "Ozark" in the "Oxus" cluster is an easy negative, while "Coumarouma" in the "Cocomero" cluster is harder.
- **Augmentation:** For each KEEP example, generate OCR-corrupted variants (ſ→s, ligature splitting, random character substitution) as additional positives. For each SPLIT example, find the highest-similarity KEEP member in the same cluster to create maximally contrastive pairs.
- **Evaluation:** Hold out ~10% stratified by pattern type. Key metric is recall@1 for KEEP members while maintaining <5% false acceptance of SPLIT members. The `sim_to_canonical` and `sim_to_modern` scores in the dataset provide a baseline to beat.

### Synonym Chain Detection Training Data

**Location:** `data/training/synonym_chain_examples.jsonl` (75 examples) + `data/training/synonym_chain_examples.csv`

Created by expert curation of second-pass synonym chain extraction results. Each example is a found entity in an excerpt alongside a known entity, labeled with one of 8 relationship types and graduated link strength (0.0–1.0).

| Label | Count | Link Strength | Description |
|-------|-------|---------------|-------------|
| cross_linguistic | 28 | 0.9 | Same entity in different language (cassab = calamus, Zafferano = saffron) |
| true_synonym | 14 | 1.0 | Explicit equivalence claim (pompholige = Spodio, Antimonio = Estibio) |
| ingredient_cooccurrence | 10 | 0.0 | Recipe ingredients listed together — NOT synonyms |
| contested_identity | 7 | 0.7 | Early modern authors debated whether A = B (tabaxir ≟ spodium) |
| subtype_relation | 7 | 0.5 | A is a variety of B (emblic myrobalan ⊂ myrobalan) |
| authority_cooccurrence | 4 | 0.0 | Person names cited together (Galen + Avicenna) — NOT synonyms |
| ocr_noise | 3 | 0.0 | OCR garbage mistakenly extracted as entity |
| generic_term | 2 | 0.0 | Word too generic to be an entity (sale, lattouaro) |

**What this adds beyond membership_decisions.jsonl:**
- **Hard negatives for synonym detection:** ingredient co-occurrences look like synonym chains (both use "o vero", "cioè" markers) but are fundamentally different relationships
- **Graduated link strength:** not binary but 0.0–1.0, capturing the spectrum from true equivalence to contested identity to mere co-occurrence
- **Text excerpts with OCR noise:** real source text with long-s, ligatures, line breaks, allowing models to learn extraction in noisy conditions
- **Expert reasoning:** each example has a 1–3 sentence explanation of WHY the link is/isn't genuine, usable as chain-of-thought training signal

**Combined training corpus:** 566 expert-labeled examples (491 membership + 75 synonym chain)

### Second-Pass Extraction Results

**Location:** `data/synonym_chains/` (4 files)

The second-pass extraction (`scripts/extract_synonym_chains.py`) scanned 1,629 excerpts with synonym chain markers and found 5,384 new entity mentions. Key outputs:

- `findings.json` — all 5,384 entities with metadata
- `cross_cluster_links.json` — 1,690 links between existing clusters (1,323 unique pairs)
- `unmatched_entities.json` — 3,546 entities not yet in concordance
- `summary.csv` — tabular overview

**Caveat:** ~17% of findings are ingredient co-occurrences from recipes, not true synonym chains. The cross_cluster_links should be treated as candidates for human review, not auto-integrated.

### Next Steps

1. ~~Convert training data to triplet format for contrastive learning~~ Done
2. ~~Re-fine-tune BGE-M3 with expanded multilingual training data~~ Done (finetuned-bge-m3-v2)
3. ~~Run full extraction on Semedo (1922 chunks) and Culpeper (409 chunks)~~ Done
4. ~~Evaluate improved model on cross-book matching~~ Done (138 matches, 50 auto-accepted on partial data)
5. ~~Second-pass synonym chain extraction~~ Done (5,384 entities, 1,690 cross-links)
6. Build human review interface for uncertain matches
7. Integrate high-confidence synonym chain links into concordance

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

> **Current production model (as of February 2026).** The app currently runs on the cluster-based schema (`clusters` + `cluster_members` + `embeddings`). A migration to a unified canonical entity registry is planned for later February 2026; see [`docs/entity_registry_schema.md`](docs/entity_registry_schema.md).

### Concordance UI

The concordance page shows:

1. **Search bar** — find concordance entries by name, across all books and languages
2. **Filterable table** of concordance entries:
   - Canonical name, category, number of books, total attestations
   - Color-coded book badges showing which books contain this entity
   - Expand to see all attestations with link types
3. **Network view** (optional) — graph showing books as nodes, concordance entries as edges, thickness = number of shared entities
4. **Stats dashboard** — how many shared entities between each book pair, by category, by link type

---

## Database Migration Plan

> **Planned work (not yet implemented).** Current production still uses static JSON + cluster architecture. The migration target is the canonical entity registry described in the [Planned Work](#planned-work-later-february-2026-canonical-entity-pages--database-registry) section above, hosted on **Turso/libSQL**. See [`docs/entity_registry_schema.md`](docs/entity_registry_schema.md) for the proposed schema.

### Why migrate from JSON

The current architecture serves entity data as static JSON files loaded entirely by the browser. This works at 8 books but doesn't scale to the 500-book target:

- At 100 books, total JSON could reach several gigabytes
- The browser downloads and parses everything even to display one entity
- Cross-book queries require loading all books into memory
- Single-book entities are invisible to search

---

## Data Interoperability & External Access (Feb 2026)

Roadmap for making the concordance machine-readable, AI-accessible, and interoperable with the scholarly linked data web. Ordered by priority and effort.

### JSON-LD (high priority, ~1 afternoon)

Add `@context` to API responses (or static JSON exports) mapping fields to standard vocabularies. Wikidata QIDs already present on many entities make this natural. No data shape changes — just a context header.

```json
{
  "@context": {
    "@vocab": "https://schema.org/",
    "wikidata_id": { "@id": "sameAs", "@type": "@id" },
    "category": "additionalType",
    "canonical_name": "name",
    "members": "hasPart"
  },
  "@type": "DefinedTerm",
  "canonical_name": "Mercury",
  "wikidata_id": "https://www.wikidata.org/entity/Q925"
}
```

Vocabularies: Schema.org for basics, CIDOC-CRM (`crm:E55_Type`, `crm:P1_is_identified_by`) for cultural heritage relationships if granularity needed. Can implement pre-API as a "Download JSON-LD" client-side export button alongside existing CSV/TXT.

### HuggingFace Dataset (high priority, ~1 afternoon)

Publish as `datasets` package. Parquet splits: `clusters`, `members`, `edges`, `books`. One-liner access: `ds = load_dataset("username/premodern-concordance")`. Immediate visibility to ML/NLP researchers. Update on each data release. Include dataset card with schema, citation, license.

### TEI Export (moderate priority, ~1-2 days)

XML export using TEI P5. Category-to-element mapping:

| Category | TEI Element | Key Attributes |
|----------|-------------|----------------|
| PERSON | `<listPerson><person>` | `<persName>`, `@ref` to Wikidata |
| PLACE | `<listPlace><place>` | `<placeName>`, `@ref` to Pelagios gazetteer |
| PLANT/ANIMAL | `<list type="entities"><item>` | `<name>`, `<idno type="Wikidata">`, `<idno type="Linnaean">` |
| SUBSTANCE/OBJECT | `<list type="entities"><item>` | `<name>`, `<idno type="Wikidata">` |
| DISEASE/CONCEPT | `<list type="entities"><item>` | `<term>`, `<gloss>` |

Expose as "Download TEI-XML" button on `/data` page. ~200 lines of export code. Useful when collaborators request it for integration with oXygen, XSLT pipelines, collation tools.

### MCP Server (~200 lines TypeScript)

Model Context Protocol server exposing concordance as AI-agent-accessible tools:

- `search_concordance(query, category?, book?)` — semantic search across clusters
- `get_cluster(id)` — full cluster with members, edges, ground truth
- `list_books()` — corpus metadata
- `get_stats()` — quantitative summary

Any MCP-compatible AI (Claude Code, etc.) can query the concordance mid-conversation. Compelling DH + AI demo. Low effort, high novelty.

### OpenAPI Spec (do alongside API build)

Publish Swagger/OpenAPI 3.0 spec for the REST API. AI coding assistants auto-generate client code from the spec. Even before the full API exists, the spec documents intent and allows tooling.

### DH Network Integrations (longer term)

**Pelagios / Linked Pasts**: Connect PLACE clusters (303 currently) to historical gazetteers via Pelagios network. Established DH infrastructure for geospatial linked data. Adoption = visibility in ancient/early modern DH community.

**Recogito**: Collaborative semantic annotation platform (built on W3C Web Annotation model). If building user annotations, adopt Recogito's data model rather than inventing a new one. Could potentially integrate directly — Recogito supports custom vocabularies.

**IIIF**: Only relevant if adding facsimile page images from source texts. Low priority unless project moves toward digital edition territory.

**Zotero**: Export book metadata as CSL-JSON/BibTeX. Minor feature, trivial to implement.

### For AI Agents / Vibe Coders

Priority order:
1. **HuggingFace dataset** — standard ML ecosystem, `pip install`-able
2. **OpenAPI spec** — AI assistants generate typed clients automatically
3. **MCP server** — direct tool-use from AI coding environments
4. **Stable raw JSON URL** — `/data/concordance.json` already works; just needs schema docs
5. **JSON-LD** — machines parse entity relationships without custom code

### Hosting Context

Current recommendation: **Turso/libSQL** (SQLite-compatible, 9GB free tier, edge replicas). Revisit PostgreSQL + pgvector when/if semantic vector search over the full entity universe becomes a core requirement.

| Books | Est. DB Size | Turso Free Tier (9GB) |
|-------|-------------|----------------------|
| 8 | ~30 MB | Comfortable |
| 50 | ~150 MB | Comfortable |
| 200 | ~500 MB | Comfortable |
| 500 | ~1.5 GB | Comfortable |
| 2,000 | ~5 GB | Comfortable |

Pipeline bottleneck shifts from database to NER/clustering at ~200 books. At 1k+, pairwise entity comparison needs approximate nearest neighbors (FAISS with IVF index) instead of brute-force.

# Scaling the Premodern Concordance: 4 Books to 5,000

## The Core Question

How does a concordance designed for 4 books become useful at 5,000? The answer isn't just "make everything bigger" — the product changes shape. At 4 books, the concordance is a browsable list. At 5,000, it's a search engine for historical science.

---

## 1. Entity Convergence at Scale

The entity count does **not** grow linearly with books. The domain vocabulary of early modern medicine and natural philosophy is finite. At 4 books we have ~943 concordance clusters. At 5,000 books, we'd expect convergence:

| Scale | Estimated unique clusters | Why |
|-------|---------------------------|-----|
| 4 books | ~1,000 | Current state |
| 50 books | ~5,000 | Most common entities already captured |
| 500 books | ~15,000 | Long tail begins: local remedies, obscure figures |
| 5,000 books | ~25,000–30,000 | Plateau. The 5,000th book adds very few new entities |

This convergence works because of the ground truth layer. A cluster isn't just "things with similar embeddings" — it's anchored to a Wikidata ID. *Artemisia absinthium* (Q23485) is the gravitational center, and every spelling variant from every book orbits it: wormwood, absintio, alosna, wermut, assenzio, αψίνθιον. Adding book #4,999 doesn't create a new entity; it adds a new attestation to an existing one.

**Where convergence breaks down:** Generic concepts ("virtues," "nature," "body," "spirit"). These appear in every book and don't resolve to a specific Wikidata entity. They need different treatment (see Tiered Entity Model below).

---

## 2. Tiered Entity Model

Not all entities are equally valuable. The concordance should recognize this explicitly:

### Tier 1: Specific Referents (~15,000 clusters at scale)
- **What:** Named species, named persons, named places, specific diseases, specific substances
- **Characteristics:** Has a Wikidata ID. Resolves to a Wikipedia page. Linnaean binomial for plants. Birth/death dates for persons.
- **Value:** This is the core scholarly product. A botanist searching for *Cinchona* finds every historical reference across the corpus. A medical historian finds every mention of Galen.
- **UI treatment:** Full entity profile pages with search, temporal visualization, geographic heatmap, passage browser.

### Tier 2: Domain Concepts (~3,000–5,000 clusters)
- **What:** Humoral qualities (hot/cold/moist/dry), medical procedures (bloodletting, purging), broad disease categories (fever, plague), theoretical frameworks (sympathies, signatures)
- **Characteristics:** May or may not have a Wikidata ID. Meaning shifts over time. Multiple books disagree about the concept.
- **Value:** Corpus linguistics and intellectual history. Tracking how "melancholy" shifts meaning from 1500 to 1800. Mapping when humoral theory gives way to chemical medicine.
- **UI treatment:** Frequency-over-time charts. Co-occurrence networks. Semantic shift visualization.

### Tier 3: Generic Vocabulary (filter out)
- **What:** "virtues," "nature," "body," "water," "time," "thing"
- **Characteristics:** Appears in >50% of books. No meaningful Wikidata resolution. Confidence: "low."
- **Value:** Potentially useful for corpus-level statistical analysis but actively harmful in the concordance — it's noise that crowds out signal.
- **UI treatment:** Excluded from concordance by default. Available in a "corpus statistics" section if desired.

### How to classify tiers automatically:
- **Tier 1:** Has Wikidata ID + high confidence ground truth + appears in <50% of books
- **Tier 2:** Has Wikidata ID OR domain-specific significance, but high frequency or shifting meaning
- **Tier 3:** No Wikidata ID + low confidence + appears in >50% of books

The `enrich_concordance.py` output already provides most of what's needed: `confidence`, `wikidata_id`, `type`. Add a `tier` field computed from these.

---

## 3. UI at 5,000 Books

The current expandable-card UI works for 4 books but won't work at scale. The product needs to evolve into three connected experiences:

### A. Search Engine (primary entry point)

The landing page is a search box. You type "artemisia" and get:

```
Artemisia absinthium (Asteraceae)                    Q23485
Wormwood · Common wormwood
───────────────────────────────────────────────────
Found in 847 of 5,000 texts (1502–1798)
23 spelling variants across 6 languages
Most common: wormwood (EN), absintio (PT), ajenjo (ES)

[▓▓▓░░░▓▓▓▓▓▓▓▓░░░░░░] frequency by decade, 1500–1800

[View full profile →]
```

Search must work across:
- Historical spellings (absintio, alosna, wermut)
- Modern names (wormwood, Artemisia absinthium)
- Wikidata IDs (Q23485)
- Linnaean binomials

This is possible because the ground truth layer maps all of these to the same cluster.

### B. Entity Profile Page (the research tool)

When a researcher clicks through, they get a rich profile with tabs:

**Overview tab:**
- Modern identification with Wikipedia thumbnail, Linnaean name, Wikidata link
- Confidence level and any notes about contested identification
- Summary statistics: N books, N total mentions, date range, languages

**Temporal tab:**
- Chart: mentions per decade across the corpus
- Overlaid with related entities (does "wormwood" decline as "Artemisia" rises in usage?)
- Notable: first appearance, peak usage, last appearance

**Geographic tab:**
- Heatmap on a historical map showing publication locations where this entity is mentioned most
- Requires: publication place metadata on books (city/country of publication)
- Example: cinnamon mentioned heavily in Lisbon-published texts (Portuguese spice trade) but rarely in English texts before 1600

**Linguistic tab:**
- All variant spellings grouped by language
- Network visualization of which variants cluster together
- Etymology and derivation chains if known

**Passages tab:**
- Paginated list of actual textual excerpts
- Filterable by book, date, language
- Sortable by date (chronological reading of how a term was used)
- This is the "full data" view — the thing that makes the tool citable for scholars

**Co-occurrence tab:**
- What other entities frequently appear alongside this one?
- Network graph of co-occurring entities
- "Books that mention wormwood also frequently mention: fever (78%), Galen (65%), purging (52%)..."

### C. Corpus Overview (discovery)

For users who don't know what they're looking for:
- Category breakdown with clickable sunburst/treemap
- "Most connected entities" — highest cross-book frequency
- Book timeline showing temporal coverage of the corpus
- Network graph of the top 500 entities and their connections
- "Featured clusters" — editorially highlighted interesting findings

---

## 4. Architecture for Scale

### Current (works for 4 books)
```
Static JSON files (concordance.json, *_entities.json)
  → Browser loads everything
  → Client-side search and filtering
```

### Target (works for 5,000 books)
```
PostgreSQL + pgvector (or SQLite + FAISS)
  → API layer (Next.js API routes or separate service)
  → Server-side search, pagination, aggregation
  → Browser receives only what it needs
```

### Key architectural changes:

**1. Database migration** (already planned in agents.md)
- Entity data, mentions, clusters, ground truth all in SQL
- Vector embeddings in pgvector or FAISS index alongside
- Pre-computed aggregates: temporal frequency curves, co-occurrence matrices, geographic distributions

**2. Approximate nearest neighbor search**
- Current all-pairs matching is O(n^2) across books — fine for 4, impossible for 5,000
- FAISS IVF index: O(n log n) for finding similar entities
- Incremental: adding a new book queries the existing index, no full rebuild

**3. Incremental ingestion pipeline**
When adding book #5,001:
1. Extract entities (Gemini Flash Lite) — minutes
2. Embed entities (fine-tuned BGE-M3) — seconds
3. Query FAISS for nearest neighbors — seconds
4. Assign to existing clusters or create new ones — seconds
5. Run ground truth enrichment on new clusters only — seconds
6. Update database — seconds

The cost of adding one book should be approximately constant regardless of corpus size.

**4. Background processing queue**
- Books queued for processing
- Pipeline runs asynchronously
- Status dashboard shows extraction progress
- Webhook or email notification when a book is ready

---

## 5. Concrete Use Cases (for non-technical audiences)

The pitch isn't "we fine-tuned an embedding model." The pitch is what researchers can now do:

### For a botanist:
> "I'm studying the historical distribution of *Cinchona* (quinine). The concordance shows me every reference to quina, quinquina, Peruvian bark, Jesuits' bark, and cascarilla across 5,000 texts in 6 languages — with dates, locations, and the actual passages. I can see that the term first appears in Spanish texts from Lima in the 1630s, spreads to Portuguese texts by the 1650s, and reaches English texts by the 1670s — with the preferred name shifting from 'Jesuits' bark' to 'Peruvian bark' to 'Cinchona' over two centuries."

### For a medical historian:
> "How does the concept of 'melancholy' change between 1500 and 1800? The concordance shows me the shifting co-occurrence network: in 1550, melancholy co-occurs with 'black bile,' 'Saturn,' and 'spleen.' By 1750, it co-occurs with 'nerves,' 'fibres,' and 'digestion.' I can trace the transition from humoral to mechanistic thinking through the changing company a word keeps."

### For a pharmacologist:
> "What substances were historically used to treat malaria-like fevers? I search 'fever' and filter for co-occurring SUBSTANCE entities. The concordance returns: theriac, bezoar stone, Jesuits' bark, mercury, antimony, opium — each with Linnaean names where applicable, Wikidata IDs, and links to the original passages. I can export this as a structured dataset for further analysis."

### For a linguist:
> "Show me all Portuguese-to-English translation pairs for plant names in the corpus. The concordance's cross-lingual matching gives me 400+ paired terms with similarity scores and link types. I can filter for 'contested identity' to find cases where the translation is uncertain — which tells me something about how botanical knowledge was (mis)translated across linguistic boundaries."

---

## 6. What to Build Next (Priority Order)

### Phase 1: Complete the 4-book MVP (current)
- [x] Entity extraction for 4 books
- [x] Within-book deduplication
- [x] Cross-book concordance with embedding matching
- [x] LLM verification of suspicious clusters
- [x] Ground truth enrichment (Wikidata, Linnaean, Wikipedia)
- [ ] Monardes extraction (in progress)
- [ ] Rebuild concordance with 4 books
- [ ] Add link type classification to clusters
- [ ] Implement tier classification (filter out Tier 3 generics)

### Phase 2: Search-first UI
- [ ] Replace browsable list with search-engine interface
- [ ] Entity profile pages with temporal and linguistic tabs
- [ ] SQLite migration for server-side queries
- [ ] Passage browser with pagination and filtering

### Phase 3: Visualization
- [ ] Temporal frequency charts (mentions per decade)
- [ ] Co-occurrence network graphs
- [ ] Geographic heatmap (requires publication place metadata)
- [ ] Corpus overview / discovery page

### Phase 4: Scale the pipeline
- [ ] FAISS index for approximate nearest neighbor
- [ ] Incremental ingestion (add books without re-clustering)
- [ ] Background processing queue
- [ ] Batch ingestion tooling (process 50 books at once)

### Phase 5: 500+ books
- [ ] PostgreSQL + pgvector migration
- [ ] Full-text search (Elasticsearch or Meilisearch)
- [ ] API rate limiting and caching
- [ ] Export functionality (CSV, JSON-LD, BibTeX)
- [ ] Researcher accounts and saved searches

---

## 7. What Not to Build

Some things that sound useful but aren't worth the complexity:

- **Real-time collaborative annotation.** Let historians submit corrections via a simple form/email. Don't build a full annotation platform.
- **Machine translation of passages.** Just link to the source text. Researchers in this field read the languages.
- **AI-generated summaries of entity significance.** Scholars will (rightly) distrust these. Provide the data; let them draw conclusions.
- **Social features.** No comments, no followers, no sharing. This is a reference tool, not a social network.
- **Mobile-first design.** Researchers use this on desktop with multiple tabs open. Responsive is fine; mobile-optimized is wasted effort.

---

## 8. Success Metrics

How to know this is working:

| Metric | 4-book MVP | 500 books | 5,000 books |
|--------|-----------|-----------|-------------|
| Unique clusters | ~1,000 | ~15,000 | ~25,000 |
| With Wikidata ID | ~70% | ~75% | ~80% |
| With Wikipedia link | ~40% | ~50% | ~55% |
| Search → useful result | <2 clicks | <2 clicks | <2 clicks |
| Time to add a book | ~30 min | ~5 min | ~2 min |
| Cited in publications | — | 1–5 | 10+ |

The most important metric is the last one. If historians and scientists cite this tool in their publications, it's working. Everything else is infrastructure.

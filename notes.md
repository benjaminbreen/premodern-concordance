# Premodern Concordance: Embedding Model Evaluation

## Fine-tuned BGE-M3 vs Base Model on Historical Name Variants

**Date:** February 3, 2026
**Test Dataset:** `pilot/semedo_authorities.csv` (90 name variant pairs, 30 historical figures)
**Source:** Authorities cited in João Curvo Semedo's *Polyanthea Medicinal* (1741)

---

## Summary Results

The fine-tuned model dramatically outperforms the base BGE-M3 on cross-linguistic historical name matching.

| Metric | Base BGE-M3 | Fine-tuned | Change |
|--------|-------------|------------|--------|
| Average similarity | 0.664 | 0.924 | **+0.260** |
| Pairs ≥ 0.7 threshold | 40.0% (36/90) | 96.7% (87/90) | +56.7% |
| Pairs ≥ 0.8 threshold | 26.7% (24/90) | 91.1% (82/90) | +64.4% |
| Pairs ≥ 0.9 threshold | 12.2% (11/90) | 80.0% (72/90) | +67.8% |

---

## Performance by Link Type

| Link Type | Base Model | Fine-tuned | Δ |
|-----------|------------|------------|---|
| `orthographic_variant` (n=70) | 0.708 | 0.947 | +0.239 |
| `same_referent` (n=20) | 0.513 | 0.844 | +0.331 |

The base model particularly struggles with `same_referent` pairs—cases where the same person is known by completely different names (e.g., Latin scholarly name vs. vernacular birth name). The fine-tuned model shows the largest gains here.

---

## Biggest Improvements from Fine-tuning

These pairs show where the model learned the most:

| Term A | Term B | Base | Fine-tuned | Improvement |
|--------|--------|------|------------|-------------|
| Riverius | Lazzaro Riviera | 0.312 | 0.976 | **+0.664** |
| Sylvius (Dubois) | Giacomo Silvio | 0.316 | 0.936 | **+0.619** |
| Crollius | Osvaldo Crollo | 0.380 | 0.937 | **+0.557** |
| Franciscus Sylvius | Franz de le Boe | 0.395 | 0.931 | **+0.536** |
| Albertus | Alberto Magno | 0.370 | 0.898 | **+0.528** |
| Lullius | Raimondo Lullo | 0.453 | 0.948 | **+0.495** |
| Jacobus Sylvius | Jacques Dubois | 0.414 | 0.909 | **+0.495** |
| Avicenna | Ibn Sina | 0.456 | 0.949 | **+0.493** |
| Guilielmus Harvaeus | William Harvey | 0.438 | 0.931 | **+0.493** |
| Bartholinus | Gaspare Bartolino | 0.511 | 0.990 | **+0.479** |

The model successfully learned:
- Latin abbreviated citation forms (-ius, -us) → vernacular full names
- Cross-linguistic patterns (Latin → Italian, Spanish, French, German)
- Scholarly name conventions of the early modern period

---

## Remaining Hard Cases

### Lowest Similarity Pairs (Fine-tuned Model)

| Term A | Term B | Similarity | Notes |
|--------|--------|------------|-------|
| Aureolus Philippus Theophrastus Bombastus von Hohenheim | Paracelsus | 0.406 | Pseudonym with no lexical overlap |
| Paracelsus | Paracelse | 0.560 | Unexpected regression |
| Abu Ali al-Husayn ibn Abd Allah ibn Sina | Avicenna | 0.679 | Arabic → Latin transliteration |
| Claudius Galenus | Galen | 0.710 | Latin praenomen + nomen → English |
| Rhazes | Abu Bakr Muhammad ibn Zakariya al-Razi | 0.736 | Arabic → Latin |

### Analysis of Hard Cases

1. **The Paracelsus Problem:** The connection between "Aureolus Philippus Theophrastus Bombastus von Hohenheim" and his self-chosen name "Paracelsus" requires biographical knowledge—there is zero lexical overlap. This is a fundamental limitation of embedding-based approaches.

2. **Arabic-Latin Transliterations:** Pairs involving Arabic names (Ibn Sina, al-Razi, ibn Masawaih) score lower than intra-European variants. The Latinized forms (Avicenna, Rhazes, Mesue) bear little resemblance to the Arabic originals.

3. **Unexpected Regression:** `Paracelsus → Paracelse` dropped from 0.718 to 0.560 after fine-tuning. This may indicate slight overfitting to patterns where French forms differed more substantially from Latin.

---

## One Regression Case

| Pair | Base | Fine-tuned | Change |
|------|------|------------|--------|
| Van Helmont ↔ Jean Baptiste van Helmont | 0.824 | 0.824 | ~0 |
| Paracelsus ↔ Paracelse | 0.718 | 0.560 | **-0.158** |

The Paracelsus/Paracelse regression is notable and suggests the model may have learned some spurious patterns. Worth investigating with additional French examples.

---

## Assessment

### What the Fine-tuning Achieved

1. **Learned Latin scholarly name conventions:** The model now understands that -ius/-us endings in Latin names correspond to -o/-e endings in Italian, and similar patterns across Romance languages.

2. **Handles abbreviated citations:** Citation forms like "Lemery," "Sylvius," "Fernelius" are now correctly matched to full names across languages.

3. **Cross-linguistic competence:** Strong performance on Latin ↔ Italian, Latin ↔ French, Latin ↔ German, and Latin ↔ Spanish pairs.

4. **Robust threshold behavior:** At a 0.7 threshold, the fine-tuned model achieves 96.7% recall vs. 40% for the base model.

### Limitations

1. **Pseudonyms and radical name changes** cannot be captured by embedding similarity alone. Cases like Paracelsus require external knowledge.

2. **Arabic/Persian ↔ Latin pairs** remain challenging. The training data may need more examples from Islamic scholarly traditions.

3. **Possible overfitting** on some patterns, as evidenced by the Paracelse regression.

4. **No negative examples tested:** This evaluation only includes true matches. Need to test against hard negatives (different people with similar names) to assess precision.

---

## Recommendations

1. **Deploy the fine-tuned model** for the concordance pipeline—it's clearly superior for this domain.

2. **Supplement with lookup table** for known pseudonym cases (Paracelsus, Avicenna, etc.) where embedding similarity is insufficient.

3. **Add LLM verification step** for borderline cases (similarity 0.5-0.75) to catch both false positives and false negatives.

4. **Expand training data** with:
   - More Arabic/Persian scholarly names
   - Greek → Latin transliterations
   - Medieval vs. early modern name variants
   - Hard negatives (different people, similar names)

5. **Investigate French patterns** to understand the Paracelse regression.

---

## Files

- **Model:** `models/finetuned-bge-m3-premodern/`
- **Test data:** `pilot/semedo_authorities.csv`
- **Results:** `pilot/semedo_embedding_comparison.csv`
- **Test script:** `pilot/test_semedo_authorities.py`

---

# Entity Extraction Pipeline

## Overview

A pipeline to automatically extract named entities (persons, substances, concepts) from early modern texts and deduplicate them using the fine-tuned embedding model.

**Goal:** Process 500+ books, extracting 300-400 significant entities per book, with automatic deduplication so that "ambar Gris," "ambergris," and "Ambra grisea" all resolve to the same canonical entity.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT                                        │
│  PDF → pdftotext → raw .txt file                                    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      1. CHUNKING                                     │
│  Split text into ~3000 char chunks with overlap                      │
│  Break at paragraph/sentence boundaries                              │
│  For Polyanthea: ~1400 chunks                                        │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      2. LLM EXTRACTION                               │
│  Model: llama3.1:8b via ollama (local, free)                        │
│  For each chunk, extract:                                            │
│    - name: as it appears in text                                     │
│    - category: PERSON | SUBSTANCE | CONCEPT                          │
│    - context: brief description                                      │
│  Output: JSON array of entities per chunk                            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   3. RAW AGGREGATION                                 │
│  Collect all extractions across chunks                               │
│  Expected: thousands of raw mentions with many duplicates            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│               4. EMBEDDING-BASED DEDUPLICATION                       │
│  Model: finetuned-bge-m3-premodern                                  │
│  Embed all unique surface forms                                      │
│  Cluster using agglomerative clustering (threshold: 0.82)           │
│  Pick canonical name per cluster (most frequent)                     │
│  Preserve variants list                                              │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        OUTPUT                                        │
│  CSV with columns:                                                   │
│    - canonical_name: primary name for entity                         │
│    - category: PERSON | SUBSTANCE | CONCEPT                          │
│    - variants: semicolon-separated alternate spellings               │
│    - count: total mentions across all chunks                         │
│    - chunk_count: number of distinct chunks mentioning entity        │
│    - contexts: sample context phrases                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Why local LLM (ollama) instead of API?

- **Cost**: 500 books × 1400 chunks × $0.01/call = $7,000 via API
- **Speed**: Can parallelize across local GPUs
- **Privacy**: Text never leaves your machine
- **Control**: Can fine-tune extraction model if needed

### Why embedding-based deduplication?

The fine-tuned embedding model already learned that:
- "Galenus" = "Galen" = "Galeno" = "Galien"
- Latin abbreviated forms match full vernacular names
- Cross-linguistic spelling variants cluster together

Using cosine similarity > 0.82 as the clustering threshold captures most true variants while avoiding false merges.

### Why not ask the LLM to deduplicate?

- LLMs have limited context windows (can't see all 1400 chunks at once)
- Embeddings are faster and more consistent
- The fine-tuned model is specifically optimized for this domain

## Usage

```bash
# Single book
python pilot/extract_entities.py --input books/polyanthea_medicinal.txt

# With options
python pilot/extract_entities.py \
    --input books/polyanthea_medicinal.txt \
    --output pilot/polyanthea_entities.csv \
    --model llama3.1:8b \
    --threshold 0.82
```

## Scaling to 500 Books

For batch processing:

1. **PDF extraction**: `pdftotext` in parallel across all PDFs
2. **Entity extraction**: Run multiple ollama instances or queue jobs
3. **Cross-book deduplication**: After per-book extraction, run a second clustering pass across all books to unify entities
4. **Master database**: Build a graph linking entities to books, with frequency and context

## Files

- **Pipeline script:** `pilot/extract_entities.py`
- **Test input:** `books/polyanthea_medicinal.txt`
- **LLM:** `llama3.1:8b` via ollama
- **Embedding model:** `models/finetuned-bge-m3-premodern/`

---

# Concordance at Scale: 500 Books

## Scale Estimates

**Per book (based on Polyanthea Medicinal pilot):**
- ~1500 chunks per book (varies by length)
- ~7 entities extracted per chunk
- ~10,000 raw extractions per book
- After within-book deduplication: **400-800 unique entities per book**

**Across 500 books:**
- 500 × 600 avg = 300,000 total entity mentions (before cross-corpus deduplication)

**After cross-corpus deduplication (realistic):**

| Tier | Description | Estimated Count |
|------|-------------|-----------------|
| Core entities | Appear in 10+ books | 1,000 - 3,000 |
| Common entities | Appear in 3-9 books | 5,000 - 10,000 |
| Long tail | Appear in 1-2 books | 20,000+ |
| **Total unique** | | **~30,000** |

The key insight: most entities repeat across books. Galen, Hippocrates, Dioscorides, rhubarb, theriac, mercury—these appear in virtually every early modern medical text. The long tail consists of local remedies, obscure authorities, and text-specific concepts.

## Managing Scale: Tiered Visibility

The concordance is **not** a flat list of 30,000 items. It's a navigable system with layers:

### Layer 1: Visual Concordance (2,000-5,000 entities)
- Only entities appearing in **5+ books** are visualized
- Node size = frequency (books mentioning it)
- Clustered by co-occurrence and category
- This is what users see and interact with by default

### Layer 2: Searchable Index (all ~30,000 entities)
- Full-text search across all extracted entities
- "Show me all books mentioning [obscure remedy X]"
- Returns list of books + contexts where entity appears
- Not visualized, but accessible

### Layer 3: Per-Book Views
- Drill down into any single book
- See all 400-800 entities from that book
- Highlights which are "core" vs "unique to this text"

## User Interface Approach

```
┌─────────────────────────────────────────────────────────────────────┐
│  PREMODERN CONCORDANCE                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  [Search: _______________]  [Category: All ▼]  [Min books: 5]│   │
│  └─────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│              ┌─────────────────────────────────────┐               │
│              │                                     │               │
│              │     NETWORK VISUALIZATION          │               │
│              │     (2,000-5,000 core entities)    │               │
│              │                                     │               │
│              │   ○ Galen        ○ Hippocrates     │               │
│              │      \          /                   │               │
│              │       ○ Theriac                    │               │
│              │      /    |    \                   │               │
│              │  ○ Opium  ○ Viper  ○ Mercury       │               │
│              │                                     │               │
│              └─────────────────────────────────────┘               │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  SELECTED: Theriac                                                  │
│  Category: SUBSTANCE (preparation)                                  │
│  Appears in: 247 / 500 books                                       │
│  Variants: theriaca, tiriaca, triaca, theriacum                    │
│  Related: Galen, viper, opium, Andromachus, mithridate             │
│  ──────────────────────────────────────────────────────────────    │
│  Sample contexts:                                                   │
│  • "universal antidote against all poisons" (Semedo 1741)          │
│  • "the Venice treacle is most esteemed" (Salmon 1693)             │
│  • "debe tomarse con vino" (Monardes 1574)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Filtering Strategies

**By category:**
- PERSON (~30% of entities): authorities, physicians, translators
- SUBSTANCE (~50%): drugs, plants, minerals, preparations
- CONCEPT (~20%): diseases, theories, procedures

**By time period:**
- Ancient authorities (Galen, Hippocrates, Dioscorides)
- Medieval/Islamic (Avicenna, Rhazes, Mesue)
- Early modern (Paracelsus, Helmont, Sydenham)

**By frequency:**
- Slider: "Show entities appearing in at least [N] books"
- Default: 5 books (shows ~3,000 entities)
- Maximum: 50+ books (shows ~500 "universal" entities)

**By book:**
- Select a specific book to see its entity profile
- Compare two books' entity overlap

## Data Model

```
ENTITIES table:
- id (canonical identifier)
- canonical_name
- category (PERSON | SUBSTANCE | CONCEPT)
- subcategory (optional: medical, alchemical, plant, mineral, etc.)
- variants (JSON array of alternate spellings)
- book_count (number of books mentioning)
- total_mentions (sum across all books)

MENTIONS table:
- entity_id
- book_id
- chunk_id
- context (LLM-generated description)
- raw_name (as it appeared in text)

BOOKS table:
- id
- title
- author
- year
- language
- entity_count

ENTITY_COOCCURRENCE table:
- entity_a_id
- entity_b_id
- cooccurrence_count (books where both appear)
- cooccurrence_strength (normalized)
```

## Processing Pipeline (Full Scale)

```
Phase 1: Extraction (parallelizable)
├── For each of 500 books:
│   ├── PDF → pdftotext → raw .txt
│   ├── Chunk text (~1500 chunks)
│   ├── LLM extraction (llama3.1:8b via ollama)
│   └── Save raw entities to book_entities.json
│
Phase 2: Within-book deduplication
├── For each book:
│   ├── Embed all entity names (fine-tuned BGE-M3)
│   ├── Cluster within category (threshold 0.97)
│   └── Output: deduplicated book_entities_clean.csv
│
Phase 3: Cross-corpus entity resolution
├── Collect all unique entities across 500 books
├── Embed all (~50,000 surface forms)
├── Cluster across corpus (threshold 0.95)
├── Human review of ambiguous clusters
└── Output: master_entities.csv with canonical IDs
│
Phase 4: Build concordance database
├── Assign canonical IDs to all mentions
├── Compute co-occurrence matrix
├── Calculate frequency statistics
└── Export to graph.json for visualization
```

## Estimated Processing Time

| Phase | Per Book | 500 Books | Notes |
|-------|----------|-----------|-------|
| PDF extraction | 30 sec | 4 hours | Parallelizable |
| LLM extraction | 6 hours | 3000 hours | Parallelizable across machines |
| Within-book dedup | 5 min | 42 hours | Parallelizable |
| Cross-corpus resolution | - | 8-12 hours | Single pass |
| Human review | - | 10-20 hours | Spot-check clusters |

**Total: ~2-3 weeks with parallelization, or partner with cloud GPU resources**

## Quality Control

1. **Spot-check extraction**: Manually review 5% of books for missed entities
2. **Review merged clusters**: Flag any cluster with >10 variants for human review
3. **Category validation**: Check that persons aren't labeled as substances
4. **Cross-reference known authorities**: Verify Galen, Hippocrates, etc. are correctly resolved
5. **Iterative refinement**: Use errors to improve prompts and thresholds

## Success Metrics

- **Precision**: >90% of extracted entities are real entities (not OCR garbage)
- **Recall**: >80% of "important" entities captured (based on sample manual review)
- **Resolution accuracy**: >95% of variant clusters are correct (same entity)
- **Coverage**: Core 2,000 entities should include all major authorities, drugs, and concepts from the period

---

# Model Fine-Tuning Workflow (February 2026)

## Goal
Fine-tune a lightweight, fast model for entity extraction from early modern texts, then compare against commercial APIs.

## Models to Test

| Model | Size | Speed | Notes |
|-------|------|-------|-------|
| **Qwen3-0.6B** (fine-tuned) | 0.6B | ~5x faster than 3B | Most tunable per distilabs benchmark |
| Gemini 2.5 Flash Lite | API | Fast | ~$0.02/book, teacher model |
| GPT-5 Nano | API | Fast | ~$0.05/book |

## Workflow

```
Step 1: Generate training data
        - Use Gemini 2.5 Flash Lite as teacher model
        - Label 500 chunks from Semedo + other texts
        - Cost: ~$0.50
        - Output: pilot/entity_training_data.jsonl

Step 2: Fine-tune Qwen3-0.6B
        - Google Colab with free T4 GPU
        - Use Unsloth or HuggingFace PEFT/LoRA
        - Time: ~1-2 hours
        - Output: LoRA adapter weights

Step 3: Compare all three on same test set
        - 20 chunks from Semedo
        - Metrics: entity count, accuracy, speed, cost

Step 4: Scale up winner to full corpus
```

## Why Qwen3-0.6B?

Per [distilabs benchmark](https://www.distillabs.ai/blog/we-benchmarked-12-small-language-models-across-8-tasks-to-find-the-best-base-model-for-fine-tuning):
- High tunability score (improves most after fine-tuning)
- 0.6B params = runs on CPU, very fast inference
- Multilingual including Portuguese
- If insufficient quality, step up to Qwen3-1.7B

## Dutch Language Note

Qwen3 and SmolLM3 don't officially support Dutch, but:
- Include Dutch examples in training data
- German support provides some transfer learning
- Early modern Dutch texts often have Latin passages
- Fine-tuning teaches Dutch patterns even without official support

## Files

- `pilot/generate_training_data.py` - Creates labeled training data using teacher model
- `pilot/extract_entities_multi.py` - Tests multiple providers on same input
- `pilot/entity_training_data.jsonl` - Training data for fine-tuning (generated)
- `models/qwen3-0.6b-entities/` - Fine-tuned model weights (after training)

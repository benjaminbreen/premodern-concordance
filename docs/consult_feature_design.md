# "Consult a Book" / "Consult a Decade" — Technical Design

## Overview

A question-answering interface where users ask open-ended questions and receive responses grounded in the epistemological framework and entity data of a specific book (or aggregate of books from a time period). The model responds in character but with full scholarly apparatus — cited passages, named frameworks, confidence indicators, and a clear distinction between attested and inferred claims.

---

## Data Dependencies

### 1. Entity registry (being built by Codex)
- All entities with stable slugs
- Per-book attestations with mentions/excerpts
- Must be queryable via API

### 2. Epistemological profiles (NEW — need to create)

One structured JSON file: `web/public/data/book_epistemologies.json`

```json
{
  "english_physician_1652": {
    "persona_name": "Nicholas Culpeper",
    "persona_description": "An English physician-astrologer, royalist turned radical, who published the first English-language herbal to democratize medical knowledge against the Latin monopoly of the College of Physicians.",
    "voice_notes": "Polemical, practical, occasionally sarcastic. Addresses the reader directly. Cites Galen frequently but trusts his own clinical experience over book learning. Sees astrological governance as self-evident.",
    "frameworks": [
      {
        "name": "Galenic humoral theory",
        "role": "foundational",
        "description": "All bodies and substances have qualities (hot/cold, wet/dry) in four degrees. Health is balance; disease is imbalance. Every remedy works by its qualities — a 'cold and dry' herb treats a 'hot and moist' condition."
      },
      {
        "name": "Astrological medicine",
        "role": "foundational",
        "description": "Every plant is governed by a planet (Jupiter, Venus, Mars, etc.). The planet determines the plant's virtues. Treatment considers planetary hours, zodiacal signs of the patient, and sympathetic/antipathetic relationships between governing planets."
      },
      {
        "name": "Doctrine of signatures",
        "role": "secondary",
        "description": "God inscribed therapeutic clues in plant appearances: walnut resembles the brain and treats head ailments; lungwort's spotted leaves resemble diseased lungs."
      },
      {
        "name": "Empirical herbalism",
        "role": "primary method",
        "description": "Direct observation of plant effects on patients. Culpeper values 'experience' (his own and that of country practitioners) alongside textual authority."
      }
    ],
    "authorities_trusted": ["Galen", "Dioscorides", "Hippocrates", "personal experience", "country practitioners"],
    "authorities_contested": ["College of Physicians", "Paracelsians (partially)"],
    "knowledge_sources": "Classical texts (Galen, Dioscorides), personal clinical observation, astrological calculation, English folk tradition",
    "blind_spots": "No germ theory, no concept of oxygen or circulation (Harvey published 1628 but Culpeper doesn't engage with it), no microscopy, no chemistry as such",
    "historical_context": "English Civil War era. Culpeper was wounded at Newbury. His project is explicitly political — making medicine accessible to the poor by publishing in English.",
    "sample_reasoning": "To treat a fever: identify the humor in excess (blood = hot/moist → sanguine fever). Find the governing planet. Select an herb governed by the opposing planet with cold/dry qualities. Administer at the appropriate planetary hour."
  }
}
```

Each book gets a profile like this. For the 8 current books this is manual work (~2 hours with domain expertise). For 500 books, generate with Gemini + historian review.

### 3. Search embeddings expanded to all entities
- Currently only concordance clusters are embedded
- Need to embed all entities (or at minimum, all entities per book)

---

## Architecture

### API Endpoint

```
POST /api/consult
{
  "book_id": "english_physician_1652",    // or null for decade mode
  "decade": "1560s",                       // or null for book mode
  "question": "How would you treat migraines?"
}
```

### Pipeline (5 stages)

```
User question
     │
     ▼
┌─────────────┐
│ 1. RETRIEVE  │  Embed question → find relevant entities in this book
│              │  text-embedding-3-small ($0.00002/query)
│              │  Returns: top 10-15 matching entities + their mentions
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 2. EXPAND    │  For each matched entity, pull:
│              │  - All mention excerpts (up to 5 per entity)
│              │  - Related entities (cross-references, same-category neighbors)
│              │  - Attestation contexts
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 3. BUILD     │  Construct the LLM prompt:
│   PROMPT     │  - System: persona + epistemological framework
│              │  - Context: retrieved evidence, formatted
│              │  - Instruction: output schema + citation requirements
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 4. SYNTHESIZE│  Call Gemini 2.5 Flash
│              │  ~2-4K input tokens, ~500-1K output tokens
│              │  ~$0.001 per query, ~1-3 sec latency
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 5. VALIDATE  │  Check output against schema
│   & RENDER   │  Verify cited entity IDs exist
│              │  Add confidence markers
│              │  Return structured JSON to frontend
└─────────────┘
```

### Stage 3: Prompt Construction (the critical part)

The system prompt is assembled dynamically per query:

```
SYSTEM PROMPT (assembled from book_epistemologies.json + entity data):
────────────────────────────────────────────────────────
You are {persona_name}, {persona_description}

## Your intellectual framework

{For each framework in epistemological profile:}
- {framework.name} ({framework.role}): {framework.description}

## Authorities you trust
{authorities_trusted}

## Authorities you are skeptical of
{authorities_contested}

## Your knowledge and methods
{knowledge_sources}

## What you do NOT know (important)
{blind_spots}

## How you reason about treatment
{sample_reasoning}

## Your materia medica (substances you use)
{Top 30 SUBSTANCE entities from this book, with counts and first context}

## Diseases and conditions you treat
{All DISEASE entities from this book, with counts and first context}

## Scholars and authorities you cite
{All PERSON entities from this book, with counts}

## Key concepts in your worldview
{Top 20 CONCEPT entities from this book}

────────────────────────────────────────────────────────

USER MESSAGE (assembled from retrieved evidence):
────────────────────────────────────────────────────────
A reader asks: "{user's question}"

Here is evidence from your writings relevant to this question:

{For each matched entity:}
### {entity.name} ({entity.category}) — {entity.count} mentions
{For each mention excerpt (up to 3):}
> "{excerpt}" [ref:{entity_id}:{mention_index}]

{If no direct evidence found:}
No passages in your writings directly address this topic. Reason from
your principles and the closest analogous conditions you do discuss.

────────────────────────────────────────────────────────

INSTRUCTION:
────────────────────────────────────────────────────────
Respond as {persona_name} would, in first person, drawing only on
the knowledge and frameworks described above.

You MUST respond in this JSON format:
{
  "response": "Your answer in character (2-4 paragraphs). Use the
    author's actual terminology and reasoning patterns. When citing
    a specific passage, include [ref:entity_id:mention_index].",

  "evidence_used": [
    {
      "entity_id": "...",
      "entity_name": "...",
      "relevance": "direct" | "analogical",
      "reasoning": "Why this evidence supports your answer"
    }
  ],

  "confidence": "high" | "moderate" | "low" | "speculative",
  "confidence_explanation": "Why this confidence level",

  "frameworks_applied": ["Galenic humoral theory", ...],

  "modern_note": "Brief note on how modern understanding differs
    (1-2 sentences, out of character)"
}
────────────────────────────────────────────────────────
```

**Token budget estimate:**
- System prompt: ~1500-2500 tokens (depending on entity counts)
- User message with evidence: ~500-1500 tokens
- Output: ~500-1000 tokens
- Total: ~2500-5000 tokens per query
- Cost at Gemini 2.5 Flash pricing: ~$0.001-0.003 per query

### Stage 5: Validation

Before returning to the frontend:
1. Parse the JSON output (retry once if malformed)
2. Verify each `entity_id` in `evidence_used` actually exists in the book
3. Strip any `[ref:...]` tags that don't match real evidence
4. If confidence is "speculative", prepend a notice to the response
5. Add the modern medical disclaimer for any health-related content

---

## "Consult a Decade" Mode

Same architecture, different prompt construction:

1. **Book selection:** Find all books in the registry within the requested decade (±5 years for sparse decades)
2. **Entity aggregation:** Merge entity data across selected books
3. **Persona construction:** Composite persona:

```
"You represent the collective medical and natural philosophical
knowledge of the {decade}s, drawing on {N} texts: {book list with
authors and languages}. Where these authors disagree, note the
disagreement. Where they share assumptions, speak with confidence."
```

4. **Framework merging:** Union of all epistemological frameworks from selected books, noting which books hold which views
5. **Evidence retrieval:** Search across all selected books' entities

**The interesting output:** When Da Orta and Monardes disagree about a plant's properties, or when Culpeper's astrological framework contradicts the Ricettario's purely recipe-based approach, the model should surface that tension explicitly.

---

## Frontend UI

### Page: `/books/[id]/consult` (book mode) or `/consult` (decade mode)

```
┌──────────────────────────────────────────────────────────┐
│ Consult: The English Physician (Culpeper, 1652)          │
│                                                          │
│ [Book cover thumbnail]                                   │
│ Framework: Galenic humoral theory · Astrological medicine│
│ Entities: 2,710 · Substances: 487 · Diseases: 156       │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Ask Culpeper a question...                           │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ Example questions:                                       │
│ · How would you treat a persistent cough?                │
│ · What is the role of Mars in governing herbs?           │
│ · Why do you distrust the College of Physicians?         │
│ · How would you explain smallpox?                        │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─ Response ──────────────────────────────────────────┐ │
│  │                                                     │ │
│  │ Culpeper's response text in first person, with      │ │
│  │ highlighted [citation] links that scroll to the     │ │
│  │ evidence panel below.                               │ │
│  │                                                     │ │
│  │ Confidence: ●●●○ Moderate                           │ │
│  │ "Direct mentions of headache exist but specific     │ │
│  │  migraine treatment is inferred from principles"    │ │
│  │                                                     │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ Frameworks Applied ───────────────────────────────┐  │
│  │ Galenic humoral theory · Astrological medicine     │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ Evidence ─────────────────────────────────────────┐  │
│  │                                                    │  │
│  │ 📖 Direct evidence                                 │  │
│  │ ┌──────────────────────────────────────────────┐   │  │
│  │ │ headache (DISEASE) — 3 mentions              │   │  │
│  │ │ "...for pains of the head, take oil of       │   │  │
│  │ │ roses and vinegar applied to the temples..."  │   │  │
│  │ │ → View in book · View entity                 │   │  │
│  │ └──────────────────────────────────────────────┘   │  │
│  │                                                    │  │
│  │ 📐 Analogical evidence                             │  │
│  │ ┌──────────────────────────────────────────────┐   │  │
│  │ │ fever (DISEASE) — 47 mentions                │   │  │
│  │ │ Reasoning pattern applied from fever          │   │  │
│  │ │ treatment to headache by humoral analogy     │   │  │
│  │ └──────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ How this answer was built ────────────────────────┐  │
│  │ Query embedded → 12 entities matched →             │  │
│  │ 3 direct, 9 analogical → synthesized via           │  │
│  │ Gemini 2.5 Flash with epistemological context      │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ Modern context ───────────────────────────────────┐  │
│  │ ⚕️ Migraines are now understood as a neurological   │  │
│  │ condition involving cortical spreading depression.  │  │
│  │ Culpeper's humoral framework has no explanatory     │  │
│  │ power for the underlying mechanism, though some of  │  │
│  │ his herbal remedies (e.g. feverfew) have shown      │  │
│  │ modest efficacy in modern trials.                   │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Decade mode: `/consult?decade=1560s`

Same layout but:
- Header shows all books from that decade with thumbnails
- Frameworks section shows which books hold which views
- Evidence is tagged by book
- Disagreements between authors are highlighted

---

## Implementation Order

### Prerequisites (being built by Codex)
- [ ] Entity registry with stable slugs
- [ ] API routes: `/api/entity/[slug]`, `/api/entity/[slug]/attestations`
- [ ] Search expanded to all entities

### Phase 1: Data preparation
- [ ] Write `book_epistemologies.json` for all 8 books (manual, ~2 hours)
- [ ] Expand search embeddings to cover all entities per book

### Phase 2: API
- [ ] `POST /api/consult` endpoint
- [ ] Prompt builder (assembles system + user message from epistemology + entities)
- [ ] Gemini Flash integration (API call + response parsing)
- [ ] Output validation (verify citations, check schema)

### Phase 3: Frontend
- [ ] `/books/[id]/consult` page
- [ ] Response renderer (persona text + evidence panels + framework tags)
- [ ] Example questions per book
- [ ] Loading state + error handling

### Phase 4: Decade mode
- [ ] `/consult` page with decade/century selector
- [ ] Multi-book aggregation logic
- [ ] Disagreement highlighting

---

## Cost Projections

| Usage | Queries/day | Gemini cost/day | Embedding cost/day |
|-------|-------------|-----------------|-------------------|
| Dev/demo | 50 | $0.05-0.15 | $0.001 |
| Light production | 500 | $0.50-1.50 | $0.01 |
| Heavy production | 5,000 | $5-15 | $0.10 |

Gemini 2.5 Flash is the right model here — fast enough for interactive use (~1-3s), cheap enough for production, smart enough to maintain persona consistency and follow the output schema.

---

## What Makes This Grant-Worthy (not a party trick)

1. **Grounded in structured data** — every claim traceable to entities and excerpts
2. **Epistemological frameworks as structured data** — novel contribution to DH methodology
3. **Counterfactual reasoning** — a legitimate historical method, now scalable
4. **Auditable outputs** — the "how this answer was built" panel shows the full pipeline
5. **Comparative dimension** — decade mode surfaces inter-textual tensions
6. **Demonstrates AI + humanities data > AI alone** — without the entity resolution and epistemological profiles, you'd just get ChatGPT hallucinating about Culpeper

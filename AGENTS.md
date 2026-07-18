# AGENTS.md

## Project direction

Premodern Concordance is a research and discovery engine for historical
scientific and medical texts. It should move beyond full-text search by finding
and explaining:

- historical names, spellings, translations, and referents;
- changes and splits in meaning across time and language;
- claims, attributions, disagreements, and reframings;
- unexpected but evidence-backed connections between distinct topics.

The target is roughly 500 important texts and about 5,000 curated anchor topics,
expandable toward 10,000. Surface forms, contextual usages, induced senses,
claims, and candidate links may be much larger.

Read [the discovery roadmap](docs/v2/discovery-roadmap.md) before planning
substantial product, data-model, retrieval, or pipeline work.

The active corpus-foundation contract is
[passage and retrieval architecture](docs/v2/passage-retrieval.md). Read it
before changing source ingestion, passage boundaries, page alignment,
embeddings, lexical retrieval, or candidate ranking.

## Architectural idea

Build a typed diachronic evidence graph:

    sources → passages → contextual usages → senses/referents
                                     ↘ claims → agreements/disagreements
                                               ↘ sourced hypotheses

Keep the upper schema small and let the evidence graph grow. Related topics
remain separate entries connected by typed edges; similarity never silently
means identity. Every derived object should lead back to citable passage
evidence.

The V2 web app is the reader and materialized read model. Heavy extraction,
retrieval, clustering, and LLM analysis happen offline.

## Adaptability

The roadmap is directional, not prescriptive.

- Treat model, embedding, vector-index, clustering, and storage choices as
  replaceable implementation details.
- The fine-tuned BGE-M3 model is an experiment, not a required dependency.
- Compare existing work with current off-the-shelf models and new fine-tuning
  approaches before assuming any model is best.
- Prefer the simplest method that produces useful historical discoveries.
- Record enough run and evidence provenance to compare methods and reproduce an
  interesting result.
- It is acceptable to change the schema or roadmap when experiments reveal a
  better approach; update the relevant document when doing so.

## Intellectual and communication standard

The project owner explicitly prefers direct criticism to agreement, reassurance,
or praise. Accuracy and research value take priority over conversational
smoothness.

- Do not endorse a proposal merely because the owner suggested it.
- State plainly when evidence is weak, a result is banal, a method is unlikely
  to work, or effort is being spent on the wrong layer.
- Separate observed results, reasonable inference, and speculation.
- When disagreeing, give the concrete evidence and a better alternative.
- Do not flatter the owner's expertise or treat expert judgment as infallible.
  Preserve it as high-value labeled data while keeping objective support and
  subjective research interest as separate fields.
- Directness is not performative negativity: calibrate criticism to the
  evidence and acknowledge genuinely strong results without exaggeration.

## Historian assessment workflow

The local-only interface at `/apps/concordance/review/findings` records expert
assessment of model-generated findings. Read
[historian assessment](docs/v2/historian-assessment.md) before changing this
workflow or using its output.

- Live assessments are append-only events in ignored
  `var/historian-reviews.sqlite`; never put them in the public database.
- Each event snapshots the exact release, entry, finding, claims, quotations,
  and scan links reviewed. Later pipeline runs must not rewrite old judgments.
- Evidence support, research value, failure mode, and claim fidelity are
  distinct labels. Never collapse them into one positive/negative target.
- Export the latest judgment per finding with `premodern export-reviews` to
  versioned JSONL before treating reviews as durable evaluation or training
  data. The export adds model-run and prompt provenance from the authoring DB.
- Use small reviewed sets first as evaluation and error diagnosis. Do not claim
  that dozens of findings justify generative fine-tuning. Derive task-specific
  datasets only after enough consistent labels accumulate.

## Active passage and retrieval contract

The next research layers depend on one stable citable passage corpus. Unless a
corpus-specific evaluation shows a better method:

- Passageize immutable source text paragraph-first: merge fragments under
  roughly 80 words, target 150–220 words, and split over 320 words near a
  sentence boundary.
- Canonical passages do not overlap. Expand to adjacent passages only when a
  model needs context.
- Preserve raw character offsets, raw text, normalized search text, corrected
  display text, headings, printed-page ranges, scan-leaf ranges, and direct
  scan links. Normalization or OCR correction must never overwrite the source.
- Passage IDs derive from the source and immutable raw offsets. Published IDs
  are never silently renumbered.
- Parse Internet Archive DJVU `PAGE` parameters for real zero-based scan leaves;
  do not infer leaves from XML array position. Derive printed pages from Page
  Numbers JSON when available and retain alignment provenance.
- Use `gemini-embedding-2` at 768 dimensions as the default passage embedder,
  preferably through Batch. Embed normalized passage text with its work/section
  title, not year, page, language, or archive metadata.
- Dense retrieval proposes passages; it never resolves identity. Candidate
  retrieval is the union of exact/normalized forms, OCR-aware lexical search,
  and dense search, combined by reciprocal-rank fusion with component scores
  retained.
- Gemini 3.1 Flash-Lite is the current default for bounded candidate analysis.
  Give it the candidate plus adjacent context, but require evidence spans to
  resolve to canonical passages.
- Keep the fine-tuned BGE-M3 experiment available for entity-label resolution.
  Do not use it as the default passage embedder: it was trained on label pairs,
  not query-to-passage retrieval.
- LLMs may propose historical names, translations, and periphrases. Generate
  OCR variants deterministically from known confusions and actual corpus forms;
  do not trust invented lists of plausible OCR errors.
- Embeddings, vector indexes, raw corpus files, and analysis outputs are offline
  build artifacts and never ship in the Vercel bundle. The reader receives only
  materialized evidence and bounded database responses.

The first vertical discovery slice is complete: source registry and page-aware
passageization; offset/page/scan audit; Gemini embedding index; hybrid retrieval;
contextual usage and claim analysis; entry-local sense induction; and
claim-linked research findings. The next operation is historian assessment of
the resulting evidence packet, followed by targeted retrieval/prompt repair and
then a broader source-and-topic slice. Do not redesign the schema before using
the real outputs to identify a concrete failure.

Current checkpoint (July 17, 2026): the private database contains 16,016
canonical passages from 17 complete legacy texts plus 254 citable Jamesiana
passages. All legacy passage audits pass; 15,525 passages align directly to
scan OCR and 491 retain explicitly marked inferred locators. Gemini Embedding 2
at 768 dimensions has embedded all 16,270 passages and 20 trial queries. The
saved matrix is finite, normalized, and keyed; its estimated standard-endpoint
cost was $1.03. The batch endpoint could not accept the 5.17M-token embedding
job under its published queue cap, so the resumable, rate-limited standard
endpoint was used without changing the artifact contract.

Weighted hybrid retrieval is the active baseline. On the 15 entries with
existing evidence it improves macro recall over lexical-only retrieval from
49.0% to 52.0% at 20 and from 63.1% to 65.0% at 50; all 15 have a known hit in
the top 50. Dense retrieval alone is substantially worse and must not replace
inspectable lexical/OCR retrieval.

The first bounded Gemini 3.1 Flash-Lite discovery slice analyzed the top 20
hybrid candidates for all 20 trial entries. Of 400 candidates, 373 passed
source-span validation; 292 relevant same-entry or related-distinct usages and
454 claims are public. Entry-local induction groups 253 same-entry usages into
63 senses. Claim comparison produced 42 suggested findings linked through 89
explicit claim roles. Analysis, senses, and findings cost about $0.21 combined;
the public reader still makes no model calls. These are candidate research
objects, not asserted historical truth. Weak examples are useful evaluation
data and should be corrected by better retrieval or bounded prompts, not by
silently editing model prose.

The next active step is historian assessment. The local review workbench covers
all 42 findings, supports claim-level fidelity labels, saves append-only
snapshots, and exports JSONL. Use its error distribution to decide whether the
next repair belongs in retrieval, entry resolution, claim extraction, or
finding comparison. Do not scale the same error distribution to thousands of
topics first.

## Working style

- Build vertical research slices before broad infrastructure.
- Candidate links and model suggestions are useful during internal development;
  expose their reason, confidence, method, and evidence.
- Do not create elaborate review queues, approval systems, governance layers,
  or test frameworks unless a demonstrated workflow requires them.
- Use compact evaluations to compare retrieval and analysis methods. Testing
  should support decisions, not become the product.
- Avoid extracting every abstract noun into an ontology. Start from curated
  topics while preserving recurring unmatched clusters for discovery.
- Keep the interface focused on one path: search → topic → findings, senses,
  claims, connections, and passages.
- Keep original text readable, citable, and linked to the edition or scan.

## Repository boundaries

- web/ — frozen legacy prototype for comparison; localhost:3000.
- apps/concordance/ — V2 reader application; localhost:3001 at
  /apps/concordance.
- pipeline/ — private/offline ingestion and research analysis.
- var/ — ignored local databases and releases.
- docs/v2/ — active architecture, roadmap, operations, and progress.

V2 must not import web/ or the legacy root scripts at runtime. Client
components must not import server repositories, secrets, filesystem code, model
SDKs, or private pipeline modules.

## Active documents

- [Discovery roadmap](docs/v2/discovery-roadmap.md) — research and product
  direction.
- [V2 architecture](docs/v2/README.md) — application boundaries and deployment
  shape.
- [Data contract](docs/v2/data-contract.md) — current and planned records.
- [Operations](docs/v2/operations.md) — commands and release flow.
- [Implementation ledger](docs/v2/implementation-ledger.md) — current state and
  decisions.
- [Passage and retrieval architecture](docs/v2/passage-retrieval.md) — active
  chunking, page-alignment, embedding, and hybrid-retrieval contract.
- [Historian assessment](docs/v2/historian-assessment.md) — local review,
  durable export, and task-specific use of expert judgments.

Preserve unrelated user work and keep the legacy prototype available until V2
has clearly superseded it.

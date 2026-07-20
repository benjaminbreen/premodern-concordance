# V2 implementation ledger

This ledger is the durable progress record for Premodern Concordance V2. Routine
implementation updates belong here so work can continue without requiring
frequent user decisions.

## Settled decisions

- Preserve the prototype at `web/`; build V2 at `apps/concordance/`.
- Compare on ports 3000 and 3001 rather than mounting V2 at `/new`.
- Preserve visual identity but do not share legacy runtime components.
- Use private local SQLite plus an allowlisted public projection.
- Use Turso for public structured data and R2 for source text/page maps.
- Public site is read-only and makes no runtime model calls.
- Launch target: 50–75 sources and 500–1,000 curated entries.
- Eventual target: about 500 sources and 5,000–10,000 entries.
- Period: 1500–1950; Latin-script languages first.
- Source selection: digitization readiness first, coverage second.
- Research workflow: agent-led, with candidate suggestions visible and linked to
  their method and evidence; no elaborate review platform by default.
- Model and retrieval choices remain replaceable experiments.
- Canonical passages are paragraph-first, non-overlapping, offset-stable, and
  retain printed-page and scan-leaf ranges.
- Gemini Embedding 2 at 768 dimensions is the current passage-retrieval default;
  hybrid retrieval also retains exact/normalized and OCR-aware lexical results.
- Fine-tuned BGE-M3 remains scoped to entity-label experiments unless
  passage-level evaluation shows otherwise.

## Visual language

- The legacy homepage is the visual reference, but V2 does not import legacy
  runtime components.
- Interface typography uses the native system sans stack. EB Garamond is
  reserved for source reading and the homepage title's optional typeface cycle;
  it is not the default heading font.
- Page shells are capped at 80rem, headings are compact, rules are thin, and
  cards use minimal radius and shadow.
- The homepage pattern is: two-column search hero, inline corpus statistics,
  then an archival title-page rail. It should read as a scholarly reference
  work, not a product landing page.
- The shared footer follows the legacy dark colophon treatment and appears on
  every public route. The About page retains the legacy project's compact
  project description, personnel, and colophon hierarchy.
- Public entry pages show a short scope sentence, term forms, relationships,
  and passage evidence. Editorial exclusion notes remain in the data model but
  are not rendered as reader-facing `Boundary` callouts.
- Unreviewed material is labeled tersely as `Suggested`; longer methodological
  cautions belong in editorial tooling or the About page.

## Stage status

| Stage | Status | Verification |
| --- | --- | --- |
| Architecture contracts | Complete | README, data contract, operations runbook, and AGENTS pointer |
| Discovery roadmap | Complete | Typed usage, claim, disagreement, and hypothesis direction documented |
| Relationship model bake-off | Complete | Three models compared on the same 75 saved examples; Gemini 3.1 selected provisionally |
| Isolated V2 scaffold | Complete | Independent Next.js app on port 3001; architecture check passes |
| Authoring/public schemas | Complete | Strict private schema plus allowlisted public schema v6 |
| Immutable publication | Complete | Evidence validation, hashes, manifests, atomic promotion, and audit tests |
| Core public routes | Complete | Search, entries, passages, sources, context APIs, and archive links |
| Acceptance entries | Complete | 20 boundaries defined; 15 currently public only because they have evidence |
| Legacy source adapter | Complete | Citable evidence imported without a legacy runtime dependency |
| Jamesiana adapter | Complete | Release/checksum verified; 22 relevant stable-edition sources imported as suggestions |
| Local build and route QA | Complete | Checks/build pass; core HTML/API routes return 200; acceptance searches verified |
| Visual browser QA | Blocked locally | In-app browser control was unavailable; HTTP interaction and responsive-code review completed |
| Citable full-corpus passages | Complete | 16,016 legacy passages; offset/overlap/range audit clean; 15,525 direct and 491 inferred scan alignments |
| Gemini passage embeddings | Complete | 16,270 passage + 20 query vectors; 768d normalized matrix, exact keys/hashes, estimated standard cost $1.03 |
| Hybrid topic retrieval | Complete | Lexical, dense, and weighted RRF compared; hybrid wins macro and micro recall at 20/50 |
| Contextual usage and claim analysis | Complete | 373/400 outputs validated; 292 relevant usages and 454 grounded claims published |
| Entry-local sense induction | Complete | 253 same-entry usages grouped into 63 senses across 18 evidenced entries |
| Claim-linked research findings | Complete | 42 suggested findings linked to 89 exact claims across 10 qualifying entries |
| Local historian assessment | Complete | Append-only finding/claim review, progress queue, local save API, JSONL export, and provenance enrichment |
| Turso/R2/Vercel deployment | In progress | Turso and R2 provisioned and checksum-verified; Vercel preview/production promotion pending |

## Deviations and decisions during implementation

Record any departure from `README.md` or `data-contract.md` here before it is
implemented. A departure that changes product scope, editorial meaning, public
cost, or user-visible behavior requires user guidance.

- The current acceptance release contains 33 citable editions rather than the
  50–75 source launch target. This is a working release, not the launch
  corpus; only digitization-ready sources with evidence for the trial entries
  were admitted.
- Five defined entries remain private because current eligible sources provide
  no evidence. Publication correctly omits them instead of manufacturing empty
  public pages.

## Current discovery release

- Release: `v2-discovery-004`
- Public schema: `6`
- Sources: 38
- Passages: 498
- Public entries: 20
- Occurrences: 308
- Contextual usages: 292
- Usage claims: 454
- Sense clusters / memberships: 63 / 253
- Research findings / claim links: 42 / 89
- Clean Next.js build: 11 MB (`.next/server` 9.9 MB; static assets 1.0 MB)
- Warm local responses: search 12 ms, homepage 211 ms, entry page 205 ms
- Largest tested initial HTML response: 71 KB (Genius entry, 10 passages)
- Public database audit: passed
- Pipeline tests: 18 passed
- TypeScript, ESLint, architecture check, and production build: passed
- Production dependency audit: 0 known vulnerabilities
- Verified searches: `Quinaquina` → Cinchona bark; `human species` keeps Human
  species and *Homo sapiens* as distinct results

## July 2026 implementation review

The first localhost review found and corrected the following defects:

- mounted V2 at `/apps/concordance` and fixed subpath form/API navigation;
- preserved the complete mobile navigation rather than hiding it;
- classified Engineer as `ROLE_OCCUPATION`, not a practice;
- removed duplicate source-page passages caused by multi-entry occurrences;
- added bounded pagination to entry and source registries;
- made entry-passage API pagination terminal and missing-entry behavior explicit;
- retained entry-specific occurrence spans on citable passage pages;
- linked entry-relationship claims directly to their evidence passages;
- corrected backwards chronological pagination labels;
- made repeated query parameters safe;
- fixed Unicode case-folding offset drift and added a publication-time span gate;
- excluded source records with no published passages from the public projection.

Release-level audits now report zero invalid occurrence spans, empty sources,
or unevidenced relationships.

## July 2026 relationship-model bake-off

The first compact model comparison is complete. On 70 shared cluster-membership
examples, Gemini 3.1 Flash-Lite achieved 82.5% balanced accuracy with no false
merges, outperforming GPT-5.4 Nano and GPT-5 Nano. The comparison cost $0.0331
for measured successful calls. Five shared synonym-chain cases were retained as
diagnostics but are too few for ranking.

The experiment also found mislabeled or contaminated examples in the existing
training corpus. Before classifier fine-tuning, the next data task is a narrow
repair of disagreement cases and relation boundaries—not a general review
platform. Full results are in
[model-bakeoff-2026-07.md](model-bakeoff-2026-07.md).

At the planned 100-text/1,000-entity scale, retrieval-first Gemini 3.1
classification is expected to cost about $1–$4, plus roughly $3–$8 for a full
corpus extraction pass. Batch processing and local candidate retrieval keep the
combined one-time build below a planning ceiling of approximately $12; the
public reader makes no runtime model calls.

## Credential boundary

Local implementation, fixtures, database projection, tests, and browser QA can
proceed without external credentials. User input is required only when creating
or authorizing Turso, Cloudflare R2, and the new Vercel project.

## July 2026 passage/retrieval decision

William Jamesiana's source-edition machinery is the architectural reference for
stable passage IDs, immutable OCR, embedding-input hashes, and Internet Archive
page/leaf mapping. Premodern does not copy its older fixed-character chunker or
its existing OpenAI embedding choice verbatim. The active contract is in
[passage-retrieval.md](passage-retrieval.md): paragraph-first passages,
range-aware scan locators, Gemini Embedding 2 at 768 dimensions, hybrid
retrieval, adjacent analysis context, and compact known-passage recall checks.

## July 2026 corpus-foundation build

The complete legacy corpus is now passageized in the private authoring database:

- 17 full texts; 16,016 canonical, non-overlapping passages;
- median 200 words, 99th percentile 311, hard maximum 320;
- 15,525 direct four-gram scan matches and 491 marked page/leaf inferences;
- zero audit errors for raw source slices, offsets, ordering, overlap, ranges,
  or scan URLs;
- legacy curated occurrences remapped to stable passage IDs rather than lost;
- 254 imported Jamesiana passages remain in the same retrieval corpus.

The saved Gemini Embedding 2 build has 16,290 items (16,270 passages and 20
queries), 768 dimensions, asymmetric retrieval prefixes, exact input hashes,
and 5.17M estimated input tokens. Because that exceeds the embedding Batch API
queue cap, the resumable standard endpoint completed it at an estimated $1.03.
All vectors are finite, unit-normalized, and mapped to stable keys.

The inspectable lexical baseline is already useful. Over 15 entries with known
evidence, it retrieves at least one known passage within the top 20 for 14
entries (93.3%) and within the top 50 for all 15. Compact-space matching was
added after real OCR rendered `Água de Inglaterra` as `aguade Inglaterra`.
All-evidence micro recall remains deliberately reported (18.9% at 20 and 33.1%
at 50) because common Jamesiana topics have more known passages than a small
candidate cutoff can contain. Weighted hybrid retrieval raises macro recall to
52.0% at 20 and 65.0% at 50, and micro recall to 21.5% and 38.1%. Dense-only
retrieval performs markedly worse, while hybrid retrieval adds useful
periphrastic and conceptual candidates without discarding lexical evidence.

The first analysis run used the top 20 hybrid candidates for each of 20 trial
entries. Its middle-ground record distinguishes mention type, same-entry versus
related-distinct resolution, typed relations, local sense glosses, and up to
two claims with stance and evidence basis. Exact target-passage spans are a hard
ingestion requirement; adjacent passages are context only. OCR-aware alignment
may recover a source slice at high similarity, but the stored quotation is
always the exact underlying source text.

Gemini 3.1 Flash-Lite returned 400 analyses. The validator admitted 373 and
rejected 27; 292 relevant usages and 454 claims entered the public projection.
The run cost $0.1864. A second closed-set pass grouped 253 same-entry usages into
63 entry-local senses across 18 entries for $0.0117. A final closed-set pass
compared 206 claims across 10 entries and produced 42 suggested findings linked
to 89 exact claim records for $0.0096. The complete discovery analysis cost was
therefore about $0.21, or about $1.24 including passage embeddings.

The resulting reader now exposes historical usages and claims, adjacent but
non-identical histories, induced senses, and a `What the corpus suggests`
section. These outputs include strong leads and visible weak cases. The next
evaluation should record a historian's compact verdicts on the actual findings;
that evidence, rather than another abstract schema revision, should determine
the next retrieval and prompt changes.

## July 2026 historian assessment workbench

The local-only `/review/findings` route now presents all 42 candidate findings
with their exact claims, quotations, passages, and scan links. It records
evidentiary support separately from research value, supports controlled failure
modes and claim-level fidelity labels, and accepts concise corrections or
diagnostic notes. Saves are append-only snapshots in
`var/historian-reviews.sqlite`; public production remains read-only.

`premodern export-reviews` writes the latest judgment per finding as versionable
JSONL plus an aggregate error summary and enriches each record with the original
model-run and prompt provenance. This dataset is an evaluation and error-
diagnosis asset first. Fine-tuning remains conditional on accumulating enough
consistent labels for a specific task.

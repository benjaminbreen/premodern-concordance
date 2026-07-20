# Relation-classification bake-off, July 2026

## Decision

Use `gemini-3.1-flash-lite` as the current default for bounded offline
relationship classification. Keep the model configurable: this is an empirical
choice, not an architectural dependency.

## Test

The three available models were compared on the same 75 saved examples:

- 70 cluster-membership decisions, stratified across the existing labels;
- 5 synonym-chain examples completed before long-passage output failures began.

The five synonym cases are diagnostic only. They are too few to rank models.
Gemini 2.5 Flash-Lite was dropped because its API endpoint reported that the
model is unavailable to new users. No completed GPT-5 Nano work was rerun.

| Model | Membership balanced accuracy | Precision | Recall | F1 | Measured cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemini 3.1 Flash-Lite | **82.5%** | **100%** | **64.9%** | **78.7%** | $0.0107 |
| GPT-5.4 Nano | 73.7% | **100%** | 47.4% | 64.3% | $0.0204 |
| GPT-5 Nano (2025-08-07) | 67.9% | 90.5% | **66.7%** | 76.8% | $0.0020 |

Measured successful-call cost was $0.0331. Failed or incomplete requests did
not always return usage, so the provider total may be a few cents higher.

## Findings

- Gemini 3.1 made no false-positive merges in the membership sample while
  recovering substantially more real links than GPT-5.4 Nano. It was also fast
  and operationally stable.
- GPT-5.4 Nano was too conservative: it rejected more than half of the positive
  links, cost roughly twice as much as Gemini, and had severe latency outliers.
- GPT-5 Nano was extremely cheap and had similar recall to Gemini, but allowed
  four false merges and repeatedly produced truncated structured output on
  longer passage batches.
- Exact typed-relation accuracy was low for every model (about 30–33% on
  membership). This is partly a label problem, not simply a model problem.

The disagreement cases exposed errors in the current gold data. Examples
include broad/narrow place names marked as translations, subtypes marked as
orthographic variants, unrelated words preserved by old clusters, and incorrect
modern enrichments. `Wounds`/`contusões`, `Santiago de Cuba`/`Cuba`, and
`Arithmetica`/`mathématique` should not be trained as simple equivalences.

## Consequence for the pipeline

Retrieval should continue to propose candidates cheaply. Gemini 3.1 should then
judge short, contextualized candidate pairs and assign a typed relation. Long
source passages should be reduced to the relevant evidence window before the
classification call.

A historian spot-check established three requirements that the synthetic data
did not capture well:

- the model should propose and resolve plausible OCR errors, such as
  `fezes ardentes` → `febres ardentes`, before classifying the relationship;
- distinct but historically related concepts must retain a typed edge, as with
  contusions and wounds, rather than being flattened into `unrelated`;
- contextual usage can override dictionary-level generality, as when `noz`
  functions elliptically for nutmeg within Orta's nutmeg chapter.

The classifier output should therefore separate canonical identity, typed
entity-to-entity relationships, passage-level claims, and proposed OCR
normalization. A single `linked` boolean is insufficient.

Do not fine-tune a replacement classifier on all 566 existing labels yet. First
repair the compact set of model/gold disagreements and clarify the boundary
between lexical variant, translation, same referent, subtype, and conceptual
overlap. This is a focused data correction pass, not a new review system.

The resumable evaluator is
`pipeline/experiments/relation_bakeoff.py`. Raw run artifacts and per-pattern
metrics are stored under `var/experiments/relation-bakeoff-100-20260716/` and
are intentionally excluded from deployment.

## Cost at 100-text scale

As checked in July 2026, Gemini 3.1 Flash-Lite costs $0.25 per million input
tokens and $1.50 per million output tokens through the standard API. Batch
processing halves those rates to $0.125 and $0.75. Current prices should be
verified before a large run against Google's
[official pricing page](https://ai.google.dev/gemini-api/docs/pricing).

The completed bake-off used 11,402 input tokens and 5,222 output/thinking tokens
for 75 Gemini judgments, costing $0.0107. That is approximately $0.000142 per
judgment at standard rates or $0.000071 through Batch.

| Candidate judgments | Standard | Batch |
| ---: | ---: | ---: |
| 1,000 | $0.14 | $0.07 |
| 5,000 | $0.71 | $0.36 |
| 10,000 | $1.42 | $0.71 |
| 100,000 | $14.24 | $7.12 |

The 100,000-judgment row represents the wasteful all-pairs strategy of testing
1,000 entities independently against all 100 texts. The intended workflow is:

1. retrieve plausible passages locally with lexical, OCR-aware, and embedding
   methods;
2. retain roughly 5–10 candidate passages per entity across the corpus;
3. send those bounded passages to Gemini through the Batch API;
4. materialize the results offline for a reader that makes no model calls.

Allowing 400–1,000 input tokens per candidate for richer source context, a
1,000-entity relationship pass should cost roughly $1–$2 through Batch or
$2–$4 through standard requests. Budget $5 for retries and difficult passages.

A separate full extraction pass over 100 books averaging 150,000 tokens each
would contain about 15 million input tokens. Including structured extraction
output, a reasonable planning range is $3–$8. The combined one-time analytical
build for 100 texts and 1,000 entities should normally remain below $12.

These are offline ingestion costs, not weekly site costs. The deployed public
reader remains precomputed and model-free at runtime.

# Passage and retrieval architecture

Status: active implementation contract, July 2026.

## Purpose

The concordance needs stable evidence before it can infer usages, senses,
claims, disagreements, or transmission. This layer turns each edition into
citable passages, preserves links to the scan, and retrieves candidates for
curated topics. It is an offline research build; the public reader makes no
embedding or model calls.

## Source and passage layers

Each source is one citable edition with immutable raw text, a checksum,
language/date metadata, and an archive reference. Internet Archive sources also
retain DJVU OCR and Page Numbers JSON as alignment evidence.

A canonical passage is non-overlapping and stable. Passageization is
paragraph-first:

1. retain source offsets and structural boundaries;
2. merge fragments under about 80 words;
3. target 150–220 words;
4. split passages over 320 words near a sentence boundary;
5. fall back to clauses or lines only when OCR punctuation is unusable.

Each passage stores raw and normalized text, start/end offsets, optional
heading, printed-page start/end, scan-leaf start/end, scan URL, alignment method
and score, and chunker version. Corrected display text is derived; it never
replaces raw source text. Passage IDs are deterministic from source ID and raw
offsets and remain fixed after publication.

Canonical passages do not overlap. Candidate analysis may load the preceding
and following passage as context, while evidence spans still point to canonical
passage IDs.

## Page alignment

For Internet Archive editions:

- read the actual leaf from each DJVU `PAGE` parameter, because blank or corrupt
  leaves may be absent from the XML;
- normalize only for alignment and compare passage four-grams with page OCR;
- prefer monotonic matches near the previous passage;
- derive printed pages from exact Page Numbers JSON anchors, with an inferred
  page-one offset only as fallback;
- record matched, inferred, and unaligned counts and retain start/end leaf and
  page ranges;
- link to `https://archive.org/details/{item}/page/n{leaf}/mode/1up`.

An inferred locator is useful but must remain distinguishable from a direct OCR
match. A source without a trustworthy scan alignment may still be searchable,
but its passage must not pretend to have a verified page.

## Search text and embedding input

`search_text` may normalize whitespace, line-break hyphenation, long-s,
ligatures, and high-confidence OCR errors. It preserves historical vocabulary
and spelling. Raw and display text remain available for reading and citation.

Default embedding model:

- model: `gemini-embedding-2`
- dimensions: 768
- mode: asymmetric search
- build path: Gemini Batch API when practical
- document: `title: {work — section} | text: {search_text}`
- query: `task: search result | query: {label}. {scope}. Historical forms: ...`

Do not embed page, year, language, or archive metadata; those are structured
filters. Store exact embedding inputs and hashes so unchanged passages can reuse
vectors. Embeddings and indexes live under ignored `var/` paths.

## Hybrid retrieval

Topic candidate retrieval has three inspectable channels:

1. exact and normalized curated term forms;
2. OCR-aware lexical/fuzzy search over actual corpus text;
3. dense query-to-passage search.

Union the channels and combine ranks with reciprocal-rank fusion. Retain each
channel's rank and score; do not present a fused score as epistemic confidence.
LLM query expansion may propose historical names, translations, and
periphrases, but candidates become useful only when grounded in corpus
passages. OCR variation is handled deterministically and mined from observed
forms rather than generated speculatively.

Gemini 3.1 Flash-Lite then makes bounded local judgments about mention
explicitness, resolution, typed relationship, claim, stance, and evidence
basis. Similarity is candidate generation, never identity.

## Compact evaluation

For the initial topics, retain about ten known relevant passages where
available. Report recall at practical candidate depths, unique contributions by
retrieval channel, and examples of useful discoveries and false positives.
Historian reactions are saved as JSONL with a short verdict and reason so they
become real evaluation data. This evaluation chooses methods; it is not a
review-platform project.

## Scale and deployment

The current 17 legacy text files contain about 3.2 million words and produce
16,016 canonical passages. Another 254 citable passages come from the
Jamesiana adapter. The legacy audit finds a 200-word median, 320-word maximum,
15,525 direct scan alignments, 491 marked inferences, and no source-slice,
overlap, ordering, or range errors. A 768-dimensional float32 index is tens of
megabytes. At 500 comparable texts it is still an ordinary offline artifact,
but it is never part of the Vercel deployment.

Passage and embedding builds are incremental by source checksum, chunker
version, embedding model, dimensions, and exact input hash. The public release
contains only passages and derived records needed by the reader; source text
and page maps live in object storage.

The first lexical/OCR baseline over all 16,270 passages retrieves at least one
known evidence passage in the top 20 for 14/15 evaluable entries and the top 50
for 15/15. This is a channel sanity check, not the final quality score: entries
with many Jamesiana attestations naturally have low all-evidence recall at a
small cutoff. Dense and fused scores must be compared against this saved
baseline rather than judged without it.

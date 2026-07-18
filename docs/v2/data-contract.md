# V2 data contract

Status: active record contract. Contextual usages, claims, entry-local senses,
and research findings are implemented in the first discovery slice. Usage-to-
usage edges and open-world topic discovery remain later work.

## Current records

### Work and source

A work groups related editions or translations. A source is one citable witness
with its own language, date, edition metadata, archive location, text checksum,
and rights status.

### Passage

A passage is a stable citable unit within a source. It stores sequence,
immutable character offsets, raw text, normalized search text, corrected display
text, optional heading, printed-page start/end, scan-leaf start/end, archive
URL, alignment provenance, and chunker version. Normalization never overwrites
raw or display text. Canonical passages do not overlap; adjacent passages may be
loaded temporarily for analysis context.

The default chunker is paragraph-first, targets 150–220 words, merges fragments
under about 80 words, and splits over 320 words near sentence boundaries.
Passage IDs derive from source and immutable raw offsets rather than array
position.

### Research entry

An entry is a stable anchor topic. Current kinds:

- ORGANISM_TAXON
- SUBSTANCE_MATERIAL
- DISEASE_CONDITION
- ANATOMY
- PRACTICE_METHOD
- ROLE_OCCUPATION
- CONCEPT_THEORY
- PHENOMENON_PROCESS
- OBJECT_INSTRUMENT

Every entry has a stable ID and slug, preferred label, short scope, status, and
summary counts. Closely related topics remain separate unless the evidence
supports identity in context.

### Term form and occurrence

A term form is a language- and period-aware label that may point toward one or
more entries. An occurrence resolves a surface span in a passage to an entry and
records method, confidence, status, and analysis provenance when available.

Current term relationships:

- PREFERRED_LABEL
- ORTHOGRAPHIC_VARIANT
- TRANSLATION
- HISTORICAL_LABEL
- TAXONOMIC_SYNONYM
- TRADE_NAME
- DERIVED_FORM
- CONTESTED_LABEL

### Entry relationship

Entry relationships are typed edges, not hidden synonyms.

Precise relationships:

- PREPARATION_OF
- BROADER_THAN
- NARROWER_THAN
- PART_OF
- CONTESTED_IDENTITY

Exploratory relationships:

- INFLUENCE
- SHARED_PROBLEM
- FUNCTIONAL_ANALOGY
- LATER_REFRAMING
- CONTRAST

Each relationship carries direction, rationale, status, confidence when
available, and passage evidence.

### Supporting entity

People, places, works, and institutions may be supporting records connected to
passages and claims. They do not compete with the anchor-topic registry.

## Discovery records

### Contextual usage

A usage represents one topic-relevant passage span in context. The implemented
record stores mention type (`NAMED`, `DESCRIBED`, `IMPLIED`, `ABSENT`),
resolution (`SAME_ENTRY`, `RELATED_DISTINCT`, `AMBIGUOUS`, `NOT_RELEVANT`), an
optional typed relationship, a local sense gloss, confidence, retrieval rank,
analysis provenance, and an exact evidence span. Adjacent passages may inform
analysis but cannot supply the stored evidence.

### Usage edge and sense cluster

A usage edge records a graded, typed comparison between two contextual usages.
Possible judgments include same sense, same referent, related sense, distinct
sense, translation, derivation, and contested identity.

A sense cluster groups connected usages without requiring a permanent global
sense inventory. The implemented first pass is entry-local and closed-set: a
model groups every supplied same-entry usage exactly once and may not invent or
drop IDs. Clusters have a label, gloss, date range, status, confidence, and
explicit usage memberships. Cross-entry usage edges remain planned.

### Claim

A claim records up to two historically comparable assertions per usage:

- subject, predicate, and object;
- assertion, denial, qualification, uncertainty, or attribution;
- author and attributed authority when present;
- topic, passage, source, date, and language;
- extraction method and confidence.

The implemented first pass uses a compact controlled vocabulary for claim
type, stance, and evidence basis. Summaries are model prose; evidence is always
an exact slice of the source passage. Failed evidence alignment keeps the
record private rather than manufacturing a quotation.

Claim edges may represent repetition, contradiction, qualification, reframing,
attribution, citation, or possible transmission.

### Research finding

A research finding is an evidence-backed suggestion such as a recurrence,
disagreement, qualification, sense shift, method shift, transmission candidate,
or anomaly. The implemented pass compares an entry's existing claims as a
closed set. Every finding links at least two exact claim IDs with controlled
roles (`SUPPORTS`, `CONTRADICTS`, `QUALIFIES`, or `EXAMPLE`) and records its
analysis run. Findings remain `SUGGESTED`; they are leads for historical
assessment rather than claims of fact by the application.

### Analysis run

An analysis run records the method needed to understand or reproduce a result:
model or algorithm, configuration, prompt/schema version when relevant, input
set, output location, and basic cost or timing.

### Historian assessment

An assessment is a private, append-only event over a snapshot of a finding and
its claim evidence. It records evidence support, research value, pipeline
failure modes, claim fidelity, optional correction, reviewer, release, and
timestamp. The latest event is the active judgment; older events remain
available. Assessment data never enters the public read model automatically.

Evidence support and research value are intentionally separate: an accurate
finding may be banal, while a promising question may remain only partly
supported. Training exports must preserve these distinct targets.

## Status

- CORE — seeded, deterministic, or strongly supported material.
- SUGGESTED — a useful candidate generated by a model or heuristic.
- PRIVATE — malformed, rejected, irrelevant, or not included in the reader
  release.

Status is lightweight provenance, not a requirement for a complex review
workflow. During internal development, suggested material may appear when its
method and evidence are available.

## Search

Search covers preferred labels, historical forms, taxonomic names, and
eventually supporting records, induced senses, claims, and hypotheses. Results
must explain what matched and must not imply identity solely from similarity.
The active candidate retriever unions exact/normalized forms, OCR-aware lexical
search, and Gemini Embedding 2 dense search. It retains per-channel ranks and
scores and uses rank fusion only for ordering, not as historical confidence.

## Citation

Every displayed passage should expose:

- a stable internal URL;
- exact-edition metadata;
- date and language;
- printed page or scan leaf when available;
- bounded expanded context;
- original archive, PDF, or IIIF link;
- matched surface form and analysis status.

Use “earliest in this corpus,” not an unsupported claim of first use. Keep
frequency and comparison claims tied to the corpus represented.

## Initial topic set

The current test set contains independent entries:

1. Alligator
2. Cinchona bark
3. *Cinchona officinalis*
4. Água de Inglaterra
5. Engineer
6. Military engineer
7. Machine
8. Consciousness
9. Cosmos
10. *Homo sapiens*
11. Human species
12. Evolution
13. Transmutation of species
14. Genius
15. Intelligence
16. Mental measurement
17. Eugenics
18. Melancholy
19. Contagion
20. Electricity

Important distinctions remain:

- human species and *Homo sapiens* are linked but not automatically identical;
- evolution and transmutation remain separate;
- genius, intelligence, mental measurement, and eugenics remain separate;
- Água de Inglaterra is a cinchona preparation, not an alias;
- engineer cognates do not make “man of science” an alias;
- machine, consciousness, and melancholy require contextual sense analysis.

## Practical evaluation

Use a compact, representative set of historically meaningful positives, hard
negatives, and ambiguous cases. Compare candidate recall, typed-relation
accuracy, and usefulness of discovered connections. Do not hard-code a model or
universal threshold before comparison, and do not expand evaluation into a
separate workflow product.

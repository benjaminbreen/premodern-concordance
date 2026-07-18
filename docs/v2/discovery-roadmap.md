# Discovery roadmap

Status: project direction, not a fixed technical specification.

## North star

Premodern Concordance should do something full-text search cannot: discover how
scientific and medical terms, referents, senses, claims, and disagreements move
across languages and time.

Google Books and Internet Archive already find strings. This project should help
a researcher ask:

- What else was this called?
- Did the same word refer to different things?
- When did a sense appear, split, or disappear?
- Which claims traveled with a term?
- Who disagreed, qualified, or reframed those claims?
- Which related historical concepts are worth investigating without being
  treated as synonyms?

The eventual target is roughly 500 important texts and about 5,000 curated
anchor topics, expandable toward 10,000. Historical forms, induced senses,
claims, and candidate connections can be much more numerous.

## Core architecture

    Scans and OCR
          ↓
    Citable passages
          ↓
    Candidate usages
    lexical + fuzzy + multilingual retrieval
          ↓
    Typed usage graph
    forms · referents · senses · translations · contested identities
          ↓
    Historical claim graph
    assertions · denials · attributions · disagreements · citations
          ↓
    Topic pages and discovery reports
    changes · connections · controversies · evidence

### Corpus layer

Keep original text, page alignment, edition metadata, and scan links. Every
derived object must lead back to a passage.

### Topic and usage layer

An anchor topic is a stable research entry such as Cinchona bark, engineer,
consciousness, or *Homo sapiens*. Related subjects remain separate entries.

Each occurrence is also a contextual usage. Pairwise similarity and typed
relationship judgments connect usages into a graph that can be clustered into
historical senses across time and language.

### Claim layer

Extract structured claims from relevant passages:

- subject, predicate, and object;
- assertion, denial, qualification, or uncertainty;
- author and attributed authority;
- passage, source, date, and language.

Claims can then be linked as repetition, contradiction, qualification,
reframing, attribution, or possible transmission.

### Hypothesis layer

Agents and models can propose evidence-backed findings: an emerging sense, an
unexpected translation, a contested identity, a cross-language bridge, or a
historical disagreement. Hypotheses remain linked to supporting and conflicting
passages.

## Thin schema, thick graph

Do not build an exhaustive top-down ontology of every noun. Use a small set of
stable record and relationship types while allowing the evidence graph to grow.

Core records:

- source and passage;
- topic and historical form;
- contextual usage and induced sense;
- claim;
- typed edge;
- hypothesis;
- analysis run.

Relationship families:

- lexical: spelling variant, OCR variant, translation, cognate, derivation;
- referential: same referent, broader, narrower, part of, preparation of,
  contested identity;
- conceptual: overlap, analogy, influence, later reframing, contrast;
- argumentative: asserts, denies, qualifies, cites, attributes, disputes.

LLMs should make bounded local judgments and propose nodes or edges. They should
not be expected to produce a globally consistent ontology in one pass.

## Model strategy

Model choices are experiments, not architecture.

Candidate retrieval should compare an ensemble of:

- exact, fuzzy, morphological, and OCR-aware search;
- off-the-shelf multilingual embeddings;
- the existing fine-tuned BGE-M3 experiment;
- newer local retrieval or reranking models;
- LLM-generated historical query expansions.

The fine-tuned BGE model may be useful, replaceable, or unnecessary. Benchmark
it against current alternatives on contextual usages and hard negatives before
investing further. If fine-tuning helps, prefer passage-level historical
Word-in-Context and typed-relation objectives over label similarity alone.

Use inexpensive models for bounded extraction and classification. Use stronger
models selectively for difficult relations, cluster interpretation,
counterexample searches, and cross-source synthesis. Keep model IDs and prompts
versioned and configurable.

No runtime model calls are required for the reader application. Heavy analysis
runs offline and publishes materialized results.

## System shape

Research build:

- source files or object storage for OCR and scans;
- Parquet and DuckDB for passage, usage, and claim analysis;
- a replaceable vector index such as FAISS;
- relational edge tables for the graph;
- incremental, agent-operated scripts.

Reader application:

- Turso/libSQL materialized views;
- R2 for source text and page maps;
- Next.js on Vercel;
- precomputed findings, neighborhoods, timelines, and passages.

A dedicated graph database is not required unless ordinary edge tables become a
measured limitation.

## Reader workflow

Search remains the main entry point. A topic page should eventually offer:

1. **What the corpus suggests** — sourced findings and anomalies.
2. **Names and senses** — forms, languages, usage clusters, and change over time.
3. **Claims and disagreements** — what authors asserted, denied, or attributed.
4. **Connections** — typed paths to distinct topics.
5. **Evidence** — readable, citable passages and scans.

Candidate material is useful in this internal phase. Show why a link was
proposed, its type, evidence, confidence, and analysis provenance. Do not build
an elaborate review platform unless the research workflow demonstrates a need.

## Phases

### 0. Reader shell — complete

Search, topic, source, passage, citation, and deployment boundaries exist.

### 1. Typed historical usage graph

- Choose about 20 varied topics. **Complete.**
- Generate contextual usage candidates from the current corpus. **Complete for
  the first top-20 slice.**
- Compare lexical, off-the-shelf, fine-tuned, and LLM-assisted retrieval.
  **Lexical, Gemini dense, and hybrid compared; hybrid retained.**
- Type usage relationships and cluster senses across time and language.
- Materialize the results into the existing topic pages. **Complete for the
  first slice: contextual usages, claims, and entry-local senses are in public
  schema v6. Pairwise cross-entry usage edges remain later work.**

### 2. Claim and disagreement graph

- Extract structured claims for 5–10 topics. **Complete for 10 qualifying
  entries, using 206 claims.**
- Link agreement, contradiction, qualification, and attribution. **Complete in
  the first closed-set comparison.**
- Generate sourced findings and search for counterexamples. **42 findings are
  materialized; dedicated counterexample retrieval remains next.**
- Add findings and disagreements to the topic UI. **Complete.**

### 3. Open-world discovery

- Retain recurring unmatched usage and claim clusters.
- Propose new topics and relations from those clusters.
- Produce agentic discovery reports for a historian to explore.

### 4. Scale

- Expand incrementally toward 500 texts and 5,000 anchor topics.
- Reuse prior passage and claim analysis.
- Recompute affected graph neighborhoods rather than the whole corpus.
- Fine-tune or distill local models only when accumulated evidence shows value.

## Immediate milestone

Build the citable retrieval foundation, then Phase 1 as a vertical slice:

1. passageize the current complete texts with immutable offsets and scan/page
   ranges;
2. build the Gemini Embedding 2 passage index and OCR-aware lexical index;
3. retrieve candidates for the 20 trial topics and run known-passage recall
   checks;
4. add usage, usage-edge, sense-cluster, and analysis-run records;
5. construct usage graphs and materialize names, senses, claims, and
   connections in the existing UI.

Checkpoint: the first Gemini 3.1 Flash-Lite batch produced 373 validated passage
analyses; 292 relevant usages and 454 claims are materialized in the reader.
Entry-local induction groups 253 same-entry usages into 63 senses. Claim
comparison produced 42 suggested findings linked to 89 claims. The next
research operation is compact historian assessment, counterexample retrieval,
and targeted repair of weak cases—not another redesign of the upper schema.

The assessment workbench is now implemented. It captures finding-level support
and value, claim fidelity, and failure stages as append-only snapshots. The next
decision should come from the observed error distribution. Strong findings then
receive counterexample retrieval; the dominant failure layer is repaired before
the next corpus expansion.

Keep evaluation compact: a representative set of historian-meaningful examples,
candidate recall, typed-relation accuracy, and direct comparison of methods.
Testing should answer research questions, not become a separate bureaucracy.

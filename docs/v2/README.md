# Premodern Concordance V2

Status: active architecture contract.

The [discovery roadmap](discovery-roadmap.md) defines the research direction.
This document defines the V2 application and repository boundaries.
The [passage and retrieval contract](passage-retrieval.md) defines the active
corpus-foundation build.
The [historian assessment contract](historian-assessment.md) defines the
local-only finding review and durable evaluation export.

## Product

Premodern Concordance is a passage-centered research instrument for tracing
historical scientific and medical terminology across languages and time. It
should reveal names, referents, senses, claims, disagreements, and connections
that ordinary full-text search cannot organize.

The primary public object is a stable research entry or anchor topic, not an
automatically extracted noun. Related subjects remain separate entries joined
by typed, evidenced relationships.

The eventual target is about 500 digitization-ready texts from 1500–1950 and
roughly 5,000 anchor topics, expandable toward 10,000.

## Research and reader architecture

    Offline research build
    source files + passages + retrieval + embeddings + LLM analysis
                    |
                    | materialize a bounded release
                    v
    Reader data
    SQLite locally; Turso + R2 in production
                    |
                    v
    Next.js on Vercel
    read-only queries; no runtime corpus analysis

The offline build can be computationally ambitious. The deployed reader remains
small, fast, and inexpensive.

## Repository boundaries

    web/                         frozen prototype; localhost:3000
    apps/concordance/            V2 reader + local review UI; localhost:3001/apps/concordance
    pipeline/                    offline ingestion and research analysis
    var/                         ignored databases and staged releases
    docs/v2/                     roadmap, contracts, operations, and ledger

V2 must not import the prototype or legacy scripts as runtime dependencies.

V2 route files compose behavior but do not own SQL or business rules:

    routes → features and UI → contracts
    routes → repositories → database

Only the database client initializes libSQL. Public corpus SQL stays in
repositories; the explicitly local review store owns only its private review
schema and queries.
Client components may not import repositories, secrets, filesystem code, model
SDKs, or private pipeline modules.

## Reader workflow

The default path is:

1. search a modern or historical term;
2. open a topic or disambiguated sense;
3. inspect findings, names, senses, claims, and connections;
4. read and cite the supporting passages;
5. open the original edition or scan.

The current shell implements search, entries, passages, sources, context, and
citations. The discovery roadmap describes the analytical layers still to add.

## Evidence and uncertainty

- Every usage, claim, relationship, and hypothesis should lead back to a real
  passage.
- A surface form may resolve differently in different contexts.
- Similarity proposes a connection; it does not establish identity.
- Contested identity and conceptual proximity are typed relations, not merges.
- Candidate material is useful during internal development and may remain
  visible with method, confidence, and evidence.
- Keep review proportional to the demonstrated research need. The implemented
  finding workbench captures compact expert judgments without approval gates or
  public write paths.

## Visual identity

V2 preserves the prototype's restrained editorial design: system sans
typography, stone and ink neutrals, category accents, dark mode, archival cover
imagery, and the multilingual/typeface-changing title. Source passages use a
reading serif. Search remains the dominant action.

## Model policy

Model choices are replaceable experiments.

The [July 2026 relation-classification bake-off](model-bakeoff-2026-07.md)
currently favors Gemini 3.1 Flash-Lite for bounded offline judgments.

- The existing fine-tuned BGE-M3 model is a baseline, not a requirement.
- Compare lexical retrieval, current off-the-shelf models, fine-tuned models,
  rerankers, and LLM judgments on representative historical examples.
- Prefer contextual usage and typed-relation objectives over label similarity
  alone when fine-tuning.
- Use inexpensive models for bounded high-volume work and stronger models only
  where they produce a measured gain.
- Keep model IDs, prompts, and analysis runs configurable and attributable.
- Public browsing makes no model calls.

The current passage-retrieval default is Gemini Embedding 2 at 768 dimensions,
used offline with asymmetric query/document inputs. Hybrid retrieval combines
that dense index with exact, normalized, and OCR-aware lexical search. The
fine-tuned BGE-M3 model remains an entity-label experiment rather than the
default passage embedder.

## Scale and cost

- Keep corpus text, public JSON, and embeddings out of the Vercel artifact.
- Serve bounded database responses and object-storage excerpts.
- Precompute graphs, findings, and aggregates offline.
- Add sources and topics incrementally rather than rebuilding everything.
- Aim for negligible runtime model cost and inexpensive annual hosting.

## Working standard

Keep citations and stable identifiers correct. Use compact evaluations to choose
retrieval and analysis methods. Avoid speculative infrastructure, elaborate
review workflows, and large feature systems until a vertical research slice
shows they are needed.

Commands and credentials are in [operations.md](operations.md). Current state is
in [implementation-ledger.md](implementation-ledger.md). Record definitions are
in [data-contract.md](data-contract.md).

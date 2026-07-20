# V2 operations runbook

This runbook is the shortest safe path from private authoring data to the local
V2 application. Run commands from the paths shown; the legacy app in `web/` is
not modified or imported at runtime.

## First local release

From `pipeline/`:

```bash
PYTHONPATH=src python3 -m premodern.cli init
PYTHONPATH=src python3 -m premodern.cli seed-acceptance
PYTHONPATH=src python3 -m premodern.cli import-jamesiana
PYTHONPATH=src python3 -m premodern.cli publish --release-id v2-acceptance-001
PYTHONPATH=src python3 -m premodern.cli audit
```

## Corpus passage and retrieval build

The active offline build is incremental and does not publish the full private
corpus automatically:

```bash
cd pipeline
PYTHONPATH=src python3 -m premodern.cli init
PYTHONPATH=src python3 -m premodern.cli passageize-legacy
PYTHONPATH=src python3 -m premodern.cli audit-passages
PYTHONPATH=src python3 -m premodern.cli prepare-embeddings
PYTHONPATH=src python3 -m premodern.cli embed-standard
PYTHONPATH=src python3 -m premodern.cli build-retrieval --mode lexical --limit 100
PYTHONPATH=src python3 -m premodern.cli build-retrieval --mode dense --limit 100
PYTHONPATH=src python3 -m premodern.cli build-retrieval --mode hybrid --limit 100
PYTHONPATH=src python3 -m premodern.cli prepare-analysis --top-k 20
PYTHONPATH=src python3 -m premodern.cli submit-analysis
PYTHONPATH=src python3 -m premodern.cli analysis-status
PYTHONPATH=src python3 -m premodern.cli analysis-status --fetch
PYTHONPATH=src python3 -m premodern.cli prepare-senses
PYTHONPATH=src python3 -m premodern.cli submit-senses
PYTHONPATH=src python3 -m premodern.cli sense-status --fetch
PYTHONPATH=src python3 -m premodern.cli prepare-findings
PYTHONPATH=src python3 -m premodern.cli submit-findings
PYTHONPATH=src python3 -m premodern.cli findings-status --fetch
PYTHONPATH=src python3 -m premodern.cli publish --release-id v2-discovery-004
PYTHONPATH=src python3 -m premodern.cli audit
```

`passageize-legacy` reads the complete legacy source texts and cached Internet
Archive DJVU/Page Numbers artifacts, creates non-overlapping private passages,
and records alignment metrics. `audit-passages` checks boundaries, source
slices, ordering, page ranges, and scan URLs.

`prepare-embeddings` writes the exact Gemini Embedding 2 inputs and hashes under
`var/embeddings/`. Submitting or resuming the external batch is a separate
command so passage preparation is reproducible without a network call. The
public Vercel application never receives the resulting vector files or a model
key.

The prepared embedding build contains 16,270 passages and 20 entry queries at
768 dimensions and about 5.17M estimated tokens. That exceeds the embedding
Batch API's active queued-token cap, so the completed build used
`embed-standard`: a resumable standard-endpoint worker paced for the 3,000
contents/minute quota. It writes the same `vectors.npy`, `keys.json`, failure
log, hashes, and manifest as the batch fetcher. All 16,290 normalized vectors
are complete; estimated input cost was $1.03. Do not resubmit them.

The unused `submit-embeddings` and `embedding-status --fetch` path remains a
valid option for a future smaller batch. Any alternative embedder must preserve
the exact-input, key, vector, and manifest contract in a separate artifact
directory so comparisons remain real.

`build-retrieval` requires fetched vectors and produces dense/lexical reciprocal
rank fusion, per-channel ranks, a recall report, candidate JSONL, and a compact
historian packet under `var/retrieval/`. To reproduce the working pre-embedding
baseline, use:

```bash
PYTHONPATH=src python3 -m premodern.cli build-retrieval --lexical-only --limit 100
```

The weighted hybrid ranking is the default candidate source. Dense similarity
alone is not an identity decision and performed worse than lexical retrieval in
the first corpus comparison. `prepare-analysis` takes a bounded cutoff from the
hybrid candidate file and gives Gemini the target plus adjacent passages. Only
verbatim spans in the target can become evidence. `analysis-status --fetch`
downloads the batch, validates the JSON and evidence spans, records one model
run, and materializes contextual usages and up to two claims per passage in the
private authoring database. Raw prompts, responses, failures, warnings, hashes,
and aggregate counts remain under `var/analysis/` and are not published.

`prepare-senses` sends each entry's validated same-entry usages as one closed
set. The model may group only the supplied usage IDs; ingestion requires every
ID exactly once and stores compact entry-local sense clusters rather than a
global ontology. `prepare-findings` similarly sends only existing claims for
entries with at least two sources and four claims. It may return only controlled
finding and claim-role types and exact supplied claim IDs. Findings with fewer
than two claims or invalid contradiction/qualification roles are rejected.
Both stages are offline, resumable Batch jobs and retain their complete artifacts
under `var/`.

## Historian assessment

With the development reader running, open:

`http://localhost:3001/apps/concordance/review/findings`

The workbench records evidence support, historical value, failure modes,
claim-level fidelity, corrections, and notes. Each save appends a full snapshot
to `var/historian-reviews.sqlite`; revising an assessment does not erase the old
event. The normal production reader returns 404 for these routes.

To make the latest judgments available as versionable evaluation data:

```bash
cd pipeline
PYTHONPATH=src python3 -m premodern.cli export-reviews
```

The JSONL export and aggregate summary are written under `data/evaluation/` and
enriched with authoring model-run provenance. See
[historian-assessment.md](historian-assessment.md) before deriving training
data. The live review database remains private and is never deployed.

`seed-acceptance` is an adapter over citable legacy passages. It does not make
the legacy cluster JSON a V2 runtime dependency. `import-jamesiana` reads only
William Jamesiana's `dist/public-release/current.json` pointer and two
checksum-verified artifacts: `public-sources.json` and
`index.from-db.json.gz`. It never reads the Jamesiana authoring database or
embeddings. Only public 1500–1950 book/article-style sources with stable edition
URLs are eligible, and imported matches remain `SUGGESTED`.

The publisher validates referential integrity and evidence, constructs a new
allowlisted SQLite database, stages versioned source-text objects, records a
manifest and checksum, and then atomically promotes the release to
`var/public.sqlite` and `var/objects/`.

## Run and compare

From `apps/concordance/`:

```bash
npm install
npm run dev
```

V2 runs on `http://localhost:3001/apps/concordance` (the port root redirects
there). The unchanged legacy app continues to run from `web/` on
`http://localhost:3000`. This separate-process arrangement keeps dependencies,
routing, and deploy artifacts independent while the two versions are compared.

Before merging any V2 change:

```bash
npm run check
npm run build
```

From `pipeline/`, run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Production boundary

Vercel receives only `apps/concordance/`. It requires:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `R2_PUBLIC_BASE_URL`
- `NEXT_PUBLIC_CONCORDANCE_STANDALONE=1`

The promoted public SQLite file is uploaded to Turso. The contents of
`var/objects/` are uploaded under the same keys to a public or read-only R2
origin. The private `var/authoring.sqlite`, release staging directories, legacy
JSON, source PDFs, and embeddings are never deployed.

Vercel project root: `apps/concordance`. Framework preset: Next.js. No runtime
model key is required or permitted.

The standalone flag serves the deployed reader at `/`; leave it unset locally
to preserve the side-by-side `/apps/concordance` route. Use Git-linked previews
for deployment and promote the verified preview. Do not run a source upload
from the monorepo root: the repository contains large private/offline artifacts
that are outside the configured Vercel application root.

Current shared-reader resources (non-secret identifiers):

- Vercel project: `premodern-concordance`
- Turso database: `premodern-concordance-v2`
- R2 bucket: `premodern-concordance-sources`
- R2 origin: `https://pub-f4e25c9e98614a0cbacaac3f3ab54a16.r2.dev`

The Turso token configured in Vercel is read-only. The R2 objects use the same
`sources/...` keys and SHA-256 values recorded in the public release database.
The deployed project must not contain model API keys.

## Release and rollback

Never edit `var/public.sqlite` directly. Make changes in the authoring database,
publish under a new release ID, audit, and promote. A release directory is
immutable. Rollback means re-promoting a previously audited release database
and its matching object directory, then updating Turso/R2 from that release.

Restart the local Next.js process after promoting a new SQLite file so its
long-lived local libSQL connection opens the replacement database cleanly.

## Credential handoff

Creating the Turso database, R2 bucket/domain, and separate Vercel project is
the only stage that needs the owner's account authorization. Once those three
resources exist, an agent can upload releases, configure environment variables,
deploy, and run production smoke tests without changing the architecture.

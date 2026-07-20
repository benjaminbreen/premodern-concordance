# Historian assessment

Status: implemented for research findings.

## Purpose

Expert assessment should reveal which pipeline layer fails and create durable
evaluation data. It is not an approval bureaucracy and does not make a weak
result true by attaching an expert label.

The local workbench is:

`http://localhost:3001/apps/concordance/review/findings`

It is enabled automatically in development and hidden in production unless
`ENABLE_HISTORIAN_REVIEW=1`. It is not linked or writable in the normal public
deployment.

## What is recorded

Every save appends an event to `var/historian-reviews.sqlite` containing:

- the exact public release and complete finding snapshot;
- evidence support: supported, partial, unsupported, or unclear;
- research value: footnote-worthy, promising, known, banal, irrelevant, or
  unclear;
- zero or more pipeline failure modes;
- optional claim-level fidelity judgments;
- an optional corrected summary and concise diagnostic note;
- reviewer and timestamp.

Revising a judgment creates another event. The UI and export use the latest
event without deleting the history. Deferred findings remain distinct from
assessed findings.

## Durable export

The live database is ignored local state. Export the latest assessment per
finding from `pipeline/`:

```bash
PYTHONPATH=src python3 -m premodern.cli export-reviews
```

This writes:

- `data/evaluation/historian-findings-v1.jsonl`
- `data/evaluation/historian-findings-v1.summary.json`

The export retains snapshots and judgments and adds the finding model, run,
prompt, schema, and input/output hashes from the private authoring database.
Inspect the files before versioning them.

## Correct use

Do not create a generic `good/bad` dataset. Use each label for its own task:

| Judgment | Primary use |
| --- | --- |
| Passage or claim relevance | retrieval/reranking evaluation |
| Entry resolution failure | same-entry versus related classifier |
| Claim fidelity | claim extraction evaluation |
| Comparison validity | finding relation classifier |
| Corrected summary | supervised synthesis example |
| Research value | prioritization and historian-facing ranking |

Free-text notes help prompt and code repair but are not automatically suitable
as training rationales. Split future evaluation data by entry and source so the
same claims do not leak across training and evaluation.

The first 42 findings are enough to diagnose the pipeline and compare revisions.
They are not enough to justify fine-tuning a generative model. Review a
stratified sample of rejected and related-distinct usages before training any
accept/reject classifier, otherwise the dataset will contain selection bias.

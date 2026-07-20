from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.legacy import seed_acceptance_entries
from .adapters.jamesiana import import_public_release
from .analysis import (
    analysis_batch_status,
    artifact_dir as analysis_artifact_dir,
    fetch_analysis_batch,
    prepare_analysis_batch,
    submit_analysis_batch,
)
from .config import paths
from .db import apply_migrations, connect
from .embeddings import (
    artifact_dir,
    embedding_batch_status,
    embed_standard,
    fetch_embedding_batch,
    prepare_embedding_batch,
    submit_embedding_batch,
)
from .findings import (
    artifact_dir as findings_artifact_dir,
    fetch_findings_batch,
    findings_batch_status,
    prepare_findings_batch,
    submit_findings_batch,
)
from .passages import audit_passages, passageize_legacy_corpus
from .publication import audit_public_database, build_release, promote_release
from .retrieval import build_retrieval
from .reviews import export_historian_reviews
from .senses import (
    artifact_dir as sense_artifact_dir,
    fetch_sense_batch,
    prepare_sense_batch,
    sense_batch_status,
    submit_sense_batch,
)


def command_init() -> None:
    config = paths()
    connection = connect(config.authoring_db)
    migrations = apply_migrations(connection, config.authoring_migrations)
    connection.close()
    print(json.dumps({"authoring_db": str(config.authoring_db), "migrations": migrations}))


def command_publish(release_id: str | None, no_promote: bool) -> None:
    config = paths()
    manifest = build_release(config, release_id)
    result = {"manifest": manifest.__dict__}
    if not no_promote:
        result["promoted_to"] = str(promote_release(config, manifest.release_id))
        result["audit"] = audit_public_database(config.public_db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_audit() -> None:
    config = paths()
    print(json.dumps(audit_public_database(config.public_db), indent=2))


def command_seed_acceptance() -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = seed_acceptance_entries(
        connection,
        repository=config.repository,
        fixture_path=config.pipeline / "fixtures" / "acceptance_entries.json",
    )
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_import_jamesiana(public_release_root: str | None) -> None:
    config = paths()
    release_root = (
        Path(public_release_root).expanduser().resolve()
        if public_release_root
        else (config.repository.parent / "William Jamesiana" / "dist" / "public-release").resolve()
    )
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = import_public_release(connection, public_release_root=release_root)
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_passageize_legacy(source_id: str | None) -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = passageize_legacy_corpus(
        connection,
        repository=config.repository,
        output_dir=config.var / "page-maps",
        source_id=source_id,
    )
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_audit_passages() -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = audit_passages(connection)
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["errors"]:
        raise SystemExit(1)


def command_prepare_embeddings() -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = prepare_embedding_batch(
        connection,
        output_dir=artifact_dir(config.var),
    )
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_submit_embeddings() -> None:
    config = paths()
    result = submit_embedding_batch(
        repository=config.repository,
        output_dir=artifact_dir(config.var),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_embedding_status(fetch: bool) -> None:
    config = paths()
    function = fetch_embedding_batch if fetch else embedding_batch_status
    result = function(repository=config.repository, output_dir=artifact_dir(config.var))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_embed_standard(batch_size: int, minimum_interval: float) -> None:
    config = paths()
    result = embed_standard(
        repository=config.repository,
        output_dir=artifact_dir(config.var),
        batch_size=batch_size,
        minimum_interval_seconds=minimum_interval,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_build_retrieval(mode: str, lexical_only: bool, limit: int) -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = build_retrieval(
        connection,
        var_dir=config.var,
        mode="lexical" if lexical_only else mode,
        limit=limit,
    )
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_prepare_analysis(top_k: int) -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = prepare_analysis_batch(connection, var_dir=config.var, top_k=top_k)
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_submit_analysis() -> None:
    config = paths()
    result = submit_analysis_batch(
        repository=config.repository,
        output_dir=analysis_artifact_dir(config.var),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_analysis_status(fetch: bool) -> None:
    config = paths()
    output_dir = analysis_artifact_dir(config.var)
    if fetch:
        connection = connect(config.authoring_db)
        apply_migrations(connection, config.authoring_migrations)
        result = fetch_analysis_batch(
            connection,
            repository=config.repository,
            output_dir=output_dir,
        )
        connection.close()
    else:
        result = analysis_batch_status(repository=config.repository, output_dir=output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_prepare_senses(minimum_usages: int) -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = prepare_sense_batch(
        connection,
        var_dir=config.var,
        minimum_usages=minimum_usages,
    )
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_submit_senses() -> None:
    config = paths()
    result = submit_sense_batch(
        repository=config.repository,
        output_dir=sense_artifact_dir(config.var),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_sense_status(fetch: bool) -> None:
    config = paths()
    output_dir = sense_artifact_dir(config.var)
    if fetch:
        connection = connect(config.authoring_db)
        apply_migrations(connection, config.authoring_migrations)
        result = fetch_sense_batch(
            connection,
            repository=config.repository,
            output_dir=output_dir,
        )
        connection.close()
    else:
        result = sense_batch_status(repository=config.repository, output_dir=output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_prepare_findings(minimum_sources: int, minimum_claims: int) -> None:
    config = paths()
    connection = connect(config.authoring_db)
    apply_migrations(connection, config.authoring_migrations)
    result = prepare_findings_batch(
        connection,
        var_dir=config.var,
        minimum_sources=minimum_sources,
        minimum_claims=minimum_claims,
    )
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_submit_findings() -> None:
    config = paths()
    result = submit_findings_batch(
        repository=config.repository,
        output_dir=findings_artifact_dir(config.var),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_findings_status(fetch: bool) -> None:
    config = paths()
    output_dir = findings_artifact_dir(config.var)
    if fetch:
        connection = connect(config.authoring_db)
        apply_migrations(connection, config.authoring_migrations)
        result = fetch_findings_batch(
            connection,
            repository=config.repository,
            output_dir=output_dir,
        )
        connection.close()
    else:
        result = findings_batch_status(repository=config.repository, output_dir=output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_export_reviews(review_db: str | None, output: str) -> None:
    config = paths()
    review_path = (
        Path(review_db).expanduser().resolve()
        if review_db
        else (config.var / "historian-reviews.sqlite").resolve()
    )
    output_path = Path(output).expanduser()
    if not output_path.is_absolute():
        output_path = (config.repository / output_path).resolve()
    result = export_historian_reviews(
        review_db=review_path,
        authoring_db=config.authoring_db,
        output_path=output_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="premodern")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create or migrate the private authoring database")
    commands.add_parser(
        "seed-acceptance",
        help="Seed independent acceptance entries from citable legacy passages",
    )
    jamesiana = commands.add_parser(
        "import-jamesiana",
        help="Import suggestions from William Jamesiana's verified public release",
    )
    jamesiana.add_argument("--public-release-root")
    passageize = commands.add_parser(
        "passageize-legacy",
        help="Create stable page-aligned passages from complete legacy texts",
    )
    passageize.add_argument("--source-id")
    commands.add_parser(
        "audit-passages",
        help="Audit stable passage offsets, source slices, and scan ranges",
    )
    commands.add_parser(
        "prepare-embeddings",
        help="Write reproducible Gemini Embedding 2 passage and query batch inputs",
    )
    commands.add_parser(
        "submit-embeddings",
        help="Upload prepared inputs and submit a Gemini Embedding 2 batch job",
    )
    embedding_status = commands.add_parser(
        "embedding-status",
        help="Report the current embedding batch state and optionally fetch results",
    )
    embedding_status.add_argument("--fetch", action="store_true")
    standard_embeddings = commands.add_parser(
        "embed-standard",
        help="Embed prepared inputs with resumable standard Gemini requests",
    )
    standard_embeddings.add_argument("--batch-size", type=int, default=100)
    standard_embeddings.add_argument("--minimum-interval", type=float, default=2.1)
    retrieval = commands.add_parser(
        "build-retrieval",
        help="Build lexical or hybrid candidate rankings and recall reports",
    )
    retrieval.add_argument("--lexical-only", action="store_true")
    retrieval.add_argument("--mode", choices=("lexical", "dense", "hybrid"), default="hybrid")
    retrieval.add_argument("--limit", type=int, default=100)
    analysis = commands.add_parser(
        "prepare-analysis",
        help="Prepare bounded Gemini passage-usage and claim analysis inputs",
    )
    analysis.add_argument("--top-k", type=int, default=20)
    commands.add_parser(
        "submit-analysis",
        help="Upload and submit the prepared passage-analysis batch",
    )
    analysis_status = commands.add_parser(
        "analysis-status",
        help="Report the analysis batch state and optionally fetch/materialize results",
    )
    analysis_status.add_argument("--fetch", action="store_true")
    senses = commands.add_parser(
        "prepare-senses",
        help="Prepare closed-set entry-local sense clustering from grounded usages",
    )
    senses.add_argument("--minimum-usages", type=int, default=2)
    commands.add_parser(
        "submit-senses",
        help="Upload and submit the prepared sense-clustering batch",
    )
    sense_status = commands.add_parser(
        "sense-status",
        help="Report the sense batch state and optionally fetch/materialize results",
    )
    sense_status.add_argument("--fetch", action="store_true")
    findings = commands.add_parser(
        "prepare-findings",
        help="Prepare closed-set synthesis of claim-linked research findings",
    )
    findings.add_argument("--minimum-sources", type=int, default=2)
    findings.add_argument("--minimum-claims", type=int, default=4)
    commands.add_parser(
        "submit-findings",
        help="Upload and submit the prepared research-findings batch",
    )
    findings_status = commands.add_parser(
        "findings-status",
        help="Report the findings batch state and optionally fetch/materialize results",
    )
    findings_status.add_argument("--fetch", action="store_true")
    export_reviews = commands.add_parser(
        "export-reviews",
        help="Export the latest historian finding assessments as versionable JSONL",
    )
    export_reviews.add_argument("--review-db")
    export_reviews.add_argument(
        "--output",
        default="data/evaluation/historian-findings-v1.jsonl",
    )
    publish = commands.add_parser("publish", help="Build, validate, and promote a public release")
    publish.add_argument("--release-id")
    publish.add_argument("--no-promote", action="store_true")
    commands.add_parser("audit", help="Audit the promoted public database")
    return root


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "init":
        command_init()
    elif arguments.command == "seed-acceptance":
        command_seed_acceptance()
    elif arguments.command == "import-jamesiana":
        command_import_jamesiana(arguments.public_release_root)
    elif arguments.command == "passageize-legacy":
        command_passageize_legacy(arguments.source_id)
    elif arguments.command == "audit-passages":
        command_audit_passages()
    elif arguments.command == "prepare-embeddings":
        command_prepare_embeddings()
    elif arguments.command == "submit-embeddings":
        command_submit_embeddings()
    elif arguments.command == "embedding-status":
        command_embedding_status(arguments.fetch)
    elif arguments.command == "embed-standard":
        command_embed_standard(arguments.batch_size, arguments.minimum_interval)
    elif arguments.command == "build-retrieval":
        command_build_retrieval(arguments.mode, arguments.lexical_only, arguments.limit)
    elif arguments.command == "prepare-analysis":
        command_prepare_analysis(arguments.top_k)
    elif arguments.command == "submit-analysis":
        command_submit_analysis()
    elif arguments.command == "analysis-status":
        command_analysis_status(arguments.fetch)
    elif arguments.command == "prepare-senses":
        command_prepare_senses(arguments.minimum_usages)
    elif arguments.command == "submit-senses":
        command_submit_senses()
    elif arguments.command == "sense-status":
        command_sense_status(arguments.fetch)
    elif arguments.command == "prepare-findings":
        command_prepare_findings(arguments.minimum_sources, arguments.minimum_claims)
    elif arguments.command == "submit-findings":
        command_submit_findings()
    elif arguments.command == "findings-status":
        command_findings_status(arguments.fetch)
    elif arguments.command == "export-reviews":
        command_export_reviews(arguments.review_db, arguments.output)
    elif arguments.command == "publish":
        command_publish(arguments.release_id, arguments.no_promote)
    elif arguments.command == "audit":
        command_audit()


if __name__ == "__main__":
    main()

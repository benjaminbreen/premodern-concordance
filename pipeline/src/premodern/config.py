from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    repository: Path
    pipeline: Path
    var: Path
    authoring_db: Path
    public_db: Path
    releases: Path
    authoring_migrations: Path
    public_migrations: Path


def paths() -> Paths:
    pipeline_dir = Path(__file__).resolve().parents[2]
    repository = pipeline_dir.parent
    var_dir = Path(os.environ.get("PREMODERN_VAR_DIR", repository / "var")).resolve()
    return Paths(
        repository=repository,
        pipeline=pipeline_dir,
        var=var_dir,
        authoring_db=Path(
            os.environ.get("PREMODERN_AUTHORING_DB", var_dir / "authoring.sqlite")
        ).resolve(),
        public_db=Path(
            os.environ.get("PREMODERN_PUBLIC_DB", var_dir / "public.sqlite")
        ).resolve(),
        releases=(var_dir / "releases").resolve(),
        authoring_migrations=pipeline_dir / "migrations" / "authoring",
        public_migrations=pipeline_dir / "migrations" / "public",
    )

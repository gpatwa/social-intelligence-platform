"""CLI for the authenticated, idempotent pilot record append boundary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .record_append import (
    TOKEN_ENV,
    DatabricksSqlRecordStore,
    PrincipalAuthenticator,
    append_record,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Append a reviewed pilot artifact. The caller token is read from ${TOKEN_ENV}, never from arguments."
    )
    parser.add_argument("kind", choices=["review", "outcome", "experiment", "measurement"])
    parser.add_argument("input", type=Path, help="Compiled artifact JSON")
    parser.add_argument("--dry-run", action="store_true", help="Authenticate and validate without writing")
    args = parser.parse_args()
    artifact = json.loads(args.input.read_text(encoding="utf-8"))
    result = append_record(
        args.kind,
        artifact,
        token=os.environ.get(TOKEN_ENV),
        authenticator=PrincipalAuthenticator.from_environment(),
        store=DatabricksSqlRecordStore.from_environment(),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()

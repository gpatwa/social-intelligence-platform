"""CLI: load pilot topic labels from a CSV into ``reviewed_pilot_topic``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .pilot_labels import LABEL_SOURCES, PLATFORMS, LabelFileError, load_labels, parse_labels
from .record_append import ConflictError, DatabricksSqlRecordStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load pilot topic labels. Every label records who made it and whether that was a human or a model."
    )
    parser.add_argument("csv", type=Path, help="Labelled CSV with post_id, topic_label and audience_fit columns")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--labeller", required=True, help="Opaque labeller id (not an email address)")
    parser.add_argument("--label-source", required=True, choices=sorted(LABEL_SOURCES),
                        help="'human' only for labels a person verified; the quality gate counts human labels only")
    parser.add_argument("--labelled-on", required=True, type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="The day the labels were made; fixed so reloading the same file changes nothing")
    parser.add_argument("--dry-run", action="store_true", help="Validate and compare against the table without writing")
    args = parser.parse_args(argv)
    try:
        labels = parse_labels(
            args.csv.read_text(encoding="utf-8"), tenant_id=args.tenant, platform=args.platform,
            labeller_id=args.labeller, label_source=args.label_source, labelled_on=args.labelled_on,
        )
        result = load_labels(labels, DatabricksSqlRecordStore.from_environment(), dry_run=args.dry_run)
    except (LabelFileError, ConflictError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

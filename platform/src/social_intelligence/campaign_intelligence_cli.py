"""CLI for compile-only Campaign Intelligence v1 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .campaign_intelligence import (
    CampaignExperimentRequest,
    CampaignMeasurementRequest,
    create_campaign_experiment,
    measurement_to_outcome_signal,
    record_campaign_measurement,
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile non-mutating Campaign Intelligence v1 artifacts")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("experiment", help="Compile a draft campaign experiment from an approved review").add_argument("input", type=Path)
    commands.add_parser("measurement", help="Compile aggregate control/treatment outcome measurements").add_argument("input", type=Path)
    commands.add_parser("feedback", help="Extract an eligible offline reranking signal from a measurement").add_argument("input", type=Path)
    args = parser.parse_args()
    payload = _load(args.input)
    if args.command == "experiment":
        result = create_campaign_experiment(CampaignExperimentRequest(**payload))
    elif args.command == "measurement":
        result = record_campaign_measurement(CampaignMeasurementRequest(**payload))
    else:
        result = measurement_to_outcome_signal(payload)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()

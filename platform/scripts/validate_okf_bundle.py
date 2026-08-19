#!/usr/bin/env python3
"""Validate the repository's OKF profile and deterministic catalog."""

from __future__ import annotations

import argparse
from pathlib import Path

from social_intelligence.knowledge import validate_okf_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_okf_bundle(args.bundle)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OKF {args.bundle} is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

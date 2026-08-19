#!/usr/bin/env python3
"""Build or verify the deterministic discovery catalog for an OKF bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from social_intelligence.knowledge import CATALOG_FILENAME, render_catalog, write_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render_catalog(args.bundle)
    output = args.bundle / CATALOG_FILENAME
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            print(f"{output} is missing or out of date")
            return 1
        print(f"OKF catalog is current: {output}")
        return 0
    print(f"Wrote {write_catalog(args.bundle)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

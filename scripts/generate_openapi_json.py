#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OpenAPI JSON for the BayesianQC FastAPI app.")
    parser.add_argument(
        "--out",
        default="openapi.json",
        help="Output file path (default: openapi.json in current working directory)",
    )
    args = parser.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from app.main import app  # noqa: PLC0415 - import after sys.path adjustment

    schema = app.openapi()
    out_path = pathlib.Path(args.out)
    out_path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote OpenAPI schema to {out_path}")


if __name__ == "__main__":
    main()


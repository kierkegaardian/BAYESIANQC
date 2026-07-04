from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.demo_kiosk.generator import write_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic demo kiosk fixtures.")
    parser.add_argument("--check", action="store_true", help="Fail if committed demo kiosk fixtures are stale")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = write_outputs(check=args.check)
    if args.check:
        print(f"Demo kiosk fixtures current ({result['files']} files checked)")
    else:
        print(f"Demo kiosk fixtures written ({result['files']} files, {result['changed']} changed)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from package_archives import select_latest_from_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select the newest built package archive by pacman version")
    parser.add_argument("--package-dir", required=True, help="directory containing built .pkg.tar.* archives")
    parser.add_argument("--pkgname", help="expected package name inside the archive metadata")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="search recursively under --package-dir for built package archives",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_dir = Path(args.package_dir).resolve()
    selected = select_latest_from_dir(
        package_dir,
        pkgname=args.pkgname,
        recursive=args.recursive,
    )
    if selected is None:
        target = args.pkgname or "package archive"
        print(
            f"LATEST_PACKAGE_NOT_FOUND: {target} under {package_dir}",
            file=sys.stderr,
        )
        return 2
    print(selected.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

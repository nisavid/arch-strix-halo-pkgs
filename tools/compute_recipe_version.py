#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def compute_version(repo: Path, subdir: str, upstream_version: str) -> str:
    commit_count = git_output(repo, "rev-list", "--count", "HEAD", "--", subdir)
    latest = git_output(repo, "log", "-1", "--date=format:%Y%m%d", "--format=%cd %h", "--", subdir)
    if not latest:
        raise RuntimeError(f"no git history found for path '{subdir}' in {repo}")
    commit_date, short_sha = latest.split()
    return f"{upstream_version}.r{commit_count}.d{commit_date}.g{short_sha}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute recipe-derived pkgver suffixes")
    parser.add_argument("--recipe-root", required=True, help="git repo root containing the recipe")
    parser.add_argument("--recipe-subdir", default=".", help="path within the recipe repo to version against")
    parser.add_argument("--upstream-version", required=True, help="upstream/base version to prefix")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.recipe_root).resolve()
    try:
        print(compute_version(repo, args.recipe_subdir, args.upstream_version))
    except subprocess.CalledProcessError as exc:
        print(f"VERSION_COMPUTE_FAILED: git {' '.join(exc.cmd)}", file=sys.stderr)
        print("HINT: ensure the recipe root is a git repository and the subdir path is correct.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"VERSION_COMPUTE_FAILED: {exc}", file=sys.stderr)
        print("HINT: check that the target recipe subdir has committed history.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

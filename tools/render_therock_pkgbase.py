#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the TheRock split package base into packages/therock-gfx1151")
    parser.add_argument("--therock-root", default="/", help="filesystem root containing the staged opt/rocm tree")
    parser.add_argument("--recipe-root", required=True, help="git repo root containing the Strix Halo recipe")
    parser.add_argument("--recipe-subdir", default="strix-halo", help="path within the recipe repo used for pkgver tracking")
    parser.add_argument("--recipe-repo-url", default="https://github.com/paudley/ai-notes", help="canonical recipe repository URL")
    parser.add_argument("--recipe-author", default="Blackcat Informatics Inc.", help="recipe attribution string")
    parser.add_argument("--output", default="packages/therock-gfx1151", help="output directory relative to this repo")
    parser.add_argument("--policy", default="policies/therock-packages.toml", help="policy file relative to this repo")
    parser.add_argument("--template", default="templates/PKGBUILD.in", help="PKGBUILD template relative to this repo")
    args = parser.parse_args()

    here = repo_root()
    policy_path = here / args.policy
    template_path = here / args.template
    output_path = here / args.output
    recipe_root = Path(args.recipe_root).resolve()

    try:
        upstream_version = None
        for line in policy_path.read_text().splitlines():
            if line.startswith('pkgver = "'):
                upstream_version = line.split('"', 2)[1]
                break
        if not upstream_version:
            raise RuntimeError(f"could not determine upstream pkgver from {policy_path}")

        pkgver = subprocess.run(
            [
                sys.executable,
                str(here / "tools" / "compute_recipe_version.py"),
                "--recipe-root",
                str(recipe_root),
                "--recipe-subdir",
                args.recipe_subdir,
                "--upstream-version",
                upstream_version,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        latest = git_output(recipe_root, "log", "-1", "--date=format:%Y%m%d", "--format=%cd %h", "--", args.recipe_subdir)
        recipe_date, recipe_commit = latest.split()

        subprocess.run(
            [
                sys.executable,
                str(here / "generators" / "therock_split.py"),
                "--root",
                args.therock_root,
                "--policy",
                str(policy_path),
                "--template",
                str(template_path),
                "--output",
                str(output_path),
                "--pkgver-override",
                pkgver,
                "--recipe-repo-url",
                args.recipe_repo_url,
                "--recipe-subdir",
                args.recipe_subdir,
                "--recipe-author",
                args.recipe_author,
                "--recipe-commit",
                recipe_commit,
                "--recipe-date",
                recipe_date,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"THEROCK_RENDER_FAILED: {' '.join(map(str, exc.cmd))}", file=sys.stderr)
        print("HINT: fix the preceding generator/version error before promoting the TheRock package base.", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover
        print(f"THEROCK_RENDER_FAILED: {exc}", file=sys.stderr)
        print("HINT: verify the recipe repo path, policy file, and staged TheRock tree.", file=sys.stderr)
        return 2

    print(f"Rendered TheRock pkgbase into {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

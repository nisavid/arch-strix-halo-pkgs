#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
import sys
import subprocess
from pathlib import Path

from package_archives import PackageInfo, read_package_infos, select_latest_by_name, vercmp


DEFAULT_REPO_NAME = "strix-halo-gfx1151"
FOREIGN_REPO_NAMES = {"nisavid"}


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        try:
            if src.exists() and src.samefile(dst):
                return
        except OSError:
            pass
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def merge_package_sets(
    incoming: list[PackageInfo],
    existing: list[PackageInfo],
    *,
    incoming_authoritative: bool = False,
) -> dict[str, PackageInfo]:
    selected = select_latest_by_name(existing)
    incoming_selected = select_latest_by_name(incoming)
    if incoming_authoritative:
        selected.update(incoming_selected)
        return selected
    for pkg in incoming_selected.values():
        current = selected.get(pkg.pkgname)
        if current is None or vercmp(pkg.pkgver, current.pkgver) > 0:
            selected[pkg.pkgname] = pkg
    return selected


def expected_package_paths(package_dir: Path) -> list[Path]:
    result = subprocess.run(
        ["makepkg", "--packagelist"],
        cwd=str(package_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "PACKAGE_PACKAGELIST_FAILED: makepkg --packagelist exited "
            f"with status {result.returncode}: {result.stderr.strip()}"
        )
    paths = [
        (Path(line) if Path(line).is_absolute() else package_dir / line)
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    if not paths:
        raise RuntimeError(f"PACKAGE_PACKAGELIST_EMPTY: {package_dir}")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "PACKAGE_ARCHIVE_MISSING: current PKGBUILD expects missing archive(s): "
            + ", ".join(str(path) for path in missing)
        )
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate a local pacman repo from built package archives")
    parser.add_argument("--package-dir", required=True, help="directory containing built .pkg.tar.* archives")
    parser.add_argument("--repo-dir", required=True, help="destination repo directory")
    parser.add_argument("--repo-name", default=DEFAULT_REPO_NAME, help="repo database basename")
    parser.add_argument(
        "--allow-foreign-repo-name",
        action="store_true",
        help="allow a repo database basename that is known to belong to another local repo",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="search recursively under --package-dir for built package archives",
    )
    parser.add_argument(
        "--require-packagelist",
        action="store_true",
        help="publish only archives named by makepkg --packagelist for the current PKGBUILD",
    )
    return parser.parse_args()


def validate_repo_name(repo_name: str, *, allow_foreign: bool = False) -> None:
    if allow_foreign or repo_name not in FOREIGN_REPO_NAMES:
        return
    raise RuntimeError(
        "PACMAN_REPO_NAME_REFUSED: this repo defaults to "
        f"{DEFAULT_REPO_NAME!r}; refusing foreign repo database basename "
        f"{repo_name!r}. Pass --allow-foreign-repo-name to override intentionally."
    )


def main() -> int:
    args = parse_args()
    try:
        validate_repo_name(args.repo_name, allow_foreign=args.allow_foreign_repo_name)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2
    package_dir = Path(args.package_dir).resolve()
    repo_dir = Path(args.repo_dir).resolve()
    repo_dir.mkdir(parents=True, exist_ok=True)

    if args.require_packagelist:
        try:
            package_infos = read_package_infos(expected_package_paths(package_dir))
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 2
    else:
        package_iter = package_dir.rglob("*.pkg.tar.*") if args.recursive else package_dir.glob("*.pkg.tar.*")
        package_infos = read_package_infos(package_iter)
    if not package_infos:
        print(f"PACMAN_REPO_UPDATE_FAILED: no package archives found in {package_dir}", file=sys.stderr)
        print("HINT: build the package base first so .pkg.tar.zst artifacts exist.", file=sys.stderr)
        return 2

    existing_infos = read_package_infos(repo_dir.glob("*.pkg.tar.*"))
    selected = merge_package_sets(
        package_infos,
        existing_infos,
        incoming_authoritative=args.require_packagelist,
    )

    staged = []
    selected_names = {pkg.path.name for pkg in selected.values()}
    for existing in repo_dir.glob("*.pkg.tar.*"):
        if existing.name not in selected_names:
            existing.unlink()

    for pkg in sorted(selected.values(), key=lambda item: item.path.name):
        dst = repo_dir / pkg.path.name
        link_or_copy(pkg.path, dst)
        staged.append(dst)

    db_path = repo_dir / f"{args.repo_name}.db.tar.zst"
    files_path = repo_dir / f"{args.repo_name}.files.tar.zst"
    for path in (db_path, files_path):
        if path.exists():
            path.unlink()

    subprocess.run(
        ["repo-add", str(db_path), *[str(pkg) for pkg in staged]],
        check=True,
    )
    print(f"Updated pacman repo {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

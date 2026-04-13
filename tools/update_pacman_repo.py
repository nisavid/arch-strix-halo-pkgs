#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


class PackageInfo(NamedTuple):
    path: Path
    pkgname: str
    pkgver: str


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def read_pkginfo(path: Path) -> PackageInfo:
    result = subprocess.run(
        ["bsdtar", "-xOf", str(path), ".PKGINFO"],
        check=True,
        capture_output=True,
        text=True,
    )
    pkgname = None
    pkgver = None
    for line in result.stdout.splitlines():
        if line.startswith("pkgname = "):
            pkgname = line.split(" = ", 1)[1]
        elif line.startswith("pkgver = "):
            pkgver = line.split(" = ", 1)[1]
    if not pkgname or not pkgver:
        raise RuntimeError(f"PACKAGE_METADATA_MISSING: {path}")
    return PackageInfo(path=path, pkgname=pkgname, pkgver=pkgver)


def vercmp(a: str, b: str) -> int:
    result = subprocess.run(
        ["vercmp", a, b],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate a local pacman repo from built package archives")
    parser.add_argument("--package-dir", required=True, help="directory containing built .pkg.tar.* archives")
    parser.add_argument("--repo-dir", required=True, help="destination repo directory")
    parser.add_argument("--repo-name", default="strix-halo-gfx1151", help="repo database basename")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="search recursively under --package-dir for built package archives",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_dir = Path(args.package_dir).resolve()
    repo_dir = Path(args.repo_dir).resolve()
    repo_dir.mkdir(parents=True, exist_ok=True)

    package_iter = package_dir.rglob("*.pkg.tar.*") if args.recursive else package_dir.glob("*.pkg.tar.*")
    package_infos = [
        read_pkginfo(pkg) for pkg in sorted(
            pkg for pkg in package_iter
            if pkg.is_file() and ".db.tar." not in pkg.name and ".files.tar." not in pkg.name
        )
    ]
    if not package_infos:
        print(f"PACMAN_REPO_UPDATE_FAILED: no package archives found in {package_dir}", file=sys.stderr)
        print("HINT: build the package base first so .pkg.tar.zst artifacts exist.", file=sys.stderr)
        return 2

    selected: dict[str, PackageInfo] = {}
    for pkg in package_infos:
        current = selected.get(pkg.pkgname)
        if current is None or vercmp(pkg.pkgver, current.pkgver) > 0:
            selected[pkg.pkgname] = pkg

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

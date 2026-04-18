from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, NamedTuple


class PackageInfo(NamedTuple):
    path: Path
    pkgname: str
    pkgver: str


def is_package_archive(path: Path) -> bool:
    return (
        path.is_file()
        and ".pkg.tar." in path.name
        and ".db.tar." not in path.name
        and ".files.tar." not in path.name
    )


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


def read_package_infos(paths: Iterable[Path]) -> list[PackageInfo]:
    return [read_pkginfo(path) for path in sorted(path for path in paths if is_package_archive(path))]


def select_latest_by_name(package_infos: list[PackageInfo]) -> dict[str, PackageInfo]:
    selected: dict[str, PackageInfo] = {}
    for pkg in package_infos:
        current = selected.get(pkg.pkgname)
        if current is None or vercmp(pkg.pkgver, current.pkgver) > 0:
            selected[pkg.pkgname] = pkg
    return selected


def read_package_infos_from_dir(package_dir: Path, recursive: bool = False) -> list[PackageInfo]:
    iterator = package_dir.rglob("*.pkg.tar.*") if recursive else package_dir.glob("*.pkg.tar.*")
    return read_package_infos(iterator)


def select_latest_from_dir(
    package_dir: Path,
    pkgname: str | None = None,
    recursive: bool = False,
) -> PackageInfo | None:
    selected = select_latest_by_name(read_package_infos_from_dir(package_dir, recursive=recursive))
    if pkgname is not None:
        return selected.get(pkgname)
    if not selected:
        return None
    if len(selected) != 1:
        names = ", ".join(sorted(selected))
        raise RuntimeError(
            f"AMBIGUOUS_PACKAGE_DIR: {package_dir} contains multiple package names ({names}); "
            "pass pkgname explicitly"
        )
    return next(iter(selected.values()))

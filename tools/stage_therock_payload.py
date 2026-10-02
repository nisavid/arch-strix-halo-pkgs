#!/usr/bin/env python3
"""Fetch, verify, and extract the pinned TheRock dist tarball into a stage.

The pin (URL, sha256, size) lives in the ``[payload]`` table of
``policies/therock-packages.toml``. The tarball root is the ROCm prefix
itself, so it is extracted into ``<stage>/opt/rocm``. The resulting stage is
the ``--stage`` input for ``tools/stage_migraphx_for_therock.zsh``, the
``--therock-root`` input for ``tools/render_therock_pkgbase.py``, and the
``_THEROCK_ROOT`` input for the split-package build.

Disk: the 7.14.1 tarball is 1.6 GiB and the extracted stage is about 8.3 GiB.
Pass ``--remove-tarball`` to drop the verified tarball after extraction.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path


STAGE_ENV_VAR = "THEROCK_STAGE_ROOT"
DOWNLOAD_ENV_VAR = "THEROCK_DOWNLOAD_DIR"
CHUNK = 1 << 20


class StageError(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_payload_pin(policy_path: Path) -> dict:
    with policy_path.open("rb") as fh:
        policy = tomllib.load(fh)
    payload = policy.get("payload")
    if not isinstance(payload, dict):
        raise StageError(f"PAYLOAD_PIN_MISSING: no [payload] table in {policy_path}")
    for key in ("url", "sha256"):
        if not payload.get(key):
            raise StageError(f"PAYLOAD_PIN_MISSING: [payload].{key} is empty in {policy_path}")
    return {
        "url": str(payload["url"]),
        "sha256": str(payload["sha256"]).lower(),
        "size": int(payload.get("size", 0)),
        "pkgver": str(policy.get("repo", {}).get("pkgver", "")),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify_tarball(path: Path, pin: dict) -> None:
    if pin["size"] and path.stat().st_size != pin["size"]:
        raise StageError(
            f"PAYLOAD_SIZE_MISMATCH: {path} is {path.stat().st_size} bytes, pinned size is {pin['size']}"
        )
    actual = sha256_file(path)
    if actual != pin["sha256"]:
        raise StageError(f"PAYLOAD_SHA256_MISMATCH: {path} has sha256 {actual}, pinned sha256 is {pin['sha256']}")


def download(url: str, destination: Path) -> None:
    partial = destination.with_name(destination.name + ".part")
    print(f"==> downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, CHUNK)
    partial.replace(destination)


def resolve_tarball(pin: dict, download_dir: Path, tarball: Path | None) -> Path:
    if tarball is not None:
        if not tarball.is_file():
            raise StageError(f"PAYLOAD_TARBALL_MISSING: {tarball}")
        verify_tarball(tarball, pin)
        return tarball

    download_dir.mkdir(parents=True, exist_ok=True)
    name = pin["url"].rstrip("/").rsplit("/", 1)[-1]
    cached = download_dir / name
    if cached.is_file():
        try:
            verify_tarball(cached, pin)
            print(f"==> reusing verified tarball {cached}")
            return cached
        except StageError as exc:
            print(f"==> discarding cached tarball: {exc}")
            cached.unlink()
    download(pin["url"], cached)
    verify_tarball(cached, pin)
    return cached


def extract(tarball: Path, stage: Path, *, force: bool) -> Path:
    rocm = stage / "opt" / "rocm"
    if rocm.exists() and any(rocm.iterdir()):
        if not force:
            raise StageError(f"STAGE_NOT_EMPTY: {rocm} already exists; pass --force to replace it")
        print(f"==> removing existing {rocm}")
        shutil.rmtree(rocm)
    partial = stage / "opt" / "rocm.partial"
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    print(f"==> extracting {tarball.name} into {rocm}")
    subprocess.run(
        ["tar", "--extract", "--no-same-owner", "--file", str(tarball), "--directory", str(partial)],
        check=True,
    )
    if rocm.exists():
        rocm.rmdir()
    partial.rename(rocm)
    return rocm


def check_version(rocm: Path, pkgver: str) -> str:
    version_file = rocm / ".info" / "version"
    if not version_file.is_file():
        raise StageError(f"PAYLOAD_LAYOUT_UNEXPECTED: {version_file} is missing; is the tarball root the ROCm prefix?")
    version = version_file.read_text().strip()
    if pkgver and version != pkgver:
        raise StageError(f"PAYLOAD_VERSION_MISMATCH: {version_file} says {version}, policy pkgver is {pkgver}")
    return version


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch the pinned TheRock dist tarball, verify its sha256, and extract it into <stage>/opt/rocm",
    )
    parser.add_argument(
        "--stage",
        default=os.environ.get(STAGE_ENV_VAR),
        help=f"staged filesystem root to create; defaults to ${STAGE_ENV_VAR}",
    )
    parser.add_argument(
        "--download-dir",
        default=os.environ.get(DOWNLOAD_ENV_VAR),
        help=f"tarball cache directory; defaults to ${DOWNLOAD_ENV_VAR} or <stage>.download",
    )
    parser.add_argument("--tarball", help="use an already downloaded tarball instead of fetching the pinned URL")
    parser.add_argument("--policy", default="policies/therock-packages.toml", help="policy file relative to this repo")
    parser.add_argument("--force", action="store_true", help="replace an existing <stage>/opt/rocm")
    parser.add_argument(
        "--remove-tarball",
        action="store_true",
        help="delete the downloaded tarball after a successful extraction (never deletes a --tarball input)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.stage:
        print(f"STAGE_ROOT_MISSING: pass --stage or set {STAGE_ENV_VAR}", file=sys.stderr)
        return 2
    stage = Path(args.stage).expanduser().resolve()
    download_dir = (
        Path(args.download_dir).expanduser().resolve()
        if args.download_dir
        else stage.with_name(stage.name + ".download")
    )
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = repo_root() / policy_path

    supplied = Path(args.tarball).expanduser().resolve() if args.tarball else None
    try:
        pin = load_payload_pin(policy_path)
        tarball = resolve_tarball(pin, download_dir, supplied)
        rocm = extract(tarball, stage, force=args.force)
        version = check_version(rocm, pin["pkgver"])
        if args.remove_tarball and supplied is None:
            print(f"==> removing {tarball}")
            tarball.unlink()
    except (StageError, subprocess.CalledProcessError, OSError) as exc:
        print(f"THEROCK_STAGE_FAILED: {exc}", file=sys.stderr)
        return 2

    print(f"Staged TheRock {version} at {rocm}")
    print(f"Next: tools/stage_migraphx_for_therock.zsh --stage {stage}")
    print(f"Dry render before MIGraphX: python tools/render_therock_pkgbase.py --therock-root {stage} "
          "--output <scratch-dir> --pre-migraphx-dry-render")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

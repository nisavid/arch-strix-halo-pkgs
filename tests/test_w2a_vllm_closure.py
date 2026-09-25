"""The W2A vLLM lease-job closure (#110, #111).

The vLLM lease job builds the small closure packages in the generation-C root
before vLLM itself. These tests pin what that job relies on: the rebuilt
packages carry a new pkgrel, the Rust build stays inside $srcdir, and every
makedepend is named in the targets files the vLLM root is resolved from.
"""

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDROOT = REPO_ROOT / "tools/buildroot"

# The vLLM root is torch-chain + model-closure + vllm-build
# (docs/maintainers/c-build-root.md).
VLLM_ROOT_TARGETS = ("torch-chain.targets", "model-closure.targets", "vllm-build.targets")

# Existing ASHP vLLM depends that the lease job rebuilds unchanged.
REBUILDS = {
    "python-uvloop-gfx1151": ("0.22.1", "2"),
    "python-httptools-gfx1151": ("0.8.0", "2"),
    "python-msgspec-gfx1151": ("0.21.1", "2"),
    "python-openai-harmony-gfx1151": ("0.0.8", "2"),
}

LEASE_JOB_PACKAGES = [
    *REBUILDS,
    "python-einops-gfx1151",
    "python-py-cpuinfo-gfx1151",
    "python-pybase64-gfx1151",
    "python-model-hosting-container-standards-gfx1151",
    "python-prometheus-fastapi-instrumentator-gfx1151",
    "python-vllm-rocm-gfx1151",
]

# makedepends that a root target satisfies under another name.
PROVIDED_BY = {
    # The targets floor rust so a host rustup cannot stand in for it; Arch
    # rust also provides cargo.
    "rust": "rust>=1:1.90",
    "cargo": "rust>=1:1.90",
    "gcc": "base-devel",
    "perl": "base-devel",  # autoconf and automake depend on perl
    "make": "base-devel",
}


def pkgbuild_value(package: str, expr: str) -> list[str]:
    pkgbuild = REPO_ROOT / "packages" / package / "PKGBUILD"
    script = f'source "$1" && printf "%s\\n" {expr}'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(pkgbuild)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def root_targets() -> set[str]:
    targets = set()
    for name in VLLM_ROOT_TARGETS:
        for line in (BUILDROOT / name).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                targets.add(line)
    return targets


@pytest.mark.parametrize("package", sorted(REBUILDS))
def test_rebuilds_keep_the_source_and_bump_pkgrel(package):
    # The source is unchanged; pkgrel 2 keeps the generation-C build apart
    # from the previous generation's 0.x-1 in the host repo.
    pkgver, pkgrel = REBUILDS[package]
    assert pkgbuild_value(package, '"$pkgver"') == [pkgver]
    assert pkgbuild_value(package, '"$pkgrel"') == [pkgrel]


def test_openai_harmony_keeps_cargo_and_rustup_inside_srcdir():
    text = (REPO_ROOT / "packages/python-openai-harmony-gfx1151/PKGBUILD").read_text()

    # w2a-build.sh passes CARGO_HOME=/ccache/cargo; the PKGBUILD must
    # override it so crates land under $srcdir, and rustup must never
    # download a toolchain.
    assert 'export CARGO_HOME="$srcdir/.cargo"' in text
    assert "export RUSTUP_AUTO_INSTALL=0" in text
    assert text.index("export RUSTUP_AUTO_INSTALL=0") < text.index("python -m build")


@pytest.mark.parametrize("package", LEASE_JOB_PACKAGES)
def test_lease_job_makedepends_are_in_the_vllm_root_targets(package):
    targets = root_targets()
    missing = []
    for dep in pkgbuild_value(package, '"${makedepends[@]}"'):
        if dep in targets or PROVIDED_BY.get(dep) in targets:
            continue
        missing.append(dep)
    assert missing == []

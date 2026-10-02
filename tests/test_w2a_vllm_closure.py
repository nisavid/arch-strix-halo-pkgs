"""The W2A vLLM lease-job closure (#110, #111).

The vLLM lease job builds the small closure packages in the generation-C root
before vLLM itself. These tests pin what that job relies on: the rebuilt
packages carry a new pkgrel, the Rust build stays inside $srcdir, and every
makedepend is named in the targets files the vLLM root is resolved from.
"""

import subprocess
import tomllib
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

# The lease job's build order (docs/maintainers/c-build-root.md): each
# package is published to ashp-w2a and added to the root before the next one,
# so a later package may build against an earlier one.
LEASE_JOB_PACKAGES = [
    "python-py-cpuinfo-gfx1151",
    "python-einops-gfx1151",
    "python-prometheus-fastapi-instrumentator-gfx1151",
    "python-msgspec-gfx1151",
    "python-httptools-gfx1151",
    "python-uvloop-gfx1151",
    "python-pybase64-gfx1151",
    "python-openai-harmony-gfx1151",
    "python-apache-tvm-ffi-gfx1151",
    "python-xgrammar-gfx1151",
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
def test_lease_job_makedepends_are_in_the_root_before_the_build(package):
    targets = root_targets()
    built_earlier = set(LEASE_JOB_PACKAGES[: LEASE_JOB_PACKAGES.index(package)])
    missing = []
    for dep in pkgbuild_value(package, '"${makedepends[@]}"'):
        if dep in targets or dep in built_earlier or PROVIDED_BY.get(dep) in targets:
            continue
        missing.append(dep)
    assert missing == []


def test_lease_job_covers_the_rebuilds():
    assert set(REBUILDS) <= set(LEASE_JOB_PACKAGES)


def test_build_order_doc_matches_the_lease_job():
    doc = (REPO_ROOT / "docs/maintainers/c-build-root.md").read_text()
    section = doc.split("## W2A vLLM lease job closure", 1)[1]
    order = [
        line.split()[1]
        for line in section.split("```sh", 1)[1].split("```", 1)[0].splitlines()
        if line.startswith("w2a-build.sh ")
    ]

    assert order == LEASE_JOB_PACKAGES


def test_vllm_depends_on_every_lease_job_runtime_lane():
    # apache-tvm-ffi is xgrammar's dependency; vLLM never imports tvm_ffi.
    depends = set(pkgbuild_value("python-vllm-rocm-gfx1151", '"${depends[@]}"'))
    transitive = {"python-vllm-rocm-gfx1151", "python-apache-tvm-ffi-gfx1151"}

    assert set(LEASE_JOB_PACKAGES) - transitive <= depends


def test_the_root_has_ps_for_the_scenario_runner():
    # tools/inference/runner.py runs `ps -eo ...` before each vLLM scenario to
    # find stale engine cores, so the in-root runner fails without procps-ng.
    assert "procps-ng" in root_targets()


def test_the_sagemaker_standards_lane_is_gone():
    # The 0016 carry makes model_hosting_container_standards optional, so the
    # lane that an earlier W2A lease-job commit in #174 added is not part of
    # the required runtime set. It stays a #110 gap (optdepend once packaged),
    # not a lane.
    name = "python-model-hosting-container-standards-gfx1151"
    recipe = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())
    freshness = tomllib.loads((REPO_ROOT / "policies/package-freshness.toml").read_text())
    ledger = tomllib.loads(
        (REPO_ROOT / "docs/maintainers/update-candidates.toml").read_text()
    )

    assert not (REPO_ROOT / "packages" / name).exists()
    assert name not in recipe["packages"]
    assert "model_hosting_container_standards" not in freshness["families"]
    assert not [
        key
        for key, candidate in ledger["candidates"].items()
        if candidate.get("family") == "model_hosting_container_standards"
    ]
    # Its runtime closure (jmespath and the supervisor daemon) leaves the root.
    assert not {"python-jmespath", "supervisor"} & root_targets()


@pytest.mark.parametrize(
    ("family", "package", "selected", "reviewed_latest"),
    [
        ("apache_tvm_ffi", "python-apache-tvm-ffi-gfx1151", "0.1.10", "0.1.14.post1"),
        ("xgrammar", "python-xgrammar-gfx1151", "0.2.3", "0.2.8"),
    ],
)
def test_xgrammar_lanes_record_their_selected_and_newer_releases(
    family, package, selected, reviewed_latest
):
    # The pins lag PyPI on purpose: the selected release is tracked on #110
    # until it is built and smoked, and the newer release is rejected for this
    # vLLM line so the freshness sweep does not reopen it.
    freshness = tomllib.loads((REPO_ROOT / "policies/package-freshness.toml").read_text())
    ledger = tomllib.loads(
        (REPO_ROOT / "docs/maintainers/update-candidates.toml").read_text()
    )["candidates"]

    pypi = next(
        check for check in freshness["families"][family]["checks"] if check["id"] == "pypi"
    )
    assert pypi["recorded"] == selected
    assert pkgbuild_value(package, '"$pkgver"') == [selected]

    records = {
        candidate["latest"]: candidate
        for candidate in ledger.values()
        if candidate["family"] == family
    }
    assert records[selected]["disposition"] == "tracked"
    assert records[selected]["next_gate_issue"] == 110
    assert records[reviewed_latest]["disposition"] == "rejected"
    assert records[reviewed_latest]["previous_recorded"] == selected
    assert records[reviewed_latest]["next_gate_kind"] == "none"

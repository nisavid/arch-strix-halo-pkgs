"""The generation-C model closure move (#183).

Transformers 5.16.1 and 5.17.0 require huggingface-hub <2.0 and fail at
import beside hub 2.x, and the 5.16.1-1 and 0.23.2-1 W2A builds depend on an
unversioned python-huggingface-hub. These tests pin what keeps that pair out
of a build-root lock: the floors in `model-closure.targets`, and the hub range
the 5.18.0 and 0.23.3 packages declare with Arch's epoch.
"""

import importlib.util
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = REPO_ROOT / "tools/buildroot/model-closure.targets"
MODULE_PATH = REPO_ROOT / "tools/c_buildroot.py"
SPEC = importlib.util.spec_from_file_location("c_buildroot_closure_move", MODULE_PATH)
assert SPEC and SPEC.loader
cbr = importlib.util.module_from_spec(SPEC)
sys.modules["c_buildroot_closure_move"] = cbr
SPEC.loader.exec_module(cbr)

TRANSFORMERS = "python-transformers-gfx1151"
TOKENIZERS = "python-tokenizers-gfx1151"
HUB = "python-huggingface-hub"
# The W2A builds that the closure move replaces.
STALE = {
    TRANSFORMERS: ("5.16.1-1", [HUB, TOKENIZERS]),
    TOKENIZERS: ("0.23.2-1", []),
}


def pkgbuild_value(package: str, expr: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" {expr}'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(REPO_ROOT / "packages" / package / "PKGBUILD")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def closure_targets() -> list[str]:
    lines = (line.split("#", 1)[0].strip() for line in TARGETS.read_text().splitlines())
    return [line for line in lines if line]


def published() -> dict[str, tuple[str, list[str]]]:
    return {
        package: (
            pkgbuild_value(package, '"$pkgver-$pkgrel"')[0],
            pkgbuild_value(package, '"${depends[@]}"'),
        )
        for package in (TRANSFORMERS, TOKENIZERS)
    }


def desc(name: str, version: str, depends=()) -> str:
    blocks = [
        ("FILENAME", [f"{name}-{version}-any.pkg.tar.zst"]),
        ("NAME", [name]),
        ("VERSION", [version]),
        ("DEPENDS", list(depends)),
    ]
    return "\n\n".join(f"%{k}%\n" + "\n".join(v) for k, v in blocks if v) + "\n"


def write_db(path: Path, packages: dict[str, tuple[str, list[str]]]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, (version, depends) in packages.items():
            data = desc(name, version, depends).encode()
            info = tarfile.TarInfo(f"{name}-{version}/desc")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def lock_problems(tmp_path, targets, w2a, *, hub="1:2.1.1-1"):
    """Resolve TARGETS over a W2A repo and a userland repo.

    The userland repo holds huggingface-hub at HUB and a stub, at its floor,
    for every other name the targets and the W2A packages ask for.
    """
    wanted = list(targets) + [dep for _, depends in w2a.values() for dep in depends]
    userland = {}
    for dep in wanted:
        name, _, want = cbr.split_dep(dep)
        if name not in w2a and name != HUB:
            userland.setdefault(name, (f"{want}-1" if want else "1-1", []))
    userland[HUB] = (hub, [])
    repos = [
        ("ashp-w2a", cbr.read_db(write_db(tmp_path / "w2a.db", w2a), "ashp-w2a")),
        ("extra", cbr.read_db(write_db(tmp_path / "extra.db", userland), "extra")),
    ]
    lock = cbr.resolve(targets, cbr.ResolveConfig(repos=repos, foundation=["ashp-w2a"]))
    # No archive exists in this fake world, so every package is a file to fetch.
    return lock, [p for p in lock["problems"] if p["kind"] != "missing-file"]


def test_targets_floor_the_packaged_versions_and_hub_2():
    targets = closure_targets()
    versions = {package: pkgver.rsplit("-", 1)[0] for package, (pkgver, _) in published().items()}

    assert f"{TRANSFORMERS}>={versions[TRANSFORMERS]}" in targets
    assert f"{TOKENIZERS}>={versions[TOKENIZERS]}" in targets
    # An unfloored name would let the stale build satisfy the target.
    assert TRANSFORMERS not in targets
    assert TOKENIZERS not in targets
    hub = [cbr.split_dep(t) for t in targets if cbr.split_dep(t)[0] == HUB]
    assert [(op, want) for _, op, want in hub] == [(">=", "1:2.1.1")]
    # hub 2.x's runtime dependencies that Arch pulls in or leaves unversioned.
    assert {
        "python-httpx2>=2.0.0",
        "python-httpcore2",
        "python-truststore>=0.10",
        "python-anyio>=4.10",
        "python-click>=8.4.2",
    } <= set(targets)


def test_the_published_closure_locks_with_hub_2(tmp_path):
    lock, problems = lock_problems(tmp_path, closure_targets(), published())

    assert problems == []
    versions = {entry["name"]: entry["version"] for entry in lock["packages"]}
    assert versions[HUB] == "1:2.1.1-1"
    assert versions[TRANSFORMERS] == published()[TRANSFORMERS][0]
    assert versions[TOKENIZERS] == published()[TOKENIZERS][0]


def test_the_stale_builds_cannot_lock_beside_hub_2(tmp_path):
    # Their depends name no hub version, so only the target floors refuse them.
    _, problems = lock_problems(tmp_path, closure_targets(), STALE)

    assert {(p["kind"], p["package"]) for p in problems} == {
        ("unresolved", TRANSFORMERS),
        ("unresolved", TOKENIZERS),
    }


def test_the_old_floor_let_the_stale_builds_lock_beside_hub_2(tmp_path):
    # The defect: every requirement the old targets and the 5.16.1-1 depends
    # stated was met, so the lock had no problem.
    lock, problems = lock_problems(tmp_path, [TOKENIZERS, TRANSFORMERS, f"{HUB}>=1:1.31.0"], STALE)

    assert problems == []
    versions = {entry["name"]: entry["version"] for entry in lock["packages"]}
    assert (versions[TRANSFORMERS], versions[HUB]) == ("5.16.1-1", "1:2.1.1-1")


def test_a_future_hub_major_is_refused_by_the_package_depends(tmp_path):
    # The hub target is a floor, so the packages' own upper bound is what
    # refuses hub 3.
    _, problems = lock_problems(tmp_path, closure_targets(), published(), hub="1:3.0.0-1")

    details = [p["detail"] for p in problems]
    assert problems and {(p["kind"], p["package"]) for p in problems} == {("unresolved", HUB)}
    assert any(f"{HUB}<1:3 needed by {TRANSFORMERS}" in detail for detail in details)
    assert any(f"{HUB}<1:3 needed by {TOKENIZERS}" in detail for detail in details)


@pytest.mark.parametrize(
    ("have", "op", "want", "expected"),
    [
        ("1:2.1.1-1", "<", "1:3", True),
        ("1:3.0.0-1", "<", "1:3", False),
        ("1:1.32.0-1", ">=", "1:1.31.0", True),
        # Without the epoch, the upper bound rejects every epoch-1 hub and the
        # lower bound accepts all of them.
        ("1:2.1.1-1", "<", "3", False),
        ("1:1.30.0-1", ">=", "1.31.0", True),
    ],
)
def test_hub_bounds_need_the_arch_epoch(have, op, want, expected):
    assert cbr.version_ok(have, op, want) is expected

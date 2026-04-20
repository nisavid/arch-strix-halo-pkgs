from pathlib import Path
import importlib.util
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools/check_package_updates.py"
SPEC = importlib.util.spec_from_file_location("check_package_updates", MODULE_PATH)
assert SPEC and SPEC.loader
updates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updates)


def write_pkg(root: Path, name: str) -> None:
    pkg_dir = root / "packages" / name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "PKGBUILD").write_text("pkgname='x'\n", encoding="utf-8")


def write_policy(root: Path, body: str) -> Path:
    policy = root / "policies" / "package-freshness.toml"
    policy.parent.mkdir(parents=True)
    policy.write_text(textwrap.dedent(body), encoding="utf-8")
    return policy


def test_given_uncovered_pkgbuild_when_policy_loads_then_reports_metadata_mismatch(
    tmp_path,
):
    write_pkg(tmp_path, "python-vllm-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.vllm]
        packages = []
        priority = "high"
        workflow = "upstream_source_update"
        """,
    )

    report = updates.run_check(
        tmp_path, refresh=True, clients=updates.FakeClients()
    )

    assert report["families"][0]["status"] == "metadata_mismatch"
    assert "python-vllm-rocm-gfx1151" in report["families"][0]["message"]


def test_given_package_in_two_families_when_policy_loads_then_reports_metadata_mismatch(
    tmp_path,
):
    write_pkg(tmp_path, "python-vllm-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.one]
        packages = ["python-vllm-rocm-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "manual", role = "primary", kind = "manual", recorded = "n/a" }]

        [families.two]
        packages = ["python-vllm-rocm-gfx1151"]
        priority = "low"
        workflow = "manual_review"
        checks = [{ id = "manual", role = "primary", kind = "manual", recorded = "n/a" }]
        """,
    )

    report = updates.run_check(
        tmp_path, refresh=True, clients=updates.FakeClients()
    )

    assert report["summary"]["metadata_mismatch"] == 1
    assert report["families"][0]["family"] == "policy-coverage"


def test_statuses_are_stable_public_api():
    assert updates.PUBLIC_STATUSES == {
        "current",
        "stable_update_available",
        "prerelease_only",
        "baseline_drift",
        "branch_head_ahead",
        "metadata_mismatch",
        "manual_review_required",
        "query_failed",
    }

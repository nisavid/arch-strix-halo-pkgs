from pathlib import Path
import importlib.util
import json
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


def test_given_same_pypi_version_when_checked_then_family_is_current(tmp_path):
    write_pkg(tmp_path, "python-numpy-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.numpy]
        packages = ["python-numpy-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "pypi", role = "primary", kind = "pypi", package = "numpy", recorded = "2.4.4", comparison = "pep440" }]
        """,
    )
    clients = updates.FakeClients(pypi={"numpy": {"version": "2.4.4"}})

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "current"


def test_given_newer_pypi_stable_when_checked_then_stable_update_available(
    tmp_path,
):
    write_pkg(tmp_path, "python-mistral-common-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.mistral_common]
        packages = ["python-mistral-common-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "pypi", role = "primary", kind = "pypi", package = "mistral_common", recorded = "1.10.0", comparison = "pep440" }]
        """,
    )
    clients = updates.FakeClients(
        pypi={"mistral_common": {"version": "1.11.0"}}
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "stable_update_available"
    assert report["families"][0]["workflow"] == "upstream_source_update"


def test_given_only_prerelease_tag_when_checked_then_prerelease_only(tmp_path):
    write_pkg(tmp_path, "python-vllm-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.vllm]
        packages = ["python-vllm-rocm-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "release", role = "primary", kind = "github_release", repo = "vllm-project/vllm", recorded = "0.19.1", tag_prefix = "v", comparison = "pep440", include_prereleases = false }]
        """,
    )
    clients = updates.FakeClients(
        github_releases={
            "vllm-project/vllm": [
                {"tag": "v0.19.2rc0", "prerelease": True}
            ]
        }
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "prerelease_only"


def test_given_recorded_aur_baseline_changes_then_baseline_drift_not_upstream_update(
    tmp_path,
):
    write_pkg(tmp_path, "python-vllm-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.vllm]
        packages = ["python-vllm-rocm-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "aur", role = "baseline", kind = "aur", package = "python-vllm", recorded = "0.12.0-1", comparison = "pkgver" }]
        """,
    )
    clients = updates.FakeClients(aur={"python-vllm": {"version": "0.13.0-1"}})

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "baseline_drift"


def test_given_query_failure_when_checked_then_not_current(tmp_path):
    write_pkg(tmp_path, "python-triton-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.triton]
        packages = ["python-triton-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "git", role = "primary", kind = "git_ref", repo = "https://github.com/ROCm/triton.git", ref = "refs/heads/main_perf", recorded = "0ec280c", comparison = "sha" }]
        """,
    )
    clients = updates.FakeClients(
        fail={
            "git_ref:https://github.com/ROCm/triton.git:refs/heads/main_perf": "timeout"
        }
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "query_failed"


def test_cli_json_output_is_parseable(tmp_path, capsys):
    write_pkg(tmp_path, "python-numpy-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.numpy]
        packages = ["python-numpy-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "manual", role = "primary", kind = "manual", recorded = "n/a" }]
        """,
    )

    code = updates.main(
        ["--repo-root", str(tmp_path), "--json", "--refresh"],
        clients=updates.FakeClients(),
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["families"][0]["family"] == "numpy"


def test_fail_on_actionable_returns_10_for_stable_update(tmp_path):
    write_pkg(tmp_path, "python-mistral-common-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.mistral_common]
        packages = ["python-mistral-common-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "pypi", role = "primary", kind = "pypi", package = "mistral_common", recorded = "1.10.0", comparison = "pep440" }]
        """,
    )
    clients = updates.FakeClients(
        pypi={"mistral_common": {"version": "1.11.0"}}
    )

    code = updates.main(
        [
            "--repo-root",
            str(tmp_path),
            "--refresh",
            "--fail-on",
            "actionable",
        ],
        clients=clients,
    )

    assert code == 10


def test_cache_is_reused_when_policy_digest_matches(tmp_path):
    write_pkg(tmp_path, "python-numpy-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.numpy]
        packages = ["python-numpy-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "pypi", role = "primary", kind = "pypi", package = "numpy", recorded = "2.4.4", comparison = "pep440" }]
        """,
    )
    first = updates.run_check(
        tmp_path,
        refresh=True,
        clients=updates.FakeClients(pypi={"numpy": {"version": "2.4.4"}}),
    )
    second = updates.run_check(
        tmp_path,
        refresh=False,
        clients=updates.FakeClients(fail={"pypi:numpy": "should not query"}),
    )

    assert second["cache"]["used"] is True
    assert second["families"] == first["families"]


def test_real_freshness_policy_covers_every_pkgbuild_dir():
    repo = Path(__file__).resolve().parents[1]

    report = updates.run_check(
        repo,
        refresh=True,
        clients=updates.FakeClients(allow_missing=True),
        validate_only=True,
    )

    assert report["summary"].get("metadata_mismatch", 0) == 0

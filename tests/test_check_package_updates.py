from pathlib import Path
import importlib.util
import json
import subprocess
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
        "candidate_head_ahead",
        "scout_head_ahead",
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


def test_only_selector_does_not_turn_unselected_covered_packages_into_mismatches(
    tmp_path,
):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_pkg(tmp_path, "python-numpy-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "afddcbf4", comparison = "sha" }]

        [families.numpy]
        packages = ["python-numpy-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "pypi", role = "primary", kind = "pypi", package = "numpy", recorded = "2.4.4", comparison = "pep440" }]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/aiter.git:refs/heads/main": "afddcbf4"
        },
        fail={"pypi:numpy": "unselected family should not be queried"},
    )

    report = updates.run_check(
        tmp_path,
        refresh=True,
        clients=clients,
        only=["python-amd-aiter-gfx1151"],
    )

    assert report["summary"] == {"current": 1}
    assert [family["family"] for family in report["families"]] == ["aiter"]


def test_unknown_only_selector_reports_metadata_mismatch(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_pkg(tmp_path, "python-numpy-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "afddcbf4", comparison = "sha" }]

        [families.numpy]
        packages = ["python-numpy-gfx1151"]
        priority = "medium"
        workflow = "upstream_source_update"
        checks = [{ id = "pypi", role = "primary", kind = "pypi", package = "numpy", recorded = "2.4.4", comparison = "pep440" }]
        """,
    )
    clients = updates.FakeClients(
        fail={
            "git_ref:https://github.com/ROCm/aiter.git:refs/heads/main": "selected families should not be queried when a selector is invalid"
        }
    )

    report = updates.run_check(
        tmp_path,
        refresh=True,
        clients=clients,
        only=["python-amd-aiter-gfx1151", "does-not-exist"],
    )

    assert report["summary"] == {"metadata_mismatch": 1}
    assert report["families"][0]["family"] == "policy-selector"
    assert "does-not-exist" in report["families"][0]["message"]


def test_given_candidate_ref_ahead_when_checked_then_candidate_head_ahead(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "cf12b138", comparison = "sha" }]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/aiter.git:refs/heads/main": "afddcbf4"
        }
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "candidate_head_ahead"
    assert report["families"][0]["checks"][0]["status"] == "candidate_head_ahead"


def test_candidate_head_ahead_is_actionable(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "cf12b138", comparison = "sha" }]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/aiter.git:refs/heads/main": "afddcbf4"
        }
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


def test_given_scout_ref_ahead_when_checked_then_scout_head_ahead(tmp_path):
    write_pkg(tmp_path, "python-pytorch-opt-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.rocm_pytorch]
        packages = ["python-pytorch-opt-rocm-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "scout", kind = "git_ref", repo = "https://github.com/ROCm/pytorch.git", ref = "refs/heads/main", recorded = "8543095", comparison = "sha" }]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/pytorch.git:refs/heads/main": "1234567"
        }
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "scout_head_ahead"
    assert report["families"][0]["checks"][0]["status"] == "scout_head_ahead"


def test_scout_head_ahead_is_not_actionable(tmp_path):
    write_pkg(tmp_path, "python-pytorch-opt-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.rocm_pytorch]
        packages = ["python-pytorch-opt-rocm-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "scout", kind = "git_ref", repo = "https://github.com/ROCm/pytorch.git", ref = "refs/heads/main", recorded = "8543095", comparison = "sha" }]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/pytorch.git:refs/heads/main": "1234567"
        }
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

    assert code == 0


def test_unknown_role_reports_metadata_mismatch(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main", role = "candiate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "cf12b138", comparison = "sha" }]
        """,
    )

    report = updates.run_check(
        tmp_path, refresh=True, clients=updates.FakeClients()
    )

    assert report["families"][0]["status"] == "metadata_mismatch"
    assert "Unsupported check role" in report["families"][0]["checks"][0]["message"]


def test_candidate_and_scout_roles_require_sha_ref_checks(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [
          { id = "candidate-release", role = "candidate", kind = "github_release", repo = "ROCm/aiter", recorded = "0.1.12.post1", comparison = "pep440" },
          { id = "scout-release", role = "scout", kind = "github_release", repo = "ROCm/aiter", recorded = "0.1.12.post1", comparison = "pep440" },
        ]
        """,
    )

    report = updates.run_check(
        tmp_path, refresh=True, clients=updates.FakeClients()
    )

    assert report["families"][0]["status"] == "metadata_mismatch"
    assert "candidate checks must use sha ref kinds" in report["families"][0]["checks"][0]["message"]
    assert "scout checks must use sha ref kinds" in report["families"][0]["checks"][1]["message"]


def test_primary_sha_ref_drift_keeps_legacy_branch_head_status(tmp_path):
    write_pkg(tmp_path, "python-triton-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.triton]
        packages = ["python-triton-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "main-perf", role = "primary", kind = "git_ref", repo = "https://github.com/ROCm/triton.git", ref = "refs/heads/main_perf", recorded = "0ec280c", comparison = "sha" }]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/triton.git:refs/heads/main_perf": "1111111"
        }
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "branch_head_ahead"


def test_candidate_drift_precedes_baseline_drift(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [
          { id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "cf12b138", comparison = "sha" },
          { id = "aur", role = "baseline", kind = "aur", package = "python-amd-aiter", recorded = "0.1.0-1", comparison = "pkgver" },
        ]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/aiter.git:refs/heads/main": "afddcbf4"
        },
        aur={"python-amd-aiter": {"version": "0.1.1-1"}},
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "candidate_head_ahead"


def test_stable_update_precedes_candidate_drift(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [
          { id = "release", role = "primary", kind = "pypi", package = "amd-aiter", recorded = "0.1.12", comparison = "pep440" },
          { id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "cf12b138", comparison = "sha" },
        ]
        """,
    )
    clients = updates.FakeClients(
        pypi={"amd-aiter": {"version": "0.1.13"}},
        git_refs={
            "https://github.com/ROCm/aiter.git:refs/heads/main": "afddcbf4"
        },
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "stable_update_available"


def test_baseline_drift_precedes_scout_drift(tmp_path):
    write_pkg(tmp_path, "python-pytorch-opt-rocm-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.rocm_pytorch]
        packages = ["python-pytorch-opt-rocm-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [
          { id = "main", role = "scout", kind = "git_ref", repo = "https://github.com/ROCm/pytorch.git", ref = "refs/heads/main", recorded = "8543095", comparison = "sha" },
          { id = "arch", role = "baseline", kind = "arch_package", package = "python-pytorch-opt-rocm", recorded = "2.11.0-3", comparison = "pkgver" },
        ]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/pytorch.git:refs/heads/main": "1234567"
        },
        arch={"python-pytorch-opt-rocm": {"version": "2.11.0-4"}},
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "baseline_drift"


def test_query_failure_precedes_candidate_drift(tmp_path):
    write_pkg(tmp_path, "python-amd-aiter-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.aiter]
        packages = ["python-amd-aiter-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [
          { id = "main", role = "candidate", kind = "git_ref", repo = "https://github.com/ROCm/aiter.git", ref = "refs/heads/main", recorded = "cf12b138", comparison = "sha" },
          { id = "release", role = "primary", kind = "github_release", repo = "ROCm/aiter", recorded = "0.1.12.post1", comparison = "pep440" },
        ]
        """,
    )
    clients = updates.FakeClients(
        git_refs={
            "https://github.com/ROCm/aiter.git:refs/heads/main": "afddcbf4"
        },
        fail={"github_release:ROCm/aiter": "timeout"},
    )

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "query_failed"


def test_python_ftp_check_can_track_one_minor_series(tmp_path):
    write_pkg(tmp_path, "python-gfx1151")
    write_policy(
        tmp_path,
        """
        [families.python]
        packages = ["python-gfx1151"]
        priority = "high"
        workflow = "upstream_source_update"
        checks = [{ id = "cpython", role = "primary", kind = "python_ftp", recorded = "3.14.4", comparison = "pep440", series = "3.14" }]
        """,
    )
    clients = updates.FakeClients(python_ftp=["3.14.3", "3.14.4", "3.15.0"])

    report = updates.run_check(tmp_path, refresh=True, clients=clients)

    assert report["families"][0]["status"] == "current"
    assert report["families"][0]["checks"][0]["latest"] == "3.14.4"


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


def test_github_release_client_ignores_drafts_and_respects_prerelease_flag():
    client = updates.RealClients(
        transport=updates.StaticTransport(
            {
                "https://api.github.com/repos/vllm-project/vllm/releases": json.dumps(
                    [
                        {
                            "tag_name": "v0.19.2rc0",
                            "draft": False,
                            "prerelease": True,
                            "published_at": "2026-04-20T00:00:00Z",
                        },
                        {
                            "tag_name": "v0.19.1",
                            "draft": False,
                            "prerelease": False,
                            "published_at": "2026-04-19T00:00:00Z",
                        },
                        {
                            "tag_name": "v0.20.0",
                            "draft": True,
                            "prerelease": False,
                            "published_at": "2026-04-21T00:00:00Z",
                        },
                    ]
                )
            }
        )
    )

    releases = client.github_releases("vllm-project/vllm")

    assert [release["tag"] for release in releases] == ["v0.19.2rc0", "v0.19.1"]


def test_aur_client_reads_rpc_version():
    client = updates.RealClients(
        transport=updates.StaticTransport(
            {
                "https://aur.archlinux.org/rpc/v5/info?arg[]=python-vllm": json.dumps(
                    {
                        "results": [
                            {"Name": "python-vllm", "Version": "0.12.0-1"}
                        ]
                    }
                )
            }
        )
    )

    assert client.aur_package("python-vllm")["version"] == "0.12.0-1"


def test_submodule_client_uses_gitmodules_url_not_parent_repo(tmp_path, monkeypatch):
    (tmp_path / ".gitmodules").write_text(
        textwrap.dedent(
            """
            [submodule "upstream/ai-notes"]
              path = upstream/ai-notes
              url = https://github.com/paudley/ai-notes.git
            """
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="ad428861b726f6bd0e0a533e9e2fccdef43d0709\trefs/heads/main\n",
            stderr="",
        )

    monkeypatch.setattr(updates.subprocess, "run", fake_run)
    client = updates.RealClients(repo_root=tmp_path)

    assert (
        client.submodule_ref("upstream/ai-notes", "refs/heads/main")
        == "ad428861b726f6bd0e0a533e9e2fccdef43d0709"
    )
    assert calls == [
        [
            "git",
            "ls-remote",
            "https://github.com/paudley/ai-notes.git",
            "refs/heads/main",
        ]
    ]


def test_update_workflow_references_freshness_checker():
    repo = Path(__file__).resolve().parents[1]
    doc = (repo / "docs/maintainers/update-workflows.md").read_text(
        encoding="utf-8"
    )

    assert "tools/check_package_updates.py" in doc
    assert "policies/package-freshness.toml" in doc

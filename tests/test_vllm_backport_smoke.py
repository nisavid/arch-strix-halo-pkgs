from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import recipe_policy  # noqa: E402
import vllm_backport_smoke as smoke  # noqa: E402


TOOL = TOOLS_DIR / "vllm_backport_smoke.py"
PACKAGE = "python-vllm-rocm-gfx1151"
REQUIRE_ENV = "REQUIRE_VLLM_BACKPORT_SMOKE"


def policy_pkg() -> dict:
    policy = recipe_policy.load_recipe_policy(REPO_ROOT / "policies/recipe-packages.toml")
    return policy["packages"][PACKAGE]


def fake_check(number: str, outcome) -> smoke.Check:
    def run() -> str:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return smoke.Check(f"{number}-backport-fake.patch", f"fake {number}", run)


def test_tool_exposes_help_without_importing_vllm():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )

    assert result.returncode == 0
    assert "Check that the installed vLLM carries each upstream backport" in result.stdout
    assert "--only" in result.stdout
    assert "--list" in result.stdout
    assert "--json" in result.stdout
    assert "--child" not in result.stdout


def test_tool_needs_only_the_standard_library_to_start():
    # The build root has no pytest; importing the tool must not need it, or
    # vLLM, or torch.
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import vllm_backport_smoke; "
        "print(sorted(m for m in ('vllm', 'torch', 'transformers', 'pytest') if m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(TOOLS_DIR)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "[]"


def test_parser_defaults_and_repeatable_only():
    parser = smoke.build_parser()

    defaults = parser.parse_args([])
    assert defaults.only == []
    assert defaults.list is False
    assert defaults.json is None
    assert defaults.in_process is False
    assert defaults.child is None
    assert defaults.timeout == 600.0

    args = parser.parse_args(["--only", "0019", "--only", "0024", "--json", "out.json"])
    assert args.only == ["0019", "0024"]
    assert args.json == "out.json"


def test_check_registry_covers_exactly_the_policy_backports():
    # A backport added to policy without a check here fails this test, and so
    # does a check left behind after its patch is dropped.
    backports = policy_pkg()["source_patches"][1:]

    assert backports
    assert [check.patch for check in smoke.CHECKS] == backports


def test_check_registry_entries_are_distinct_and_described():
    numbers = [check.number for check in smoke.CHECKS]
    runners = [check.run for check in smoke.CHECKS]

    assert len(set(numbers)) == len(numbers)
    assert len(set(runners)) == len(runners)
    for check in smoke.CHECKS:
        assert check.number.isdigit() and len(check.number) == 4
        assert (REPO_ROOT / "packages" / PACKAGE / check.patch).is_file()
        assert check.summary
        assert (check.run.__doc__ or "").strip(), check.patch


def test_select_checks_by_number_or_patch_name_in_registry_order():
    first, second = smoke.CHECKS[0], smoke.CHECKS[1]

    assert smoke.select_checks([]) == list(smoke.CHECKS)
    assert smoke.select_checks([second.patch, first.number]) == [first, second]
    with pytest.raises(ValueError, match="no check for: 9999"):
        smoke.select_checks(["9999"])


def test_list_prints_every_check_without_running_any(capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a check ran")

    monkeypatch.setattr(smoke, "run_check", refuse)
    monkeypatch.setattr(smoke, "run_check_in_child", refuse)

    assert smoke.main(["--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(" ", 1)[0] for line in lines] == [c.number for c in smoke.CHECKS]


def test_unknown_only_value_is_a_usage_error(capsys):
    assert smoke.main(["--only", "9999"]) == 2
    assert "no check for: 9999" in capsys.readouterr().err


def test_run_check_reports_pass_failure_and_unexpected_errors():
    passed = smoke.run_check(fake_check("0001", "works"))
    failed = smoke.run_check(fake_check("0002", smoke.CheckFailure("fix is absent")))
    broken = smoke.run_check(fake_check("0003", RuntimeError("boom\nsecond line")))

    assert passed == {
        "patch": "0001-backport-fake.patch",
        "number": "0001",
        "summary": "fake 0001",
        "ok": True,
        "detail": "works",
    }
    assert failed["ok"] is False and failed["detail"] == "fix is absent"
    assert broken["ok"] is False
    assert broken["detail"].startswith("RuntimeError: boom at test_vllm_backport_smoke.py:")


def test_main_prints_one_line_per_check_and_a_json_summary(monkeypatch, capsys, tmp_path):
    checks = (
        fake_check("0001", "works"),
        fake_check("0002", smoke.CheckFailure("fix is absent")),
    )
    monkeypatch.setattr(smoke, "CHECKS", checks)
    out = tmp_path / "summary.json"

    assert smoke.main(["--in-process", "--json", str(out)]) == 1

    stdout = capsys.readouterr().out
    lines = stdout.splitlines()
    assert lines[0] == "PASS 0001 0001-backport-fake.patch: works"
    assert lines[1] == "FAIL 0002 0002-backport-fake.patch: fix is absent"
    summary = json.loads("\n".join(lines[2:]))
    assert summary == json.loads(out.read_text())
    assert summary["passed"] == ["0001"]
    assert summary["failed"] == ["0002"]
    assert [record["patch"] for record in summary["results"]] == [c.patch for c in checks]
    assert set(summary["versions"]) == {"vllm", "transformers", "huggingface_hub", "torch"}


def test_main_exits_zero_only_when_every_selected_check_passes(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke,
        "CHECKS",
        (fake_check("0001", "works"), fake_check("0002", smoke.CheckFailure("absent"))),
    )

    assert smoke.main(["--in-process", "--only", "0001"]) == 0
    assert smoke.main(["--in-process", "--only", "0002"]) == 1
    assert smoke.main(["--in-process"]) == 1
    capsys.readouterr()


def test_child_environment_selects_the_cpu_platform_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("HIP_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("VLLM_TARGET_DEVICE", "rocm")

    env = smoke.child_environment(str(tmp_path))

    assert env["VLLM_TARGET_DEVICE"] == "cpu"
    assert env["HIP_VISIBLE_DEVICES"] == env["CUDA_VISIBLE_DEVICES"] == ""
    assert env["HF_HUB_OFFLINE"] == env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["VLLM_NO_USAGE_STATS"] == "1"
    for variable in ("HOME", "HF_HOME", "XDG_CACHE_HOME", "VLLM_CACHE_ROOT", "VLLM_CONFIG_ROOT"):
        assert Path(env[variable]).is_dir()
        assert Path(env[variable]).parent == tmp_path


def test_each_check_runs_in_its_own_process(monkeypatch, tmp_path):
    check = smoke.CHECKS[0]
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        record = {"patch": check.patch, "number": check.number, "summary": "s", "ok": True, "detail": "d"}
        return subprocess.CompletedProcess(
            argv, 0, stdout=f"noise\n{smoke.RESULT_MARKER}{json.dumps(record)}\n", stderr=""
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    record = smoke.run_check_in_child(check, str(tmp_path), timeout=5)

    assert record["ok"] is True and record["detail"] == "d"
    ((argv, kwargs),) = calls
    assert argv == [sys.executable, str(TOOL), "--child", check.patch]
    assert kwargs["env"]["VLLM_TARGET_DEVICE"] == "cpu"
    assert kwargs["timeout"] == 5


def test_a_check_process_that_dies_or_hangs_is_a_failure(monkeypatch, tmp_path):
    check = smoke.CHECKS[0]

    def crashed(argv, **kwargs):
        return subprocess.CompletedProcess(argv, -11, stdout="", stderr="first\nSegmentation fault\n")

    monkeypatch.setattr(smoke.subprocess, "run", crashed)
    record = smoke.run_check_in_child(check, str(tmp_path), timeout=5)
    assert record["ok"] is False
    assert record["detail"] == "the check process exited -11: Segmentation fault"

    def hung(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(smoke.subprocess, "run", hung)
    record = smoke.run_check_in_child(check, str(tmp_path), timeout=5)
    assert record["ok"] is False
    assert record["detail"] == "timed out after 5s"


def test_child_mode_prints_one_marked_record(monkeypatch, capsys):
    check = fake_check("0001", "works")
    monkeypatch.setattr(smoke, "CHECKS", (check,))

    assert smoke.main(["--child", check.patch]) == 0

    (line,) = capsys.readouterr().out.splitlines()
    assert line.startswith(smoke.RESULT_MARKER)
    assert json.loads(line[len(smoke.RESULT_MARKER) :])["detail"] == "works"


def test_end_to_end_against_the_installed_package():
    """Run the real checks when the packaged vLLM release is installed.

    A host that carries another vLLM release, or none, skips. The run must
    report every check; set REQUIRE_VLLM_BACKPORT_SMOKE=1 to also require
    that every check passes, as on a root with the rebuilt package.
    """
    required = os.getenv(REQUIRE_ENV) == "1"
    packaged = policy_pkg()["upstream_version"]
    try:
        installed = importlib.metadata.version("vllm")
    except importlib.metadata.PackageNotFoundError:
        installed = None
    if installed != packaged or importlib.util.find_spec("vllm") is None:
        if required:
            pytest.fail(f"expected vLLM {packaged} to be installed, found {installed}")
        pytest.skip(f"vLLM {packaged} is not installed (found {installed})")

    result = subprocess.run(
        [sys.executable, str(TOOL)], check=False, capture_output=True, text=True
    )

    lines = result.stdout.splitlines()
    status_lines = [line for line in lines if line.startswith(("PASS ", "FAIL "))]
    summary = json.loads("\n".join(lines[len(status_lines) :]))
    numbers = [check.number for check in smoke.CHECKS]
    assert [line.split(" ")[1] for line in status_lines] == numbers
    assert sorted(summary["passed"] + summary["failed"]) == numbers
    assert result.returncode == (1 if summary["failed"] else 0)
    if required:
        assert summary["failed"] == [], result.stdout

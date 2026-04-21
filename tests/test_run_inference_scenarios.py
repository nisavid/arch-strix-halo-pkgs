from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "tools/run_inference_scenarios.py"


def write_scenarios(tmp_path: Path) -> Path:
    scenario_dir = tmp_path / "inference" / "scenarios"
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "sample.toml").write_text(
        """
[[scenario]]
id = "vllm.demo.text"
summary = "demo text"
tags = ["smoke"]

[scenario.given]
engine = "vllm"
model = "demo-model"
tool = "gemma4_text_smoke"

[[scenario.then.assert]]
kind = "stdout.contains"
value = "hello"

[[scenario]]
id = "lemonade.demo.server"
summary = "demo server"
tags = ["smoke"]

[scenario.given]
engine = "lemonade"
model = "demo-model"
entrypoint = "lemonade"

[scenario.when]
argv = ["--help"]

[[scenario]]
id = "vllm.demo.exploratory"
summary = "demo exploratory"
tags = ["smoke", "exploratory"]

[scenario.given]
engine = "vllm"
model = "demo-model"
tool = "gemma4_text_smoke"
""",
        encoding="utf-8",
    )
    return scenario_dir


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )


def test_noninteractive_without_selector_fails_fast(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner("--scenario-dir", str(scenario_dir), "--dry-run")

    assert result.returncode == 2
    assert "SCENARIO_SELECTION_REQUIRED" in result.stderr


def test_selector_filters_scenarios_and_preserves_serial_order(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--engine",
        "vllm",
        "--scenario",
        "vllm.demo.text",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_mode"] == "serial"
    assert payload["selected_ids"] == ["vllm.demo.text"]


def test_tag_selector_filters_scenarios(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--tag",
        "smoke",
        "--engine",
        "lemonade",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["selected_ids"] == ["lemonade.demo.server"]


def test_engine_selector_excludes_exploratory_scenarios_by_default(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--engine",
        "vllm",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["selected_ids"] == ["vllm.demo.text"]


def test_engine_selector_can_include_exploratory_scenarios(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--engine",
        "vllm",
        "--include-exploratory",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["selected_ids"] == ["vllm.demo.text", "vllm.demo.exploratory"]


def test_explicit_scenario_selector_includes_exploratory_scenario(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--scenario",
        "vllm.demo.exploratory",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["selected_ids"] == ["vllm.demo.exploratory"]


def test_selector_supports_model_filtering(tmp_path: Path):
    scenario_dir = write_scenarios(tmp_path)
    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--model",
        "demo-model",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["selected_ids"] == ["vllm.demo.text", "lemonade.demo.server"]


def write_fake_command_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_command.py"
    script.write_text(
        """
from __future__ import annotations

import argparse
from pathlib import Path
import sys


parser = argparse.ArgumentParser()
parser.add_argument("--stdout", default="")
parser.add_argument("--stderr", default="")
parser.add_argument("--exit-code", type=int, default=0)
args = parser.parse_args()

if args.stdout:
    print(args.stdout)
if args.stderr:
    print(args.stderr, file=sys.stderr)

raise SystemExit(args.exit_code)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return script


def test_dry_run_includes_resolved_commands_and_model_bindings(tmp_path: Path):
    scenario_dir = tmp_path / "inference" / "scenarios"
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "vllm.toml").write_text(
        """
[[scenario]]
id = "vllm.gemma4.text"
summary = "Gemma text smoke"

[scenario.given]
engine = "vllm"
model = "google/gemma-4-26B-A4B-it"
tool = "gemma4_text_smoke"
""",
        encoding="utf-8",
    )

    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--scenario",
        "vllm.gemma4.text",
        "--model-path",
        "google/gemma-4-26B-A4B-it=/models/google/gemma-4-26B-A4B-it",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["selected_ids"] == ["vllm.gemma4.text"]
    assert payload["planned"][0]["command"] == [
        sys.executable,
        str(REPO_ROOT / "tools/gemma4_text_smoke.py"),
        "/models/google/gemma-4-26B-A4B-it",
    ]


def test_dry_run_includes_scenario_environment(tmp_path: Path):
    scenario_dir = tmp_path / "inference" / "scenarios"
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "vllm.toml").write_text(
        """
[[scenario]]
id = "vllm.gemma4.aiter-moe"
summary = "Gemma AITER MoE probe"

[scenario.given]
engine = "vllm"
model = "google/gemma-4-26B-A4B-it"
tool = "gemma4_server_smoke.basic"

[scenario.when.env]
VLLM_ROCM_USE_AITER_MOE = "1"
""",
        encoding="utf-8",
    )

    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--dry-run",
        "--scenario",
        "vllm.gemma4.aiter-moe",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["planned"][0]["env"] == {"VLLM_ROCM_USE_AITER_MOE": "1"}


def test_qwen_server_dry_run_includes_server_log_and_environment(tmp_path: Path):
    scenario_dir = tmp_path / "inference" / "scenarios"
    scenario_dir.mkdir(parents=True)
    run_root = tmp_path / "run"
    (scenario_dir / "vllm-qwen.toml").write_text(
        """
[[scenario]]
id = "vllm.qwen3_6.35b-a3b.server.reasoning"
summary = "Qwen server reasoning smoke"

[scenario.given]
engine = "vllm"
model = "Qwen/Qwen3.6-35B-A3B"
tool = "qwen_server_smoke.reasoning"

[scenario.when.env]
VLLM_ROCM_USE_AITER = "0"
VLLM_ROCM_USE_AITER_MOE = "0"
""",
        encoding="utf-8",
    )

    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--run-root",
        str(run_root),
        "--dry-run",
        "--scenario",
        "vllm.qwen3_6.35b-a3b.server.reasoning",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    planned = payload["planned"][0]
    server_log_path = (
        run_root
        / "scenarios"
        / "vllm.qwen3_6.35b-a3b.server.reasoning"
        / "server.log"
    )
    assert planned["command"] == [
        sys.executable,
        str(REPO_ROOT / "tools/qwen_server_smoke.py"),
        "Qwen/Qwen3.6-35B-A3B",
        "--mode",
        "reasoning",
        "--server-log",
        str(server_log_path),
    ]
    assert planned["server_log_path"] == str(server_log_path)
    assert planned["env"] == {
        "VLLM_ROCM_USE_AITER": "0",
        "VLLM_ROCM_USE_AITER_MOE": "0",
    }


def test_runner_executes_scenario_and_writes_logs(tmp_path: Path):
    script = write_fake_command_script(tmp_path)
    scenario_dir = tmp_path / "inference" / "scenarios"
    scenario_dir.mkdir(parents=True)
    run_root = tmp_path / "run"
    (scenario_dir / "generic.toml").write_text(
        f"""
[[scenario]]
id = "llama.cpp.fake.ok"
summary = "fake command succeeds"

[scenario.given]
engine = "llama.cpp"
model = "builtin"
entrypoint = "{sys.executable}"

[scenario.when]
argv = ["{script}", "--stdout", "hello from fake", "--stderr", "warn from fake"]

[[scenario.then.assert]]
kind = "stdout.contains"
value = "hello from fake"

[[scenario.then.assert]]
kind = "stderr.contains"
value = "warn from fake"

[[scenario.then.assert]]
kind = "exit_code.equals"
value = 0
""",
        encoding="utf-8",
    )

    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--run-root",
        str(run_root),
        "--scenario",
        "llama.cpp.fake.ok",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] == 1
    assert payload["failed"] == 0
    assert payload["run_root"] == str(run_root)
    result_file = run_root / "scenarios" / "llama.cpp.fake.ok" / "result.json"
    stdout_log = run_root / "scenarios" / "llama.cpp.fake.ok" / "stdout.log"
    stderr_log = run_root / "scenarios" / "llama.cpp.fake.ok" / "stderr.log"
    assert result_file.is_file()
    assert stdout_log.read_text(encoding="utf-8").strip() == "hello from fake"
    assert stderr_log.read_text(encoding="utf-8").strip() == "warn from fake"


def test_runner_returns_nonzero_when_assertion_fails(tmp_path: Path):
    script = write_fake_command_script(tmp_path)
    scenario_dir = tmp_path / "inference" / "scenarios"
    scenario_dir.mkdir(parents=True)
    run_root = tmp_path / "run"
    (scenario_dir / "generic.toml").write_text(
        f"""
[[scenario]]
id = "lemonade.fake.fail"
summary = "fake command fails expectation"

[scenario.given]
engine = "lemonade"
model = "builtin"
entrypoint = "{sys.executable}"

[scenario.when]
argv = ["{script}", "--stdout", "actual output"]

[[scenario.then.assert]]
kind = "stdout.contains"
value = "missing marker"
""",
        encoding="utf-8",
    )

    result = run_runner(
        "--scenario-dir",
        str(scenario_dir),
        "--run-root",
        str(run_root),
        "--scenario",
        "lemonade.fake.fail",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] == 0
    assert payload["failed"] == 1
    scenario_result = json.loads(
        (
            run_root / "scenarios" / "lemonade.fake.fail" / "result.json"
        ).read_text(encoding="utf-8")
    )
    assert scenario_result["ok"] is False
    assert "stdout.contains" in scenario_result["failures"][0]

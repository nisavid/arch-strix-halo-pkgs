from __future__ import annotations

import json
from pathlib import Path
import os
import re
import shutil
import subprocess
import time
from typing import Any

from .adapters import build_execution_plan
from .logging import default_run_root
from .scenario_loader import Scenario


def _scenario_metadata(scenario: Scenario) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": scenario.id,
        "engine": scenario.engine,
        "model": scenario.model,
    }
    if scenario.draft_model is not None:
        metadata["draft_model"] = scenario.draft_model
    if scenario.speculative_model is not None:
        metadata["speculative_model"] = scenario.speculative_model
    return metadata


def build_run_plan(
    scenarios: list[Scenario],
    *,
    repo_root: Path,
    run_root: Path | None = None,
    model_bindings: dict[str, str] | None = None,
) -> dict[str, object]:
    actual_run_root = run_root or default_run_root(repo_root)
    bindings = model_bindings or {}
    planned: list[dict[str, object]] = []
    for scenario in scenarios:
        scenario_run_root = actual_run_root / "scenarios" / scenario.id
        plan = build_execution_plan(
            scenario,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=bindings,
        )
        planned.append(
            {
                **_scenario_metadata(scenario),
                "command": plan.command,
                "server_log_path": (
                    str(plan.server_log_path) if plan.server_log_path is not None else None
                ),
                "env": plan.env or {},
            }
        )
    return {
        "execution_mode": "serial",
        "planned_run_root": str(actual_run_root),
        "selected_ids": [scenario.id for scenario in scenarios],
        "planned": planned,
    }


def write_run_manifest(run_root: Path, payload: dict[str, object]) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def find_stale_vllm_engine_cores(ps_output: str) -> list[str]:
    matches: list[str] = []
    for raw_line in ps_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        if parts[3] == "VLLM::EngineCore":
            matches.append(line)
    return matches


def _amd_smi_bin() -> str | None:
    discovered = shutil.which("amd-smi")
    if discovered:
        return discovered
    fallback = Path("/opt/rocm/bin/amd-smi")
    if fallback.is_file():
        return str(fallback)
    return None


def _capture_gpu_process_table(run_root: Path, *, phase: str) -> None:
    amd_smi = _amd_smi_bin()
    if amd_smi is None:
        return
    completed = subprocess.run(
        [amd_smi, "process", "-G", "--json"],
        capture_output=True,
        text=True,
    )
    payload = completed.stdout if completed.stdout else completed.stderr
    _write_text(run_root / f"amd-smi-{phase}.json", payload)


def _preexisting_stale_vllm_engine_cores() -> list[str]:
    completed = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,etimes=,comm=,cmd="],
        capture_output=True,
        text=True,
        check=True,
    )
    return find_stale_vllm_engine_cores(completed.stdout)


def _assertion_failures(
    assertions: list[dict[str, object]],
    *,
    stdout: str,
    stderr: str,
    exit_code: int,
    server_log: str,
    duration_seconds: float,
) -> list[str]:
    sources = {
        "stdout": stdout,
        "stderr": stderr,
        "output": stdout + stderr,
        "server_log": server_log,
    }
    combined = sources["output"]
    failures: list[str] = []
    for assertion in assertions:
        kind = str(assertion["kind"])
        expected = assertion.get("value")
        if kind.endswith(".json_path.equals"):
            source_name = kind.removesuffix(".json_path.equals")
            if source_name not in sources:
                raise ValueError(f"UNKNOWN_ASSERTION_KIND: {kind}")
            failure = _json_path_equals_failure(
                assertion,
                source=sources[source_name],
                source_name=source_name,
                expected=expected,
            )
            if failure is not None:
                failures.append(f"{kind}: {failure}")
            continue
        if kind == "exit_code.equals":
            if exit_code != int(expected):
                failures.append(f"{kind}: expected {expected}, got {exit_code}")
            continue
        if kind == "stdout.contains":
            if str(expected) not in stdout:
                failures.append(f"{kind}: missing {expected!r}")
            continue
        if kind == "stderr.contains":
            if str(expected) not in stderr:
                failures.append(f"{kind}: missing {expected!r}")
            continue
        if kind == "output.contains":
            if str(expected) not in combined:
                failures.append(f"{kind}: missing {expected!r}")
            continue
        if kind == "stdout.regex":
            if re.search(str(expected), stdout, re.MULTILINE) is None:
                failures.append(f"{kind}: pattern {expected!r} did not match")
            continue
        if kind == "stderr.regex":
            if re.search(str(expected), stderr, re.MULTILINE) is None:
                failures.append(f"{kind}: pattern {expected!r} did not match")
            continue
        if kind == "output.regex":
            if re.search(str(expected), combined, re.MULTILINE) is None:
                failures.append(f"{kind}: pattern {expected!r} did not match")
            continue
        if kind == "server_log.contains":
            if str(expected) not in server_log:
                failures.append(f"{kind}: missing {expected!r}")
            continue
        if kind == "server_log.regex":
            if re.search(str(expected), server_log, re.MULTILINE) is None:
                failures.append(f"{kind}: pattern {expected!r} did not match")
            continue
        if kind == "duration.seconds_lte":
            if duration_seconds > float(expected):
                failures.append(
                    f"{kind}: expected <= {float(expected):.3f}, got {duration_seconds:.3f}"
                )
            continue
        raise ValueError(f"UNKNOWN_ASSERTION_KIND: {kind}")
    return failures


def _json_path_equals_failure(
    assertion: dict[str, object],
    *,
    source: str,
    source_name: str,
    expected: object,
) -> str | None:
    payload, failure = _json_payload_for_assertion(
        assertion,
        source=source,
        source_name=source_name,
    )
    if failure is not None:
        return failure
    actual, failure = _value_at_json_path(payload, assertion.get("path"))
    if failure is not None:
        return failure
    if actual != expected:
        return f"path {assertion.get('path')!r} expected {expected!r}, got {actual!r}"
    return None


def _json_payload_for_assertion(
    assertion: dict[str, object],
    *,
    source: str,
    source_name: str,
) -> tuple[Any, str | None]:
    label = assertion.get("label")
    if label is None:
        raw_json = source.strip()
        context = source_name
    else:
        label_text = str(label)
        prefix = f"{label_text} "
        raw_json = ""
        context = f"{source_name} label {label_text!r}"
        for line in source.splitlines():
            if line.startswith(prefix):
                raw_json = line[len(prefix) :].strip()
                break
        if not raw_json:
            return None, f"missing {context}"
    try:
        return json.loads(raw_json), None
    except json.JSONDecodeError as exc:
        return None, f"{context} was not valid JSON: {exc}"


def _value_at_json_path(payload: Any, path: object) -> tuple[Any, str | None]:
    if path is None or str(path) == "":
        return payload, None
    current = payload
    for raw_part in str(path).split("."):
        if isinstance(current, dict):
            if raw_part not in current:
                return None, f"path {path!r} missing key {raw_part!r}"
            current = current[raw_part]
            continue
        if isinstance(current, list):
            try:
                index = int(raw_part)
            except ValueError:
                return None, f"path {path!r} expected list index, got {raw_part!r}"
            if index < 0 or index >= len(current):
                return None, f"path {path!r} missing index {index}"
            current = current[index]
            continue
        return None, f"path {path!r} cannot descend into {current!r}"
    return current, None


def _scenario_assertions(scenario: Scenario) -> list[dict[str, object]]:
    then = scenario.definition.get("then") or {}
    raw_assertions = then.get("assert") or []
    return [dict(item) for item in raw_assertions]


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run_scenarios(
    scenarios: list[Scenario],
    *,
    repo_root: Path,
    run_root: Path,
    model_bindings: dict[str, str],
) -> dict[str, object]:
    manifest = build_run_plan(
        scenarios,
        repo_root=repo_root,
        run_root=run_root,
        model_bindings=model_bindings,
    )
    write_run_manifest(run_root, manifest)

    results: list[dict[str, object]] = []
    passed = 0
    failed = 0

    for scenario in scenarios:
        scenario_run_root = run_root / "scenarios" / scenario.id
        scenario_run_root.mkdir(parents=True, exist_ok=True)
        plan = build_execution_plan(
            scenario,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=model_bindings,
        )
        _write_text(
            scenario_run_root / "plan.json",
            json.dumps(
                {
                    **_scenario_metadata(scenario),
                    "command": plan.command,
                    "server_log_path": (
                        str(plan.server_log_path) if plan.server_log_path is not None else None
                    ),
                    "env": plan.env or {},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        if scenario.engine == "vllm":
            _capture_gpu_process_table(scenario_run_root, phase="before")
            stale_cores = _preexisting_stale_vllm_engine_cores()
            if stale_cores:
                failures = [
                    "preexisting stale VLLM::EngineCore detected before scenario run",
                    *stale_cores,
                ]
                result = {
                    **_scenario_metadata(scenario),
                    "ok": False,
                    "exit_code": None,
                    "duration_seconds": 0.0,
                    "stdout_log": str(scenario_run_root / "stdout.log"),
                    "stderr_log": str(scenario_run_root / "stderr.log"),
                    "server_log_path": (
                        str(plan.server_log_path) if plan.server_log_path is not None else None
                    ),
                    "failures": failures,
                }
                _write_text(scenario_run_root / "stdout.log", "")
                _write_text(
                    scenario_run_root / "stderr.log",
                    "\n".join(failures) + "\n",
                )
                _write_text(
                    scenario_run_root / "result.json",
                    json.dumps(result, indent=2, sort_keys=True) + "\n",
                )
                results.append(result)
                failed += 1
                continue

        start = time.monotonic()
        completed = subprocess.run(
            plan.command,
            capture_output=True,
            text=True,
            cwd=repo_root,
            env={**os.environ, **(plan.env or {})},
        )
        duration_seconds = time.monotonic() - start

        stdout_log = scenario_run_root / "stdout.log"
        stderr_log = scenario_run_root / "stderr.log"
        _write_text(stdout_log, completed.stdout)
        _write_text(stderr_log, completed.stderr)

        server_log_text = ""
        if plan.server_log_path is not None and plan.server_log_path.exists():
            server_log_text = plan.server_log_path.read_text(encoding="utf-8")
        if scenario.engine == "vllm":
            _capture_gpu_process_table(scenario_run_root, phase="after")

        failures = _assertion_failures(
            _scenario_assertions(scenario),
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            server_log=server_log_text,
            duration_seconds=duration_seconds,
        )
        ok = not failures
        if ok:
            passed += 1
        else:
            failed += 1

        result = {
            **_scenario_metadata(scenario),
            "ok": ok,
            "exit_code": completed.returncode,
            "duration_seconds": round(duration_seconds, 6),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "server_log_path": (
                str(plan.server_log_path) if plan.server_log_path is not None else None
            ),
            "failures": failures,
        }
        _write_text(
            scenario_run_root / "result.json",
            json.dumps(result, indent=2, sort_keys=True) + "\n",
        )
        results.append(result)

    summary = {
        "execution_mode": "serial",
        "run_root": str(run_root),
        "selected_ids": [scenario.id for scenario in scenarios],
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    _write_text(run_root / "summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
AMERGE = REPO_ROOT / "tools/amerge"
MODULE_PATH = REPO_ROOT / "tools/amerge_lib.py"


def run_amerge(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AMERGE), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp", "TERM": "xterm-256color"},
    )


def load_module():
    spec = importlib.util.spec_from_file_location("amerge_lib", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_recipe_package(
    tmp_path: Path,
    name: str,
    *,
    depends: list[str] | None = None,
    makedepends: list[str] | None = None,
) -> Path:
    depends = depends or []
    makedepends = makedepends or []
    package_dir = tmp_path / "packages" / name
    package_dir.mkdir(parents=True)
    (package_dir / "recipe.json").write_text(
        json.dumps({"name": name, "package_name": name}),
        encoding="utf-8",
    )
    (package_dir / "PKGBUILD").write_text(
        "\n".join(
            [
                f"pkgname={name}",
                f"depends=({' '.join(depends)})" if depends else "depends=()",
                (
                    f"makedepends=({' '.join(makedepends)})"
                    if makedepends
                    else "makedepends=()"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return package_dir


def write_pkgbase(tmp_path: Path) -> Path:
    package_dir = tmp_path / "packages" / "therock-gfx1151"
    package_dir.mkdir(parents=True)
    (package_dir / "PKGBUILD").write_text(
        "pkgbase=therock-gfx1151\npkgname=('rocm-core-gfx1151' 'rocblas-gfx1151')\n",
        encoding="utf-8",
    )
    (package_dir / "manifest.json").write_text(
        json.dumps(
            {
                "pkgbase": "therock-gfx1151",
                "packages": {
                    "rocm-core-gfx1151": {"depends": []},
                    "rocblas-gfx1151": {"depends": []},
                },
            }
        ),
        encoding="utf-8",
    )
    return package_dir


def graph_fixture(tmp_path: Path) -> Path:
    write_pkgbase(tmp_path)
    write_recipe_package(tmp_path, "python-core-gfx1151", makedepends=["rocm-core-gfx1151"])
    write_recipe_package(
        tmp_path,
        "python-leaf-gfx1151",
        depends=["python-core-gfx1151", "rocblas-gfx1151"],
    )
    write_recipe_package(
        tmp_path,
        "python-app-gfx1151",
        depends=["python-leaf-gfx1151"],
    )
    return tmp_path / "packages"


def test_default_explicit_targets_do_not_rebuild_dependencies(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--json",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["merge_plan"]["build_roots"] == ["python-app-gfx1151"]
    assert "python-leaf-gfx1151" not in payload["merge_plan"]["build_roots"]
    assert "therock-gfx1151" not in payload["merge_plan"]["build_roots"]


def test_no_target_noninteractive_requires_selector(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--packages-root",
        str(packages_root),
    )

    assert result.returncode != 0
    assert "Choose packages to merge" in result.stderr
    assert "AMERGE_" not in result.stderr


def test_all_selector_expands_to_every_root(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--json",
        "--all",
        "--packages-root",
        str(packages_root),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["merge_plan"]["build_roots"] == [
        "therock-gfx1151",
        "python-core-gfx1151",
        "python-leaf-gfx1151",
        "python-app-gfx1151",
    ]


def test_deps_expands_rebuild_selection_to_dependencies(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--json",
        "--deps",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["merge_plan"]["build_roots"] == [
        "therock-gfx1151",
        "python-core-gfx1151",
        "python-leaf-gfx1151",
        "python-app-gfx1151",
    ]
    step_labels = [step["label"] for step in payload["steps"]]
    assert step_labels.index("install therock-gfx1151 outputs") < step_labels.index(
        "build python-core-gfx1151"
    )
    assert payload["merge_plan"]["install_outputs_by_root"]["therock-gfx1151"] == [
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
    ]


def test_selected_split_root_installs_dependency_outputs_for_later_builds(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--json",
        "--packages-root",
        str(packages_root),
        "rocm-core-gfx1151",
        "python-leaf-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["merge_plan"]["build_roots"] == [
        "therock-gfx1151",
        "python-leaf-gfx1151",
    ]
    assert payload["merge_plan"]["install_outputs_by_root"]["therock-gfx1151"] == [
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
    ]
    step_labels = [step["label"] for step in payload["steps"]]
    assert step_labels.index("install therock-gfx1151 outputs") < step_labels.index(
        "build python-leaf-gfx1151"
    )


def test_rdeps_expands_rebuild_selection_to_reverse_dependencies(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--json",
        "--rdeps",
        "--packages-root",
        str(packages_root),
        "python-core-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["merge_plan"]["build_roots"] == [
        "python-core-gfx1151",
        "python-leaf-gfx1151",
        "python-app-gfx1151",
    ]


def test_install_subcommand_keeps_explicit_split_output_precise(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "install",
        "--dry-run",
        "--json",
        "--packages-root",
        str(packages_root),
        "rocm-core-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["merge_plan"]["build_roots"] == ["therock-gfx1151"]
    assert payload["merge_plan"]["install_outputs"] == ["rocm-core-gfx1151"]
    assert payload["steps"][0]["commands"][0]["argv"][-1] == "rocm-core-gfx1151"


def test_tree_preview_uses_unicode_tree_characters(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--preview=tree",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    assert "Merge plan" in result.stdout
    assert "└──" in result.stdout
    assert "[1] python-app-gfx1151" in result.stdout


def test_tree_preview_renders_dependency_forest_for_dependency_expansion(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--preview=tree",
        "--deps",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    assert "Dependency forest" in result.stdout
    assert "[1] therock-gfx1151" in result.stdout
    assert "[2] python-core-gfx1151" in result.stdout
    assert "[3] python-leaf-gfx1151" in result.stdout
    assert "[4] python-app-gfx1151" in result.stdout
    assert result.stdout.index("[1] therock-gfx1151") < result.stdout.index(
        "[2] python-core-gfx1151"
    )
    assert result.stdout.index("[2] python-core-gfx1151") < result.stdout.index(
        "[3] python-leaf-gfx1151"
    )
    assert result.stdout.index("[3] python-leaf-gfx1151") < result.stdout.index(
        "[4] python-app-gfx1151"
    )


def test_commands_preview_includes_concrete_commands(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--preview=commands",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    assert "$ makepkg -Csf --noconfirm" in result.stdout
    assert "$ sudo pacman -Sy --noconfirm python-app-gfx1151" in result.stdout


def test_tree_preview_can_be_colored(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--preview=tree",
        "--color=always",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    assert "\x1b[" in result.stdout
    assert "Build order" in result.stdout
    assert "python-app-gfx1151" in result.stdout


def test_color_never_keeps_preview_plain(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "run",
        "--dry-run",
        "--preview=tree",
        "--color=never",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    assert "\x1b[" not in result.stdout


def test_history_and_logs_report_persisted_runs(tmp_path: Path):
    module = load_module()
    state_root = tmp_path / "state"
    run_dir = state_root / "20260418T120000-demo"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        json.dumps({"plan_id": "demo", "command": "run", "targets": ["pkg"]}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps({"status": "failed", "run_ids": ["run-1"], "active_pid": None}),
        encoding="utf-8",
    )
    (run_dir / "run-1.log").write_text("hello log\n", encoding="utf-8")

    history = module.history_records(state_root)
    assert history[0]["status"] == "failed"
    assert history[0]["path"] == str(run_dir)
    assert module.latest_plan_dir(state_root) == run_dir
    assert module.resolve_log_paths(run_dir, step_id=None, run_id=None) == [
        run_dir / "run-1.log"
    ]


def test_build_steps_do_not_request_sudo_keepalive(tmp_path: Path):
    module = load_module()
    plan = {
        "steps": [
            {
                "id": "0001-build-demo",
                "kind": "build",
                "commands": [
                    {
                        "argv": ["makepkg", "-Csf", "--noconfirm"],
                        "cwd": "/tmp/demo",
                        "privileged": False,
                    }
                ],
            }
        ],
    }

    assert not module.plan_requires_sudo_keepalive(plan)
    assert plan["steps"][0]["commands"][0]["argv"] == ["makepkg", "-Csf", "--noconfirm"]


def test_privileged_steps_request_sudo_keepalive(tmp_path: Path):
    module = load_module()
    plan = {
        "steps": [
            {
                "id": "0001-publish-demo",
                "kind": "publish",
                "commands": [
                    {
                        "argv": ["sudo", "install", "-d", "/srv/pacman/demo"],
                        "privileged": True,
                    }
                ],
            }
        ],
    }

    assert module.plan_requires_sudo_keepalive(plan)


def test_publish_steps_require_current_packagelist_artifacts(tmp_path: Path):
    packages_root = graph_fixture(tmp_path)
    result = run_amerge(
        "publish",
        "--dry-run",
        "--json",
        "--packages-root",
        str(packages_root),
        "python-app-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    update_command = payload["steps"][0]["commands"][0]["argv"]
    assert "--require-packagelist" in update_command


def test_command_environment_removes_user_python_state(monkeypatch):
    module = load_module()
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", "/home/demo/.cache/python")
    monkeypatch.setenv("PYTHONSTARTUP", "/home/demo/.config/python/startup.py")
    monkeypatch.setenv("PYTHONUSERBASE", "/home/demo/.local/share/python")
    monkeypatch.setenv("PYTHON_EGG_CACHE", "/home/demo/.cache/python-eggs")
    monkeypatch.setenv("PYTHONPATH", "/home/demo/python")
    monkeypatch.setenv("TERM", "xterm-256color")

    env = module.sanitized_command_env()

    for key in module.SANITIZED_COMMAND_ENV_KEYS:
        assert key not in env
    assert env["TERM"] == "xterm-256color"
    assert module.sanitized_command_env_note() == (
        "# amerge unset Python user environment: "
        "PYTHON_EGG_CACHE, PYTHONPATH, PYTHONPYCACHEPREFIX, "
        "PYTHONSTARTUP, PYTHONUSERBASE\n"
    )


def test_write_json_preserves_existing_file_when_atomic_replace_fails(
    tmp_path: Path,
    monkeypatch,
):
    module = load_module()
    path = tmp_path / "state.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        module.write_json(path, {"old": False})

    assert path.read_text(encoding="utf-8") == '{"old": true}\n'
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_history_does_not_treat_reused_pid_as_active_without_lock(tmp_path: Path):
    module = load_module()
    state_root = tmp_path / "state"
    run_dir = state_root / "20260418T120000-demo"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        json.dumps({"plan_id": "demo", "command": "run", "targets": ["pkg"]}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps({"status": "running", "run_ids": ["run-1"], "active_pid": os.getpid()}),
        encoding="utf-8",
    )

    [record] = module.history_records(state_root)

    assert record["active"] is False


def test_history_can_read_plan_state_without_write_permission(tmp_path: Path):
    module = load_module()
    state_root = tmp_path / "state"
    run_dir = state_root / "20260418T120000-demo"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        json.dumps({"plan_id": "demo", "command": "build", "targets": ["pkg"]}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps({"status": "completed", "run_ids": ["run-1"], "active_pid": None}),
        encoding="utf-8",
    )
    lock_path = run_dir / module.LOCK_FILE
    lock_path.write_text("12345\n", encoding="utf-8")

    try:
        lock_path.chmod(0o444)
        run_dir.chmod(0o555)

        [record] = module.history_records(state_root)
    finally:
        run_dir.chmod(0o755)
        lock_path.chmod(0o644)

    assert record["status"] == "completed"
    assert record["active"] is False


def test_run_plan_refuses_when_plan_lock_is_already_held(tmp_path: Path):
    module = load_module()
    plan = {
        "schema_version": 1,
        "plan_id": "locked-demo",
        "created_at": "2026-04-18T12:00:00-04:00",
        "command": "run",
        "targets": ["demo"],
        "flags": {"deps": False, "rdeps": False},
        "config": {},
        "merge_plan": {"build_roots": ["demo"], "install_outputs": ["demo"]},
        "dependency_graph": [],
        "steps": [
            {
                "id": "0001-ok",
                "label": "ok",
                "kind": "test",
                "root": "demo",
                "commands": [{"argv": [sys.executable, "-c", "print('ok')"], "cwd": None}],
            }
        ],
    }
    plan_dir = module.save_new_plan(plan, tmp_path / "state")

    with module.PlanRunLock(plan_dir):
        assert module.run_plan(plan_dir) == 1

    state = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "pending"
    assert state["steps"]["0001-ok"]["status"] == "pending"


def test_running_command_is_recorded_before_it_exits(tmp_path: Path):
    module = load_module()
    plan = {
        "schema_version": 1,
        "plan_id": "running-command-demo",
        "created_at": "2026-04-18T12:00:00-04:00",
        "command": "run",
        "targets": ["demo"],
        "flags": {"deps": False, "rdeps": False},
        "config": {},
        "merge_plan": {"build_roots": ["demo"], "install_outputs": ["demo"]},
        "dependency_graph": [],
        "steps": [
            {
                "id": "0001-sleep",
                "label": "sleep",
                "kind": "test",
                "root": "demo",
                "commands": [
                    {
                        "argv": [
                            sys.executable,
                            "-c",
                            "import time; print('started', flush=True); time.sleep(1)",
                        ],
                        "cwd": None,
                    }
                ],
            }
        ],
    }
    plan_dir = module.save_new_plan(plan, tmp_path / "state")
    result: dict[str, int] = {}
    thread = threading.Thread(
        target=lambda: result.setdefault("exit_status", module.run_plan(plan_dir))
    )
    thread.start()
    try:
        deadline = time.monotonic() + 5
        command_record = None
        while time.monotonic() < deadline:
            state = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
            commands = state["steps"]["0001-sleep"]["commands"]
            if commands:
                command_record = commands[0]
                break
            time.sleep(0.05)

        assert command_record is not None
        assert command_record["status"] == "running"
        assert command_record["exit_status"] is None
        assert Path(command_record["log_path"]).is_file()
    finally:
        thread.join(timeout=5)

    assert result == {"exit_status": 0}


def test_failed_plan_records_logs_and_resume_skip_continues(
    tmp_path: Path,
    capsys,
):
    module = load_module()
    plan = {
        "schema_version": 1,
        "plan_id": "failed-demo",
        "created_at": "2026-04-18T12:00:00-04:00",
        "command": "run",
        "targets": ["demo"],
        "flags": {"deps": False, "rdeps": False},
        "config": {},
        "merge_plan": {"build_roots": ["demo"], "install_outputs": ["demo"]},
        "dependency_graph": [],
        "steps": [
            {
                "id": "0001-fail",
                "label": "fail intentionally",
                "kind": "test",
                "root": "demo",
                "commands": [
                    {
                        "argv": [
                            sys.executable,
                            "-c",
                            "import sys; print('bad step'); raise SystemExit(7)",
                        ],
                        "cwd": None,
                        "privileged": False,
                    }
                ],
            },
            {
                "id": "0002-ok",
                "label": "continue after skip",
                "kind": "test",
                "root": "demo",
                "commands": [
                    {
                        "argv": [sys.executable, "-c", "print('ok step')"],
                        "cwd": None,
                        "privileged": False,
                    }
                ],
            },
        ],
    }
    plan_dir = module.save_new_plan(plan, tmp_path / "state")

    assert module.run_plan(plan_dir) == 1
    captured = capsys.readouterr()
    assert "Merge failed" in captured.err
    assert "Failed step: 0001-fail" in captured.err
    assert "AMERGE_" not in captured.err
    failed_state = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
    assert failed_state["status"] == "failed"
    assert failed_state["steps"]["0001-fail"]["status"] == "failed"
    assert failed_state["steps"]["0001-fail"]["commands"][0]["exit_status"] == 7
    first_log = Path(failed_state["steps"]["0001-fail"]["commands"][0]["log_path"])
    assert "bad step" in first_log.read_text(encoding="utf-8")
    assert not (plan_dir / "active.pid").exists()

    start_index = module.first_incomplete_step_index(plan, failed_state)
    assert module.run_plan(plan_dir, start_index=start_index, skip_first=True) == 0
    resumed_state = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
    assert resumed_state["status"] == "completed"
    assert resumed_state["steps"]["0001-fail"]["status"] == "skipped"
    assert resumed_state["steps"]["0002-ok"]["status"] == "completed"


def test_repo_metadata_does_not_reference_python_meson_python():
    checked = [
        REPO_ROOT / "policies/recipe-packages.toml",
        REPO_ROOT / "packages/python-numpy-gfx1151/PKGBUILD",
        REPO_ROOT / "packages/python-numpy-gfx1151/recipe.json",
    ]

    for path in checked:
        text = path.read_text(encoding="utf-8")
        assert "python-meson-python" not in text
        assert "meson-python" in text

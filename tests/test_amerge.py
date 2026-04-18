from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


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
    assert "AMERGE_TARGETS_REQUIRED" in result.stderr


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


def test_build_steps_request_sudo_keepalive_without_wrapping_makepkg(tmp_path: Path):
    module = load_module()
    plan = {
        "steps": [
            {
                "id": "0001-build-demo",
                "kind": "build",
                "commands": [
                    {
                        "argv": ["makepkg", "-sf", "--noconfirm"],
                        "cwd": "/tmp/demo",
                        "privileged": False,
                    }
                ],
            }
        ],
    }

    assert module.plan_requires_sudo_keepalive(plan)
    assert plan["steps"][0]["commands"][0]["argv"][0] == "makepkg"


def test_failed_plan_records_logs_and_resume_skip_continues(tmp_path: Path):
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

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from repo_package_graph import RepoPackageRoot, discover_repo_package_roots


DEFAULT_PACKAGES_ROOT = REPO_ROOT / "packages"
DEFAULT_REPO_DIR = REPO_ROOT / "repo/x86_64"
DEFAULT_PUBLISH_ROOT = Path(
    os.environ.get("PUBLISH_ROOT", "/srv/pacman/strix-halo-gfx1151/x86_64")
)
DEFAULT_STATE_ROOT = REPO_ROOT / "docs/worklog/amerge"
SANITIZED_COMMAND_ENV_KEYS = (
    "PYTHON_EGG_CACHE",
    "PYTHONPATH",
    "PYTHONPYCACHEPREFIX",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)
LOCK_FILE = "active.lock"

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"


def colorize(text: object, enabled: bool, *codes: str) -> str:
    value = str(text)
    if not enabled or not codes:
        return value
    return "".join(codes) + value + RESET


def preview_uses_color(args: argparse.Namespace) -> bool:
    choice = getattr(args, "color", "auto")
    if choice == "always":
        return True
    if choice == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


@dataclass(frozen=True)
class CommandSpec:
    argv: tuple[str, ...]
    cwd: str | None = None
    privileged: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "privileged": self.privileged,
        }


@dataclass(frozen=True)
class StepSpec:
    id: str
    label: str
    kind: str
    root: str | None
    commands: tuple[CommandSpec, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "root": self.root,
            "commands": [command.to_json() for command in self.commands],
        }


class PlanAlreadyActive(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def timestamp_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def new_plan_id() -> str:
    return f"{timestamp_id()}-{uuid.uuid4().hex[:8]}"


def output_to_root_map(roots: dict[str, RepoPackageRoot]) -> dict[str, str]:
    return {
        output: root_name
        for root_name, root in roots.items()
        for output in root.outputs
    }


def installed_repo_outputs(roots: dict[str, RepoPackageRoot]) -> list[str]:
    repo_outputs = set(output_to_root_map(roots))
    result = subprocess.run(
        ["pacman", "-Qq"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Could not list installed packages: pacman -Qq exited "
            f"with status {result.returncode}."
        )
    return sorted(output for output in result.stdout.splitlines() if output in repo_outputs)


def parse_menu_selection(selection: str, count: int) -> list[int]:
    indexes: set[int] = set()
    for chunk in selection.replace(",", " ").split():
        try:
            if "-" in chunk:
                start_text, end_text = chunk.split("-", 1)
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    start, end = end, start
                indexes.update(range(start, end + 1))
            else:
                indexes.add(int(chunk))
        except ValueError as exc:
            raise SystemExit(f"Invalid menu selection: {chunk}") from exc
    invalid = sorted(index for index in indexes if index < 1 or index > count)
    if invalid:
        raise SystemExit(f"Menu selection is out of range: {invalid[0]}")
    return sorted(indexes)


def prompt_for_targets(roots: dict[str, RepoPackageRoot]) -> list[str]:
    root_names = sorted(roots)
    print("No amerge targets were selected.")
    print("  1. all repo package roots")
    print("  2. installed repo package outputs")
    print("  3. choose package roots")
    answer = input("Select target set [1/2/3]: ").strip() or "1"
    if answer == "1":
        return root_names
    if answer == "2":
        outputs = installed_repo_outputs(roots)
        if not outputs:
            raise SystemExit("No installed repo packages were found.")
        return outputs
    if answer != "3":
        raise SystemExit("No package selection was made.")

    for index, root_name in enumerate(root_names, start=1):
        outputs = ", ".join(roots[root_name].outputs)
        print(f"  {index}. {root_name} ({outputs})")
    selection = input("Select package roots by number or range: ").strip()
    if not selection:
        raise SystemExit("No package selection was made.")
    return [root_names[index - 1] for index in parse_menu_selection(selection, len(root_names))]


def resolve_targets(
    roots: dict[str, RepoPackageRoot],
    targets: list[str],
) -> set[str]:
    outputs = output_to_root_map(roots)
    resolved: set[str] = set()
    for target in targets:
        if target in roots:
            resolved.add(target)
        elif target in outputs:
            resolved.add(outputs[target])
        else:
            raise SystemExit(f"Unknown repo package or output: {target}")
    return resolved


def requested_outputs_for_targets(
    roots: dict[str, RepoPackageRoot],
    targets: list[str],
) -> dict[str, set[str]]:
    outputs = output_to_root_map(roots)
    requested: dict[str, set[str]] = {}
    for target in targets:
        if target in outputs:
            requested.setdefault(outputs[target], set()).add(target)
        elif target in roots:
            requested.setdefault(target, set()).update(roots[target].outputs)
        else:
            raise SystemExit(f"Unknown repo package or output: {target}")
    return requested


def resolve_initial_targets(
    roots: dict[str, RepoPackageRoot],
    args: argparse.Namespace,
) -> list[str]:
    targets = list(args.targets)
    if targets and (args.all or args.installed):
        raise SystemExit("Choose package names or a selector, not both.")
    if targets:
        return targets
    if args.all:
        return sorted(roots)
    if args.installed:
        outputs = installed_repo_outputs(roots)
        if not outputs:
            raise SystemExit("No installed repo packages were found.")
        return outputs
    if sys.stdin.isatty() and sys.stdout.isatty():
        return prompt_for_targets(roots)
    raise SystemExit(
        "Choose packages to merge: pass package names, --all, or --installed."
    )


def dependency_closure(
    roots: dict[str, RepoPackageRoot],
    selected: set[str],
) -> set[str]:
    expanded = set(selected)
    stack = list(selected)
    while stack:
        root_name = stack.pop()
        for dependency in roots[root_name].repo_dependency_roots:
            if dependency not in expanded:
                expanded.add(dependency)
                stack.append(dependency)
    return expanded


def reverse_dependency_closure(
    roots: dict[str, RepoPackageRoot],
    selected: set[str],
) -> set[str]:
    reverse: dict[str, set[str]] = {root_name: set() for root_name in roots}
    for root_name, root in roots.items():
        for dependency in root.repo_dependency_roots:
            reverse.setdefault(dependency, set()).add(root_name)

    expanded = set(selected)
    stack = list(selected)
    while stack:
        root_name = stack.pop()
        for dependent in reverse.get(root_name, set()):
            if dependent not in expanded:
                expanded.add(dependent)
                stack.append(dependent)
    return expanded


def topo_sort_selected(
    roots: dict[str, RepoPackageRoot],
    selected: set[str],
) -> list[str]:
    incoming = {
        root_name: {
            dependency
            for dependency in roots[root_name].repo_dependency_roots
            if dependency in selected
        }
        for root_name in selected
    }
    ordered: list[str] = []
    ready = sorted(root_name for root_name, dependencies in incoming.items() if not dependencies)

    while ready:
        root_name = ready.pop(0)
        ordered.append(root_name)
        for other_name in sorted(incoming):
            if root_name not in incoming[other_name]:
                continue
            incoming[other_name].remove(root_name)
            if not incoming[other_name] and other_name not in ordered and other_name not in ready:
                ready.append(other_name)
        ready.sort()

    if len(ordered) != len(selected):
        unresolved = sorted(root_name for root_name, deps in incoming.items() if deps)
        raise SystemExit(
            "The package dependency graph contains a cycle involving: "
            f"{', '.join(unresolved)}"
        )
    return ordered


def selected_roots_for_args(
    roots: dict[str, RepoPackageRoot],
    targets: list[str],
    *,
    include_deps: bool,
    include_rdeps: bool,
) -> set[str]:
    selected = resolve_targets(roots, targets)
    expanded = set(selected)
    if include_deps:
        expanded |= dependency_closure(roots, selected)
    if include_rdeps:
        expanded |= reverse_dependency_closure(roots, selected)
    return expanded


def install_outputs_by_root_for_plan(
    roots: dict[str, RepoPackageRoot],
    build_roots: list[str],
    requested_outputs: dict[str, set[str]],
    *,
    include_deps: bool,
    include_rdeps: bool,
) -> dict[str, list[str]]:
    build_root_set = set(build_roots)
    outputs = output_to_root_map(roots)
    by_root = {
        root_name: set(root_outputs)
        for root_name, root_outputs in requested_outputs.items()
        if root_name in build_root_set
    }

    for root_name in build_roots:
        root = roots[root_name]
        for dependency in (*root.depends, *root.makedepends):
            dependency_root = outputs.get(dependency)
            if dependency_root in build_root_set and dependency_root != root_name:
                by_root.setdefault(dependency_root, set()).add(dependency)

    if include_rdeps:
        for root_name in build_roots:
            by_root.setdefault(root_name, set()).update(roots[root_name].outputs)

    return {
        root_name: sorted(root_outputs)
        for root_name, root_outputs in by_root.items()
        if root_outputs
    }


def build_steps(
    *,
    command: str,
    roots: dict[str, RepoPackageRoot],
    build_roots: list[str],
    install_outputs_by_root: dict[str, list[str]],
    repo_dir: Path,
    publish_root: Path,
) -> list[StepSpec]:
    steps: list[StepSpec] = []
    python = sys.executable
    update_repo = str(REPO_ROOT / "tools/update_pacman_repo.py")

    def update_repo_command(root: RepoPackageRoot) -> CommandSpec:
        return CommandSpec(
            argv=(
                python,
                update_repo,
                "--package-dir",
                str(root.package_dir),
                "--repo-dir",
                str(repo_dir),
                "--recursive",
                "--require-packagelist",
            )
        )

    if command in {"run", "build"}:
        for index, root_name in enumerate(build_roots, start=1):
            root = roots[root_name]
            steps.append(
                StepSpec(
                    id=f"{index:04d}-build-{root_name}",
                    label=f"build {root_name}",
                    kind="build",
                    root=root_name,
                    commands=(
                        CommandSpec(
                            argv=("makepkg", "-Csf", "--noconfirm"),
                            cwd=str(root.package_dir),
                        ),
                    ),
                )
            )
            if command == "run":
                steps.append(
                    StepSpec(
                        id=f"{index:04d}-publish-{root_name}",
                        label=f"publish {root_name}",
                        kind="publish",
                        root=root_name,
                        commands=(
                            update_repo_command(root),
                            CommandSpec(
                                argv=("sudo", "install", "-d", str(publish_root)),
                                privileged=True,
                            ),
                            CommandSpec(
                                argv=(
                                    "sudo",
                                    "rsync",
                                    "-a",
                                    "--delete",
                                    f"{repo_dir}/",
                                    f"{publish_root}/",
                                ),
                                privileged=True,
                            ),
                        ),
                    )
                )
                root_install_outputs = install_outputs_by_root.get(root_name, [])
                if root_install_outputs:
                    steps.append(
                        StepSpec(
                            id=f"{index:04d}-install-{root_name}",
                            label=f"install {root_name} outputs",
                            kind="install",
                            root=root_name,
                            commands=(
                                CommandSpec(
                                    argv=(
                                        "sudo",
                                        "pacman",
                                        "-Sy",
                                        "--noconfirm",
                                        *root_install_outputs,
                                    ),
                                    privileged=True,
                                ),
                            ),
                        )
                    )

    if command == "publish":
        for index, root_name in enumerate(build_roots, start=1):
            root = roots[root_name]
            steps.append(
                StepSpec(
                    id=f"{index:04d}-publish-{root_name}",
                    label=f"publish {root_name}",
                    kind="publish",
                    root=root_name,
                    commands=(
                        update_repo_command(root),
                        CommandSpec(
                            argv=("sudo", "install", "-d", str(publish_root)),
                            privileged=True,
                        ),
                        CommandSpec(
                            argv=(
                                "sudo",
                                "rsync",
                                "-a",
                                "--delete",
                                f"{repo_dir}/",
                                f"{publish_root}/",
                            ),
                            privileged=True,
                        ),
                    ),
                )
            )

    if command == "install":
        install_outputs = [
            output
            for root_name in build_roots
            for output in install_outputs_by_root.get(root_name, [])
        ]
        steps.append(
            StepSpec(
                id=f"{len(steps) + 1:04d}-install-selected",
                label="install selected outputs",
                kind="install",
                root=None,
                commands=(
                    CommandSpec(
                        argv=("sudo", "pacman", "-Sy", "--noconfirm", *install_outputs),
                        privileged=True,
                    ),
                ),
            )
        )
    return steps


def create_merge_plan(args: argparse.Namespace, *, command: str) -> dict[str, object]:
    packages_root = args.packages_root.resolve()
    repo_dir = args.repo_dir.resolve()
    publish_root = args.publish_root.resolve()
    roots = discover_repo_package_roots(packages_root)
    targets = resolve_initial_targets(roots, args)
    requested_outputs = requested_outputs_for_targets(roots, targets)
    selected = selected_roots_for_args(
        roots,
        targets,
        include_deps=args.deps,
        include_rdeps=args.rdeps,
    )
    build_roots = topo_sort_selected(roots, selected)
    install_outputs_by_root = (
        {}
        if command in {"build", "publish"}
        else install_outputs_by_root_for_plan(
            roots,
            build_roots,
            requested_outputs,
            include_deps=args.deps,
            include_rdeps=args.rdeps,
        )
    )
    install_outputs = [
        output
        for root_name in build_roots
        for output in install_outputs_by_root.get(root_name, [])
    ]
    steps = build_steps(
        command=command,
        roots=roots,
        build_roots=build_roots,
        install_outputs_by_root=install_outputs_by_root,
        repo_dir=repo_dir,
        publish_root=publish_root,
    )
    plan_id = new_plan_id()
    return {
        "schema_version": 1,
        "plan_id": plan_id,
        "created_at": utc_now(),
        "command": command,
        "targets": targets,
        "flags": {
            "deps": args.deps,
            "rdeps": args.rdeps,
            "all": args.all,
            "installed": args.installed,
        },
        "config": {
            "packages_root": str(packages_root),
            "repo_dir": str(repo_dir),
            "publish_root": str(publish_root),
            "state_root": str(args.state_root.resolve()),
        },
        "merge_plan": {
            "build_roots": build_roots,
            "install_outputs": install_outputs,
            "install_outputs_by_root": install_outputs_by_root,
        },
        "dependency_graph": [
            {
                "root_name": root_name,
                "outputs": list(roots[root_name].outputs),
                "dependencies": sorted(
                    dependency
                    for dependency in roots[root_name].repo_dependency_roots
                    if dependency in selected
                ),
            }
            for root_name in build_roots
        ],
        "steps": [step.to_json() for step in steps],
    }


def render_flat_preview(plan: dict[str, object], *, color: bool = False) -> str:
    roots = plan["merge_plan"]["build_roots"]
    lines = [
        f"{colorize('Merge plan', color, BOLD, CYAN)} "
        f"{colorize(plan['plan_id'], color, DIM)}",
        colorize("Build order:", color, BOLD, BLUE),
    ]
    for index, root_name in enumerate(roots, start=1):
        lines.append(
            f"  {colorize(f'[{index}]', color, YELLOW)} "
            f"{colorize(root_name, color, GREEN)}"
        )
    lines.append(colorize("Steps:", color, BOLD, BLUE))
    for index, step in enumerate(plan["steps"], start=1):
        lines.append(
            f"  {colorize(f'{index}.', color, YELLOW)} "
            f"{colorize(step['label'], color, step_color(str(step['kind'])))}"
        )
    return "\n".join(lines)


def step_color(kind: str) -> str:
    if kind == "build":
        return MAGENTA
    if kind == "publish":
        return CYAN
    if kind == "install":
        return GREEN
    return BLUE


def render_dependency_forest(plan: dict[str, object], *, color: bool = False) -> list[str]:
    build_order = list(plan["merge_plan"]["build_roots"])
    order_index = {root_name: index for index, root_name in enumerate(build_order)}
    dependencies_by_root = {
        str(item["root_name"]): [
            dependency
            for dependency in item.get("dependencies", [])
            if dependency in order_index
        ]
        for item in plan.get("dependency_graph", [])
    }
    lines: list[str] = []
    for index, root_name in enumerate(build_order):
        branch = "└──" if index == len(build_order) - 1 else "├──"
        child_prefix = "│       " if index == len(build_order) - 1 else "│   │   "
        lines.append(
            f"│   {colorize(branch, color, DIM)} "
            f"{colorize(f'[{index + 1}]', color, YELLOW)} "
            f"{colorize(root_name, color, GREEN)}"
        )
        dependencies = sorted(
            dependencies_by_root.get(root_name, []),
            key=lambda dependency: order_index[dependency],
        )
        for dep_index, dependency in enumerate(dependencies):
            dep_branch = "└──" if dep_index == len(dependencies) - 1 else "├──"
            lines.append(
                f"{child_prefix}{colorize(dep_branch, color, DIM)} "
                f"{colorize('needs', color, DIM)} "
                f"{colorize(f'[{order_index[dependency] + 1}]', color, YELLOW)} "
                f"{colorize(dependency, color, GREEN)}"
            )
    return lines


def render_tree_preview(plan: dict[str, object], *, color: bool = False) -> str:
    roots = list(plan["merge_plan"]["build_roots"])
    lines = [
        f"{colorize('Merge plan', color, BOLD, CYAN)} "
        f"{colorize(plan['plan_id'], color, DIM)}",
        f"{colorize('├──', color, DIM)} {colorize('Dependency forest', color, BOLD, BLUE)}",
    ]
    lines.extend(render_dependency_forest(plan, color=color))
    lines.append(f"{colorize('├──', color, DIM)} {colorize('Build order', color, BOLD, BLUE)}")
    for index, root_name in enumerate(roots, start=1):
        branch = "└──" if index == len(roots) else "├──"
        lines.append(
            f"    {colorize(branch, color, DIM)} "
            f"{colorize(f'[{index}]', color, YELLOW)} "
            f"{colorize(root_name, color, GREEN)}"
        )
    lines.append(f"{colorize('└──', color, DIM)} {colorize('Steps', color, BOLD, BLUE)}")
    steps = list(plan["steps"])
    for index, step in enumerate(steps, start=1):
        branch = "└──" if index == len(steps) else "├──"
        lines.append(
            f"    {colorize(branch, color, DIM)} "
            f"{colorize(f'{index}.', color, YELLOW)} "
            f"{colorize(step['label'], color, step_color(str(step['kind'])))}"
        )
    return "\n".join(lines)


def render_commands_preview(plan: dict[str, object], *, color: bool = False) -> str:
    lines = [
        f"{colorize('Merge plan', color, BOLD, CYAN)} "
        f"{colorize(plan['plan_id'], color, DIM)}",
        colorize("Commands:", color, BOLD, BLUE),
    ]
    for step in plan["steps"]:
        lines.append(f"  {colorize(str(step['label']), color, step_color(str(step['kind'])))}")
        for command in step["commands"]:
            lines.append(f"    $ {shlex.join(str(part) for part in command['argv'])}")
    return "\n".join(lines)


def render_preview(plan: dict[str, object], preview: str, *, color: bool = False) -> str:
    if preview == "tree":
        return render_tree_preview(plan, color=color)
    if preview == "commands":
        return render_commands_preview(plan, color=color)
    return render_flat_preview(plan, color=color)


def plan_requires_sudo_keepalive(plan: dict[str, object]) -> bool:
    return any(
        any(command.get("privileged") for command in step["commands"])
        for step in plan["steps"]
    )


def plan_dir_for(state_root: Path, plan_id: str) -> Path:
    return state_root / plan_id


def initial_state(plan: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "plan_id": plan["plan_id"],
        "status": "pending",
        "created_at": utc_now(),
        "started_at": None,
        "ended_at": None,
        "active_pid": None,
        "termination": None,
        "run_ids": [],
        "steps": {
            step["id"]: {
                "status": "pending",
                "attempts": 0,
                "started_at": None,
                "ended_at": None,
                "run_ids": [],
                "commands": [],
            }
            for step in plan["steps"]
        },
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        try:
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


class PlanRunLock:
    def __init__(self, plan_dir: Path):
        self.plan_dir = plan_dir
        self.path = plan_dir / LOCK_FILE
        self.handle: Any | None = None

    def __enter__(self) -> "PlanRunLock":
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise PlanAlreadyActive(f"Plan is already running: {self.plan_dir}") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"{os.getpid()}\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.handle is None:
            return
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def plan_lock_is_held(plan_dir: Path) -> bool:
    lock_path = plan_dir / LOCK_FILE
    if not lock_path.exists():
        return False
    with lock_path.open("r", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def save_new_plan(plan: dict[str, object], state_root: Path) -> Path:
    directory = plan_dir_for(state_root, str(plan["plan_id"]))
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "plan.json", plan)
    write_json(directory / "state.json", initial_state(plan))
    return directory


def latest_plan_dir(state_root: Path) -> Path | None:
    if not state_root.is_dir():
        return None
    candidates = [
        path
        for path in state_root.iterdir()
        if path.is_dir() and (path / "plan.json").is_file()
    ]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def history_records(state_root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not state_root.is_dir():
        return records
    for directory in sorted(state_root.iterdir()):
        if not directory.is_dir() or not (directory / "plan.json").is_file():
            continue
        plan = read_json(directory / "plan.json")
        state = read_json(directory / "state.json") if (directory / "state.json").is_file() else {}
        active = plan_lock_is_held(directory)
        records.append(
            {
                "plan_id": plan.get("plan_id", directory.name),
                "command": plan.get("command"),
                "targets": plan.get("targets", []),
                "status": state.get("status", "unknown"),
                "active": active,
                "created_at": plan.get("created_at"),
                "started_at": state.get("started_at"),
                "ended_at": state.get("ended_at"),
                "path": str(directory),
            }
        )
    return records


def resolve_plan_dir(state_root: Path, plan: str | None) -> Path:
    if plan in {None, "latest"}:
        latest = latest_plan_dir(state_root)
        if latest is None:
            raise SystemExit("No amerge history was found.")
        return latest
    candidate = state_root / str(plan)
    if not candidate.is_dir():
        matches = sorted(path for path in state_root.glob(f"{plan}*") if path.is_dir())
        if not matches:
            raise SystemExit(f"No amerge plan matched: {plan}")
        candidate = matches[-1]
    return candidate


def resolve_log_paths(plan_dir: Path, *, step_id: str | None, run_id: str | None) -> list[Path]:
    if step_id:
        root = plan_dir / "logs" / step_id
        if not root.is_dir():
            return []
        if run_id:
            return sorted(root.glob(f"{run_id}*.log"))
        return sorted(root.glob("*.log"))
    if run_id:
        return sorted(plan_dir.glob(f"{run_id}.log"))
    root_logs = sorted(plan_dir.glob("*.log"))
    if root_logs:
        return root_logs
    return sorted((plan_dir / "logs").glob("**/*.log"))


class SudoKeepalive:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "SudoKeepalive":
        if not self.enabled:
            return self
        subprocess.run(["sudo", "-v"], check=True)
        self.thread = threading.Thread(target=self.keepalive, daemon=True)
        self.thread.start()
        return self

    def keepalive(self) -> None:
        while not self.stop_event.wait(30):
            subprocess.run(
                ["sudo", "-n", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.thread is None:
            return
        self.stop_event.set()
        self.thread.join(timeout=2)


def append_run_log(plan_dir: Path, run_id: str, text: str) -> None:
    with (plan_dir / f"{run_id}.log").open("a", encoding="utf-8") as handle:
        handle.write(text)


def sanitized_command_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in SANITIZED_COMMAND_ENV_KEYS:
        env.pop(key, None)
    return env


def sanitized_command_env_note() -> str | None:
    removed = [key for key in SANITIZED_COMMAND_ENV_KEYS if key in os.environ]
    if not removed:
        return None
    return f"# amerge unset Python user environment: {', '.join(removed)}\n"


def execute_command(
    command: dict[str, object],
    *,
    log_path: Path,
    run_log_path: Path,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [str(part) for part in command["argv"]]
    cwd = command.get("cwd")
    header = f"$ {' '.join(argv)}\n"
    env_note = sanitized_command_env_note()
    if env_note:
        header += env_note
    log_path.write_text(header, encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as step_log, run_log_path.open(
        "a", encoding="utf-8"
    ) as run_log:
        run_log.write(header)
        run_log.flush()
        process = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=sanitized_command_env(),
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                print(line, end="")
                step_log.write(line)
                run_log.write(line)
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise


def append_command_attempt(
    state: dict[str, Any],
    *,
    step_id: str,
    command: dict[str, object],
    run_id: str,
    log_path: Path,
) -> None:
    state["steps"][step_id]["commands"].append(
        {
            "argv": command["argv"],
            "cwd": command.get("cwd"),
            "status": "running",
            "exit_status": None,
            "log_path": str(log_path),
            "run_id": run_id,
            "started_at": utc_now(),
            "ended_at": None,
        }
    )


def finish_command_attempt(
    state: dict[str, Any],
    *,
    step_id: str,
    run_id: str,
    log_path: Path,
    exit_status: int | None,
    status: str,
) -> None:
    log_path_text = str(log_path)
    for command in reversed(state["steps"][step_id]["commands"]):
        if command.get("run_id") == run_id and command.get("log_path") == log_path_text:
            command["status"] = status
            command["exit_status"] = exit_status
            command["ended_at"] = utc_now()
            return
    raise RuntimeError(f"COMMAND_ATTEMPT_MISSING: {step_id} {run_id} {log_path}")


def print_failure_summary(
    *,
    plan: dict[str, object],
    state: dict[str, object],
    failed_step_id: str,
    failed_command: dict[str, object],
    exit_status: int,
    log_path: Path,
) -> None:
    step_ids = [step["id"] for step in plan["steps"]]
    failed_index = step_ids.index(failed_step_id)
    completed = [
        step_id
        for step_id in step_ids
        if state["steps"][step_id]["status"] == "completed"
    ]
    remaining = step_ids[failed_index + 1 :]
    print("", file=sys.stderr)
    print(f"{RED}{BOLD}Merge failed{RESET}", file=sys.stderr)
    print(f"Failed step: {failed_step_id}", file=sys.stderr)
    print(f"Failed command: {' '.join(str(x) for x in failed_command['argv'])}", file=sys.stderr)
    print(f"Exit status: {exit_status}", file=sys.stderr)
    print(f"Log: {log_path}", file=sys.stderr)
    print(f"Completed steps: {', '.join(completed) if completed else '(none)'}", file=sys.stderr)
    print(f"Remaining steps: {', '.join(remaining) if remaining else '(none)'}", file=sys.stderr)


def run_plan(
    plan_dir: Path,
    *,
    start_index: int = 0,
    skip_first: bool = False,
) -> int:
    try:
        with PlanRunLock(plan_dir):
            return _run_plan_locked(
                plan_dir,
                start_index=start_index,
                skip_first=skip_first,
            )
    except PlanAlreadyActive as exc:
        print(f"{YELLOW}{BOLD}Merge already running:{RESET} {exc}", file=sys.stderr)
        return 1


def _run_plan_locked(
    plan_dir: Path,
    *,
    start_index: int = 0,
    skip_first: bool = False,
) -> int:
    plan = read_json(plan_dir / "plan.json")
    state = read_json(plan_dir / "state.json")
    run_id = f"{timestamp_id()}-{uuid.uuid4().hex[:8]}"
    run_log_path = plan_dir / f"{run_id}.log"
    state["status"] = "running"
    state["started_at"] = state.get("started_at") or utc_now()
    state["active_pid"] = os.getpid()
    state.setdefault("run_ids", []).append(run_id)
    write_json(plan_dir / "state.json", state)
    (plan_dir / "active.pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")

    def finish(status: str, termination: str | None) -> int:
        latest = read_json(plan_dir / "state.json")
        latest["status"] = status
        latest["ended_at"] = utc_now()
        latest["active_pid"] = None
        latest["termination"] = termination
        write_json(plan_dir / "state.json", latest)
        try:
            (plan_dir / "active.pid").unlink()
        except FileNotFoundError:
            pass
        return 0 if status == "completed" else 1

    current_step_id: str | None = None
    current_command_log_path: Path | None = None

    def mark_current_step(status: str) -> None:
        if current_step_id is None:
            return
        latest = read_json(plan_dir / "state.json")
        step_state = latest["steps"][current_step_id]
        if step_state["status"] == "running":
            step_state["status"] = status
            step_state["ended_at"] = utc_now()
            write_json(plan_dir / "state.json", latest)

    def mark_current_command(status: str) -> None:
        if current_step_id is None or current_command_log_path is None:
            return
        latest = read_json(plan_dir / "state.json")
        finish_command_attempt(
            latest,
            step_id=current_step_id,
            run_id=run_id,
            log_path=current_command_log_path,
            exit_status=None,
            status=status,
        )
        write_json(plan_dir / "state.json", latest)

    try:
        with SudoKeepalive(plan_requires_sudo_keepalive(plan)):
            steps = list(plan["steps"])
            if skip_first and start_index < len(steps):
                skipped = steps[start_index]
                state = read_json(plan_dir / "state.json")
                state["steps"][skipped["id"]]["status"] = "skipped"
                state["steps"][skipped["id"]]["ended_at"] = utc_now()
                write_json(plan_dir / "state.json", state)
                start_index += 1

            for step in steps[start_index:]:
                step_id = str(step["id"])
                state = read_json(plan_dir / "state.json")
                if state["steps"][step_id]["status"] in {"completed", "skipped"}:
                    continue
                current_step_id = step_id
                step_state = state["steps"][step_id]
                step_state["status"] = "running"
                step_state["attempts"] = int(step_state.get("attempts", 0)) + 1
                step_state["started_at"] = utc_now()
                step_state.setdefault("run_ids", []).append(run_id)
                write_json(plan_dir / "state.json", state)

                print(f"\033[36m==> {step['label']}\033[0m")
                for command_index, command in enumerate(step["commands"], start=1):
                    log_path = plan_dir / "logs" / step_id / f"{run_id}-{command_index}.log"
                    current_command_log_path = log_path
                    state = read_json(plan_dir / "state.json")
                    append_command_attempt(
                        state,
                        step_id=step_id,
                        command=command,
                        run_id=run_id,
                        log_path=log_path,
                    )
                    write_json(plan_dir / "state.json", state)
                    exit_status = execute_command(
                        command,
                        log_path=log_path,
                        run_log_path=run_log_path,
                    )
                    state = read_json(plan_dir / "state.json")
                    finish_command_attempt(
                        state,
                        step_id=step_id,
                        run_id=run_id,
                        log_path=log_path,
                        exit_status=exit_status,
                        status="completed" if exit_status == 0 else "failed",
                    )
                    write_json(plan_dir / "state.json", state)
                    if exit_status != 0:
                        state["steps"][step_id]["status"] = "failed"
                        state["steps"][step_id]["ended_at"] = utc_now()
                        write_json(plan_dir / "state.json", state)
                        print_failure_summary(
                            plan=plan,
                            state=state,
                            failed_step_id=step_id,
                            failed_command=command,
                            exit_status=exit_status,
                            log_path=log_path,
                        )
                        return finish("failed", "error_exit")
                    current_command_log_path = None

                state = read_json(plan_dir / "state.json")
                state["steps"][step_id]["status"] = "completed"
                state["steps"][step_id]["ended_at"] = utc_now()
                write_json(plan_dir / "state.json", state)
                current_step_id = None
        return finish("completed", None)
    except KeyboardInterrupt:
        mark_current_command("interrupted")
        mark_current_step("interrupted")
        return finish("interrupted", "interrupt")
    except subprocess.CalledProcessError as exc:
        append_run_log(plan_dir, run_id, f"command failed before step execution: {exc}\n")
        return finish("failed", "pre_step_error")
    except Exception as exc:
        mark_current_step("failed")
        append_run_log(
            plan_dir,
            run_id,
            f"unexpected amerge failure: {type(exc).__name__}: {exc}\n",
        )
        print(
            f"{RED}{BOLD}Amerge hit an unexpected error:{RESET} "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return finish("failed", "unexpected_exception")


def first_incomplete_step_index(plan: dict[str, object], state: dict[str, object]) -> int:
    for index, step in enumerate(plan["steps"]):
        if state["steps"][step["id"]]["status"] not in {"completed", "skipped"}:
            return index
    return len(plan["steps"])


def maybe_confirm(plan: dict[str, object], args: argparse.Namespace) -> None:
    preview = args.preview
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if preview is None and interactive and not args.noconfirm:
        preview = "tree"
    if preview:
        print(render_preview(plan, preview, color=preview_uses_color(args)))
    if interactive and not args.noconfirm:
        answer = input("Proceed with this merge plan? [Y/n] ").strip().lower()
        if answer in {"n", "no"}:
            raise SystemExit("Merge aborted.")


def print_history(records: list[dict[str, object]]) -> None:
    if not records:
        print("No amerge history.")
        return
    for record in records:
        active = " active" if record["active"] else ""
        targets = " ".join(str(target) for target in record.get("targets", []))
        print(
            f"{record['plan_id']} {record['status']}{active} "
            f"{record['command']} {targets}".rstrip()
        )


def add_common_plan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("targets", nargs="*")
    selectors = parser.add_mutually_exclusive_group()
    selectors.add_argument("--all", action="store_true", help="select all repo package roots")
    selectors.add_argument(
        "--installed",
        action="store_true",
        help="select repo package outputs currently installed on this host",
    )
    parser.add_argument("--deps", action="store_true", help="also rebuild dependencies")
    parser.add_argument("--rdeps", action="store_true", help="also rebuild reverse dependencies")
    parser.add_argument("--packages-root", type=Path, default=DEFAULT_PACKAGES_ROOT)
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--publish-root", type=Path, default=DEFAULT_PUBLISH_ROOT)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-y", "--noconfirm", action="store_true")
    parser.add_argument("--preview", choices=("tree", "flat", "commands"), default=None)
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colorize human preview output",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Source-based Arch addon repo merge runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "build", "publish", "install"):
        add_common_plan_args(subparsers.add_parser(command))

    resume = subparsers.add_parser("resume")
    resume.add_argument("plan", nargs="?", default="latest")
    resume.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    resume.add_argument("--skip", action="store_true")

    history = subparsers.add_parser("history")
    history.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    history.add_argument("--json", action="store_true")
    history.add_argument("--status")

    logs = subparsers.add_parser("logs")
    logs.add_argument("plan", nargs="?", default="latest")
    logs.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    logs.add_argument("--step")
    logs.add_argument("--run")
    logs.add_argument("--path", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"run", "build", "publish", "install"}:
        plan = create_merge_plan(args, command=args.command)
        if args.dry_run:
            if args.json:
                print(json.dumps(plan, indent=2, sort_keys=True))
            else:
                print(
                    render_preview(
                        plan,
                        args.preview or "flat",
                        color=preview_uses_color(args),
                    )
                )
            return 0
        maybe_confirm(plan, args)
        plan_dir = save_new_plan(plan, args.state_root.resolve())
        return run_plan(plan_dir)

    if args.command == "resume":
        plan_dir = resolve_plan_dir(args.state_root.resolve(), args.plan)
        plan = read_json(plan_dir / "plan.json")
        state = read_json(plan_dir / "state.json")
        start_index = first_incomplete_step_index(plan, state)
        return run_plan(plan_dir, start_index=start_index, skip_first=args.skip)

    if args.command == "history":
        records = history_records(args.state_root.resolve())
        if args.status:
            records = [record for record in records if record["status"] == args.status]
        if args.json:
            print(json.dumps(records, indent=2, sort_keys=True))
        else:
            print_history(records)
        return 0

    if args.command == "logs":
        plan_dir = resolve_plan_dir(args.state_root.resolve(), args.plan)
        paths = resolve_log_paths(plan_dir, step_id=args.step, run_id=args.run)
        if args.path:
            for path in paths:
                print(path)
            return 0
        for path in paths:
            print(f"==> {path} <==")
            print(path.read_text(encoding="utf-8"), end="")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

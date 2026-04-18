#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shlex
from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoPackageRoot:
    root_name: str
    package_dir: Path
    outputs: tuple[str, ...]
    depends: tuple[str, ...]
    makedepends: tuple[str, ...]
    repo_dependency_roots: frozenset[str]


def _strip_inline_comment(line: str) -> str:
    if "#" not in line:
        return line
    in_single = False
    in_double = False
    escaped = False
    chars: list[str] = []
    for char in line:
        if escaped:
            chars.append(char)
            escaped = False
            continue
        if char == "\\":
            chars.append(char)
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            chars.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            chars.append(char)
            continue
        if char == "#" and not in_single and not in_double:
            break
        chars.append(char)
    return "".join(chars)


def _parse_scalar(value: str) -> str:
    parsed = shlex.split(value, comments=False)
    if not parsed:
        raise RuntimeError(f"PKGBUILD_SCALAR_PARSE_FAILED: {value!r}")
    return parsed[0]


def _parse_array(body: str) -> tuple[str, ...]:
    parts = shlex.split(body, comments=False)
    return tuple(parts)


def _extract_assignment(lines: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for index, raw_line in enumerate(lines):
        line = _strip_inline_comment(raw_line).strip()
        if not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if value.startswith("("):
            collected = [value[1:]]
            depth = value.count("(") - value.count(")")
            cursor = index
            while depth > 0:
                cursor += 1
                if cursor >= len(lines):
                    raise RuntimeError(f"PKGBUILD_ARRAY_UNTERMINATED: {key}")
                next_line = _strip_inline_comment(lines[cursor]).strip()
                collected.append(next_line)
                depth += next_line.count("(") - next_line.count(")")
            joined = "\n".join(collected)
            if ")" not in joined:
                raise RuntimeError(f"PKGBUILD_ARRAY_UNTERMINATED: {key}")
            return joined.rsplit(")", 1)[0]
        return value
    return None


def read_pkgbuild_metadata(path: Path) -> dict[str, tuple[str, ...] | str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    pkgname_value = _extract_assignment(lines, "pkgname")
    if pkgname_value is None:
        raise RuntimeError(f"PKGBUILD_METADATA_MISSING: {path}")
    depends_value = _extract_assignment(lines, "depends") or ""
    makedepends_value = _extract_assignment(lines, "makedepends") or ""
    if pkgname_value.startswith("(") or "\n" in pkgname_value:
        outputs = _parse_array(pkgname_value)
    elif pkgname_value.startswith("'") or pkgname_value.startswith('"'):
        outputs = (_parse_scalar(pkgname_value),)
    elif " " in pkgname_value:
        outputs = _parse_array(pkgname_value)
    else:
        outputs = (pkgname_value.strip().strip("'\""),)
    return {
        "outputs": tuple(sorted(output for output in outputs if output)),
        "depends": _parse_array(depends_value),
        "makedepends": _parse_array(makedepends_value),
    }


def _load_recipe_output(path: Path) -> tuple[str, ...]:
    recipe = json.loads(path.read_text(encoding="utf-8"))
    package_name = recipe.get("package_name")
    if not package_name:
        raise RuntimeError(f"RECIPE_PACKAGE_NAME_MISSING: {path}")
    return (str(package_name),)


def _load_therock_outputs(package_dir: Path) -> tuple[str, ...]:
    manifest_path = package_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        packages = manifest.get("packages") or {}
        return tuple(sorted(str(name) for name in packages))
    metadata = read_pkgbuild_metadata(package_dir / "PKGBUILD")
    return tuple(metadata["outputs"])


def discover_repo_package_roots(packages_root: Path) -> dict[str, RepoPackageRoot]:
    package_dirs = sorted(
        path.parent
        for path in packages_root.glob("*/PKGBUILD")
        if path.is_file()
    )
    provisional: dict[str, RepoPackageRoot] = {}
    output_to_root: dict[str, str] = {}
    for package_dir in package_dirs:
        root_name = package_dir.name
        metadata = read_pkgbuild_metadata(package_dir / "PKGBUILD")
        if root_name == "therock-gfx1151":
            outputs = _load_therock_outputs(package_dir)
            depends = ()
            makedepends = ()
        else:
            outputs = _load_recipe_output(package_dir / "recipe.json")
            depends = tuple(metadata["depends"])
            makedepends = tuple(metadata["makedepends"])
        provisional[root_name] = RepoPackageRoot(
            root_name=root_name,
            package_dir=package_dir,
            outputs=tuple(sorted(outputs)),
            depends=depends,
            makedepends=makedepends,
            repo_dependency_roots=frozenset(),
        )
        for output in outputs:
            if output in output_to_root:
                raise RuntimeError(f"DUPLICATE_OUTPUT_PACKAGE: {output}")
            output_to_root[output] = root_name

    discovered: dict[str, RepoPackageRoot] = {}
    for root_name, root in provisional.items():
        repo_dependency_roots = frozenset(
            output_to_root[dependency]
            for dependency in (*root.depends, *root.makedepends)
            if dependency in output_to_root and output_to_root[dependency] != root_name
        )
        discovered[root_name] = RepoPackageRoot(
            root_name=root.root_name,
            package_dir=root.package_dir,
            outputs=root.outputs,
            depends=root.depends,
            makedepends=root.makedepends,
            repo_dependency_roots=repo_dependency_roots,
        )
    return discovered


def topologically_sort_package_roots(
    roots: dict[str, RepoPackageRoot],
) -> list[str]:
    incoming = {
        root_name: set(root.repo_dependency_roots)
        for root_name, root in roots.items()
    }
    ready = deque(sorted(name for name, deps in incoming.items() if not deps))
    ordered: list[str] = []
    while ready:
        root_name = ready.popleft()
        ordered.append(root_name)
        for other_name in sorted(incoming):
            if root_name not in incoming[other_name]:
                continue
            incoming[other_name].remove(root_name)
            if not incoming[other_name]:
                ready.append(other_name)
    if len(ordered) != len(roots):
        unresolved = sorted(name for name, deps in incoming.items() if deps)
        raise RuntimeError(f"PACKAGE_GRAPH_CYCLE: {', '.join(unresolved)}")
    return ordered


def select_root_closure_for_outputs(
    roots: dict[str, RepoPackageRoot],
    requested_outputs: list[str],
) -> set[str]:
    output_to_root = {
        output: root_name
        for root_name, root in roots.items()
        for output in root.outputs
    }
    selected: set[str] = set()
    stack: list[str] = []
    for output in requested_outputs:
        root_name = output_to_root.get(output)
        if root_name is None:
            if output in roots:
                root_name = output
            else:
                raise RuntimeError(f"UNKNOWN_REPO_OUTPUT: {output}")
        stack.append(root_name)
    while stack:
        root_name = stack.pop()
        if root_name in selected:
            continue
        selected.add(root_name)
        stack.extend(sorted(roots[root_name].repo_dependency_roots, reverse=True))
    return selected


def serialize_roots(
    roots: dict[str, RepoPackageRoot],
    *,
    selected_roots: set[str] | None = None,
) -> dict[str, object]:
    active_names = (
        sorted(selected_roots)
        if selected_roots is not None
        else sorted(roots)
    )
    active_roots = {name: roots[name] for name in active_names}
    return {
        "build_order": topologically_sort_package_roots(active_roots),
        "roots": [
            {
                "root_name": root.root_name,
                "package_dir": str(root.package_dir),
                "outputs": list(root.outputs),
                "depends": list(root.depends),
                "makedepends": list(root.makedepends),
                "repo_dependency_roots": sorted(root.repo_dependency_roots),
            }
            for root in (active_roots[name] for name in active_names)
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover repo package roots and emit dependency order"
    )
    parser.add_argument(
        "--packages-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "packages",
        help="packages directory to scan",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="package outputs or root names to narrow to",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = discover_repo_package_roots(args.packages_root.resolve())
    selected_roots = (
        select_root_closure_for_outputs(roots, args.targets)
        if args.targets
        else None
    )
    payload = serialize_roots(roots, selected_roots=selected_roots)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for root_name in payload["build_order"]:
        print(root_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

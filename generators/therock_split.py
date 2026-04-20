#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import textwrap
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from string import Template


STRUCTURED_FAILURES = {
    "unmapped": "UNMAPPED_COMPONENT",
    "ambiguous": "AMBIGUOUS_OWNERSHIP",
    "new_class": "NEW_THEROCK_PACKAGE_CLASS",
    "missing_pkg_meta": "MISSING_PACKAGE_METADATA",
}


@dataclass
class Failure:
    kind: str
    subject: str
    detail: str
    hint: str

    def render(self) -> str:
        return f"{STRUCTURED_FAILURES[self.kind]}: {self.subject}\nDETAIL: {self.detail}\nHINT: {self.hint}"


def load_policy(path: Path) -> dict:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data


def read_template(path: Path) -> str:
    return path.read_text()


def pkgfunc_name(pkgname: str) -> str:
    return pkgname


def derive_pkg_conflicts(name: str, meta: dict, bundle_conflict: str) -> list[str]:
    conflicts = set(meta.get("conflicts", []))
    skipped = set(meta.get("skip_conflicts_for_provides", []))
    provides = {provide for provide in meta.get("provides", []) if provide not in skipped}
    conflicts.update(provides)
    conflicts.add(bundle_conflict)
    if name.endswith("-gfx1151"):
        conflicts.add(name.removesuffix("-gfx1151"))
    return sorted(conflicts)


def render_array(values: list[str]) -> str:
    return " ".join(f"'{v}'" for v in values)


class Classifier:
    def __init__(self, policy: dict) -> None:
        self.policy = policy
        self.repo = policy["repo"]
        self.packages = policy["packages"]
        self.component_dirs = policy.get("aliases", {}).get("component_dirs", {})
        self.binary_prefixes = policy.get("aliases", {}).get("binary_prefixes", {})
        self.library_prefixes = policy.get("aliases", {}).get("library_prefixes", {})
        self.path_owners = policy.get("overrides", {}).get("path_owners", {})
        self.synthetic_files = policy.get("synthetic_files", {})
        self.ignore_globs = policy.get("filters", {}).get("ignore_globs", [])
        self.failures: list[Failure] = []
        self.package_files: dict[str, list[str]] = defaultdict(list)
        self.package_dirs: dict[str, set[str]] = defaultdict(set)
        self._new_class_seen: set[str] = set()

    def classify(self, relpath: str) -> str | None:
        if self.is_ignored(relpath):
            return "__ignored__"
        if relpath in self.path_owners:
            return self.path_owners[relpath]

        # Path prefix overrides for directories represented in the overrides map.
        for prefix, owner in self.path_owners.items():
            normalized = prefix.rstrip("/") + "/"
            if relpath.startswith(normalized):
                return owner

        candidates = set()
        path = Path(relpath)
        parts = path.parts
        if len(parts) < 2:
            return None

        # opt/rocm/... layout
        inner = parts[2:] if parts[:2] == ("opt", "rocm") else parts
        if not inner:
            return None

        top = inner[0]

        if top == "amdgcn":
            candidates.add("rocm-device-libs-gfx1151")
        elif top == "bin" and len(inner) > 1:
            name = inner[1]
            if self._is_bin_noise(inner):
                return "__ignored__"
            candidates.update(self._match_prefix(name, self.binary_prefixes))
        elif top == "lib" and len(inner) > 1:
            if inner[1] == "cmake" and len(inner) > 2:
                candidates.update(self._lookup_component(inner[2], relpath))
            elif inner[1] == "pkgconfig" and len(inner) > 2:
                candidates.update(self._classify_pkgconfig(inner[2]))
            elif inner[1] == "llvm":
                candidates.add("rocm-llvm-gfx1151")
            elif inner[1].startswith("python"):
                basename = path.name
                if "amd_smi" in relpath or "amdsmi" in basename:
                    candidates.add("amdsmi-gfx1151")
                else:
                    self._record_new_class(
                        relpath,
                        "Python site-packages subtree under opt/rocm/lib is not mapped",
                        "Add a path ownership override or define a new Python-facing ROCm package mapping.",
                    )
                    return None
            else:
                candidates.update(self._classify_library(path.name))
        elif top in {"include", "share", "libexec", "clients", "tests"} and len(inner) > 1:
            if top == "include" and len(inner) == 2 and "." in inner[1]:
                candidates.update(self._classify_include_file(inner[1]))
            elif top == "share" and inner[1] == "pkgconfig" and len(inner) > 2:
                candidates.update(self._classify_pkgconfig(inner[2]))
            else:
                candidates.update(self._lookup_component(inner[1], relpath))

        candidates.discard(None)
        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            self.failures.append(
                Failure(
                    "ambiguous",
                    relpath,
                    f"matched multiple package candidates: {', '.join(sorted(candidates))}",
                    "Add an exact path owner override or tighten the component/prefix mapping.",
                )
            )
            return None

        self.failures.append(
            Failure(
                "unmapped",
                relpath,
                "no ownership rule matched this path",
                "Add a path override, binary prefix rule, library prefix rule, or component alias.",
            )
        )
        return None

    def is_ignored(self, relpath: str) -> bool:
        return any(fnmatch.fnmatch(relpath, pattern) for pattern in self.ignore_globs)

    def _lookup_component(self, component: str, relpath: str) -> set[str]:
        owner = self.component_dirs.get(component)
        if owner:
            return {owner}
        self._record_new_class(
            component,
            f"component directory from {relpath} has no package alias",
            "Add this component to aliases.component_dirs or an exact path override if it belongs to an existing package.",
        )
        return set()

    def _record_new_class(self, subject: str, detail: str, hint: str) -> None:
        if subject in self._new_class_seen:
            return
        self._new_class_seen.add(subject)
        self.failures.append(Failure("new_class", subject, detail, hint))

    @staticmethod
    def _match_prefix(name: str, mapping: dict[str, str]) -> set[str]:
        exact = {pkg for prefix, pkg in mapping.items() if name == prefix}
        if exact:
            return exact
        matched = [(prefix, pkg) for prefix, pkg in mapping.items() if name.startswith(prefix)]
        if not matched:
            return set()
        longest = max(len(prefix) for prefix, _pkg in matched)
        return {pkg for prefix, pkg in matched if len(prefix) == longest}

    @staticmethod
    def _is_bin_noise(inner_parts: tuple[str, ...]) -> bool:
        name = inner_parts[1]
        noisy_suffixes = (".hip", ".yaml", ".txt", ".data", ".py", ".cmake")
        noisy_fragments = ("test", "bench", "perf", "validate")
        if name.endswith(noisy_suffixes):
            return True
        if any(fragment in name.lower() for fragment in noisy_fragments):
            return True
        if len(inner_parts) > 2:
            if inner_parts[1].startswith("gfx"):
                return True
            if inner_parts[2].endswith(noisy_suffixes):
                return True
        return False

    def _classify_library(self, filename: str) -> set[str]:
        stem = filename
        if stem.startswith("lib"):
            stem = stem[3:]
        stem = stem.split(".so")[0].split(".a")[0]
        return self._match_prefix(stem, self.library_prefixes)

    def _classify_pkgconfig(self, filename: str) -> set[str]:
        stem = filename.removesuffix(".pc")
        candidates = self._match_prefix(stem, self.library_prefixes)
        if candidates:
            return candidates
        return self._lookup_component(stem, f"pkgconfig/{filename}")

    def _classify_include_file(self, filename: str) -> set[str]:
        stem = filename
        for suffix in (".hpp", ".h", ".f03", ".f", ".mod"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        candidates = self._match_prefix(stem, self.library_prefixes)
        if candidates:
            return candidates
        return self._lookup_component(stem, f"include/{filename}")


def walk_scan_roots(root: Path, scan_roots: list[str]) -> list[str]:
    relpaths: list[str] = []
    for scan_root in scan_roots:
        start = root / scan_root
        if not start.exists():
            continue
        for current, dirs, files in os.walk(start, topdown=True, followlinks=False):
            dirs.sort()
            files.sort()
            for file_name in files:
                full = Path(current) / file_name
                relpaths.append(full.relative_to(root).as_posix())
            for dir_name in dirs:
                full = Path(current) / dir_name
                if full.is_symlink():
                    relpaths.append(full.relative_to(root).as_posix())
    relpaths.sort()
    return relpaths


def ensure_package_metadata(packages: dict, owners: set[str], failures: list[Failure]) -> None:
    for owner in sorted(owners):
        if owner not in packages:
            failures.append(
                Failure(
                    "missing_pkg_meta",
                    owner,
                    "a file was assigned to a package that has no metadata definition",
                    "Add a [packages.<name>] entry to the policy file.",
                )
            )


def render_pkgbuild(
    policy: dict,
    package_files: dict[str, list[str]],
    output_dir: Path,
    template_path: Path,
    render_meta: dict[str, str],
) -> None:
    template = read_template(template_path)
    pkg_defs = policy["packages"]
    pkg_names = sorted(pkg for pkg, meta in pkg_defs.items() if meta.get("fileless") or package_files.get(pkg))
    pkgname_block = "\n".join(f"  '{name}'" for name in pkg_names)
    license_block = render_array(policy["repo"]["license"])
    package_functions: list[str] = []
    bundle_conflict = policy["repo"]["bundle_conflict"]

    for pkg in pkg_names:
        meta = pkg_defs[pkg]
        provides = meta.get("provides", [])
        depends = meta.get("depends", [])
        conflicts = derive_pkg_conflicts(pkg, meta, bundle_conflict)
        body = [
            f"package_{pkgfunc_name(pkg)}() {{",
            f"    pkgdesc='{meta['desc']}'",
            f"    provides=({render_array(provides)})" if provides else "    provides=()",
            f"    conflicts=({render_array(conflicts)})" if conflicts else "    conflicts=()",
            f"    depends=({render_array(depends)})" if depends else "    depends=()",
        ]
        if meta.get("fileless"):
            body.append("    return 0")
        else:
            body.extend(
                [
                    "    _require_therock_root",
                    f"    _copy_from_filelist '{pkg}'",
                ]
            )
            for command in meta.get("post_copy_commands", []):
                body.append(f"    {command}")
            synthetic = policy.get("synthetic_files", {}).get(pkg, [])
            for entry in synthetic:
                text = entry["text"]
                body.append(f"    install -Dm644 /dev/stdin \"${{pkgdir}}/{entry['path']}\" <<'EOF'")
                body.append(text.rstrip("\n"))
                body.append("EOF")
        body.append("}")
        package_functions.append("\n".join(body))

    rendered = (
        template.replace("{{pkgbase}}", policy["repo"]["pkgbase"])
        .replace("{{pkgname_block}}", pkgname_block)
        .replace("{{pkgver}}", render_meta["pkgver"])
        .replace("{{pkgrel}}", str(policy["repo"].get("pkgrel", 1)))
        .replace("{{license_block}}", license_block)
        .replace("{{url}}", policy["repo"]["url"])
        .replace("{{recipe_repo_url}}", render_meta["recipe_repo_url"])
        .replace("{{recipe_subdir}}", render_meta["recipe_subdir"])
        .replace("{{recipe_author}}", render_meta["recipe_author"])
        .replace("{{recipe_commit}}", render_meta["recipe_commit"])
        .replace("{{recipe_date}}", render_meta["recipe_date"])
        .replace("{{package_functions}}", "\n\n".join(package_functions))
    )
    (output_dir / "PKGBUILD").write_text(rendered)


def write_filelists(package_files: dict[str, list[str]], output_dir: Path) -> None:
    filelist_dir = output_dir / "filelists"
    filelist_dir.mkdir(parents=True, exist_ok=True)
    expected = {f"{pkg}.txt" for pkg in package_files}
    for path in filelist_dir.glob("*.txt"):
        if path.name not in expected:
            path.unlink()
    for pkg, files in sorted(package_files.items()):
        (filelist_dir / f"{pkg}.txt").write_text("\n".join(sorted(files)) + "\n")


def write_manifest(
    policy: dict,
    package_files: dict[str, list[str]],
    output_dir: Path,
    render_meta: dict[str, str],
) -> None:
    manifest = {
        "pkgbase": policy["repo"]["pkgbase"],
        "pkgver": render_meta["pkgver"],
        "upstream_pkgver": policy["repo"]["pkgver"],
        "recipe": {
            "repo_url": render_meta["recipe_repo_url"],
            "subdir": render_meta["recipe_subdir"],
            "author": render_meta["recipe_author"],
            "commit": render_meta["recipe_commit"],
            "date": render_meta["recipe_date"],
        },
        "packages": {
            pkg: {
                "files": len(files),
                "provides": policy["packages"][pkg].get("provides", []),
                "depends": policy["packages"][pkg].get("depends", []),
                "fileless": bool(policy["packages"][pkg].get("fileless")),
                "rendered": True,
            }
            for pkg, files in sorted(package_files.items())
        },
    }
    for pkg, meta in sorted(policy["packages"].items()):
        if pkg not in manifest["packages"]:
            manifest["packages"][pkg] = {
                "files": 0,
                "provides": meta.get("provides", []),
                "depends": meta.get("depends", []),
                "fileless": bool(meta.get("fileless")),
                "rendered": bool(meta.get("fileless")),
            }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate split-package scaffolding from a TheRock install tree")
    parser.add_argument("--root", default="/", help="filesystem root containing opt/rocm")
    parser.add_argument("--policy", default="policies/therock-packages.toml", help="policy TOML file")
    parser.add_argument("--output", default="generated/therock/therock-gfx1151", help="output directory")
    parser.add_argument("--template", default="templates/PKGBUILD.in", help="PKGBUILD template")
    parser.add_argument("--pkgver-override", default="", help="override pkgver rendered into the generated PKGBUILD")
    parser.add_argument("--recipe-repo-url", default="", help="recipe repository URL for attribution")
    parser.add_argument("--recipe-subdir", default="", help="recipe subdirectory within the recipe repository")
    parser.add_argument("--recipe-author", default="", help="recipe author attribution string")
    parser.add_argument("--recipe-commit", default="", help="recipe commit used for this render")
    parser.add_argument("--recipe-date", default="", help="recipe commit date in YYYYMMDD form")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    policy_path = (repo_root / args.policy).resolve()
    template_path = (repo_root / args.template).resolve()
    output_dir = (repo_root / args.output).resolve()
    root = Path(args.root).resolve()

    policy = load_policy(policy_path)
    render_meta = {
        "pkgver": args.pkgver_override or policy["repo"]["pkgver"],
        "recipe_repo_url": args.recipe_repo_url or "UNKNOWN",
        "recipe_subdir": args.recipe_subdir or ".",
        "recipe_author": args.recipe_author or "UNKNOWN",
        "recipe_commit": args.recipe_commit or "UNKNOWN",
        "recipe_date": args.recipe_date or "UNKNOWN",
    }
    classifier = Classifier(policy)
    relpaths = walk_scan_roots(root, policy["repo"]["scan_roots"])

    for relpath in relpaths:
        owner = classifier.classify(relpath)
        if owner and owner != "__ignored__":
            classifier.package_files[owner].append(relpath)

    ensure_package_metadata(policy["packages"], set(classifier.package_files), classifier.failures)

    if classifier.failures:
        for failure in classifier.failures:
            print(failure.render(), file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    write_filelists(classifier.package_files, output_dir)
    write_manifest(policy, classifier.package_files, output_dir, render_meta)
    render_pkgbuild(policy, classifier.package_files, output_dir, template_path, render_meta)
    print(f"Generated {policy['repo']['pkgbase']} scaffolding in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

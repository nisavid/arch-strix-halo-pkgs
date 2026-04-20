#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib


PUBLIC_STATUSES = {
    "current",
    "stable_update_available",
    "prerelease_only",
    "baseline_drift",
    "branch_head_ahead",
    "metadata_mismatch",
    "manual_review_required",
    "query_failed",
}

STATUS_PRECEDENCE = [
    "metadata_mismatch",
    "query_failed",
    "stable_update_available",
    "branch_head_ahead",
    "baseline_drift",
    "prerelease_only",
    "manual_review_required",
    "current",
]
TOOL_VERSION = 1
CACHE_PATH = Path(".agents/session/dependency-freshness-cache.json")
ACTIONABLE_STATUSES = {
    "stable_update_available",
    "branch_head_ahead",
    "baseline_drift",
    "metadata_mismatch",
}


class QueryFailed(RuntimeError):
    pass


class FakeClients:
    def __init__(
        self,
        *,
        pypi: dict | None = None,
        github_releases: dict | None = None,
        github_tags: dict | None = None,
        git_refs: dict | None = None,
        aur: dict | None = None,
        arch: dict | None = None,
        python_ftp: list[str] | None = None,
        submodules: dict | None = None,
        fail: dict | None = None,
        allow_missing: bool = False,
    ) -> None:
        self.pypi = pypi or {}
        self.github_releases_payload = github_releases or {}
        self.github_tags_payload = github_tags or {}
        self.git_refs = git_refs or {}
        self.aur = aur or {}
        self.arch = arch or {}
        self.python_ftp = python_ftp or []
        self.submodules = submodules or {}
        self.fail = fail or {}
        self.allow_missing = allow_missing

    def _maybe_fail(self, key: str) -> None:
        if key in self.fail:
            raise QueryFailed(str(self.fail[key]))

    def _value(self, mapping: dict, key: str, fail_key: str, default):
        self._maybe_fail(fail_key)
        if key in mapping:
            return mapping[key]
        if self.allow_missing:
            return default
        raise QueryFailed(f"missing fake response for {fail_key}")

    def pypi_project(self, package: str) -> dict:
        return self._value(self.pypi, package, f"pypi:{package}", {})

    def github_releases(self, repo: str) -> list[dict]:
        return self._value(
            self.github_releases_payload,
            repo,
            f"github_release:{repo}",
            [],
        )

    def github_tags(self, repo: str) -> list[str]:
        return self._value(self.github_tags_payload, repo, f"github_tags:{repo}", [])

    def git_ref(self, repo: str, ref: str) -> str:
        return self._value(
            self.git_refs,
            f"{repo}:{ref}",
            f"git_ref:{repo}:{ref}",
            "",
        )

    def aur_package(self, package: str) -> dict:
        return self._value(self.aur, package, f"aur:{package}", {})

    def arch_package(self, package: str) -> dict:
        return self._value(self.arch, package, f"arch_package:{package}", {})

    def python_ftp_versions(self) -> list[str]:
        self._maybe_fail("python_ftp")
        return self.python_ftp

    def submodule_ref(self, path: str, remote_ref: str) -> str:
        return self._value(
            self.submodules,
            f"{path}:{remote_ref}",
            f"submodule:{path}:{remote_ref}",
            "",
        )


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def discover_package_dirs(repo_root: Path) -> set[str]:
    packages_root = repo_root / "packages"
    if not packages_root.exists():
        return set()
    return {
        path.parent.name
        for path in packages_root.glob("*/PKGBUILD")
        if path.is_file()
    }


def policy_families(repo_root: Path) -> dict:
    policy = default_policy_path(repo_root)
    if not policy.exists():
        return {}
    payload = load_toml(policy)
    return payload.get("families", {})


def default_policy_path(repo_root: Path) -> Path:
    return repo_root / "policies/package-freshness.toml"


def metadata_mismatch(message: str) -> dict:
    return {
        "family": "policy-coverage",
        "packages": [],
        "priority": "high",
        "workflow": "manual_review",
        "status": "metadata_mismatch",
        "message": message,
        "checks": [],
    }


def validate_coverage(repo_root: Path, families: dict) -> list[dict]:
    package_dirs = discover_package_dirs(repo_root)
    package_to_families: dict[str, list[str]] = defaultdict(list)
    for family_name, family in families.items():
        for package in family.get("packages", []):
            package_to_families[package].append(family_name)

    findings: list[dict] = []
    missing = sorted(package_dirs - set(package_to_families))
    duplicated = sorted(
        package
        for package, owners in package_to_families.items()
        if len(owners) > 1
    )

    if missing:
        findings.append(
            metadata_mismatch(
                "Freshness policy does not cover package directories: "
                + ", ".join(missing)
            )
        )
    if duplicated:
        findings.append(
            metadata_mismatch(
                "Freshness policy assigns packages to multiple families: "
                + ", ".join(duplicated)
            )
        )
    return findings


def version_key(value: str) -> tuple:
    normalized = re.sub(r"^[vV]", "", value)
    match = re.match(r"^(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?", normalized)
    if not match:
        number = [int(part) for part in re.findall(r"\d+", normalized)]
        return tuple(number or [0])
    base = [int(part) for part in match.group(1).split(".")]
    pre_kind = match.group(2)
    pre_num = int(match.group(3) or 0)
    pre_rank = {"a": -3, "b": -2, "rc": -1}.get(pre_kind, 0)
    return (*base, pre_rank, pre_num)


def strip_tag_prefix(value: str, prefix: str = "") -> str:
    if prefix and value.startswith(prefix):
        return value[len(prefix) :]
    return value


def is_prerelease(value: str) -> bool:
    return bool(re.search(r"(a|b|rc)\d+", value, re.IGNORECASE))


def is_newer(latest: str, recorded: str, comparison: str) -> bool:
    if not latest:
        return False
    if comparison == "sha":
        return not latest.startswith(recorded) and not recorded.startswith(latest)
    if comparison in {"pep440", "prefixed_integer"}:
        return version_key(latest) > version_key(recorded)
    return latest != recorded


def check_status(role: str, recorded: str, latest: str, comparison: str) -> str:
    if not is_newer(latest, recorded, comparison):
        return "current"
    if role == "baseline":
        return "baseline_drift"
    if comparison == "sha":
        return "branch_head_ahead"
    return "stable_update_available"


def query_check(check: dict, clients: FakeClients) -> dict:
    kind = check["kind"]
    recorded = str(check.get("recorded", ""))
    comparison = check.get("comparison", "exact")
    role = check.get("role", "primary")
    check_id = check.get("id", kind)

    base = {
        "id": check_id,
        "kind": kind,
        "role": role,
        "recorded": recorded,
        "latest": recorded,
    }
    if kind == "manual":
        return base | {"status": "manual_review_required"}
    if not recorded:
        return base | {
            "status": "metadata_mismatch",
            "message": "Check is missing a recorded value.",
        }

    try:
        if kind == "pypi":
            latest = str(clients.pypi_project(check["package"]).get("version", ""))
        elif kind == "github_release":
            latest = latest_github_release(check, clients)
            if latest is None:
                prerelease = latest_github_prerelease(check, clients)
                return base | {
                    "latest": prerelease or "",
                    "status": "prerelease_only" if prerelease else "current",
                }
        elif kind == "github_tags":
            latest = latest_github_tag(check, clients)
            if latest and is_prerelease(latest) and not check.get(
                "include_prereleases"
            ):
                return base | {"latest": latest, "status": "prerelease_only"}
        elif kind == "git_ref":
            latest = clients.git_ref(check["repo"], check["ref"])
        elif kind == "aur":
            latest = str(clients.aur_package(check["package"]).get("version", ""))
        elif kind == "arch_package":
            latest = str(clients.arch_package(check["package"]).get("version", ""))
        elif kind == "python_ftp":
            versions = clients.python_ftp_versions()
            latest = sorted(versions, key=version_key)[-1] if versions else ""
        elif kind == "submodule":
            latest = clients.submodule_ref(check["path"], check["ref"])
        else:
            return base | {
                "status": "metadata_mismatch",
                "message": f"Unsupported check kind: {kind}",
            }
    except QueryFailed as exc:
        return base | {"latest": "", "status": "query_failed", "message": str(exc)}

    return base | {
        "latest": latest,
        "status": check_status(role, recorded, latest, comparison),
    }


def latest_github_release(check: dict, clients: FakeClients) -> str | None:
    prefix = check.get("tag_prefix", "")
    releases = clients.github_releases(check["repo"])
    for release in releases:
        if release.get("draft"):
            continue
        if release.get("prerelease") and not check.get("include_prereleases"):
            continue
        return strip_tag_prefix(str(release.get("tag", "")), prefix)
    return None


def latest_github_prerelease(check: dict, clients: FakeClients) -> str | None:
    prefix = check.get("tag_prefix", "")
    releases = clients.github_releases(check["repo"])
    for release in releases:
        if release.get("draft"):
            continue
        if release.get("prerelease"):
            return strip_tag_prefix(str(release.get("tag", "")), prefix)
    return None


def latest_github_tag(check: dict, clients: FakeClients) -> str:
    prefix = check.get("tag_prefix", "")
    tags = [
        strip_tag_prefix(tag, prefix)
        for tag in clients.github_tags(check["repo"])
        if not prefix or tag.startswith(prefix)
    ]
    if check.get("include_prereleases"):
        return tags[0] if tags else ""
    stable = [tag for tag in tags if not is_prerelease(tag)]
    return stable[0] if stable else (tags[0] if tags else "")


def evaluate_checks(checks: list[dict], clients: FakeClients) -> tuple[str, list[dict], str]:
    if not checks:
        return "metadata_mismatch", [], "Freshness family declares no checks."
    reports = [query_check(check, clients) for check in checks]
    statuses = [report["status"] for report in reports]
    for status in STATUS_PRECEDENCE:
        if status in statuses:
            return status, reports, status.replace("_", " ")
    return "current", reports, "current"


def family_report(name: str, family: dict, clients: FakeClients) -> dict:
    status, check_reports, message = evaluate_checks(
        list(family.get("checks", [])), clients
    )
    return {
        "family": name,
        "packages": list(family.get("packages", [])),
        "priority": family.get("priority", "medium"),
        "workflow": family.get("workflow", "manual_review"),
        "status": status,
        "message": message,
        "checks": check_reports,
    }


def summarize(families: list[dict]) -> dict:
    return dict(Counter(family["status"] for family in families))


def policy_digest(repo_root: Path, only: list[str] | None = None) -> str:
    hasher = hashlib.sha256()
    policy = default_policy_path(repo_root)
    hasher.update(f"tool-version:{TOOL_VERSION}\n".encode())
    if policy.exists():
        hasher.update(policy.read_bytes())
    for package in sorted(discover_package_dirs(repo_root)):
        hasher.update(f"package:{package}\n".encode())
    for selector in sorted(only or []):
        hasher.update(f"only:{selector}\n".encode())
    return hasher.hexdigest()


def cache_file(repo_root: Path) -> Path:
    return repo_root / CACHE_PATH


def read_cache(repo_root: Path, digest: str, max_age_hours: float) -> dict | None:
    path = cache_file(repo_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cache = payload.get("cache", {})
    if cache.get("policy_digest") != digest:
        return None
    checked_at = float(cache.get("checked_at", 0))
    if time.time() - checked_at > max_age_hours * 3600:
        return None
    payload["cache"] = cache | {"used": True}
    return payload


def write_cache(repo_root: Path, report: dict) -> None:
    path = cache_file(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


def filtered_families(families: dict, only: list[str] | None) -> dict:
    if not only:
        return families
    selectors = set(only)
    result = {}
    for name, family in families.items():
        packages = set(family.get("packages", []))
        if name in selectors or packages & selectors:
            result[name] = family
    return result


def run_check(
    repo_root: str | Path,
    *,
    refresh: bool = False,
    clients: FakeClients | None = None,
    only: list[str] | None = None,
    max_age_hours: float = 24,
    validate_only: bool = False,
) -> dict:
    root = Path(repo_root)
    digest = policy_digest(root, only)
    if not refresh and not validate_only:
        cached = read_cache(root, digest, max_age_hours)
        if cached is not None:
            return cached

    clients = clients or FakeClients(allow_missing=True)
    families = filtered_families(policy_families(root), only)
    reports = validate_coverage(root, families)
    if not reports:
        reports.extend(
            family_report(name, family, clients)
            for name, family in sorted(families.items())
        )
    report = {
        "summary": summarize(reports),
        "families": reports,
        "cache": {
            "used": False,
            "checked_at": time.time(),
            "policy_digest": digest,
            "tool_version": TOOL_VERSION,
        },
    }
    if not validate_only:
        write_cache(root, report)
    return report


def has_status(report: dict, statuses: set[str]) -> bool:
    return any(family.get("status") in statuses for family in report["families"])


def format_table(report: dict) -> str:
    rows = [
        ("priority", "status", "family", "packages", "recorded", "latest", "workflow")
    ]
    for family in report["families"]:
        checks = family.get("checks", [])
        recorded = ",".join(str(check.get("recorded", "")) for check in checks)
        latest = ",".join(str(check.get("latest", "")) for check in checks)
        rows.append(
            (
                family.get("priority", ""),
                family.get("status", ""),
                family.get("family", ""),
                ",".join(family.get("packages", [])),
                recorded,
                latest,
                family.get("workflow", ""),
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row in rows:
        lines.append(
            "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check repo package upstream and baseline freshness"
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--policy", default="policies/package-freshness.toml")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-age-hours", type=float, default=24)
    parser.add_argument("--fail-on", choices=["actionable"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, clients: FakeClients | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    if args.policy != "policies/package-freshness.toml":
        # The option is reserved for callers; run_check uses repo-relative policy.
        policy = repo_root / args.policy
        if not policy.exists():
            print(f"POLICY_NOT_FOUND: {policy}", file=sys.stderr)
            return 2

    report = run_check(
        repo_root,
        refresh=args.refresh,
        clients=clients,
        only=args.only,
        max_age_hours=args.max_age_hours,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_table(report))

    if has_status(report, {"query_failed"}):
        return 3
    if args.fail_on == "actionable" and has_status(report, ACTIONABLE_STATUSES):
        return 10
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

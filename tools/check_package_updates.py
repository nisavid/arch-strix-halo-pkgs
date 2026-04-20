#!/usr/bin/env python3

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re
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
    policy = repo_root / "policies/package-freshness.toml"
    if not policy.exists():
        return {}
    payload = load_toml(policy)
    return payload.get("families", {})


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


def run_check(
    repo_root: str | Path,
    *,
    refresh: bool = False,
    clients: FakeClients | None = None,
    only: list[str] | None = None,
) -> dict:
    del refresh, only
    root = Path(repo_root)
    clients = clients or FakeClients(allow_missing=True)
    families = policy_families(root)
    reports = validate_coverage(root, families)
    if not reports:
        reports.extend(
            family_report(name, family, clients)
            for name, family in sorted(families.items())
        )
    return {
        "summary": summarize(reports),
        "families": reports,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(0)

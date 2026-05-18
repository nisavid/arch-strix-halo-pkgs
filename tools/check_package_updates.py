#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
from urllib.parse import quote
from urllib.request import Request, urlopen


PUBLIC_STATUSES = {
    "current",
    "stable_update_available",
    "prerelease_only",
    "baseline_drift",
    "branch_head_ahead",
    "candidate_head_ahead",
    "scout_head_ahead",
    "metadata_mismatch",
    "manual_review_required",
    "query_failed",
}

STATUS_PRECEDENCE = [
    "metadata_mismatch",
    "query_failed",
    "stable_update_available",
    "candidate_head_ahead",
    "branch_head_ahead",
    "baseline_drift",
    "scout_head_ahead",
    "prerelease_only",
    "manual_review_required",
    "current",
]
TOOL_VERSION = 4
CACHE_PATH = Path(".agents/session/dependency-freshness-cache.json")
CANDIDATE_LEDGER_PATH = Path("docs/maintainers/update-candidates.toml")
RECIPE_POLICY_PATH = Path("policies/recipe-packages.toml")
ACTIONABLE_STATUSES = {
    "stable_update_available",
    "candidate_head_ahead",
    "branch_head_ahead",
    "baseline_drift",
    "metadata_mismatch",
}
VALID_CANDIDATE_DISPOSITIONS = {"adopted", "tracked", "rejected", "blocked"}
EFFECTIVE_ACTIONABLE_STATUSES = {"action_required", "blocked_update_candidate"}
ALLOWED_ROLES = {"primary", "candidate", "scout", "baseline"}
SHA_REF_KINDS = {"git_ref", "submodule"}
ALLOWED_SOURCE_VALUE_POLICIES = {
    "matches_reviewed",
    "pinned_may_lag_reviewed",
    "pinned_commit_may_lag_reviewed",
    "owned_by_primary_release",
    "inherited",
}
SOURCE_VALUE_POLICIES_WITHOUT_RECORDED_MATCH = {
    "pinned_may_lag_reviewed",
    "pinned_commit_may_lag_reviewed",
    "owned_by_primary_release",
    "inherited",
}
CHECK_SOURCE_KINDS = {
    "pypi": {"pypi_sdist"},
    "github_release": {"github_archive", "git_tag"},
    "github_tags": {"github_archive", "git_tag"},
    "git_ref": {"git_commit", "git_branch", "git_ref"},
    "python_ftp": {"python_source_archive"},
    "submodule": {"submodule"},
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


class StaticTransport:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def get_text(self, url: str) -> str:
        if url not in self.responses:
            raise QueryFailed(f"missing static response for {url}")
        return self.responses[url]


class UrlTransport:
    def __init__(self, *, timeout: float = 10, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for _attempt in range(self.retries + 1):
            try:
                request = Request(
                    url,
                    headers={
                        "User-Agent": "arch-strix-halo-pkgs-freshness-checker/1"
                    },
                )
                with urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = exc
        raise QueryFailed(str(last_error))


class RealClients:
    def __init__(
        self,
        *,
        transport: StaticTransport | UrlTransport | None = None,
        repo_root: str | Path = ".",
    ) -> None:
        self.transport = transport or UrlTransport()
        self.repo_root = Path(repo_root)

    def _json(self, url: str):
        try:
            return json.loads(self.transport.get_text(url))
        except json.JSONDecodeError as exc:
            raise QueryFailed(f"invalid JSON from {url}: {exc}") from exc

    def pypi_project(self, package: str) -> dict:
        payload = self._json(f"https://pypi.org/pypi/{quote(package)}/json")
        return {"version": payload.get("info", {}).get("version", "")}

    def github_releases(self, repo: str) -> list[dict]:
        payload = self._json(f"https://api.github.com/repos/{repo}/releases")
        releases = []
        for item in payload:
            if item.get("draft"):
                continue
            releases.append(
                {
                    "tag": item.get("tag_name", ""),
                    "prerelease": bool(item.get("prerelease")),
                    "published_at": item.get("published_at", ""),
                }
            )
        return releases

    def github_tags(self, repo: str) -> list[str]:
        payload = self._json(f"https://api.github.com/repos/{repo}/tags?per_page=100")
        return [item.get("name", "") for item in payload]

    def git_ref(self, repo: str, ref: str) -> str:
        result = subprocess.run(
            ["git", "ls-remote", repo, ref],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise QueryFailed(result.stderr.strip() or "git ls-remote failed")
        first = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
        return first.split()[0] if first else ""

    def aur_package(self, package: str) -> dict:
        url = f"https://aur.archlinux.org/rpc/v5/info?arg[]={quote(package)}"
        payload = self._json(url)
        for item in payload.get("results", []):
            if item.get("Name") == package:
                return {"version": item.get("Version", "")}
        raise QueryFailed(f"AUR package not found: {package}")

    def arch_package(self, package: str) -> dict:
        url = f"https://archlinux.org/packages/search/json/?name={quote(package)}"
        payload = self._json(url)
        for item in payload.get("results", []):
            if item.get("pkgname") == package:
                return {
                    "version": f"{item.get('pkgver', '')}-{item.get('pkgrel', '')}"
                }
        raise QueryFailed(f"Arch package not found: {package}")

    def python_ftp_versions(self) -> list[str]:
        html = self.transport.get_text("https://www.python.org/ftp/python/")
        return re.findall(r'href="([0-9]+\.[0-9]+\.[0-9]+)/"', html)

    def submodule_ref(self, path: str, remote_ref: str) -> str:
        url = self.submodule_url(path)
        result = subprocess.run(
            ["git", "ls-remote", url, remote_ref],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise QueryFailed(result.stderr.strip() or "git ls-remote failed")
        first = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
        return first.split()[0] if first else ""

    def submodule_url(self, path: str) -> str:
        gitmodules = self.repo_root / ".gitmodules"
        if not gitmodules.exists():
            raise QueryFailed(".gitmodules not found")
        current_path = None
        current_url = None
        for line in gitmodules.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("[submodule "):
                current_path = None
                current_url = None
                continue
            if "=" not in stripped:
                continue
            key, value = [part.strip() for part in stripped.split("=", 1)]
            if key == "path":
                current_path = value
            elif key == "url":
                current_url = value
            if current_path == path and current_url:
                return current_url
        raise QueryFailed(f"submodule path not found in .gitmodules: {path}")


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


def recipe_policy_path(repo_root: Path) -> Path:
    return repo_root / RECIPE_POLICY_PATH


def candidate_ledger_path(repo_root: Path) -> Path:
    return repo_root / CANDIDATE_LEDGER_PATH


def load_candidate_ledger(repo_root: str | Path) -> dict[str, dict]:
    path = candidate_ledger_path(Path(repo_root))
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"CANDIDATE_LEDGER_UNREADABLE: {path}: {exc}") from exc
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"CANDIDATE_LEDGER_INVALID: {path}: {exc}") from exc
    raw_schema_version = payload.get("schema_version", 0)
    try:
        schema_version = int(raw_schema_version)
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version != 1:
        raise RuntimeError(
            f"CANDIDATE_LEDGER_SCHEMA_UNSUPPORTED: {path}: {raw_schema_version!r}"
        )
    candidates = payload.get("candidates", {})
    if not isinstance(candidates, dict):
        raise RuntimeError(f"CANDIDATE_LEDGER_CANDIDATES_INVALID: {path}")
    normalized: dict[str, dict] = {}
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            raise RuntimeError(f"CANDIDATE_LEDGER_ENTRY_INVALID: {candidate_id}")
        disposition = str(candidate.get("disposition", ""))
        if disposition not in VALID_CANDIDATE_DISPOSITIONS:
            raise RuntimeError(f"CANDIDATE_LEDGER_DISPOSITION_INVALID: {candidate_id}")
        normalized[candidate_id] = {**candidate, "id": candidate_id}
    return normalized


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


def selector_mismatch(unmatched: set[str]) -> dict:
    selectors = ", ".join(sorted(unmatched))
    return metadata_mismatch(
        f"Freshness --only selectors do not match a package family or package: {selectors}"
    ) | {"family": "policy-selector"}


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


def normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def normalize_origin(value: str) -> str:
    origin = str(value).strip()
    if origin.startswith("git+"):
        origin = origin[4:]
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", origin):
        origin = f"https://github.com/{origin}"
    if origin.startswith("https://github.com/") and origin.endswith(".git"):
        origin = origin[:-4]
    return origin.rstrip("/").lower()


def split_source_ref(source_ref: str) -> tuple[str | None, str]:
    if "::" not in source_ref:
        return None, source_ref
    source_name, source_spec = source_ref.split("::", 1)
    return source_name, source_spec


def parse_source_ref(package: str, source_ref: str, *, auxiliary: bool = False) -> dict:
    source_name, source_spec = split_source_ref(source_ref)
    if (
        "://" not in source_spec
        and not source_spec.startswith("git+")
        and source_spec.endswith((".patch", ".diff"))
    ):
        return {
            "package": package,
            "source_name": source_name,
            "source_ref": source_ref,
            "source_kind": "patch",
            "origin": "",
            "value": "",
            "auxiliary": auxiliary,
        }
    if source_spec.startswith("git+"):
        url_and_fragment = source_spec[4:]
        url, _, fragment = url_and_fragment.partition("#")
        source_kind = "git_ref"
        value = ""
        if fragment:
            key, _, value = fragment.partition("=")
            source_kind = {
                "commit": "git_commit",
                "tag": "git_tag",
                "branch": "git_branch",
            }.get(key, "git_ref")
        return {
            "package": package,
            "source_name": source_name,
            "source_ref": source_ref,
            "source_kind": source_kind,
            "origin": normalize_origin(url),
            "value": value,
            "auxiliary": auxiliary,
        }
    github_archive = re.match(
        r"^https://github\.com/([^/]+/[^/]+)/archive/(?:refs/(?:tags|heads)/)?(.+)\.tar\.gz$",
        source_spec,
    )
    if github_archive:
        return {
            "package": package,
            "source_name": source_name,
            "source_ref": source_ref,
            "source_kind": "github_archive",
            "origin": normalize_origin(github_archive.group(1)),
            "value": github_archive.group(2),
            "auxiliary": auxiliary,
        }
    python_archive = re.match(
        r"^https://www\.python\.org/ftp/python/([^/]+)/Python-[^/]+\.tar\.(?:xz|gz)$",
        source_spec,
    )
    if python_archive:
        return {
            "package": package,
            "source_name": source_name,
            "source_ref": source_ref,
            "source_kind": "python_source_archive",
            "origin": "python_ftp",
            "value": python_archive.group(1),
            "auxiliary": auxiliary,
        }
    return {
        "package": package,
        "source_name": source_name,
        "source_ref": source_ref,
        "source_kind": "source",
        "origin": normalize_origin(source_spec),
        "value": "",
        "auxiliary": auxiliary,
    }


def implicit_source_fact(package: str, policy_pkg: dict) -> dict | None:
    template = policy_pkg.get("template", "")
    if template == "meta-package":
        return None
    if template in {"rust-wheel-pypi", "native-wheel-pypi"}:
        pypi_name = policy_pkg["pypi_name"]
        return {
            "package": package,
            "source_name": None,
            "source_ref": f"pypi:{pypi_name}",
            "source_kind": "pypi_sdist",
            "origin": f"pypi:{normalized_distribution_name(pypi_name)}",
            "value": str(policy_pkg.get("upstream_version", "")),
            "auxiliary": False,
        }
    if policy_pkg.get("source_type") == "tarball" and policy_pkg.get("source_url"):
        return parse_source_ref(package, str(policy_pkg["source_url"]))
    return None


def recipe_source_facts(repo_root: Path) -> dict[str, list[dict]]:
    path = recipe_policy_path(repo_root)
    if not path.exists():
        raise FileNotFoundError(f"Recipe package policy not found: {path}")
    payload = load_toml(path)
    facts: dict[str, list[dict]] = {}
    for package, policy_pkg in payload.get("packages", {}).items():
        package_facts: list[dict] = []
        source_refs = list(policy_pkg.get("source_refs", []))
        if source_refs:
            package_facts.extend(parse_source_ref(package, item) for item in source_refs)
        elif fact := implicit_source_fact(package, policy_pkg):
            package_facts.append(fact)

        source_patches = set(policy_pkg.get("source_patches", []))
        for item in policy_pkg.get("extra_sources", []):
            fact = parse_source_ref(package, item, auxiliary=True)
            if fact["source_kind"] == "patch" or item in source_patches:
                continue
            package_facts.append(fact)
        facts[package] = package_facts
    return facts


def check_origin(check: dict) -> str:
    kind = check.get("kind", "")
    if kind == "pypi":
        return f"pypi:{normalized_distribution_name(str(check.get('package', '')))}"
    if kind in {"github_release", "github_tags"}:
        return normalize_origin(str(check.get("repo", "")))
    if kind == "git_ref":
        return normalize_origin(str(check.get("repo", "")))
    if kind == "python_ftp":
        return "python_ftp"
    if kind == "submodule":
        return f"submodule:{check.get('path', '')}"
    return ""


def source_value_matches_check(fact: dict, check: dict, value_policy: str) -> bool:
    if value_policy in SOURCE_VALUE_POLICIES_WITHOUT_RECORDED_MATCH:
        return True
    if value_policy != "matches_reviewed":
        return False
    actual = str(fact.get("value", ""))
    expected = str(check.get("recorded", ""))
    if not actual or not expected:
        return False
    if check.get("kind") in {"github_release", "github_tags"}:
        actual = strip_tag_prefix(actual, str(check.get("tag_prefix", "")))
    if fact.get("source_kind") == "git_branch" and check.get("kind") == "git_ref":
        ref = str(check.get("ref", ""))
        return actual in {ref, ref.removeprefix("refs/heads/")}
    if check.get("comparison") == "sha":
        return actual.startswith(expected) or expected.startswith(actual)
    return actual == expected


def explicit_contract_matches(
    fact: dict, contract: dict, family_packages: set[str], checks_by_id: dict[str, dict]
) -> bool:
    packages = set(contract.get("packages", family_packages))
    if fact["package"] not in packages:
        return False
    source_names = contract.get("source_names")
    if source_names is None and contract.get("source_name") is not None:
        source_names = [contract["source_name"]]
    if source_names is not None and fact.get("source_name") not in set(source_names):
        return False
    source_kinds = contract.get("source_kinds")
    if source_kinds is None and contract.get("source_kind") is not None:
        source_kinds = [contract["source_kind"]]
    if source_kinds is not None and fact["source_kind"] not in set(source_kinds):
        return False
    if contract.get("origin") and normalize_origin(contract["origin"]) != fact["origin"]:
        return False
    check_id = contract.get("check_id")
    if check_id and check_id not in checks_by_id:
        return False
    if not check_id:
        return False
    if not source_value_matches_check(
        fact, checks_by_id[check_id], contract.get("value_policy", "matches_reviewed")
    ):
        return False
    return True


def inferred_contract_matches(fact: dict, checks: list[dict]) -> bool:
    if fact.get("auxiliary"):
        return False
    for check in checks:
        allowed_source_kinds = CHECK_SOURCE_KINDS.get(check.get("kind", ""), set())
        if fact["source_kind"] not in allowed_source_kinds:
            continue
        if fact["origin"] and fact["origin"] == check_origin(check):
            return source_value_matches_check(fact, check, "matches_reviewed")
    return False


def validate_source_contracts(repo_root: Path, families: dict) -> list[dict]:
    try:
        facts_by_package = recipe_source_facts(repo_root)
    except FileNotFoundError as exc:
        return [
            metadata_mismatch(str(exc))
            | {
                "family": "recipe-source-contracts",
                "workflow": "source_contract_validation",
            }
        ]
    findings: list[dict] = []
    for family_name, family in families.items():
        family_packages = set(family.get("packages", []))
        checks = list(family.get("checks", []))
        checks_by_id = {str(check.get("id", check.get("kind", ""))): check for check in checks}
        contracts = list(family.get("source_contracts", []))
        contract_packages_requiring_policy = set()
        invalid_contracts = []
        for contract in contracts:
            contract_packages = set(contract.get("packages", family_packages))
            contract_packages_requiring_policy.update(contract_packages)
            unexpected_packages = sorted(contract_packages - family_packages)
            if unexpected_packages:
                invalid_contracts.append(
                    f"{contract.get('id', contract.get('check_id', 'contract'))}: "
                    "packages outside family "
                    + ", ".join(unexpected_packages)
                )
            value_policy = contract.get("value_policy", "matches_reviewed")
            if value_policy not in ALLOWED_SOURCE_VALUE_POLICIES:
                invalid_contracts.append(
                    f"{contract.get('id', contract.get('check_id', 'contract'))}: unsupported value_policy {value_policy}"
                )
            check_id = contract.get("check_id")
            if not check_id:
                invalid_contracts.append(
                    f"{contract.get('id', 'contract')}: missing check_id"
                )
            if check_id and check_id not in checks_by_id:
                invalid_contracts.append(
                    f"{contract.get('id', check_id)}: check_id {check_id} is not declared"
                )

        missing = []
        for package in sorted(family_packages):
            if package not in facts_by_package:
                if package in contract_packages_requiring_policy:
                    missing.append(f"{package}: missing recipe policy entry")
                continue
            for fact in facts_by_package.get(package, []):
                if fact["source_kind"] == "patch":
                    continue
                if any(
                    explicit_contract_matches(fact, contract, family_packages, checks_by_id)
                    for contract in contracts
                ):
                    continue
                if inferred_contract_matches(fact, checks):
                    continue
                missing.append(
                    f"{package}:{fact.get('source_name') or '<source>'} "
                    f"({fact['source_kind']} {fact['origin']})"
                )
        if invalid_contracts or missing:
            details = invalid_contracts + [
                "missing source contract for " + item for item in missing
            ]
            findings.append(
                metadata_mismatch(
                    "Source contract validation failed: " + "; ".join(details)
                )
                | {
                    "family": family_name,
                    "packages": list(family.get("packages", [])),
                    "priority": family.get("priority", "medium"),
                    "workflow": family.get("workflow", "manual_review"),
                }
            )
    return findings


def version_key(value: str) -> tuple:
    normalized = re.sub(r"^[vV]", "", value)
    match = re.match(r"^(\d+(?:\.\d+)*)(?:[-_.]?(a|b|rc)(\d+))?", normalized)
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
        if role == "candidate":
            return "candidate_head_ahead"
        if role == "scout":
            return "scout_head_ahead"
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
    if role not in ALLOWED_ROLES:
        return base | {
            "status": "metadata_mismatch",
            "message": f"Unsupported check role: {role}",
        }
    if role in {"candidate", "scout"} and (
        kind not in SHA_REF_KINDS or comparison != "sha"
    ):
        return base | {
            "status": "metadata_mismatch",
            "message": f"{role} checks must use sha ref kinds.",
        }
    if kind == "manual":
        return base | {"status": "manual_review_required"}
    if not recorded:
        return base | {
            "status": "metadata_mismatch",
            "message": "Check is missing a recorded value.",
        }

    latest_is_prerelease = False
    try:
        if kind == "pypi":
            latest = str(clients.pypi_project(check["package"]).get("version", ""))
        elif kind == "github_release":
            latest = latest_github_release(check, clients)
            if latest is None:
                prerelease = latest_github_prerelease(check, clients)
                return base | {
                    "latest": prerelease or "",
                    "latest_is_prerelease": bool(prerelease),
                    "status": "prerelease_only" if prerelease else "current",
                }
            latest_is_prerelease = is_prerelease(latest)
        elif kind == "github_tags":
            latest = latest_github_tag(check, clients)
            latest_is_prerelease = is_prerelease(latest)
            if latest and is_prerelease(latest) and not check.get(
                "include_prereleases"
            ):
                return base | {
                    "latest": latest,
                    "latest_is_prerelease": latest_is_prerelease,
                    "status": "prerelease_only",
                }
        elif kind == "git_ref":
            latest = clients.git_ref(check["repo"], check["ref"])
        elif kind == "aur":
            latest = str(clients.aur_package(check["package"]).get("version", ""))
        elif kind == "arch_package":
            latest = str(clients.arch_package(check["package"]).get("version", ""))
        elif kind == "python_ftp":
            versions = clients.python_ftp_versions()
            if check.get("series"):
                series_prefix = f"{check['series']}."
                versions = [
                    version
                    for version in versions
                    if version.startswith(series_prefix)
                ]
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

    report = base | {
        "latest": latest,
        "status": check_status(role, recorded, latest, comparison),
    }
    if kind in {"github_release", "github_tags"}:
        report["latest_is_prerelease"] = latest_is_prerelease
    return report


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


def summarize_effective(families: list[dict]) -> dict:
    return dict(Counter(family["effective_status"] for family in families))


def candidate_matches_check(candidate: dict, check: dict, family: dict) -> bool:
    """Match against checks from an evaluated family report, not raw policy."""
    if candidate.get("source_kind") != check.get("kind"):
        return False
    check_id = candidate.get("check_id")
    if check_id is None:
        matching_kind_checks = [
            family_check
            for family_check in family.get("checks", [])
            if family_check.get("kind") == check.get("kind")
        ]
        return len(matching_kind_checks) == 1
    return check_id == check.get("id")


def candidate_matches_recorded_value(candidate: dict, check: dict) -> bool:
    candidate_recorded = str(candidate.get("previous_recorded", "")).strip()
    check_recorded = str(check.get("recorded", "")).strip()
    if not candidate_recorded or not check_recorded:
        return False
    return check_recorded in candidate_previous_recorded_values(candidate)


def candidate_previous_recorded_values(candidate: dict) -> set[str]:
    return {
        value.strip()
        for value in str(candidate.get("previous_recorded", "")).split("/")
        if value.strip()
    }


def candidate_value_matches_package_version(value: str, package_version: str) -> bool:
    return bool(value) and (
        package_version == value or package_version.startswith(f"{value}-")
    )


def candidate_matches_reported_check(candidate: dict, check: dict, family: dict) -> bool:
    return candidate_matches_check(
        candidate, check, family
    ) and candidate_matches_recorded_value(candidate, check)


def candidate_covers_actionable_check(candidate: dict, check: dict, family: dict) -> bool:
    if candidate_matches_reported_check(candidate, check, family):
        return True
    if check.get("status") != "baseline_drift":
        return False
    latest = str(check.get("latest", "")).strip()
    recorded = str(check.get("recorded", "")).strip()
    latest_values = {
        str(value).strip()
        for value in (candidate.get("latest"), candidate.get("baseline_latest"))
        if str(value).strip()
    }
    return any(
        candidate_value_matches_package_version(value, latest)
        for value in latest_values
    ) and any(
        candidate_value_matches_package_version(value, recorded)
        for value in candidate_previous_recorded_values(candidate)
    )


def has_uncovered_actionable_check(candidate: dict, family: dict) -> bool:
    return any(
        check.get("status") in ACTIONABLE_STATUSES
        and not candidate_covers_actionable_check(candidate, check, family)
        for check in family.get("checks", [])
    )


def candidate_matches_family(candidate: dict, family: dict) -> bool:
    if candidate.get("family") != family.get("family"):
        return False
    if family.get("status") == "metadata_mismatch":
        return False
    if (
        family.get("status") == "current"
        and candidate.get("disposition") in VALID_CANDIDATE_DISPOSITIONS
    ):
        candidate_latest = str(candidate.get("latest", "")).strip()
        return any(
            candidate_latest
            and candidate_latest == str(check.get("recorded", "")).strip()
            and candidate_latest == str(check.get("latest", "")).strip()
            and candidate_matches_check(candidate, check, family)
            for check in family.get("checks", [])
        )
    if family.get("status") == "baseline_drift":
        return any(
            check.get("status") == "baseline_drift"
            and candidate_covers_actionable_check(candidate, check, family)
            for check in family.get("checks", [])
        ) and not has_uncovered_actionable_check(candidate, family)
    if candidate.get("discovery_status") != family.get("status"):
        return False
    if (
        family.get("status") == "query_failed"
        and candidate.get("disposition") == "blocked"
        and candidate.get("discovery_status") == "query_failed"
    ):
        failed_checks = [
            check
            for check in family.get("checks", [])
            if check.get("status") == "query_failed"
            and candidate_matches_reported_check(candidate, check, family)
        ]
        if len(failed_checks) != 1:
            return False
        return not any(
            (
                check.get("status") == "query_failed"
                or check.get("status") in ACTIONABLE_STATUSES
            )
            and not candidate_covers_actionable_check(candidate, check, family)
            for check in family.get("checks", [])
        )
    candidate_latest = str(candidate.get("latest", "")).strip()
    latest_values = {
        latest
        for check in family.get("checks", [])
        if check.get("status") == family.get("status")
        if candidate_matches_reported_check(candidate, check, family)
        if (latest := str(check.get("latest", "")).strip())
    }
    if candidate_latest and candidate_latest in latest_values:
        return not has_uncovered_actionable_check(candidate, family)
    return False


def effective_status_for(family: dict, candidate: dict | None) -> str:
    if candidate:
        return f"{candidate['disposition']}_update_candidate"
    if family.get("status") == "query_failed":
        return "query_failed"
    if family.get("status") in ACTIONABLE_STATUSES:
        return "action_required"
    return "current"


def enrich_candidate_dispositions(
    families: list[dict], candidates: dict[str, dict]
) -> list[dict]:
    enriched = []
    for family in families:
        matches = [
            candidate
            for candidate in candidates.values()
            if candidate_matches_family(candidate, family)
        ]
        if len(matches) > 1:
            match_ids = ", ".join(str(candidate["id"]) for candidate in matches)
            raise RuntimeError(
                f"CANDIDATE_LEDGER_DUPLICATE_MATCH: {family['family']}: {match_ids}"
            )
        candidate = matches[0] if matches else None
        report = family | {"effective_status": effective_status_for(family, candidate)}
        if candidate:
            report["candidate"] = candidate
        enriched.append(report)
    return enriched


def policy_digest(repo_root: Path, only: list[str] | None = None) -> str:
    hasher = hashlib.sha256()
    policy = default_policy_path(repo_root)
    hasher.update(f"tool-version:{TOOL_VERSION}\n".encode())
    if policy.exists():
        hasher.update(policy.read_bytes())
    recipe_policy = recipe_policy_path(repo_root)
    hasher.update(f"recipe-policy-present:{int(recipe_policy.exists())}\n".encode())
    if recipe_policy.exists():
        hasher.update(recipe_policy.read_bytes())
    ledger = candidate_ledger_path(repo_root)
    hasher.update(f"candidate-ledger-present:{int(ledger.exists())}\n".encode())
    if ledger.exists():
        try:
            hasher.update(ledger.read_bytes())
        except OSError as exc:
            raise RuntimeError(f"CANDIDATE_LEDGER_UNREADABLE: {ledger}: {exc}") from exc
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


def unmatched_selectors(families: dict, only: list[str] | None) -> set[str]:
    if not only:
        return set()
    known = set(families)
    for family in families.values():
        known.update(family.get("packages", []))
    return set(only) - known


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

    clients = clients or RealClients(repo_root=root)
    all_families = policy_families(root)
    reports = validate_coverage(root, all_families)
    families = filtered_families(all_families, only)
    unmatched = unmatched_selectors(all_families, only)
    if not reports and unmatched:
        reports.append(selector_mismatch(unmatched))
    if not reports:
        contract_findings = validate_source_contracts(root, families)
        reports.extend(contract_findings)
        failed_contract_families = {
            str(finding.get("family"))
            for finding in contract_findings
            if finding.get("status") == "metadata_mismatch"
        }
        reports.extend(
            family_report(name, family, clients)
            for name, family in sorted(families.items())
            if name not in failed_contract_families
        )
    reports = enrich_candidate_dispositions(reports, load_candidate_ledger(root))
    report = {
        "summary": summarize(reports),
        "effective_summary": summarize_effective(reports),
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


def has_effective_status(report: dict, statuses: set[str]) -> bool:
    return any(
        family.get("effective_status") in statuses for family in report["families"]
    )


def has_unblocked_query_failure(report: dict) -> bool:
    return any(
        family.get("status") == "query_failed"
        and family.get("effective_status") != "blocked_update_candidate"
        for family in report["families"]
    )


def format_table(report: dict) -> str:
    rows = [
        (
            "priority",
            "status",
            "effective_status",
            "family",
            "packages",
            "recorded",
            "latest",
            "workflow",
        )
    ]
    for family in report["families"]:
        checks = family.get("checks", [])
        recorded = ",".join(str(check.get("recorded", "")) for check in checks)
        latest = ",".join(str(check.get("latest", "")) for check in checks)
        rows.append(
            (
                family.get("priority", ""),
                family.get("status", ""),
                family.get("effective_status", ""),
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
        clients=clients or RealClients(repo_root=repo_root),
        only=args.only,
        max_age_hours=args.max_age_hours,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_table(report))

    if has_unblocked_query_failure(report):
        return 3
    if args.fail_on == "actionable" and has_effective_status(
        report, EFFECTIVE_ACTIONABLE_STATUSES
    ):
        return 10
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

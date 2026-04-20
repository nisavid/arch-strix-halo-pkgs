#!/usr/bin/env python3

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
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


class FakeClients:
    pass


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


def family_report(name: str, family: dict) -> dict:
    return {
        "family": name,
        "packages": list(family.get("packages", [])),
        "priority": family.get("priority", "medium"),
        "workflow": family.get("workflow", "manual_review"),
        "status": "manual_review_required",
        "message": "No automated checks have run for this family.",
        "checks": [],
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
    del refresh, clients, only
    root = Path(repo_root)
    families = policy_families(root)
    reports = validate_coverage(root, families)
    if not reports:
        reports.extend(
            family_report(name, family) for name, family in sorted(families.items())
        )
    return {
        "summary": summarize(reports),
        "families": reports,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(0)

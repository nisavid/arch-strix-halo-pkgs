#!/usr/bin/env python3
"""Rootless bubblewrap build root for generation-C package builds.

The root is assembled from package files, never from the host filesystem:

* foundation packages (for example the TheRock staging repo and the local
  output repo of the current wave) always win dependency resolution;
* the remaining userland comes from the host's sync databases, preferring the
  exact version the host runs when that package file is still in the host
  cache;
* every package that a forbidden repo (for example the previous ROCm
  generation's repo) ships is refused from the host cache, so a stale
  /opt/rocm cannot leak in through a cached file.

Subcommands:

  resolve   read sync DBs (read only) and write a lock file
  fetch     download lock members that are missing locally, checked by sha256
  populate  extract a lock into a fresh root and record file ownership
  add       extract built package files into an existing root
  remove    delete a package's files from the root (e.g. a replaced stand-in)
  publish   copy built package files into a local repo and run repo-add
  enter     run a command inside the root with bubblewrap (ROOT [flags] -- CMD...)
  verify    check root ownership, forbidden sources and the ROCm version
  probe     build and run the HIP/CMake/makepkg no-leak probes in the root

Nothing here needs root, sudo or pacman -S/-U/-Sy, and nothing writes to the
host's pacman state. See docs/maintainers/c-build-root.md.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

LOCK_SCHEMA = 1
STATE_DIR = ".ashp-root"
MANIFEST = "manifest.json"
FILES_DIR = "files"
DATA_DIR = Path(__file__).resolve().parent / "buildroot"
DEFAULT_MAKEPKG_CONF = DATA_DIR / "makepkg.conf"
PROBE_DIR = DATA_DIR / "probe"
PKG_METADATA = (".PKGINFO", ".BUILDINFO", ".MTREE", ".INSTALL", ".CHANGELOG")
ROOT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/bin:/opt/rocm/bin"

DEP_RE = re.compile(r"^([^<>=]+)(?:(<=|>=|<|>|=)(.+))?$")


class BuildRootError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Version comparison (a port of libalpm's alpm_pkg_vercmp)
# ---------------------------------------------------------------------------


def _rpmvercmp(a: str, b: str) -> int:
    if a == b:
        return 0
    i = j = 0
    pi = pj = 0
    la, lb = len(a), len(b)
    while i < la and j < lb:
        while i < la and not a[i].isalnum():
            i += 1
        while j < lb and not b[j].isalnum():
            j += 1
        if i >= la or j >= lb:
            break
        if (i - pi) != (j - pj):
            return -1 if (i - pi) < (j - pj) else 1
        si, sj = i, j
        isnum = a[i].isdigit()
        test = str.isdigit if isnum else str.isalpha
        while i < la and test(a[i]):
            i += 1
        while j < lb and test(b[j]):
            j += 1
        if j == sj:
            return 1 if isnum else -1
        seg_a, seg_b = a[si:i], b[sj:j]
        if isnum:
            seg_a, seg_b = seg_a.lstrip("0"), seg_b.lstrip("0")
            if len(seg_a) != len(seg_b):
                return 1 if len(seg_a) > len(seg_b) else -1
        if seg_a != seg_b:
            return -1 if seg_a < seg_b else 1
        pi, pj = i, j
    if i >= la and j >= lb:
        return 0
    if (i >= la and not b[j].isalpha()) or (i < la and a[i].isalpha()):
        return -1
    return 1


def _parse_evr(v: str) -> tuple[str, str, str | None]:
    epoch = "0"
    m = re.match(r"^(\d+):", v)
    if m:
        epoch, v = m.group(1), v[m.end():]
    rel = None
    if "-" in v:
        v, rel = v.rsplit("-", 1)
    return epoch, v, rel


def vercmp(a: str, b: str) -> int:
    if a == b:
        return 0
    ea, va, ra = _parse_evr(a)
    eb, vb, rb = _parse_evr(b)
    r = _rpmvercmp(ea, eb)
    if r == 0:
        r = _rpmvercmp(va, vb)
    if r == 0 and ra is not None and rb is not None:
        r = _rpmvercmp(ra, rb)
    return r


# ---------------------------------------------------------------------------
# Sync databases and dependency resolution
# ---------------------------------------------------------------------------


@dataclass
class Pkg:
    repo: str
    name: str
    version: str
    filename: str
    sha256: str
    isize: int
    depends: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def parse_desc(text: str, repo: str) -> Pkg:
    fields: dict[str, list[str]] = {}
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if lines and lines[0].startswith("%"):
            fields[lines[0].strip("%")] = lines[1:]
    return Pkg(
        repo=repo,
        name=fields["NAME"][0],
        version=fields["VERSION"][0],
        filename=fields["FILENAME"][0],
        sha256=fields.get("SHA256SUM", [""])[0],
        isize=int(fields.get("ISIZE", ["0"])[0]),
        depends=fields.get("DEPENDS", []),
        provides=fields.get("PROVIDES", []),
        conflicts=fields.get("CONFLICTS", []),
    )


def read_db(path: Path, repo: str) -> dict[str, Pkg]:
    out: dict[str, Pkg] = {}
    with tarfile.open(path, "r:*") as tf:
        for member in tf:
            if not member.name.endswith("/desc"):
                continue
            handle = tf.extractfile(member)
            if handle is None:
                continue
            pkg = parse_desc(handle.read().decode(), repo)
            out[pkg.name] = pkg
    return out


def split_dep(dep: str) -> tuple[str, str | None, str | None]:
    dep = dep.split(": ", 1)[0].strip()
    m = DEP_RE.match(dep)
    if not m:
        raise ValueError(f"unparseable dependency: {dep!r}")
    return m.group(1), m.group(2), m.group(3)


def version_ok(have: str | None, op: str | None, want: str | None) -> bool:
    if op is None:
        return True
    if have is None or want is None:
        return False
    c = vercmp(have, want)
    if "-" not in want and "-" in have:
        c = vercmp(have.rsplit("-", 1)[0], want)
    return {"=": c == 0, ">=": c >= 0, "<=": c <= 0, ">": c > 0, "<": c < 0}[op]


def satisfies(pkg: Pkg, dep: str) -> bool:
    name, op, want = split_dep(dep)
    if pkg.name == name and version_ok(pkg.version, op, want):
        return True
    for prov in pkg.provides:
        pname, _, pver = split_dep(prov)
        if pname != name:
            continue
        if op is None or version_ok(pver, op, want):
            return True
    return False


def host_installed() -> dict[str, str]:
    """Return the host's installed package versions (read only)."""
    out = subprocess.run(["pacman", "-Q"], capture_output=True, text=True, check=True).stdout
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def problem(kind: str, package: str, detail: str) -> dict[str, str]:
    return {"kind": kind, "package": package, "detail": detail}


@dataclass
class ResolveConfig:
    repos: list[tuple[str, dict[str, Pkg]]]
    foundation: list[str]
    pools: dict[str, Path] = field(default_factory=dict)
    host_cache: Path | None = None
    installed: Mapping[str, str] = field(default_factory=dict)
    forbidden_names: set[str] = field(default_factory=set)
    forbidden_repos: list[str] = field(default_factory=list)
    extra_caches: list[Path] = field(default_factory=list)


def resolve(targets: Sequence[str], cfg: ResolveConfig) -> dict:
    repo_names = [name for name, _ in cfg.repos]
    for bad in cfg.forbidden_repos:
        if bad in repo_names:
            raise BuildRootError(f"forbidden repo {bad!r} was passed as a sync DB")
    foundation_rank = {name: i for i, name in enumerate(cfg.foundation)}
    for name in cfg.foundation:
        if name not in repo_names:
            raise BuildRootError(f"foundation repo {name!r} has no --db")

    providers: dict[str, list[Pkg]] = {}
    for _, db in cfg.repos:
        for p in db.values():
            for prov in p.provides:
                providers.setdefault(split_dep(prov)[0], []).append(p)

    def find(dep: str) -> Pkg | None:
        name, _, _ = split_dep(dep)
        cands: list[Pkg] = []
        for _, db in cfg.repos:
            p = db.get(name)
            if p and satisfies(p, dep):
                cands.append(p)
        for p in providers.get(name, []):
            if p not in cands and satisfies(p, dep):
                cands.append(p)
        if not cands:
            return None
        found = [p for p in cands if p.repo in foundation_rank]
        if found:
            return min(found, key=lambda p: foundation_rank[p.repo])
        for p in cands:
            if p.name in cfg.installed:
                return p
        return cands[0]

    selected: dict[str, Pkg] = {}
    # Every (dependency, needed-by) pair each selected package answers, so that
    # a host version is only substituted when it meets the binding ones.
    required: dict[str, list[tuple[str, str]]] = {}
    trace: list[str] = []
    problems: list[dict[str, str]] = []
    queue: list[tuple[str, str]] = [(t, "<target>") for t in targets]
    while queue:
        dep, why = queue.pop(0)
        hit = next((p for p in selected.values() if satisfies(p, dep)), None)
        if hit is not None:
            required[hit.name].append((dep, why))
            continue
        pkg = find(dep)
        if pkg is None:
            problems.append(problem("unresolved", split_dep(dep)[0], f"{dep} needed by {why}"))
            continue
        selected[pkg.name] = pkg
        required[pkg.name] = [(dep, why)]
        trace.append(f"{pkg.repo}/{pkg.name} {pkg.version} <- {dep} ({why})")
        queue.extend((d, pkg.name) for d in pkg.depends)

    for p in selected.values():
        for c in p.conflicts:
            for q in selected.values():
                if q is not p and satisfies(q, c):
                    problems.append(problem("conflict", p.name, f"conflicts with {q.name} ({c})"))

    def binding(why: str) -> bool:
        # Targets, foundation packages and packages that will come at their DB
        # version state real constraints. A host-installed userland package is
        # locked at its host version, whose own depends the host already meets,
        # so the exact pins in its newer DB entry do not bind.
        if why == "<target>":
            return True
        needer = selected[why]
        return needer.repo in foundation_rank or needer.name not in cfg.installed

    def host_version_fits(p: Pkg, version: str, archive: Path, needs: list[tuple[str, str]]) -> bool:
        # Judge the host package by its own provides, not the DB entry's: a
        # soname pin such as libprotobuf.so=36.1.0-64 names the DB version.
        # Read them only when a binding need goes through a provide; if they
        # cannot be read, such a need is not met.
        binding_needs = [d for d, why in needs if binding(why)]
        provides: list[str] = []
        if any(split_dep(d)[0] != p.name for d in binding_needs):
            provides = archive_provides(archive)
        host = replace(p, version=version, provides=provides)
        return all(satisfies(host, d) for d in binding_needs)

    packages = []
    for p in sorted(selected.values(), key=lambda p: p.name):
        path: Path | None = None
        version, sha, source = p.version, p.sha256, p.repo
        use_host = (
            p.repo not in foundation_rank
            and p.repo not in cfg.pools
            and p.name in cfg.installed
            and p.name not in cfg.forbidden_names
            and cfg.host_cache is not None
        )
        if use_host:
            hv = cfg.installed[p.name]
            hits = sorted(
                c for c in cfg.host_cache.glob(f"{p.name}-{hv}-*.pkg.tar.*")
                if not c.name.endswith(".sig") and _archive_matches(c.name, p.name, hv)
            )
            if hits and host_version_fits(p, hv, hits[0], required[p.name]):
                path, version, source = hits[0], hv, f"host-cache({p.repo})"
                sha = p.sha256 if hv == p.version else ""
        if path is None and p.repo in cfg.pools:
            path = cfg.pools[p.repo] / p.filename
        if path is None:
            for cache in ([cfg.host_cache] if cfg.host_cache is not None else []) + cfg.extra_caches:
                c = cache / p.filename
                if c.exists():
                    path = c
                    break
        if path is not None and not path.exists():
            path = None
        if path is None:
            problems.append(problem("missing-file", p.name, p.filename))
        packages.append({
            "name": p.name,
            "version": version,
            "repo": p.repo,
            "source": source,
            "path": str(path) if path else None,
            "filename": p.filename,
            "sha256_db": sha,
            "isize": p.isize,
        })

    return {
        "schema": LOCK_SCHEMA,
        "created": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "targets": list(targets),
        "repos": repo_names,
        "foundation": list(cfg.foundation),
        "forbidden_repos": list(cfg.forbidden_repos),
        "packages": packages,
        "problems": problems,
        "trace": trace,
    }


def _archive_matches(filename: str, name: str, version: str) -> bool:
    prefix = f"{name}-{version}-"
    if not filename.startswith(prefix):
        return False
    rest = filename[len(prefix):]
    return re.match(r"^[A-Za-z0-9_]+\.pkg\.tar\.[a-z0-9]+$", rest) is not None


def archive_provides(archive: Path) -> list[str]:
    """The provides in a package file's .PKGINFO, or [] when it cannot be read."""
    try:
        out = subprocess.run(["bsdtar", "-xOf", str(archive), ".PKGINFO"], capture_output=True, text=True)
    except OSError:
        return []
    if out.returncode != 0:
        return []
    return [line.split(" = ", 1)[1] for line in out.stdout.splitlines() if line.startswith("provides = ")]


def summarize_lock(lock: dict) -> str:
    by_repo: dict[str, list[int]] = {}
    for e in lock["packages"]:
        by_repo.setdefault(e["repo"], []).append(e["isize"])
    lines = [f"{repo:24s} {len(s):4d} pkgs {sum(s) / 2**30:7.2f} GiB installed" for repo, s in by_repo.items()]
    total = sum(e["isize"] for e in lock["packages"])
    lines.append(f"{'total':24s} {len(lock['packages']):4d} pkgs {total / 2**30:7.2f} GiB installed")
    lines += [f"PROBLEM {p['kind']}: {p['package']}: {p['detail']}" for p in lock["problems"]]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fetching missing files
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pacman_conf_servers(repo: str) -> list[str]:
    """The host's configured mirrors for REPO, in pacman's order (read only)."""
    out = subprocess.run(["pacman-conf", "--repo", repo, "Server"], capture_output=True, text=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    subprocess.run(["curl", "-qgfsSL", "--retry", "3", "--retry-delay", "3", "-o", str(tmp), url], check=True)
    tmp.replace(dest)


def fetch_missing(
    lock: dict,
    dest: Path,
    mirrors: Mapping[str, str],
    downloader: Callable[[str, Path], None] = download,
    servers_for: Callable[[str], list[str]] = pacman_conf_servers,
) -> list[str]:
    """Download lock members with no local file; each must match its sync-DB sha256."""
    dest.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    missing = {p["package"] for p in lock["problems"] if p["kind"] == "missing-file"}
    for entry in lock["packages"]:
        if entry["name"] not in missing:
            continue
        if not entry["sha256_db"]:
            raise BuildRootError(f"{entry['name']}: no sync-DB sha256; refusing an unverified download")
        target = dest / entry["filename"]
        if not (target.exists() and sha256_file(target) == entry["sha256_db"]):
            bases = [mirrors[entry["repo"]]] if entry["repo"] in mirrors else servers_for(entry["repo"])
            if not bases:
                raise BuildRootError(f"{entry['name']}: no mirror for repo {entry['repo']}")
            errors = []
            for base in bases:
                try:
                    downloader(f"{base.rstrip('/')}/{entry['filename']}", target)
                except (subprocess.CalledProcessError, OSError) as exc:
                    errors.append(f"{base}: {exc}")
                    continue
                got = sha256_file(target)
                if got == entry["sha256_db"]:
                    break
                target.unlink()
                errors.append(f"{base}: sha256 {got} != sync DB {entry['sha256_db']}")
            else:
                raise BuildRootError(f"{entry['name']}: download failed: " + "; ".join(errors))
        entry["path"] = str(target)
        fetched.append(entry["name"])
    lock["problems"] = [
        p for p in lock["problems"] if not (p["kind"] == "missing-file" and p["package"] in fetched)
    ]
    return fetched


# ---------------------------------------------------------------------------
# Root state: manifest and file ownership
# ---------------------------------------------------------------------------


def state_dir(root: Path) -> Path:
    return root / STATE_DIR


def load_manifest(root: Path) -> list[dict]:
    path = state_dir(root) / MANIFEST
    if not path.exists():
        raise BuildRootError(f"not a populated build root: {root}")
    return json.loads(path.read_text())


def save_manifest(root: Path, manifest: list[dict]) -> None:
    path = state_dir(root) / MANIFEST
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(manifest, key=lambda e: e["name"]), indent=1) + "\n")
    tmp.replace(path)


def read_file_list(root: Path, name: str) -> list[str]:
    path = state_dir(root) / FILES_DIR / f"{name}.list"
    return path.read_text().splitlines() if path.exists() else []


def ownership_index(root: Path, manifest: Iterable[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for entry in manifest:
        for rel in read_file_list(root, entry["name"]):
            index[rel] = entry
    return index


def archive_members(archive: Path) -> list[str]:
    out = subprocess.run(["bsdtar", "-tf", str(archive)], capture_output=True, text=True, check=True).stdout
    members = []
    for line in out.splitlines():
        line = line.removeprefix("./")
        if not line or line in PKG_METADATA or line.endswith("/"):
            continue
        members.append(line)
    return members


def read_pkginfo(archive: Path) -> dict[str, str]:
    out = subprocess.run(
        ["bsdtar", "-xOf", str(archive), ".PKGINFO"], capture_output=True, text=True, check=True
    ).stdout
    info: dict[str, str] = {}
    for line in out.splitlines():
        if " = " in line and not line.startswith("#"):
            k, v = line.split(" = ", 1)
            info.setdefault(k, v)
    if "pkgname" not in info or "pkgver" not in info:
        raise BuildRootError(f"PACKAGE_METADATA_MISSING: {archive}")
    return info


def extract(archive: Path, root: Path) -> None:
    cmd = ["bsdtar", "-xpf", str(archive), "--no-xattrs", "--no-acls", "--no-fflags", "-C", str(root)]
    for meta in PKG_METADATA:
        cmd += ["--exclude", meta]
    subprocess.run(cmd, check=True)


def record_package(root: Path, name: str, version: str, source: str, archive: Path, sha: str,
                   members: list[str]) -> dict:
    files = state_dir(root) / FILES_DIR
    files.mkdir(parents=True, exist_ok=True)
    (files / f"{name}.list").write_text("\n".join(members) + ("\n" if members else ""))
    return {"name": name, "version": version, "source": source, "file": archive.name, "sha256": sha}


def populate(lock: dict, root: Path, *, uid: int | None = None, gid: int | None = None,
             post_install: bool = True) -> list[dict]:
    if lock.get("problems"):
        raise BuildRootError("lock has problems: " + "; ".join(
            f"{p['kind']} {p['package']}" for p in lock["problems"]))
    if state_dir(root).exists():
        raise BuildRootError(f"root already populated: {root}")
    root.mkdir(parents=True, exist_ok=True)
    state_dir(root).mkdir()
    manifest: list[dict] = []
    for entry in lock["packages"]:
        archive = Path(entry["path"])
        sha = sha256_file(archive)
        if entry["sha256_db"] and sha != entry["sha256_db"]:
            raise BuildRootError(f"sha256 mismatch for {archive}: {sha} != {entry['sha256_db']}")
        extract(archive, root)
        manifest.append(record_package(root, entry["name"], entry["version"], entry["source"],
                                       archive, sha, archive_members(archive)))
    save_manifest(root, manifest)
    add_build_user(root, os.getuid() if uid is None else uid, os.getgid() if gid is None else gid)
    (state_dir(root) / "lock.json").write_text(json.dumps(lock, indent=1) + "\n")
    if post_install:
        run_in_root(root, ["sh", "-c", "ldconfig && (update-ca-trust extract || true)"], rw=True)
    return manifest


MOUNT_POINTS = ("build", "pkgdest", "srcdest", "ccache")


def add_build_user(root: Path, uid: int, gid: int) -> None:
    for rel, line in (("etc/passwd", f"builder:x:{uid}:{gid}::/build:/bin/bash"),
                      ("etc/group", f"builder:x:{gid}:")):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.chmod(path.stat().st_mode | 0o200)
        text = path.read_text() if path.exists() else ""
        if not any(l.startswith("builder:") for l in text.splitlines()):
            path.write_text(text + ("" if text.endswith("\n") or not text else "\n") + line + "\n")
    # enter mounts the root read-only, so bwrap cannot create its bind targets.
    for mount in MOUNT_POINTS:
        (root / mount).mkdir(exist_ok=True)


def add_packages(root: Path, archives: Sequence[Path], source: str, *, allow_overwrite: bool = False,
                 post_install: bool = True) -> list[dict]:
    manifest = load_manifest(root)
    by_name = {e["name"]: e for e in manifest}
    added = []
    for archive in archives:
        info = read_pkginfo(archive)
        name, version = info["pkgname"], info["pkgver"]
        members = archive_members(archive)
        index = ownership_index(root, (e for e in manifest if e["name"] != name))
        clashes = sorted(m for m in members if m in index)
        if clashes and not allow_overwrite:
            owners = sorted({index[m]["name"] for m in clashes})
            raise BuildRootError(
                f"{name}: {len(clashes)} file(s) already owned by {', '.join(owners)} (e.g. {clashes[0]})")
        old = by_name.get(name)
        if old is not None:
            for rel in read_file_list(root, name):
                target = root / rel
                if (target.is_file() or target.is_symlink()) and rel not in members:
                    target.unlink()
            manifest = [e for e in manifest if e["name"] != name]
        extract(archive, root)
        entry = record_package(root, name, version, source, archive, sha256_file(archive), members)
        manifest.append(entry)
        by_name[name] = entry
        added.append(entry)
    save_manifest(root, manifest)
    if post_install and added:
        run_in_root(root, ["ldconfig"], rw=True)
    return added


def remove_packages(root: Path, names: Sequence[str], *, post_install: bool = True) -> list[dict]:
    """Delete packages' files from the root, for example an Arch stand-in replaced by a W2A build."""
    manifest = load_manifest(root)
    by_name = {e["name"]: e for e in manifest}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise BuildRootError(f"not in the root: {', '.join(unknown)}")
    keep = [e for e in manifest if e["name"] not in names]
    still_owned = set(ownership_index(root, keep))
    removed = []
    for name in names:
        for rel in read_file_list(root, name):
            target = root / rel
            if rel not in still_owned and (target.is_file() or target.is_symlink()):
                target.unlink()
        (state_dir(root) / FILES_DIR / f"{name}.list").unlink(missing_ok=True)
        removed.append(by_name[name])
    save_manifest(root, keep)
    if post_install and removed:
        run_in_root(root, ["ldconfig"], rw=True)
    return removed


# ---------------------------------------------------------------------------
# Publishing into the local output repo
# ---------------------------------------------------------------------------


def host_repo_targets() -> tuple[set[str], set[Path]]:
    """Names of the host's pacman repos and the local dirs their file:// servers use."""
    out = subprocess.run(["pacman-conf", "--repo-list"], capture_output=True, text=True)
    names = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    dirs: set[Path] = set()
    for name in names:
        servers = subprocess.run(["pacman-conf", "--repo", name, "Server"], capture_output=True, text=True)
        for url in servers.stdout.split():
            if url.startswith("file://"):
                dirs.add(Path(url[len("file://"):]))
    return names, dirs


def _init_empty_db(db: Path) -> None:
    with tarfile.open(db, "w:zst"):
        pass
    link = db.with_name(db.name.removesuffix(".tar.zst"))
    if not link.exists():
        link.symlink_to(db.name)


def publish(repo_dir: Path, db_name: str, archives: Sequence[Path], *,
            host_repos: tuple[set[str], set[Path]] | None = None, runner=subprocess.run) -> Path:
    names, dirs = host_repo_targets() if host_repos is None else host_repos
    if db_name in names:
        raise BuildRootError(f"refusing to publish into {db_name!r}: the host's pacman uses that repo")
    repo_dir = repo_dir.absolute()
    for d in dirs:
        if repo_dir == d.absolute() or d.absolute() in repo_dir.parents:
            raise BuildRootError(f"refusing to publish into {repo_dir}: a host pacman repo is served from {d}")
    repo_dir.mkdir(parents=True, exist_ok=True)
    db = repo_dir / f"{db_name}.db.tar.zst"
    if not archives:
        if not db.exists():
            _init_empty_db(db)
        return db
    copied = []
    for archive in archives:
        dst = repo_dir / archive.name
        if archive.resolve() != dst.resolve():
            shutil.copy2(archive, dst)
        copied.append(dst)
    runner(["repo-add", "-q", "-R", str(db), *map(str, copied)], check=True)
    return db


# ---------------------------------------------------------------------------
# Entering the root
# ---------------------------------------------------------------------------


@dataclass
class EnterOptions:
    work: Path | None = None
    gpu: bool = False
    net: bool = False
    rw: bool = False
    pkgdest: Path | None = None
    srcdest: Path | None = None
    ccache: Path | None = None
    makepkg_conf: Path | None = None
    env: dict[str, str] = field(default_factory=dict)


def bwrap_args(root: Path, opts: EnterOptions) -> list[str]:
    args = ["bwrap"]
    args += ["--bind" if opts.rw else "--ro-bind", str(root), "/"]
    args += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/run",
             "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
    env = {
        "HOME": "/build", "USER": "builder", "LOGNAME": "builder", "PATH": ROOT_PATH,
        "LANG": "C.UTF-8", "TERM": os.environ.get("TERM", "dumb"),
    }
    if opts.work is not None:
        args += ["--bind", str(opts.work.resolve()), "/build"]
    else:
        args += ["--tmpfs", "/build"]
    if opts.pkgdest is not None:
        args += ["--bind", str(opts.pkgdest.resolve()), "/pkgdest"]
        env["PKGDEST"] = "/pkgdest"
    if opts.srcdest is not None:
        args += ["--bind", str(opts.srcdest.resolve()), "/srcdest"]
        env["SRCDEST"] = "/srcdest"
    if opts.ccache is not None:
        args += ["--bind", str(opts.ccache.resolve()), "/ccache"]
        env["CCACHE_DIR"] = "/ccache"
    if opts.makepkg_conf is not None:
        args += ["--ro-bind", str(opts.makepkg_conf.resolve()), "/etc/makepkg.conf"]
    if opts.gpu:
        args += ["--dev-bind", "/dev/kfd", "/dev/kfd", "--dev-bind", "/dev/dri", "/dev/dri",
                 "--ro-bind", "/sys", "/sys"]
    if opts.net:
        args += ["--share-net", "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf"]
    env.update(opts.env)
    for k, v in sorted(env.items()):
        args += ["--setenv", k, v]
    args += ["--chdir", "/build", "--"]
    return args


# `enter` runs builds only inside the host's memory-capped build slice. The
# host's makepkg and ninja shims cannot see into the bubblewrap root, so the
# whole bwrap invocation is launched in the slice, and every compiler inside it
# inherits the cap and the raised OOM score.
BUILD_SLICE = "builds.slice"
BUILD_OOM_SCORE_ADJ = "500"


def current_cgroup(proc_cgroup: Path = Path("/proc/self/cgroup")) -> str:
    """The cgroup v2 path of this process, such as /user.slice/.../builds.slice/run-x.scope."""
    for line in proc_cgroup.read_text().splitlines():
        hierarchy, _, path = line.partition("::")
        if hierarchy == "0":
            return path
    raise BuildRootError(f"no cgroup v2 entry in {proc_cgroup}")


def require_build_slice(runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    """Refuse to build unless the build slice is loaded with a finite MemoryMax.

    `systemd-run --slice=` would otherwise create an uncapped transient slice.
    """
    shown = runner(["systemctl", "--user", "show", BUILD_SLICE, "-p", "LoadState", "-p", "MemoryMax"],
                   capture_output=True, text=True, check=False)
    props = dict(line.partition("=")[::2] for line in shown.stdout.splitlines() if "=" in line)
    if shown.returncode != 0 or props.get("LoadState") != "loaded":
        raise BuildRootError(f"{BUILD_SLICE} is not loaded; the host memory guards are not live")
    if props.get("MemoryMax", "infinity") in ("", "infinity"):
        raise BuildRootError(f"{BUILD_SLICE} has no MemoryMax; refusing to build without a memory cap")


def slice_wrapped(args: Sequence[str], *, cgroup: str | None = None,
                  runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[str]:
    """Wrap a bwrap command so it runs in the build slice with a raised OOM score.

    Inside the slice already, only choom is added; otherwise a new scope is
    started in the slice.
    """
    require_build_slice(runner)
    choom = ["choom", "-n", BUILD_OOM_SCORE_ADJ, "--", *args]
    if BUILD_SLICE in (current_cgroup() if cgroup is None else cgroup).split("/"):
        return choom
    return ["systemd-run", "--user", "--scope", f"--slice={BUILD_SLICE}", *choom]


def run_in_root(root: Path, cmd: Sequence[str], opts: EnterOptions | None = None, *, rw: bool = False,
                check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    opts = opts or EnterOptions()
    if rw:
        opts.rw = True
    return subprocess.run(bwrap_args(root, opts) + list(cmd), check=check,
                          capture_output=capture, text=True if capture else None)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def resolve_in_root(root: Path, path: str, max_links: int = 40) -> str:
    """Resolve PATH as the root sees it, following symlinks without leaving the root."""
    parts = [p for p in path.split("/") if p]
    done: list[str] = []
    links = 0
    while parts:
        part = parts.pop(0)
        if part == ".":
            continue
        if part == "..":
            if done:
                done.pop()
            continue
        candidate = root.joinpath(*done, part)
        if candidate.is_symlink():
            links += 1
            if links > max_links:
                raise BuildRootError(f"too many symlinks resolving {path}")
            target = os.readlink(candidate)
            if target.startswith("/"):
                done = []
            parts = [p for p in target.split("/") if p] + parts
            continue
        done.append(part)
    return "/" + "/".join(done)


def owner_of(root: Path, index: Mapping[str, dict], path: str) -> dict | None:
    rel = path.lstrip("/")
    if rel in index:
        return index[rel]
    real = resolve_in_root(root, path).lstrip("/")
    return index.get(real)


def verify_root(root: Path, *, foundation: Sequence[str], forbidden_repos: Sequence[str],
                expect_rocm: str | None) -> dict:
    manifest = load_manifest(root)
    index = ownership_index(root, manifest)
    violations: list[str] = []
    for e in manifest:
        for bad in forbidden_repos:
            if bad in e["source"]:
                violations.append(f"forbidden source {e['source']}: {e['name']}")
    rocm_files = 0
    rocm = root / "opt/rocm"
    if rocm.exists() or rocm.is_symlink():
        for dirpath, dirnames, filenames in os.walk(root / "opt"):
            for fname in filenames + [d for d in dirnames if (Path(dirpath) / d).is_symlink()]:
                rel = str((Path(dirpath) / fname).relative_to(root))
                rocm_files += 1
                owner = index.get(rel)
                if owner is None:
                    violations.append(f"unowned file under /opt: /{rel}")
                elif rel.startswith("opt/rocm") and owner["source"] not in foundation:
                    violations.append(f"/{rel} owned by {owner['name']} from {owner['source']}")
    version = None
    info = root / "opt/rocm/.info/version"
    if info.exists():
        version = info.read_text().strip()
    if expect_rocm is not None and version != expect_rocm:
        violations.append(f"/opt/rocm/.info/version is {version!r}, expected {expect_rocm!r}")
    sources: dict[str, int] = {}
    for e in manifest:
        sources[e["source"]] = sources.get(e["source"], 0) + 1
    return {"packages": len(manifest), "sources": sources, "opt_files_checked": rocm_files,
            "rocm_version": version, "violations": violations}


LDD_RE = re.compile(r"^\s*(\S+)\s+=>\s+(\S+)\s+\(0x")
LDD_DIRECT_RE = re.compile(r"^\s*(/\S+)\s+\(0x")


def ldd_paths(text: str) -> list[str]:
    paths = []
    for line in text.splitlines():
        if "=> not found" in line:
            paths.append(line.split("=>", 1)[0].strip() + " not found")
            continue
        m = LDD_RE.match(line)
        if m:
            paths.append(m.group(2))
            continue
        m = LDD_DIRECT_RE.match(line)
        if m:
            paths.append(m.group(1))
    return paths


def check_linkage(root: Path, paths: Iterable[str], *, foundation: Sequence[str],
                  forbidden_repos: Sequence[str]) -> tuple[list[dict], list[str]]:
    manifest = load_manifest(root)
    index = ownership_index(root, manifest)
    rows, violations = [], []
    for path in sorted(set(paths)):
        if path.endswith(" not found"):
            violations.append(f"unresolved library: {path}")
            continue
        if path.startswith("/build/"):
            continue  # the probe's own outputs
        owner = owner_of(root, index, path)
        row = {"path": path, "owner": owner["name"] if owner else None,
               "version": owner["version"] if owner else None, "source": owner["source"] if owner else None}
        rows.append(row)
        if owner is None:
            violations.append(f"{path}: not owned by any root package")
        elif any(bad in owner["source"] for bad in forbidden_repos):
            violations.append(f"{path}: owned by forbidden source {owner['source']}")
        elif path.startswith("/opt/") and owner["source"] not in foundation:
            violations.append(f"{path}: /opt path owned by non-foundation source {owner['source']}")
    return rows, violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _kv(specs: Iterable[str], flag: str) -> list[tuple[str, str]]:
    out = []
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"{flag} expects NAME=VALUE, got {spec!r}")
        out.append(tuple(spec.split("=", 1)))
    return out


def cmd_resolve(a: argparse.Namespace) -> int:
    repos = [(name, read_db(Path(path), name)) for name, path in _kv(a.db, "--db")]
    forbidden_names: set[str] = set()
    forbidden_repos = []
    for name, path in _kv(a.forbid_db, "--forbid-db"):
        forbidden_repos.append(name)
        forbidden_names |= set(read_db(Path(path), name))
    cfg = ResolveConfig(
        repos=repos,
        foundation=a.foundation_repo,
        pools={k: Path(v) for k, v in _kv(a.pool, "--pool")},
        host_cache=None if a.no_host_cache else Path(a.host_cache),
        installed={} if a.no_host_cache else host_installed(),
        forbidden_names=forbidden_names,
        forbidden_repos=forbidden_repos,
        extra_caches=[Path(c) for c in a.cache],
    )
    targets = list(a.targets)
    for tf in a.targets_file:
        targets += [t for t in (l.split("#", 1)[0].strip() for l in Path(tf).read_text().splitlines()) if t]
    lock = resolve(targets, cfg)
    Path(a.out).write_text(json.dumps(lock, indent=1) + "\n")
    print(summarize_lock(lock))
    return 1 if lock["problems"] else 0


def cmd_fetch(a: argparse.Namespace) -> int:
    lock = json.loads(Path(a.lock).read_text())
    fetched = fetch_missing(lock, Path(a.dest), dict(_kv(a.mirror, "--mirror")))
    Path(a.lock).write_text(json.dumps(lock, indent=1) + "\n")
    print(f"fetched {len(fetched)}: {' '.join(fetched)}")
    print(summarize_lock(lock))
    return 1 if lock["problems"] else 0


def cmd_populate(a: argparse.Namespace) -> int:
    lock = json.loads(Path(a.lock).read_text())
    manifest = populate(lock, Path(a.root).absolute(), post_install=not a.no_post_install)
    print(f"populated {a.root}: {len(manifest)} packages")
    return 0


def cmd_add(a: argparse.Namespace) -> int:
    added = add_packages(Path(a.root).absolute(), [Path(p) for p in a.packages], a.source,
                         allow_overwrite=a.allow_overwrite)
    for e in added:
        print(f"added {e['name']} {e['version']} ({e['source']})")
    return 0


def cmd_remove(a: argparse.Namespace) -> int:
    for e in remove_packages(Path(a.root).absolute(), a.names):
        print(f"removed {e['name']} {e['version']} ({e['source']})")
    return 0


def cmd_publish(a: argparse.Namespace) -> int:
    db = publish(Path(a.repo_dir), a.db_name, [Path(p) for p in a.packages])
    print(f"published {len(a.packages)} package(s) to {db}")
    return 0


def _enter_opts(a: argparse.Namespace) -> EnterOptions:
    conf = None if a.no_makepkg_conf else Path(a.makepkg_conf or DEFAULT_MAKEPKG_CONF)
    return EnterOptions(
        work=Path(a.work) if a.work else None, gpu=a.gpu, net=a.net, rw=a.rw,
        pkgdest=Path(a.pkgdest) if a.pkgdest else None,
        srcdest=Path(a.srcdest) if a.srcdest else None,
        ccache=Path(a.ccache) if a.ccache else None,
        makepkg_conf=conf, env=dict(_kv(a.setenv, "--setenv")),
    )


def cmd_enter(a: argparse.Namespace) -> int:
    cmd = a.command or ["bash"]
    args = slice_wrapped(bwrap_args(Path(a.root).absolute(), _enter_opts(a)) + cmd)
    os.execvp(args[0], args)
    return 127


def cmd_verify(a: argparse.Namespace) -> int:
    report = verify_root(Path(a.root).absolute(), foundation=a.foundation_repo,
                         forbidden_repos=a.forbid_repo, expect_rocm=a.expect_rocm)
    print(json.dumps(report, indent=1))
    return 1 if report["violations"] else 0


PROBE_BINARIES = ("hello/hello", "cmakelib/prefix/lib/libsaxpy.so", "cmakelib/prefix/bin/saxpy_probe")


def cmd_probe(a: argparse.Namespace) -> int:
    root = Path(a.root).absolute()
    work = Path(a.work).absolute()
    if work.exists() and any(work.iterdir()):
        raise BuildRootError(f"probe work dir must be empty: {work}")
    shutil.copytree(PROBE_DIR, work, dirs_exist_ok=True)
    opts = _enter_opts(a)
    opts.work, opts.gpu = work, True
    proc = run_in_root(root, ["bash", "/build/run.sh"], opts, check=False, capture=True)
    log = proc.stdout + proc.stderr
    (work / "probe.log").write_text(log)
    violations = [] if proc.returncode == 0 else [f"probe script exited {proc.returncode}"]
    for marker in ("vadd OK", "saxpy OK"):
        if marker not in log:
            violations.append(f"missing marker: {marker}")
    rows, link_viol = check_linkage(root, ldd_paths(log), foundation=a.foundation_repo,
                                    forbidden_repos=a.forbid_repo)
    violations += link_viol
    for rel in PROBE_BINARIES + tuple(str(p.relative_to(work)) for p in work.glob("pkg/*.pkg.tar.*")):
        data = (work / rel).read_bytes() if (work / rel).exists() else b""
        for leak in {str(root), str(work), str(Path.home())}:
            if leak.encode() in data:
                violations.append(f"{rel}: embeds host path {leak}")
    for line in log.splitlines():
        if "RUNPATH" in line or "RPATH" in line:
            m = re.search(r"\[(.*)\]", line)
            for entry in (m.group(1).split(":") if m else []):
                if not (entry.startswith("/opt/rocm") or entry.startswith("$ORIGIN")):
                    violations.append(f"unexpected runpath entry {entry!r}")
    report = {"returncode": proc.returncode, "libraries": rows, "violations": violations,
              "rocm_version": verify_root(root, foundation=a.foundation_repo,
                                          forbidden_repos=a.forbid_repo, expect_rocm=None)["rocm_version"]}
    (work / "probe-report.json").write_text(json.dumps(report, indent=1) + "\n")
    print("\n".join(line for line in log.splitlines() if line.startswith(("compiled", "vadd", "saxpy", "##"))))
    print(f"libraries checked: {len(rows)}; violations: {len(violations)}")
    for v in violations:
        print("VIOLATION:", v)
    return 1 if violations else 0


def _add_enter_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--work", help="host dir bound read-write at /build")
    p.add_argument("--gpu", action="store_true", help="bind /dev/kfd, /dev/dri and /sys")
    p.add_argument("--net", action="store_true", help="share the network and resolv.conf")
    p.add_argument("--rw", action="store_true", help="mount the root read-write")
    p.add_argument("--pkgdest", help="host dir bound at /pkgdest (PKGDEST)")
    p.add_argument("--srcdest", help="host dir bound at /srcdest (SRCDEST)")
    p.add_argument("--ccache", help="host dir bound at /ccache (CCACHE_DIR)")
    p.add_argument("--makepkg-conf", help=f"makepkg.conf bound at /etc/makepkg.conf (default {DEFAULT_MAKEPKG_CONF.name})")
    p.add_argument("--no-makepkg-conf", action="store_true", help="keep the root's packaged makepkg.conf")
    p.add_argument("--setenv", action="append", default=[], metavar="NAME=VALUE")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("resolve", help="resolve targets into a lock file")
    p.add_argument("--db", action="append", required=True, metavar="REPO=PATH", help="sync DB, in priority order")
    p.add_argument("--pool", action="append", default=[], metavar="REPO=DIR", help="dir holding a repo's package files")
    p.add_argument("--foundation-repo", action="append", required=True,
                   help="repo whose packages always win (repeat; earlier wins)")
    p.add_argument("--forbid-db", action="append", default=[], metavar="REPO=PATH",
                   help="repo whose package names must never come from the host cache")
    p.add_argument("--host-cache", default="/var/cache/pacman/pkg")
    p.add_argument("--no-host-cache", action="store_true", help="ignore host versions and the host cache")
    p.add_argument("--cache", action="append", default=[],
                   help="extra dir of verified package files, such as a `fetch --dest` dir")
    p.add_argument("--targets-file", action="append", default=[])
    p.add_argument("--out", required=True)
    p.add_argument("targets", nargs="*")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("fetch", help="download missing lock members, verified by sync-DB sha256")
    p.add_argument("lock")
    p.add_argument("--dest", required=True)
    p.add_argument("--mirror", action="append", default=[], metavar="REPO=URL")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("populate", help="extract a lock into a fresh root")
    p.add_argument("lock")
    p.add_argument("root")
    p.add_argument("--no-post-install", action="store_true")
    p.set_defaults(func=cmd_populate)

    p = sub.add_parser("add", help="extract built packages into the root")
    p.add_argument("root")
    p.add_argument("packages", nargs="+")
    p.add_argument("--source", default="ashp-w2a")
    p.add_argument("--allow-overwrite", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("remove", help="delete packages' files from the root")
    p.add_argument("root")
    p.add_argument("names", nargs="+")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("publish", help="copy packages into a local repo and run repo-add "
                       "(no packages: create an empty repo DB)")
    p.add_argument("repo_dir")
    p.add_argument("db_name")
    p.add_argument("packages", nargs="*")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("enter", help="run a command in the root")
    p.add_argument("root")
    _add_enter_flags(p)
    p.set_defaults(func=cmd_enter, command=[])

    for name, func in (("verify", cmd_verify), ("probe", cmd_probe)):
        p = sub.add_parser(name)
        p.add_argument("root")
        p.add_argument("--foundation-repo", action="append", required=True)
        p.add_argument("--forbid-repo", action="append", default=[])
        if name == "verify":
            p.add_argument("--expect-rocm")
        else:
            _add_enter_flags(p)
            p.set_defaults(work=None)
        p.set_defaults(func=func)
    return ap


def split_command(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split `enter ROOT [flags] -- CMD...` so flags never leak into CMD."""
    argv = list(argv)
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1:]
    return argv, []


def main(argv: Sequence[str] | None = None) -> int:
    own, command = split_command(sys.argv[1:] if argv is None else argv)
    a = build_parser().parse_args(own)
    if a.cmd == "enter":
        a.command = command
    elif command:
        raise SystemExit(f"{a.cmd} takes no command after --")
    if a.cmd == "probe" and not a.work:
        raise SystemExit("probe needs --work")
    try:
        return a.func(a)
    except BuildRootError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

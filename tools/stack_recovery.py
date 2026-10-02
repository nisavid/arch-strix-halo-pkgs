#!/usr/bin/env python3
"""Private deployed-state rollback preparation; never installs or snapshots.

See docs/maintainers/stack-recovery.md for the owner-run restore gates.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
from urllib.parse import unquote

from package_archives import is_package_archive

SCHEMA = 1
NAME = re.compile(r"^[A-Za-z0-9@_+][A-Za-z0-9@._+-]*$")


class RecoveryError(Exception):
    """An actionable refusal with a path-free public diagnostic."""


def command(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode:
        raise RecoveryError("required read-only command failed")
    return result.stdout


def installed(root: Path) -> list[dict]:
    packages = []
    names = set()
    for line in command(["pacman", "--root", str(root), "--dbpath", str(root / "var/lib/pacman"),
                         "--config", "/dev/null", "-Q"]).splitlines():
        fields = line.split()
        if len(fields) != 2 or not NAME.fullmatch(fields[0]) or fields[0] in names:
            raise RecoveryError("invalid or duplicate installed package identity")
        names.add(fields[0])
        packages.append(dict(name=fields[0], version=fields[1]))
    if not packages:
        raise RecoveryError("empty installed inventory")
    return sorted(packages, key=lambda item: item["name"])


def metadata(path: Path) -> dict:
    text = command(["bsdtar", "-xOqf", str(path), ".PKGINFO"])
    values = {}
    for line in text.splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            if key in ("pkgname", "pkgver", "arch"):
                if key in values:
                    raise RecoveryError("duplicate package metadata identity")
                values[key] = value
    if (set(values) != {"pkgname", "pkgver", "arch"}
            or not NAME.fullmatch(values["pkgname"])
            or not values["pkgver"]
            or not NAME.fullmatch(values["arch"])):
        raise RecoveryError("missing or invalid package metadata identity")
    return dict(name=values["pkgname"], version=values["pkgver"], arch=values["arch"])


def no_symlink(path: Path) -> Path:
    if ".." in path.parts:
        raise RecoveryError("parent traversal path refused")
    path = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise RecoveryError("symlink path refused")
    return path


def private_destination(path: Path) -> Path:
    path = no_symlink(path)
    if path.exists():
        raise RecoveryError("output already exists")
    parent = path.parent
    if not parent.is_dir() or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
        raise RecoveryError("output needs an existing private owner-controlled directory")
    for part in (parent, *parent.parents):
        marker = part / ".git"
        if marker.is_file() or (marker.is_dir() and (marker / "HEAD").exists()):
            raise RecoveryError("recovery output inside Git refused")
    return path


def save_private(path: Path, value: dict) -> None:
    path = private_destination(path)
    with open(path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def inventory(args) -> int:
    root = no_symlink(args.root)
    identities = installed(root)
    arches = architectures(root)
    wanted = {(p["name"], p["version"]) for p in identities}
    found = {}
    invalid = 0
    for directory in args.archive_dir or [Path("/var/cache/pacman/pkg"),
                                         Path("/srv/pacman/strix-halo-gfx1151/x86_64")]:
        for path in sorted(directory.glob("*.pkg.tar.*")):
            if path.name.endswith(".sig") or not is_package_archive(path):
                continue
            try:
                info = metadata(path)
                if info["arch"] not in arches:
                    raise RecoveryError("package architecture is outside source configuration")
            except RecoveryError:
                invalid += 1
                continue
            identity = (info["name"], info["version"])
            if identity in wanted and identity not in found:
                found[identity] = dict(info, source=str(path.absolute()))
    missing = [p for p in identities if (p["name"], p["version"]) not in found]
    mounts = json.loads(command(["findmnt", "--json", "--target", str(root),
                                "--output", "TARGET,FSTYPE,FSROOT"]))
    if installed(root) != identities or architectures(root) != arches:
        raise RecoveryError("installed inventory changed during observation")
    report = dict(schema=SCHEMA, kind="inventory", source_root=str(root),
                  observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  installed=identities, architectures=arches, packages=list(found.values()), missing=missing,
                  invalid_archives=invalid, mounts=mounts)
    save_private(args.output, report)
    print(json.dumps(dict(installed=len(identities), matched=len(found), missing=len(missing))))
    return 10 if missing else 0


def architectures(root: Path) -> list[str]:
    config = no_symlink(root / "etc/pacman.conf")
    if root != Path("/") and any(line.split("=", 1)[0].strip() == "Include"
                                 for line in config.read_text().splitlines()):
        raise RecoveryError("alternate source root requires a self-contained pacman configuration")
    values = command(["pacman-conf", "--config", str(config), "Architecture"]).split()
    if not values or any(not NAME.fullmatch(value) for value in values):
        raise RecoveryError("source pacman architecture policy is unavailable or invalid")
    return sorted({"any", *(platform.machine() if v == "auto" else v for v in values)})


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with no_symlink(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def load(path: Path) -> dict:
    return json.loads(no_symlink(path).read_text())


def relative(text: str) -> str:
    path = PurePosixPath(text)
    if not text or path.is_absolute() or any(part in (".", "..") for part in text.split("/")):
        raise RecoveryError("configuration path must be relative and contained")
    if "\n" in text or "\x00" in text or str(path) != text:
        raise RecoveryError("noncanonical configuration path")
    return text


def configuration(root: Path, paths: list[str]) -> list[dict]:
    records = {}

    def visit(rel: str) -> None:
        if rel in records:
            return
        path = root / rel
        no_symlink(path.parent)
        info = path.lstat()
        record = dict(path=rel, mode=stat.S_IMODE(info.st_mode), uid=info.st_uid,
                      gid=info.st_gid, mtime_ns=info.st_mtime_ns,
                      xattrs={key: base64.b64encode(os.getxattr(path, key, follow_symlinks=False)).decode()
                              for key in os.listxattr(path, follow_symlinks=False)})
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise RecoveryError("hardlinked configuration needs an explicit owner capture")
            record.update(type="file", sha256=digest(path))
        elif stat.S_ISLNK(info.st_mode):
            link = os.readlink(path)
            if not (root / rel).parent.joinpath(link).resolve().is_relative_to(root):
                raise RecoveryError("configuration link escapes the source root")
            record.update(type="symlink", link=link)
        elif stat.S_ISDIR(info.st_mode):
            record["type"] = "directory"
        else:
            raise RecoveryError("special configuration file needs an explicit owner capture")
        records[rel] = record
        if record["type"] == "directory":
            for child in sorted(path.iterdir()):
                visit(relative(f"{rel}/{child.name}"))

    for rel in paths:
        visit(relative(rel))
    if not records:
        raise RecoveryError("empty configuration selection")
    return [records[key] for key in sorted(records)]


def linux_acl(value: str) -> set[tuple[str, str, str]]:
    data = base64.b64decode(value, validate=True)
    if len(data) < 4 or struct.unpack_from("<I", data)[0] != 2 or (len(data) - 4) % 8:
        raise RecoveryError("unsupported POSIX ACL encoding")
    tags = {1: "user", 2: "user", 4: "group", 8: "group", 16: "mask", 32: "other"}
    entries = set()
    for tag, permission, identity in struct.iter_unpack("<HHI", data[4:]):
        if tag not in tags or permission & ~7:
            raise RecoveryError("unsupported POSIX ACL entry")
        rights = "".join(letter if permission & bit else "-" for letter, bit in (("r", 4), ("w", 2), ("x", 1)))
        entries.add((tags[tag], str(identity) if tag in (2, 8) else "", rights))
    return entries


def pax_acl(value: str) -> set[tuple[str, str, str]]:
    entries = set()
    for entry in value.split(","):
        fields = entry.split(":")
        if len(fields) == 4:
            entries.add((fields[0], fields[3], fields[2]))
        elif len(fields) == 3:
            entries.add(tuple(fields))
        else:
            raise RecoveryError("unsupported retained POSIX ACL encoding")
    return entries


def check_configuration_archive(path: Path, records: list[dict]) -> None:
    with tarfile.open(path, "r:") as archive:
        members = archive.getmembers()
        observed = {relative(member.name.rstrip("/")): member for member in members}
        if len(observed) != len(members) or set(observed) != {r["path"] for r in records}:
            raise RecoveryError("configuration archive coverage mismatch")
        for record in records:
            member = observed[record["path"]]
            if (member.mode, member.uid, member.gid) != (record["mode"], record["uid"], record["gid"]):
                raise RecoveryError("configuration archive metadata mismatch")
            xattrs = {}
            for key, value in member.pax_headers.items():
                if key.startswith("LIBARCHIVE.xattr."):
                    name = unquote(key.removeprefix("LIBARCHIVE.xattr."))
                    xattrs[name] = base64.b64encode(base64.b64decode(value + "=" * (-len(value) % 4))).decode()
                elif key.startswith("SCHILY.xattr."):
                    name = key.removeprefix("SCHILY.xattr.")
                    xattrs.setdefault(name, base64.b64encode(value.encode("utf-8", "surrogateescape")).decode())
            expected_xattrs = dict(record["xattrs"])
            for name, key in (("system.posix_acl_access", "SCHILY.acl.access"),
                              ("system.posix_acl_default", "SCHILY.acl.default")):
                raw = expected_xattrs.pop(name, None)
                retained_acl = member.pax_headers.get(key)
                if bool(raw) != bool(retained_acl) or (raw and linux_acl(raw) != pax_acl(retained_acl)):
                    raise RecoveryError("configuration archive ACL mismatch")
            if xattrs != expected_xattrs:
                raise RecoveryError("configuration archive extended attribute mismatch")
            if record["type"] == "file":
                if not member.isfile():
                    raise RecoveryError("configuration archive type mismatch")
                handle = archive.extractfile(member)
                if handle is None or hashlib.file_digest(handle, "sha256").hexdigest() != record["sha256"]:
                    raise RecoveryError("configuration archive content mismatch")
            elif record["type"] == "directory":
                if not member.isdir():
                    raise RecoveryError("configuration archive type mismatch")
            elif record["type"] == "symlink":
                if not member.issym() or member.linkname != record["link"]:
                    raise RecoveryError("configuration archive link mismatch")
            else:
                raise RecoveryError("unsupported configuration record")


def capture(args) -> int:
    output = private_destination(args.output)
    report, request = load(args.inventory), load(args.request)
    if report["schema"] != SCHEMA or report["kind"] != "inventory" or report["missing"]:
        raise RecoveryError("incomplete inventory; exact retained archives are required")
    if request["purpose"] != "trial":
        raise RecoveryError("only trial capture is supported; final activation capture remains owner-run")
    root = no_symlink(Path(report["source_root"]))
    identities = installed(root)
    if identities != report["installed"] or architectures(root) != report["architectures"]:
        raise RecoveryError("installed inventory changed since observation")
    packages = sorted(report["packages"], key=lambda item: item["name"])
    if [{"name": p["name"], "version": p["version"]} for p in packages] != identities:
        raise RecoveryError("package coverage mismatch")
    paths = [relative(p) for p in request["paths"]]
    # Overlapping selections produce duplicate tar entries; refuse them before copying.
    if len(paths) != len(set(paths)) or any(a != b and b.startswith(a + "/") for a in paths for b in paths):
        raise RecoveryError("overlapping configuration selection")
    configs = configuration(root, paths)
    output.mkdir(mode=0o700)
    try:
        (output / "packages").mkdir(mode=0o700)
        retained = []
        for index, package in enumerate(packages):
            source = no_symlink(Path(package["source"]))
            info = metadata(source)
            if any(info[key] != package[key] for key in ("name", "version", "arch")):
                raise RecoveryError("package metadata changed since inventory")
            before = digest(source)
            name = f"packages/{index:05d}.pkg.tar"
            dest = output / name
            with source.open("rb") as src, open(dest, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as dst:
                shutil.copyfileobj(src, dst)
            if digest(dest) != before or digest(source) != before or metadata(dest) != info:
                raise RecoveryError("package archive changed during capture")
            entry = dict(info, file=name, sha256=before, signature=None)
            signature = source.with_name(source.name + ".sig")
            if signature.exists() or signature.is_symlink():
                signature_sha = digest(signature)
                sig_name = name + ".sig"
                with signature.open("rb") as src, open(output / sig_name, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as dst:
                    shutil.copyfileobj(src, dst)
                if digest(output / sig_name) != signature_sha or digest(signature) != signature_sha:
                    raise RecoveryError("detached signature changed during capture")
                entry["signature"] = dict(file=sig_name, sha256=signature_sha)
            retained.append(entry)
        archive = output / "configuration.tar"
        # libarchive retains numeric ownership, links, ACLs, xattrs, and flags.
        command(["bsdtar", "--format", "pax", "--acls", "--xattrs", "--fflags",
                 "-cpf", str(archive), "-C", str(root), "--", *paths])
        archive.chmod(0o600)
        check_configuration_archive(archive, configs)
        if (configuration(root, paths) != configs or installed(root) != identities
                or architectures(root) != report["architectures"]):
            raise RecoveryError("deployed state changed during capture")
        manifest = dict(schema=SCHEMA, kind="recovery-capture", purpose="trial",
                        source_root=str(root), captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        installed=identities, architectures=report["architectures"], packages=retained, configuration=configs,
                        configuration_sha256=digest(archive), mounts=report["mounts"])
        save_private(output / "manifest.json", manifest)
        print(json.dumps(dict(state="captured-trial-files", packages=len(retained),
                              manifest_sha256=digest(output / "manifest.json"))))
    except BaseException:
        shutil.rmtree(output)
        raise
    return 0


def verified(bundle: Path, expected: str) -> dict:
    bundle = no_symlink(bundle)
    manifest_path = bundle / "manifest.json"
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(manifest_path) != expected:
        raise RecoveryError("manifest digest mismatch")
    manifest = load(manifest_path)
    if (manifest["schema"], manifest["kind"], manifest["purpose"]) != (SCHEMA, "recovery-capture", "trial"):
        raise RecoveryError("unsupported recovery capture")
    packages = manifest["packages"]
    identities = [{"name": p["name"], "version": p["version"]} for p in packages]
    if not identities or identities != manifest["installed"] or len({p["name"] for p in packages}) != len(packages):
        raise RecoveryError("retained package coverage mismatch")
    for index, package in enumerate(packages):
        if package["arch"] not in manifest["architectures"]:
            raise RecoveryError("retained package architecture mismatch")
        if package["file"] != f"packages/{index:05d}.pkg.tar":
            raise RecoveryError("retained package path mismatch")
        path = bundle / package["file"]
        if digest(path) != package["sha256"] or metadata(path) != {k: package[k] for k in ("name", "version", "arch")}:
            raise RecoveryError("retained package changed")
        signature = package["signature"]
        if signature is not None:
            if signature["file"] != package["file"] + ".sig" or digest(bundle / signature["file"]) != signature["sha256"]:
                raise RecoveryError("retained detached signature changed")
    config = bundle / "configuration.tar"
    if digest(config) != manifest["configuration_sha256"]:
        raise RecoveryError("retained configuration changed")
    check_configuration_archive(config, manifest["configuration"])
    return manifest


def verify(args) -> int:
    manifest = verified(args.bundle, args.digest)
    print(json.dumps(dict(state="verified-files", packages=len(manifest["packages"]))))
    return 0


def prepare_restore(args) -> int:
    bundle = no_symlink(args.bundle)
    manifest = verified(bundle, args.digest)
    workspace = no_symlink(args.workspace)
    root = no_symlink(args.root)
    if (not workspace.is_dir() or workspace.stat().st_uid != os.getuid()
            or workspace.stat().st_mode & 0o077 or any(workspace.iterdir())):
        raise RecoveryError("restore workspace must be empty, private, and owner-controlled")
    if root.parent != workspace or root.exists() or root == Path(manifest["source_root"]):
        raise RecoveryError("restore root must be a new direct child of the private workspace")
    if any((part / ".ashp-root").exists() or (part / ".git").is_file()
           or (part / ".git/HEAD").exists() for part in (workspace, *workspace.parents)):
        raise RecoveryError("existing build or Git workspace refused")
    output = private_destination(args.output)
    if output.is_relative_to(workspace) or output.is_relative_to(bundle):
        raise RecoveryError("handoff output must be separate from the bundle and restore workspace")
    config = no_symlink(args.pacman_config)
    options = {}
    section = False
    for line in config.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[options]" and not section:
            section = True
            continue
        if not section:
            raise RecoveryError("offline pacman options require an options section")
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key not in ("Architecture", "LocalFileSigLevel", "SigLevel") or key in options:
            raise RecoveryError("offline pacman config must contain only architecture and signature policy")
        options[key] = value
    if not options.get("LocalFileSigLevel"):
        raise RecoveryError("owner must select an explicit local archive signature policy")
    selected_arches = options.get("Architecture", "auto").split()
    if not selected_arches or any(a != "auto" and a not in manifest["architectures"] for a in selected_arches):
        raise RecoveryError("offline pacman architecture mismatch")
    effective_arches = {"any", *(platform.machine() if a == "auto" else a for a in selected_arches)}
    if any(p["arch"] not in effective_arches for p in manifest["packages"]):
        raise RecoveryError("offline pacman config does not cover every retained package architecture")
    signature_words = {"Never", "Optional", "Required", "TrustedOnly", "TrustAll",
                       "PackageNever", "PackageOptional", "PackageRequired", "PackageTrustedOnly",
                       "PackageTrustAll", "DatabaseNever", "DatabaseOptional", "DatabaseRequired",
                       "DatabaseTrustedOnly", "DatabaseTrustAll"}
    if any(not value.split() or not set(value.split()) <= signature_words
           for key, value in options.items() if key != "Architecture"):
        raise RecoveryError("invalid offline signature policy")
    argv = ["pacman", "--root", str(root), "--dbpath", str(root / "var/lib/pacman"),
            "--cachedir", str(root / "var/cache/pacman/pkg"), "--logfile", str(root / "var/log/pacman.log"),
            "--gpgdir", str(root / "etc/pacman.d/gnupg"), "--hookdir", str(root / "etc/pacman.d/hooks"),
            "--config", str(config), "-U", "--", *[str(bundle / p["file"]) for p in manifest["packages"]]]
    info = workspace.stat()
    handoff = dict(schema=SCHEMA, state="prepared-owner-handoff", bundle=str(bundle),
                   manifest_sha256=args.digest, source_root=manifest["source_root"], root=str(root),
                   workspace=dict(path=str(workspace), device=info.st_dev, inode=info.st_ino),
                   pacman_config=dict(path=str(config), sha256=digest(config)), package_install_argv=argv,
                   configuration_restore_argv=["bsdtar", "--acls", "--xattrs", "--fflags", "--numeric-owner",
                                               "-xpf", str(bundle / "configuration.tar"), "-C", str(root)],
                   package_comparison_argv=["pacman", "--root", str(root), "--dbpath", str(root / "var/lib/pacman"),
                                            "--config", str(config), "-Q"],
                   required_gates=["owner-isolated execution", "revalidate bundle, config, workspace identity and empty root before mutation",
                                   "signature policy, detached signatures and isolated keyring readiness",
                                   "complete installed package equality", "selected configuration and metadata equality",
                                   "service and backend health", "separate filesystem coverage",
                                   "final owner capture and snapshot immediately before activation"])
    save_private(output, handoff)
    print(json.dumps(dict(state="prepared-owner-handoff", packages=len(manifest["packages"]))))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="read deployed identities and find retained archives")
    inv.add_argument("--root", type=Path, default=Path("/"))
    inv.add_argument("--archive-dir", type=Path, action="append")
    inv.add_argument("--output", type=Path, required=True)
    inv.set_defaults(run=inventory)
    cap = sub.add_parser("capture", help="retain exact trial package and selected configuration files")
    cap.add_argument("--inventory", type=Path, required=True)
    cap.add_argument("--request", type=Path, required=True)
    cap.add_argument("--output", type=Path, required=True)
    cap.set_defaults(run=capture)
    ver = sub.add_parser("verify", help="verify retained bytes offline against a separately held digest")
    ver.add_argument("--bundle", type=Path, required=True)
    ver.add_argument("--digest", required=True)
    ver.set_defaults(run=verify)
    prep = sub.add_parser("prepare-restore", help="write owner commands and gates; do not execute them")
    prep.add_argument("--bundle", type=Path, required=True)
    prep.add_argument("--digest", required=True)
    prep.add_argument("--workspace", type=Path, required=True)
    prep.add_argument("--root", type=Path, required=True)
    prep.add_argument("--pacman-config", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.set_defaults(run=prepare_restore)
    args = parser.parse_args()
    try:
        return args.run(args)
    except RecoveryError as exc:
        print(f"recovery preparation refused: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, tarfile.TarError):
        # Raw exceptions and child stderr can contain private paths or secret bytes.
        print("recovery preparation refused; check private inputs and required tools", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Exercise the recovery CLI with synthetic pacman state and real small archives."""

import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools/stack_recovery.py"


def run_cli(*args, env=None):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                          env=env, capture_output=True, text=True)


def host(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "installed").write_text("engine 1.2-3\nhelper 4-1\n")
    (root / "etc").mkdir()
    (root / "etc/pacman.conf").write_text("[options]\nArchitecture = auto x86_64_v4\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pacman = bin_dir / "pacman"
    pacman.write_text("#!/usr/bin/env python3\nimport pathlib, sys\n"
                      "assert sys.argv[1] == '--root'\n"
                      "root = pathlib.Path(sys.argv[2])\n"
                      "assert sys.argv[3:] == ['--dbpath', str(root / 'var/lib/pacman'), '--config', '/dev/null', '-Q']\n"
                      "print((pathlib.Path(sys.argv[2]) / 'installed').read_text(), end='')\n")
    pacman.chmod(0o700)
    pacman_conf = bin_dir / "pacman-conf"
    pacman_conf.write_text("#!/bin/sh\n[ \"$1\" = '--config' ] && [ \"$3\" = 'Architecture' ] || exit 1\nprintf 'x86_64\\nx86_64_v4\\n'\n")
    pacman_conf.chmod(0o700)
    findmnt = bin_dir / "findmnt"
    findmnt.write_text('#!/bin/sh\nprintf \'{"filesystems":[{"target":"/","fstype":"btrfs","fsroot":"/"}]}\\n\'\n')
    findmnt.chmod(0o700)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    cache = tmp_path / "cache"
    cache.mkdir()
    return root, cache, env


def package(cache, name, version, arch="x86_64"):
    # Deliberately misleading filename: identity comes from .PKGINFO.
    path = cache / f"opaque-{name}-{version}.pkg.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        data = f"pkgname = {name}\npkgver = {version}\narch = {arch}\n".encode()
        member = tarfile.TarInfo(".PKGINFO")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return path


def test_inventory_reports_whole_installed_set_and_missing_exact_versions(tmp_path):
    root, cache, env = host(tmp_path)
    package(cache, "engine", "1.2-3")
    package(cache, "helper", "5-1")
    report = tmp_path / "inventory.json"

    result = run_cli("inventory", "--root", root, "--archive-dir", cache,
                     "--output", report, env=env)

    assert result.returncode == 10, result.stderr
    saved = json.loads(report.read_text())
    assert saved["installed"] == [{"name": "engine", "version": "1.2-3"},
                                  {"name": "helper", "version": "4-1"}]
    assert saved["missing"] == [{"name": "helper", "version": "4-1"}]
    assert saved["packages"][0]["arch"] == "x86_64"
    assert report.stat().st_mode & 0o777 == 0o600
    assert str(root) not in result.stdout + result.stderr
    assert not (root / "var/lib/pacman").exists()


def capture_inputs(tmp_path):
    root, cache, env = host(tmp_path)
    package(cache, "engine", "1.2-3")
    package(cache, "helper", "4-1", arch="any")
    etc = root / "etc"
    etc.mkdir(exist_ok=True)
    config = etc / "serving.conf"
    config.write_bytes(b"credential=synthetic-secret\n")
    config.chmod(0o640)
    os.setxattr(config, "user.recovery", b"preserve-me")
    (etc / "active.conf").symlink_to("serving.conf")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"purpose": "trial", "paths": ["etc"]}))
    inventory = tmp_path / "inventory.json"
    result = run_cli("inventory", "--root", root, "--archive-dir", cache,
                     "--output", inventory, env=env)
    assert result.returncode == 0, result.stderr
    return root, cache, env, inventory, request


def test_capture_retains_exact_private_inputs_and_verifies_without_source(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    bundle = tmp_path / "bundle"
    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)
    assert result.returncode == 0, result.stderr
    digest = json.loads(result.stdout)["manifest_sha256"]
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["purpose"] == "trial"
    assert manifest["installed"] == [{"name": "engine", "version": "1.2-3"},
                                     {"name": "helper", "version": "4-1"}]
    retained = manifest["packages"][0]
    assert (bundle / retained["file"]).read_bytes() == next(cache.glob("*engine*")).read_bytes()
    with tarfile.open(bundle / "configuration.tar") as archive:
        config = archive.getmember("etc/serving.conf")
        assert config.mode == 0o640
        assert config.uid == os.getuid()
        assert config.gid == os.getgid()
        assert archive.extractfile(config).read() == b"credential=synthetic-secret\n"
        assert config.pax_headers["SCHILY.xattr.user.recovery"] == "preserve-me"
        assert archive.getmember("etc/active.conf").linkname == "serving.conf"
    # The source can disappear; verification must use only retained bytes.
    import shutil
    shutil.rmtree(root)
    shutil.rmtree(cache)
    result = run_cli("verify", "--bundle", bundle, "--digest", digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "verified-files"
    assert "synthetic-secret" not in result.stdout + result.stderr
    assert bundle.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o077 == 0 for p in bundle.rglob("*") if not p.is_symlink())


def captured(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    bundle = tmp_path / "bundle"
    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)
    assert result.returncode == 0, result.stderr
    return bundle, json.loads(result.stdout)["manifest_sha256"]


def test_prepare_restore_records_owner_commands_without_creating_or_installing_root(tmp_path):
    bundle, digest = captured(tmp_path)
    workspace = tmp_path / "restore-workspace"
    workspace.mkdir(mode=0o700)
    target = workspace / "root"
    config = tmp_path / "offline-pacman.conf"
    config.write_text("[options]\nArchitecture = auto\nLocalFileSigLevel = Required TrustedOnly\n")
    plan = tmp_path / "restore.json"
    result = run_cli("prepare-restore", "--bundle", bundle, "--digest", digest,
                     "--workspace", workspace, "--root", target, "--pacman-config", config,
                     "--output", plan)
    assert result.returncode == 0, result.stderr
    saved = json.loads(plan.read_text())
    assert saved["state"] == "prepared-owner-handoff"
    argv = saved["package_install_argv"]
    assert argv[:3] == ["pacman", "--root", str(target)]
    assert argv[argv.index("--dbpath") + 1] == str(target / "var/lib/pacman")
    assert argv[argv.index("--gpgdir") + 1] == str(target / "etc/pacman.d/gnupg")
    assert "-U" in argv and "--noconfirm" not in argv
    assert not target.exists()
    assert saved["manifest_sha256"] == digest
    assert "owner-isolated execution" in saved["required_gates"]
    comparison = saved["package_comparison_argv"]
    assert comparison[comparison.index("--dbpath") + 1] == str(target / "var/lib/pacman")
    assert comparison[comparison.index("--config") + 1] == str(config)
    assert str(target) not in result.stdout + result.stderr


def test_restore_comparison_queries_only_the_proposed_database_with_real_pacman(tmp_path):
    bundle, digest = captured(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    root = workspace / "root"
    config = tmp_path / "offline.conf"
    config.write_text("[options]\nLocalFileSigLevel = Required TrustedOnly\n")
    plan = tmp_path / "plan.json"
    result = run_cli("prepare-restore", "--bundle", bundle, "--digest", digest,
                     "--workspace", workspace, "--root", root, "--pacman-config", config, "--output", plan)
    assert result.returncode == 0, result.stderr
    comparison = json.loads(plan.read_text())["package_comparison_argv"]

    def database(path, name, version):
        local = path / "local"
        local.mkdir(parents=True)
        (local / "ALPM_DB_VERSION").write_text("9\n")
        entry = local / f"{name}-{version}"
        entry.mkdir()
        (entry / "desc").write_text(f"%NAME%\n{name}\n\n%VERSION%\n{version}\n\n")

    database(root / "var/lib/pacman", "restored-only", "3-1")
    database(tmp_path / "host-db", "host-only", "9-1")
    host_config = tmp_path / "host.conf"
    host_config.write_text(f"[options]\nDBPath = {tmp_path / 'host-db'}\n")
    # A simulated ambient config cannot override the handoff's explicit database/config.
    result = subprocess.run(["pacman", "--config", str(host_config), *comparison[1:]],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "restored-only 3-1\n"


def test_inventory_accepts_deployed_microarchitectures_from_pacman_configuration(tmp_path):
    root, cache, env = host(tmp_path)
    package(cache, "engine", "1.2-3", arch="x86_64_v4")
    package(cache, "helper", "4-1", arch="any")
    inventory = tmp_path / "inventory.json"
    result = run_cli("inventory", "--root", root, "--archive-dir", cache,
                     "--output", inventory, env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(inventory.read_text())["architectures"] == ["any", "x86_64", "x86_64_v4"]


@pytest.mark.parametrize("include", [False, True])
def test_separate_root_policy_uses_real_pacman_conf_and_refuses_ambient_includes(tmp_path, include):
    root, cache, env = host(tmp_path)
    package(cache, "engine", "1.2-3", arch="x86_64_v4")
    package(cache, "helper", "4-1", arch="any")
    # Keep fake read-only pacman, but exercise the real config reader.
    (tmp_path / "bin/pacman-conf").unlink()
    if include:
        ambient = tmp_path / "ambient.conf"
        ambient.write_text("Architecture = x86_64_v4\n")
        (root / "etc/pacman.conf").write_text(f"[options]\nInclude = {ambient}\n")
    else:
        (root / "etc/pacman.conf").write_text("[options]\nArchitecture = x86_64_v4\n")
    report = tmp_path / "inventory.json"
    result = run_cli("inventory", "--root", root, "--archive-dir", cache, "--output", report, env=env)
    if include:
        assert result.returncode == 1
        assert not report.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(report.read_text())["architectures"] == ["any", "x86_64_v4"]


def test_microarchitecture_capture_verifies_offline_and_requires_matching_restore_policy(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    next(cache.glob("*engine*")).unlink()
    package(cache, "engine", "1.2-3", arch="x86_64_v4")
    inventory.unlink()
    assert run_cli("inventory", "--root", root, "--archive-dir", cache,
                   "--output", inventory, env=env).returncode == 0
    bundle = tmp_path / "bundle"
    result = run_cli("capture", "--inventory", inventory, "--request", request, "--output", bundle, env=env)
    assert result.returncode == 0, result.stderr
    digest = json.loads(result.stdout)["manifest_sha256"]
    # Without the fake pacman-conf or source root, verification still uses the pinned policy.
    import shutil
    shutil.rmtree(root)
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    config = tmp_path / "offline.conf"
    config.write_text("[options]\nArchitecture = auto\nLocalFileSigLevel = Required TrustedOnly\n")
    args = ("prepare-restore", "--bundle", bundle, "--digest", digest, "--workspace", workspace,
            "--root", workspace / "root", "--pacman-config", config, "--output", tmp_path / "plan.json")
    assert run_cli(*args).returncode == 1
    config.write_text("[options]\nArchitecture = auto x86_64_v4\nLocalFileSigLevel = Required TrustedOnly\n")
    result = run_cli(*args)
    assert result.returncode == 0, result.stderr


def test_capture_keeps_detached_signature_bytes_for_owner_signature_checks(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    source = next(cache.glob("*engine*"))
    signature = Path(str(source) + ".sig")
    signature.write_bytes(b"synthetic-detached-signature")
    bundle = tmp_path / "bundle"
    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)
    assert result.returncode == 0, result.stderr
    digest = json.loads(result.stdout)["manifest_sha256"]
    manifest = json.loads((bundle / "manifest.json").read_text())
    retained = manifest["packages"][0]["signature"]
    path = bundle / retained["file"]
    assert path.read_bytes() == signature.read_bytes()
    path.write_bytes(b"changed")
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 1


@pytest.mark.parametrize("change", ["package-missing", "identity-changed", "inventory-changed", "config-missing",
                                    "unsafe-config", "output-exists", "git-output", "public-output", "final-purpose"])
def test_capture_refuses_incomplete_changed_or_unsafe_inputs_without_partial_bundle(tmp_path, change):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    bundle = tmp_path / "bundle"
    if change == "package-missing":
        next(cache.glob("*engine*")).unlink()
    elif change == "identity-changed":
        next(cache.glob("*engine*")).unlink()
        path = package(cache, "engine", "2-1")
        path.rename(cache / "opaque-engine-1.2-3.pkg.tar.gz")
    elif change == "inventory-changed":
        (root / "installed").write_text("engine 2-1\nhelper 4-1\n")
    elif change == "config-missing":
        request.write_text('{"purpose":"trial","paths":["etc/missing"]}')
    elif change == "unsafe-config":
        request.write_text('{"purpose":"trial","paths":["../secret"]}')
    elif change == "output-exists":
        bundle.mkdir()
        (bundle / "owner.txt").write_text("untouched")
    elif change == "git-output":
        subprocess.run(["git", "init", "-q", str(tmp_path / "git")], check=True)
        (tmp_path / "git").chmod(0o700)
        bundle = tmp_path / "git/bundle"
    elif change == "public-output":
        parent = tmp_path / "public"
        parent.mkdir(mode=0o755)
        bundle = parent / "bundle"
    elif change == "final-purpose":
        request.write_text('{"purpose":"final","paths":["etc"]}')
    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)
    assert result.returncode == 1, result.stderr
    assert "synthetic-secret" not in result.stdout + result.stderr
    if change == "output-exists":
        assert (bundle / "owner.txt").read_text() == "untouched"
    else:
        assert not bundle.exists()


@pytest.mark.parametrize("artifact", ["package", "config", "manifest", "missing", "symlink"])
def test_verify_refuses_changed_missing_or_aliased_retained_files(tmp_path, artifact):
    bundle, digest = captured(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())
    package_path = bundle / manifest["packages"][0]["file"]
    if artifact == "package":
        package_path.write_bytes(b"changed")
    elif artifact == "config":
        (bundle / "configuration.tar").write_bytes(b"changed")
    elif artifact == "manifest":
        (bundle / "manifest.json").write_text("{}")
    elif artifact == "missing":
        package_path.unlink()
    elif artifact == "symlink":
        outside = tmp_path / "outside-package"
        package_path.rename(outside)
        package_path.symlink_to(outside)
    result = run_cli("verify", "--bundle", bundle, "--digest", digest)
    assert result.returncode == 1


def test_verify_checks_configuration_xattr_metadata_against_the_retained_archive(tmp_path):
    bundle, _ = captured(tmp_path)
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text())
    config = next(r for r in manifest["configuration"] if r["path"] == "etc/serving.conf")
    config["xattrs"]["user.recovery"] = "bm90LXRoZS1jYXB0dXJlZC12YWx1ZQ=="
    path.write_text(json.dumps(manifest))
    # Even an owner-supplied digest cannot turn inconsistent metadata into a valid bundle.
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = run_cli("verify", "--bundle", bundle, "--digest", digest)
    assert result.returncode == 1


def test_capture_preserves_posix_acls_and_binary_extended_attributes(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    config = root / "etc/serving.conf"
    os.setxattr(config, "user.binary", b"\x00\xff\x01")
    subprocess.run(["setfacl", "-m", f"u:{os.getuid()}:r--", str(config)], check=True)
    bundle = tmp_path / "bundle"
    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)
    assert result.returncode == 0, result.stderr
    with tarfile.open(bundle / "configuration.tar") as archive:
        member = archive.getmember("etc/serving.conf")
        assert "SCHILY.acl.access" in member.pax_headers
        assert member.pax_headers["LIBARCHIVE.xattr.user.binary"] == "AP8B"
    digest = json.loads(result.stdout)["manifest_sha256"]
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0


@pytest.mark.parametrize("target", ["live", "source", "symlink", "nonempty", "shared", "build-root", "outside", "changed-config", "missing-section", "late-section"])
def test_prepare_restore_refuses_live_shared_changed_or_existing_targets(tmp_path, target):
    bundle, digest = captured(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    root = workspace / "root"
    config = tmp_path / "pacman.conf"
    config.write_text("[options]\nLocalFileSigLevel = Required TrustedOnly\n")
    if target == "live":
        root = Path("/")
    elif target == "source":
        root = tmp_path / "source"
    elif target == "symlink":
        root.symlink_to(tmp_path / "source", target_is_directory=True)
    elif target == "nonempty":
        root.mkdir()
        (root / "other-worker").write_text("untouched")
    elif target == "shared":
        workspace.chmod(0o755)
    elif target == "build-root":
        (workspace / ".ashp-root").mkdir()
    elif target == "outside":
        root = tmp_path / "outside"
    elif target == "changed-config":
        config.write_text("[options]\nLocalFileSigLevel = Never\nInclude = /etc/pacman.conf\n")
    elif target == "missing-section":
        config.write_text("LocalFileSigLevel = Required TrustedOnly\n")
    elif target == "late-section":
        config.write_text("LocalFileSigLevel = Required TrustedOnly\n[options]\n")
    before = set(workspace.rglob("*"))
    plan = tmp_path / "restore.json"
    result = run_cli("prepare-restore", "--bundle", bundle, "--digest", digest,
                     "--workspace", workspace, "--root", root, "--pacman-config", config, "--output", plan)
    assert result.returncode == 1, result.stderr
    assert not plan.exists()
    assert set(workspace.rglob("*")) == before

"""Exercise the recovery CLI with synthetic pacman state and real small archives.

This integration suite requires Python 3.11+, Linux user xattrs and POSIX ACLs,
nanosecond file/directory/link timestamps, bsdtar, pacman, pacman-conf, findmnt,
setfacl, and git.
Missing capabilities fail the suite; they are not blanket-skipped. All package,
configuration, database, command-stall, and restore-workspace inputs are synthetic.
No restore handoff is executed.
"""

import io
import hashlib
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools/stack_recovery.py"


def run_cli(*args, env=None, timeout=10):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                          env=env, capture_output=True, text=True, timeout=timeout)


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


def set_exact_mtime(path, mtime_ns):
    os.utime(path, ns=(mtime_ns, mtime_ns), follow_symlinks=False)
    assert path.lstat().st_mtime_ns == mtime_ns, (
        "Recovery integration tests require exact synthetic filesystem nanoseconds"
    )


@pytest.fixture(scope="module", autouse=True)
def mandatory_recovery_integration_capabilities(tmp_path_factory):
    required = ("bsdtar", "pacman", "pacman-conf", "findmnt", "setfacl", "git")
    missing = [name for name in required if shutil.which(name) is None]
    assert not missing, f"Recovery integration tools are mandatory: {', '.join(missing)}"
    assert sys.version_info >= (3, 11), "Recovery integration tests require Python 3.11+"
    assert sys.platform == "linux", "Recovery integration tests require Linux metadata"
    probe = tmp_path_factory.mktemp("recovery-capabilities") / "file"
    probe.write_bytes(b"synthetic capability probe")
    os.setxattr(probe, "user.recovery_capability", b"available")
    assert os.getxattr(probe, "user.recovery_capability") == b"available"
    subprocess.run(["setfacl", "-m", f"u:{os.getuid()}:r--", str(probe)], check=True, timeout=5)
    assert "system.posix_acl_access" in os.listxattr(probe)
    set_exact_mtime(probe, 1700000000123456789)
    set_exact_mtime(probe, 1700000000123456790)
    link = probe.with_name("link")
    link.symlink_to("file")
    set_exact_mtime(link, 1700000000123456789)
    set_exact_mtime(link, 1700000000123456790)


def capture_with_exact_mtime(tmp_path, record_path, mtime_ns):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    set_exact_mtime(root / record_path, mtime_ns)
    bundle = tmp_path / "bundle"
    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)
    assert result.returncode == 0, result.stderr
    return bundle, json.loads(result.stdout)["manifest_sha256"]


def rebind_configuration_mtime(bundle, member_name, pax_mtime, *, base_mtime=None):
    # Build deliberately inconsistent/equivalent retained inputs, not a restore.
    archive_path = bundle / "configuration.tar"
    with tarfile.open(archive_path, "r:") as archive:
        retained = [(member, archive.extractfile(member).read() if member.isfile() else None)
                    for member in archive.getmembers()]
    rewritten = bundle / "rewritten-configuration.tar"
    with tarfile.open(rewritten, "w", format=tarfile.PAX_FORMAT) as archive:
        for member, data in retained:
            if member.name.rstrip("/") == member_name:
                if pax_mtime is None:
                    assert type(base_mtime) is int
                    member.pax_headers.pop("mtime", None)
                    member.mtime = base_mtime
                else:
                    member.pax_headers = dict(member.pax_headers, mtime=pax_mtime)
            archive.addfile(member, io.BytesIO(data) if data is not None else None)
    rewritten.chmod(0o600)
    rewritten.replace(archive_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["configuration_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def synthetic_command(tmp_path, name, body):
    command_path = tmp_path / "bin" / name
    command_path.write_text(f"#!{sys.executable}\n" + body)
    command_path.chmod(0o700)
    return dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")


def stalled_command(tmp_path, name):
    marker = tmp_path / "stall-started"
    env = synthetic_command(
        tmp_path, name,
        "import pathlib, sys, time\n"
        f"pathlib.Path({str(marker)!r}).write_text('started')\n"
        f"print({str(tmp_path)!r}, flush=True)\n"
        "print('synthetic-child-secret', file=sys.stderr, flush=True)\n"
        "time.sleep(10)\n",
    )
    return env, marker


def watch_archive_metadata(tmp_path, suspect):
    # Observe only the external archive-reader boundary, not recovery internals.
    real_bsdtar = shutil.which("bsdtar")
    assert real_bsdtar is not None
    marker = tmp_path / "aliased-metadata-read"
    env = synthetic_command(
        tmp_path, "bsdtar",
        "import os, pathlib, sys\n"
        f"suspect = {str(suspect)!r}\n"
        "if any(arg == suspect or arg.startswith(suspect + os.sep) for arg in sys.argv[1:]):\n"
        f"    pathlib.Path({str(marker)!r}).write_text('metadata read')\n"
        f"os.execv({real_bsdtar!r}, [{real_bsdtar!r}, *sys.argv[1:]])\n",
    )
    return env, marker


def assert_private_refusal(result, tmp_path):
    assert result.returncode == 1, result.stderr
    public = result.stdout + result.stderr
    assert str(tmp_path) not in public
    assert "synthetic-secret" not in public
    assert "synthetic-child-secret" not in public


@pytest.mark.parametrize("link", ["serving.conf", "/usr/share/example"])
def test_capture_preserves_relative_and_filesystem_root_absolute_configuration_links(tmp_path, link):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    target = root / "usr/share/example"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic separate-root target")
    active = root / "etc/active.conf"
    active.unlink()
    active.symlink_to(link)
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)

    assert result.returncode == 0, result.stderr
    manifest = json.loads((bundle / "manifest.json").read_text())
    record = next(item for item in manifest["configuration"] if item["path"] == "etc/active.conf")
    assert record["link"] == link
    with tarfile.open(bundle / "configuration.tar") as archive:
        assert archive.getmember("etc/active.conf").linkname == link
    digest = json.loads(result.stdout)["manifest_sha256"]
    result = run_cli("verify", "--bundle", bundle, "--digest", digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "verified-files"


@pytest.mark.parametrize("link_kind", ["physical-source-root", "escaping-relative"])
def test_capture_refuses_source_location_links_and_relative_root_escapes(tmp_path, link_kind):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    target = root / "usr/share/example"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic target")
    outside = tmp_path / "outside-target"
    outside.write_bytes(b"synthetic outside target")
    active = root / "etc/active.conf"
    active.unlink()
    active.symlink_to(str(target) if link_kind == "physical-source-root" else "../../outside-target")
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)

    assert_private_refusal(result, tmp_path)
    assert not bundle.exists()
    assert outside.read_bytes() == b"synthetic outside target"


@pytest.mark.parametrize("record_path", ["etc", "etc/serving.conf", "etc/active.conf"])
@pytest.mark.parametrize("mtime_ns,pax_mtime", [
    (1700000000000000001, "1700000000.000000001"),
    (4102444800123456789, "4102444800.123456789"),
])
def test_capture_and_verify_preserve_exact_nanosecond_configuration_mtimes(tmp_path, record_path,
                                                                         mtime_ns, pax_mtime):
    bundle, digest = capture_with_exact_mtime(tmp_path, record_path, mtime_ns)
    manifest = json.loads((bundle / "manifest.json").read_text())
    record = next(item for item in manifest["configuration"] if item["path"] == record_path)
    assert record["mtime_ns"] == mtime_ns
    with tarfile.open(bundle / "configuration.tar") as archive:
        member = next(item for item in archive.getmembers() if item.name.rstrip("/") == record_path)
        assert Decimal(member.pax_headers["mtime"]) == Decimal(pax_mtime)

    result = run_cli("verify", "--bundle", bundle, "--digest", digest)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "verified-files"


@pytest.mark.parametrize("record_path", ["etc", "etc/serving.conf", "etc/active.conf"])
def test_verify_refuses_one_nanosecond_manifest_mtime_discrepancy(tmp_path, record_path):
    bundle, digest = capture_with_exact_mtime(tmp_path, record_path, 1700000000123456789)
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = next(item for item in manifest["configuration"] if item["path"] == record_path)
    record["mtime_ns"] = 1700000000123456790
    manifest_path.write_text(json.dumps(manifest))
    # Pin the deliberately changed manifest so digest rejection cannot hide the mismatch.
    changed_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    result = run_cli("verify", "--bundle", bundle, "--digest", changed_digest)

    assert_private_refusal(result, tmp_path)


@pytest.mark.parametrize("mtime_ns,pax_mtime,accepted", [
    (1700000000123456789, "1700000000.123456789", True),
    (1700000000123456789, "1700000000.1234567890", True),
    (1700000000123456789, "1700000000.123456790", False),
    (1700000000123456789, "1700000000.123456788", False),
    (4102444800123456789, "4102444800.123456789", True),
    (4102444800123456789, "4102444800.123456790", False),
])
def test_verify_compares_decimal_pax_mtime_without_float_rounding(tmp_path, mtime_ns, pax_mtime,
                                                               accepted):
    bundle, digest = capture_with_exact_mtime(tmp_path, "etc/serving.conf", mtime_ns)
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0
    changed_digest = rebind_configuration_mtime(bundle, "etc/serving.conf", pax_mtime)

    result = run_cli("verify", "--bundle", bundle, "--digest", changed_digest)

    if accepted:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["state"] == "verified-files"
    else:
        assert_private_refusal(result, tmp_path)


@pytest.mark.parametrize("name", ["pacman", "pacman-conf", "findmnt", "bsdtar"])
def test_inventory_times_out_stalled_external_commands_without_private_output(tmp_path, name):
    root, cache, env = host(tmp_path)
    package(cache, "engine", "1.2-3")
    package(cache, "helper", "4-1", arch="any")
    env, marker = stalled_command(tmp_path, name)
    report = tmp_path / "inventory.json"

    result = run_cli("inventory", "--root", root, "--archive-dir", cache, "--output", report,
                     "--command-timeout-seconds", "0.2", env=env, timeout=5)

    assert_private_refusal(result, tmp_path)
    assert marker.read_text() == "started"
    assert not report.exists()


def test_capture_timeout_removes_populated_incomplete_bundle_and_hides_child_output(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    real_bsdtar = shutil.which("bsdtar")
    assert real_bsdtar is not None
    marker = tmp_path / "stall-started"
    env = synthetic_command(
        tmp_path, "bsdtar",
        "import json, os, pathlib, sys, time\n"
        "archive = next((pathlib.Path(arg) for arg in sys.argv[1:]\n"
        "                if pathlib.Path(arg).name == 'configuration.tar'), None)\n"
        "if archive is not None:\n"
        "    output = archive.parent\n"
        f"    pathlib.Path({str(marker)!r}).write_text(json.dumps({{\n"
        "        'output_exists': output.is_dir(),\n"
        "        'copied_packages': len(list((output / 'packages').glob('*.pkg.tar')))\n"
        "    }))\n"
        "    print(str(output), flush=True)\n"
        "    print('synthetic-child-secret', file=sys.stderr, flush=True)\n"
        "    time.sleep(10)\n"
        f"os.execv({real_bsdtar!r}, [{real_bsdtar!r}, *sys.argv[1:]])\n",
    )
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request, "--output", bundle,
                     "--command-timeout-seconds", "0.5", env=env, timeout=5)

    assert_private_refusal(result, tmp_path)
    assert json.loads(marker.read_text()) == {"output_exists": True, "copied_packages": 2}
    assert not bundle.exists()


@pytest.mark.parametrize("subcommand", ["verify", "prepare-restore"])
def test_retained_file_commands_apply_the_external_command_timeout(tmp_path, subcommand):
    bundle, digest = captured(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    config = tmp_path / "offline.conf"
    config.write_text("[options]\nLocalFileSigLevel = Required TrustedOnly\n")
    plan = tmp_path / "restore.json"
    args = [subcommand, "--bundle", bundle, "--digest", digest]
    if subcommand == "prepare-restore":
        args += ["--workspace", workspace, "--root", workspace / "root",
                 "--pacman-config", config, "--output", plan]
    env, marker = stalled_command(tmp_path, "bsdtar")

    result = run_cli(*args, "--command-timeout-seconds", "0.2", env=env, timeout=5)

    assert_private_refusal(result, tmp_path)
    assert marker.read_text() == "started"
    assert not plan.exists()
    assert not (workspace / "root").exists()
    assert (bundle / "manifest.json").is_file()


@pytest.mark.parametrize("subcommand", ["inventory", "capture", "verify", "prepare-restore"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "1e309", "not-a-number"])
def test_command_timeout_option_requires_a_positive_finite_number(tmp_path, subcommand, value):
    root, cache, env = host(tmp_path)
    output = tmp_path / "output"
    if subcommand == "inventory":
        args = ["--root", root, "--archive-dir", cache, "--output", output]
    elif subcommand == "capture":
        args = ["--inventory", tmp_path / "inventory.json", "--request", tmp_path / "request.json",
                "--output", output]
    else:
        args = ["--bundle", tmp_path / "bundle", "--digest", "0" * 64]
        if subcommand == "prepare-restore":
            args += ["--workspace", tmp_path / "workspace", "--root", tmp_path / "workspace/root",
                     "--pacman-config", tmp_path / "offline.conf", "--output", output]

    result = run_cli(subcommand, *args, f"--command-timeout-seconds={value}", env=env)

    assert result.returncode != 0
    assert "command-timeout-seconds" in result.stderr
    assert str(tmp_path) not in result.stdout + result.stderr
    assert not output.exists()


def test_inventory_and_capture_accept_direct_archive_paths(tmp_path):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    saved = json.loads(inventory.read_text())
    assert saved["missing"] == []
    assert {Path(item["source"]) for item in saved["packages"]} == set(cache.glob("*.pkg.tar.gz"))
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request, "--output", bundle,
                     "--command-timeout-seconds", "2", env=env)

    assert result.returncode == 0, result.stderr
    digest = json.loads(result.stdout)["manifest_sha256"]
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0


@pytest.mark.parametrize("alias_kind", ["leaf", "ancestor"])
def test_inventory_never_admits_or_reads_aliased_archive_candidates(tmp_path, alias_kind):
    root, cache, env = host(tmp_path)
    archive = package(cache, "engine", "1.2-3")
    package(cache, "helper", "4-1", arch="any")
    if alias_kind == "leaf":
        direct = tmp_path / archive.name
        archive.rename(direct)
        archive.symlink_to(direct)
        suspect = archive
    else:
        direct = tmp_path / "direct-cache"
        cache.rename(direct)
        cache.symlink_to(direct, target_is_directory=True)
        suspect = cache
    env, marker = watch_archive_metadata(tmp_path, suspect)
    report = tmp_path / "inventory.json"

    result = run_cli("inventory", "--root", root, "--archive-dir", cache, "--output", report, env=env)

    assert result.returncode != 0
    assert not marker.exists()
    assert str(tmp_path) not in result.stdout + result.stderr
    if report.exists():
        saved = json.loads(report.read_text())
        assert {"name": "engine", "version": "1.2-3"} in saved["missing"]
        assert all(item["name"] != "engine" for item in saved["packages"])


@pytest.mark.parametrize("alias_kind", ["leaf", "ancestor"])
def test_capture_refuses_archives_retargeted_to_symlinks_after_inventory(tmp_path, alias_kind):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    archive = next(cache.glob("*engine*"))
    if alias_kind == "leaf":
        direct = tmp_path / archive.name
        archive.rename(direct)
        archive.symlink_to(direct)
        suspect = archive
    else:
        direct = tmp_path / "direct-cache"
        cache.rename(direct)
        cache.symlink_to(direct, target_is_directory=True)
        suspect = cache
    env, marker = watch_archive_metadata(tmp_path, suspect)
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)

    assert_private_refusal(result, tmp_path)
    assert not marker.exists()
    assert not bundle.exists()


@pytest.mark.parametrize("subcommand", ["inventory", "capture", "verify", "prepare-restore"])
def test_recovery_subcommand_help_exposes_the_command_timeout_and_300_second_default(subcommand):
    result = run_cli(subcommand, "--help")

    assert result.returncode == 0, result.stderr
    help_text = " ".join(result.stdout.split())
    assert "--command-timeout-seconds SECONDS" in help_text
    assert "default: 300" in help_text


@pytest.mark.parametrize("link", ["missing.conf", "/usr/share/missing-recovery-configuration"])
def test_capture_preserves_dangling_relative_and_absolute_configuration_links(tmp_path, link):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    active = root / "etc/active.conf"
    active.unlink()
    active.symlink_to(link)
    # Check only the synthetic root; do not inspect an absolute host target.
    assert not (root / "etc/missing.conf").exists()
    assert not (root / "usr/share/missing-recovery-configuration").exists()
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)

    assert result.returncode == 0, result.stderr
    manifest = json.loads((bundle / "manifest.json").read_text())
    record = next(item for item in manifest["configuration"] if item["path"] == "etc/active.conf")
    assert record["link"] == link
    with tarfile.open(bundle / "configuration.tar") as archive:
        assert archive.getmember("etc/active.conf").linkname == link
    digest = json.loads(result.stdout)["manifest_sha256"]
    shutil.rmtree(root)
    result = run_cli("verify", "--bundle", bundle, "--digest", digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "verified-files"


@pytest.mark.parametrize("chain", ["relative-first", "absolute-first"])
@pytest.mark.parametrize("endpoint", ["existing", "dangling"])
def test_capture_preserves_contained_mixed_configuration_link_chains(tmp_path, chain, endpoint):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    active = root / "etc/active.conf"
    active.unlink()
    middle = root / "etc/middle.conf"
    unselected = root / "usr/share/current"
    unselected.parent.mkdir(parents=True)
    if chain == "relative-first":
        active.symlink_to("middle.conf")
        middle.symlink_to("/usr/share/current")
        unselected.symlink_to("../../etc/serving.conf")
        expected = {"etc/active.conf": "middle.conf", "etc/middle.conf": "/usr/share/current"}
    else:
        active.symlink_to("/usr/share/current")
        unselected.symlink_to("../../etc/middle.conf")
        middle.symlink_to("serving.conf")
        expected = {"etc/active.conf": "/usr/share/current", "etc/middle.conf": "serving.conf"}
    if endpoint == "dangling":
        (root / "etc/serving.conf").unlink()
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)

    assert result.returncode == 0, result.stderr
    manifest = json.loads((bundle / "manifest.json").read_text())
    retained = {item["path"]: item["link"] for item in manifest["configuration"]
                if item["type"] == "symlink"}
    assert retained == expected
    with tarfile.open(bundle / "configuration.tar") as archive:
        assert {path: archive.getmember(path).linkname for path in expected} == expected
    digest = json.loads(result.stdout)["manifest_sha256"]
    shutil.rmtree(root)
    result = run_cli("verify", "--bundle", bundle, "--digest", digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "verified-files"


@pytest.mark.parametrize("cycle", ["self", "selected-chain", "unselected-chain"])
def test_capture_refuses_configuration_link_cycles_without_partial_bundle(tmp_path, cycle):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    active = root / "etc/active.conf"
    active.unlink()
    if cycle == "self":
        active.symlink_to("active.conf")
    elif cycle == "selected-chain":
        active.symlink_to("middle.conf")
        (root / "etc/middle.conf").symlink_to("/etc/active.conf")
    else:
        active.symlink_to("/usr/share/current")
        current = root / "usr/share/current"
        current.parent.mkdir(parents=True)
        current.symlink_to("../../etc/active.conf")
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env, timeout=5)

    assert_private_refusal(result, tmp_path)
    assert not bundle.exists()


@pytest.mark.parametrize("intermediate", ["selected", "unselected"])
@pytest.mark.parametrize("invalid_target", ["relative-escape", "physical-source-root"])
def test_capture_refuses_unsafe_targets_hidden_in_configuration_link_chains(tmp_path, intermediate,
                                                                          invalid_target):
    root, cache, env, inventory, request = capture_inputs(tmp_path)
    active = root / "etc/active.conf"
    active.unlink()
    outside = tmp_path / "outside-target"
    outside.write_bytes(b"synthetic outside target")
    if intermediate == "selected":
        active.symlink_to("middle.conf")
        middle = root / "etc/middle.conf"
        escape = "../../outside-target"
    else:
        active.symlink_to("/usr/share/middle.conf")
        middle = root / "usr/share/middle.conf"
        middle.parent.mkdir(parents=True)
        escape = "../../../outside-target"
    middle.symlink_to(escape if invalid_target == "relative-escape" else str(root / "etc/serving.conf"))
    bundle = tmp_path / "bundle"

    result = run_cli("capture", "--inventory", inventory, "--request", request,
                     "--output", bundle, env=env)

    assert_private_refusal(result, tmp_path)
    assert not bundle.exists()
    assert outside.read_bytes() == b"synthetic outside target"


@pytest.mark.parametrize("record_path", ["etc", "etc/serving.conf", "etc/active.conf"])
@pytest.mark.parametrize("mtime_ns,base_seconds,accepted", [
    (0, 0, True),
    (1700000000000000000, 1700000000, True),
    (1700000000000000000, 1700000001, False),
])
def test_verify_compares_integer_base_header_mtime_when_pax_mtime_is_absent(tmp_path, record_path,
                                                                         mtime_ns, base_seconds,
                                                                         accepted):
    bundle, digest = capture_with_exact_mtime(tmp_path, record_path, mtime_ns)
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0
    changed_digest = rebind_configuration_mtime(bundle, record_path, None, base_mtime=base_seconds)
    with tarfile.open(bundle / "configuration.tar") as archive:
        member = next(item for item in archive.getmembers() if item.name.rstrip("/") == record_path)
        assert "mtime" not in member.pax_headers
        assert type(member.mtime) is int
        assert member.mtime == base_seconds

    result = run_cli("verify", "--bundle", bundle, "--digest", changed_digest)

    if accepted:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["state"] == "verified-files"
    else:
        assert_private_refusal(result, tmp_path)


@pytest.mark.parametrize("record_path", ["etc", "etc/serving.conf", "etc/active.conf"])
@pytest.mark.parametrize("change,value,mtime_ns", [
    ("missing", None, 0),
    ("false", False, 0),
    ("true", True, 1),
    ("whole-number", 1700000000000000000.0, 1700000000000000000),
    ("fractional-number", 1.5, 1),
    ("text", "1700000000000000000", 1700000000000000000),
    ("null", None, 0),
    ("array", [0], 0),
    ("object", {"value": 0}, 0),
])
def test_verify_requires_integer_manifest_mtime_ns_without_coercion_or_defaults(tmp_path, record_path,
                                                                             change, value,
                                                                             mtime_ns):
    bundle, digest = capture_with_exact_mtime(tmp_path, record_path, mtime_ns)
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = next(item for item in manifest["configuration"] if item["path"] == record_path)
    if change == "missing":
        del record["mtime_ns"]
    else:
        record["mtime_ns"] = value
    manifest_path.write_text(json.dumps(manifest, allow_nan=False))
    changed_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    result = run_cli("verify", "--bundle", bundle, "--digest", changed_digest)

    assert_private_refusal(result, tmp_path)


@pytest.mark.parametrize("record_path", ["etc", "etc/serving.conf", "etc/active.conf"])
@pytest.mark.parametrize("pax_mtime", [
    "", "NaN", "inf", "-inf", "Infinity", "synthetic-secret",
    "1700000000.1234567891", "1700000000.1234567889999999999",
])
def test_verify_refuses_nonfinite_unusable_and_subnanosecond_pax_mtimes(tmp_path, record_path,
                                                                    pax_mtime):
    bundle, digest = capture_with_exact_mtime(tmp_path, record_path, 1700000000123456789)
    assert run_cli("verify", "--bundle", bundle, "--digest", digest).returncode == 0
    changed_digest = rebind_configuration_mtime(bundle, record_path, pax_mtime)

    result = run_cli("verify", "--bundle", bundle, "--digest", changed_digest)

    assert_private_refusal(result, tmp_path)

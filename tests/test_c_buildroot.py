import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools/c_buildroot.py"
SPEC = importlib.util.spec_from_file_location("c_buildroot", MODULE_PATH)
assert SPEC and SPEC.loader
cbr = importlib.util.module_from_spec(SPEC)
sys.modules["c_buildroot"] = cbr
SPEC.loader.exec_module(cbr)

needs_bsdtar = pytest.mark.skipif(shutil.which("bsdtar") is None, reason="bsdtar not installed")


# --- fakes -------------------------------------------------------------------


def desc(name, version, *, filename=None, sha256="", depends=(), provides=(), conflicts=(), isize=1024):
    blocks = [
        ("FILENAME", [filename or f"{name}-{version}-x86_64.pkg.tar.zst"]),
        ("NAME", [name]),
        ("VERSION", [version]),
        ("ISIZE", [str(isize)]),
        ("SHA256SUM", [sha256] if sha256 else []),
        ("DEPENDS", list(depends)),
        ("PROVIDES", list(provides)),
        ("CONFLICTS", list(conflicts)),
    ]
    return "\n\n".join(f"%{k}%\n" + "\n".join(v) for k, v in blocks if v) + "\n"


def write_db(path: Path, entries: list[str]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for text in entries:
            name = text.split("%NAME%\n", 1)[1].split("\n", 1)[0]
            version = text.split("%VERSION%\n", 1)[1].split("\n", 1)[0]
            data = text.encode()
            info = tarfile.TarInfo(f"{name}-{version}/desc")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def make_pkg(path: Path, name: str, version: str, files: dict[str, str]) -> Path:
    """Write a minimal package archive with a .PKGINFO and the given files."""
    with tarfile.open(path, "w:gz") as tf:
        pkginfo = f"pkgname = {name}\npkgver = {version}\narch = x86_64\n".encode()
        info = tarfile.TarInfo(".PKGINFO")
        info.size = len(pkginfo)
        tf.addfile(info, io.BytesIO(pkginfo))
        dirs = set()
        for rel in files:
            parts = rel.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        for d in sorted(dirs):
            info = tarfile.TarInfo(d)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            tf.addfile(info)
        for rel, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return path


def base_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "etc").mkdir(parents=True)
    (root / "etc/passwd").write_text("root:x:0:0::/root:/bin/bash\n")
    (root / "etc/group").write_text("root:x:0:\n")
    return root


# --- vercmp ------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,want",
    [
        ("1.0", "1.0", 0),
        ("1.0", "1.1", -1),
        ("1.10", "1.9", 1),
        ("1.0a", "1.0", -1),
        ("1.0", "1.0.1", -1),
        ("1:1.0", "2.0", 1),
        ("7.14.1-1", "7.13.0-3", 1),
        ("2.5.3-1.1", "2.5.3-1", 1),
        ("1.0rc1", "1.0", -1),
        ("20260526.0-2.1", "20260817.0-2.1", -1),
    ],
)
def test_vercmp_matches_libalpm(a, b, want):
    assert cbr.vercmp(a, b) == want
    if shutil.which("vercmp"):
        out = subprocess.run(["vercmp", a, b], capture_output=True, text=True, check=True).stdout
        assert int(out) == want


# --- resolve -----------------------------------------------------------------


def config(tmp_path, *, installed=None, forbidden_names=(), host_cache=None, pools=None):
    found = write_db(tmp_path / "found.db", [
        desc("rocm-core-gfx1151", "7.14.1-1", provides=["rocm-core=7.14.1"], sha256="aa"),
        desc("hip-runtime-amd-gfx1151", "7.14.1-1", depends=["rocm-core-gfx1151", "glibc"], sha256="bb"),
    ])
    wave = write_db(tmp_path / "wave.db", [
        desc("python-numpy-gfx1151", "2.5.3-1", provides=["python-numpy=2.5.3"], depends=["glibc"], sha256="cc"),
    ])
    user = write_db(tmp_path / "core.db", [
        desc("glibc", "2.44-1", sha256="dd"),
        desc("rocm-core", "7.13.0-1", sha256="ee"),
        desc("python-numpy", "2.4.0-1", depends=["glibc"], sha256="ff"),
        desc("cmake", "4.1-1", depends=["glibc>=2.40"], sha256="11"),
    ])
    repos = [
        ("found", cbr.read_db(found, "found")),
        ("wave", cbr.read_db(wave, "wave")),
        ("core", cbr.read_db(user, "core")),
    ]
    pool_dir = tmp_path / "pool"
    pool_dir.mkdir(exist_ok=True)
    for name in ("rocm-core-gfx1151-7.14.1-1", "hip-runtime-amd-gfx1151-7.14.1-1", "python-numpy-gfx1151-2.5.3-1"):
        (pool_dir / f"{name}-x86_64.pkg.tar.zst").touch()
    return cbr.ResolveConfig(
        repos=repos,
        foundation=["found", "wave"],
        pools=pools if pools is not None else {"found": pool_dir, "wave": pool_dir},
        host_cache=host_cache,
        installed=installed or {},
        forbidden_names=set(forbidden_names),
        forbidden_repos=["old-rocm"],
    )


def by_name(lock):
    return {p["name"]: p for p in lock["packages"]}


def test_foundation_provider_beats_same_named_userland_package(tmp_path):
    lock = cbr.resolve(["hip-runtime-amd-gfx1151", "rocm-core", "python-numpy"], config(tmp_path))
    pkgs = by_name(lock)
    assert "rocm-core" not in pkgs, "the foundation provides rocm-core, so the userland one must not enter"
    assert pkgs["rocm-core-gfx1151"]["source"] == "found"
    assert pkgs["python-numpy-gfx1151"]["source"] == "wave"
    assert "python-numpy" not in pkgs


def test_host_version_is_taken_from_host_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "glibc-2.43-2-x86_64.pkg.tar.zst").touch()
    (cache / "glibc-2.43-2-x86_64.pkg.tar.zst.sig").touch()
    (cache / "glibc-extra-2.43-2-x86_64.pkg.tar.zst").touch()
    lock = cbr.resolve(["cmake"], config(tmp_path, installed={"glibc": "2.43-2"}, host_cache=cache))
    glibc = by_name(lock)["glibc"]
    assert glibc["version"] == "2.43-2"
    assert glibc["source"] == "host-cache(core)"
    assert glibc["path"].endswith("glibc-2.43-2-x86_64.pkg.tar.zst")
    assert glibc["sha256_db"] == "", "a host version that differs from the DB has no DB checksum"
    assert {p["kind"] for p in lock["problems"]} == {"missing-file"}  # cmake has no file anywhere


def test_host_version_is_not_used_when_it_breaks_a_version_constraint(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "glibc-2.43-2-x86_64.pkg.tar.zst").touch()
    (cache / "glibc-2.44-1-x86_64.pkg.tar.zst").touch()
    cfg = config(tmp_path, installed={"glibc": "2.43-2"}, host_cache=cache)
    glibc = by_name(cbr.resolve(["cmake", "glibc>=2.44"], cfg))["glibc"]
    assert glibc["version"] == "2.44-1", "the installed 2.43-2 does not meet glibc>=2.44"
    assert glibc["source"] == "core"
    assert glibc["sha256_db"] == "dd"


def test_exact_pins_from_host_locked_packages_do_not_evict_host_versions(tmp_path):
    # The DB's systemd 2 pins systemd-libs=2, but the host runs systemd 1 with
    # systemd-libs 1. Both come from the host cache as a consistent pair.
    db = write_db(tmp_path / "core.db", [
        desc("systemd", "2-1", depends=["systemd-libs=2"], sha256="s2"),
        desc("systemd-libs", "2-1", sha256="l2"),
    ])
    cache = tmp_path / "cache"
    cache.mkdir()
    for name in ("systemd-1-1", "systemd-libs-1-1"):
        (cache / f"{name}-x86_64.pkg.tar.zst").touch()
    cfg = cbr.ResolveConfig(repos=[("core", cbr.read_db(db, "core"))], foundation=[], host_cache=cache,
                            installed={"systemd": "1-1", "systemd-libs": "1-1"})
    pkgs = by_name(cbr.resolve(["systemd"], cfg))
    assert pkgs["systemd"]["version"] == "1-1"
    assert pkgs["systemd-libs"]["version"] == "1-1"


def test_forbidden_repo_names_never_come_from_host_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "glibc-2.43-2-x86_64.pkg.tar.zst").touch()
    (cache / "glibc-2.44-1-x86_64.pkg.tar.zst").touch()
    cfg = config(tmp_path, installed={"glibc": "2.43-2"}, host_cache=cache, forbidden_names={"glibc"})
    glibc = by_name(cbr.resolve(["glibc"], cfg))["glibc"]
    assert glibc["version"] == "2.44-1"
    assert glibc["source"] == "core"
    assert glibc["sha256_db"] == "dd"


def test_forbidden_repo_cannot_be_a_sync_db(tmp_path):
    cfg = config(tmp_path)
    cfg.repos.append(("old-rocm", {}))
    with pytest.raises(cbr.BuildRootError, match="forbidden repo"):
        cbr.resolve(["glibc"], cfg)


def test_unresolved_and_missing_files_are_problems(tmp_path):
    lock = cbr.resolve(["does-not-exist", "glibc"], config(tmp_path))
    kinds = {(p["kind"], p["package"]) for p in lock["problems"]}
    assert ("unresolved", "does-not-exist") in kinds
    assert ("missing-file", "glibc") in kinds


def test_extra_cache_supplies_fetched_files(tmp_path):
    cfg = config(tmp_path)
    extra = tmp_path / "fetched"
    extra.mkdir()
    (extra / "glibc-2.44-1-x86_64.pkg.tar.zst").touch()
    cfg.extra_caches = [extra]
    lock = cbr.resolve(["glibc"], cfg)
    assert lock["problems"] == []
    assert by_name(lock)["glibc"]["path"] == str(extra / "glibc-2.44-1-x86_64.pkg.tar.zst")


# --- fetch -------------------------------------------------------------------


def missing_lock(sha):
    return {
        "packages": [{"name": "glibc", "version": "2.44-1", "repo": "core", "source": "core", "path": None,
                      "filename": "glibc-2.44-1-x86_64.pkg.tar.zst", "sha256_db": sha, "isize": 1}],
        "problems": [{"kind": "missing-file", "package": "glibc", "detail": "x"}],
    }


def test_fetch_falls_back_to_next_mirror_on_checksum_mismatch(tmp_path):
    import hashlib

    good = b"good package"
    lock = missing_lock(hashlib.sha256(good).hexdigest())
    calls = []

    def downloader(url, dest):
        calls.append(url)
        dest.write_bytes(b"tampered" if "bad" in url else good)

    fetched = cbr.fetch_missing(lock, tmp_path / "dl", {}, downloader=downloader,
                                servers_for=lambda repo: ["https://bad.example/core", "https://good.example/core"])
    assert fetched == ["glibc"]
    assert calls == ["https://bad.example/core/glibc-2.44-1-x86_64.pkg.tar.zst",
                     "https://good.example/core/glibc-2.44-1-x86_64.pkg.tar.zst"]
    assert lock["problems"] == []
    assert Path(lock["packages"][0]["path"]).read_bytes() == good


def test_fetch_refuses_unverifiable_download(tmp_path):
    with pytest.raises(cbr.BuildRootError, match="unverified"):
        cbr.fetch_missing(missing_lock(""), tmp_path, {}, downloader=lambda u, d: None,
                          servers_for=lambda repo: ["https://x.example"])


# --- populate / add / verify -------------------------------------------------


@needs_bsdtar
def test_populate_add_and_verify(tmp_path):
    rocm = make_pkg(tmp_path / "rocm-core-gfx1151-7.14.1-1-x86_64.pkg.tar.gz", "rocm-core-gfx1151", "7.14.1-1",
                    {"opt/rocm/.info/version": "7.14.1\n", "opt/rocm/lib/libfoo.so": "foo"})
    glibc = make_pkg(tmp_path / "glibc-2.44-1-x86_64.pkg.tar.gz", "glibc", "2.44-1",
                     {"etc/passwd": "root:x:0:0::/root:/bin/bash\n", "etc/group": "root:x:0:\n",
                      "usr/lib/libc.so.6": "libc"})
    lock = {"packages": [
        {"name": "glibc", "version": "2.44-1", "source": "host-cache(core)", "path": str(glibc), "sha256_db": ""},
        {"name": "rocm-core-gfx1151", "version": "7.14.1-1", "source": "found", "path": str(rocm),
         "sha256_db": cbr.sha256_file(rocm)},
    ], "problems": []}
    root = tmp_path / "root"
    cbr.populate(lock, root, uid=1234, gid=1234, post_install=False)

    assert (root / "opt/rocm/lib/libfoo.so").read_text() == "foo"
    assert "builder:x:1234:1234::/build:/bin/bash" in (root / "etc/passwd").read_text()
    # enter binds these into a read-only root, so populate must create them.
    assert all((root / d).is_dir() for d in ("build", "pkgdest", "srcdest", "ccache"))
    manifest = cbr.load_manifest(root)
    assert [e["name"] for e in manifest] == ["glibc", "rocm-core-gfx1151"]
    assert cbr.read_file_list(root, "rocm-core-gfx1151") == ["opt/rocm/.info/version", "opt/rocm/lib/libfoo.so"]
    with pytest.raises(cbr.BuildRootError, match="already populated"):
        cbr.populate(lock, root, post_install=False)

    ok = cbr.verify_root(root, foundation=["found", "wave"], forbidden_repos=["old-rocm"], expect_rocm="7.14.1")
    assert ok["violations"] == []

    # A W2A output replaces its previous version and drops files it no longer ships.
    v1 = make_pkg(tmp_path / "python-x-1-1.pkg.tar.gz", "python-x", "1-1",
                  {"usr/lib/x/old.py": "old", "usr/lib/x/keep.py": "1"})
    v2 = make_pkg(tmp_path / "python-x-2-1.pkg.tar.gz", "python-x", "2-1", {"usr/lib/x/keep.py": "2"})
    cbr.add_packages(root, [v1], "wave", post_install=False)
    cbr.add_packages(root, [v2], "wave", post_install=False)
    assert not (root / "usr/lib/x/old.py").exists()
    assert (root / "usr/lib/x/keep.py").read_text() == "2"
    assert {e["name"]: e["version"] for e in cbr.load_manifest(root)}["python-x"] == "2-1"

    # A package may not silently overwrite another package's files.
    clash = make_pkg(tmp_path / "evil-1-1.pkg.tar.gz", "evil", "1-1", {"opt/rocm/lib/libfoo.so": "evil"})
    with pytest.raises(cbr.BuildRootError, match="already owned by rocm-core-gfx1151"):
        cbr.add_packages(root, [clash], "wave", post_install=False)

    # Anything under /opt/rocm that no foundation package owns is a violation.
    (root / "opt/rocm/lib/stray.so").write_text("stray")
    bad = cbr.verify_root(root, foundation=["found"], forbidden_repos=["old-rocm"], expect_rocm="7.13.0")
    assert any("unowned file under /opt: /opt/rocm/lib/stray.so" in v for v in bad["violations"])
    assert any("expected '7.13.0'" in v for v in bad["violations"])


@needs_bsdtar
def test_populate_rejects_checksum_mismatch(tmp_path):
    pkg = make_pkg(tmp_path / "a-1-1.pkg.tar.gz", "a", "1-1", {"usr/share/a": "a"})
    lock = {"packages": [{"name": "a", "version": "1-1", "source": "core", "path": str(pkg), "sha256_db": "00"}],
            "problems": []}
    with pytest.raises(cbr.BuildRootError, match="sha256 mismatch"):
        cbr.populate(lock, base_root(tmp_path), post_install=False)


def test_populate_refuses_lock_with_problems(tmp_path):
    lock = {"packages": [], "problems": [{"kind": "missing-file", "package": "a", "detail": ""}]}
    with pytest.raises(cbr.BuildRootError, match="lock has problems"):
        cbr.populate(lock, tmp_path / "root", post_install=False)


# --- linkage -----------------------------------------------------------------


def test_resolve_in_root_follows_absolute_links_inside_the_root(tmp_path):
    root = tmp_path / "root"
    (root / "usr/lib").mkdir(parents=True)
    (root / "usr/lib/ld-linux-x86-64.so.2").write_text("")
    (root / "usr/lib64").symlink_to("lib")
    (root / "lib64").symlink_to("/usr/lib")
    assert cbr.resolve_in_root(root, "/usr/lib64/ld-linux-x86-64.so.2") == "/usr/lib/ld-linux-x86-64.so.2"
    assert cbr.resolve_in_root(root, "/lib64/ld-linux-x86-64.so.2") == "/usr/lib/ld-linux-x86-64.so.2"


LDD = """\
\tlinux-vdso.so.1 (0x00007f0d375c8000)
\tlibamdhip64.so.7 => /opt/rocm/lib/libamdhip64.so.7 (0x00007f0d35a00000)
\tlibsaxpy.so => /build/cmakelib/prefix/bin/../lib/libsaxpy.so (0x00007f847f5be000)
\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f0d35200000)
\tlibmagma.so => not found
\t/lib64/ld-linux-x86-64.so.2 => /usr/lib64/ld-linux-x86-64.so.2 (0x00007f0d375ca000)
"""


def test_ldd_paths_parse_resolved_and_missing_libraries():
    assert cbr.ldd_paths(LDD) == [
        "/opt/rocm/lib/libamdhip64.so.7",
        "/build/cmakelib/prefix/bin/../lib/libsaxpy.so",
        "/usr/lib/libc.so.6",
        "libmagma.so not found",
        "/usr/lib64/ld-linux-x86-64.so.2",
    ]


def test_check_linkage_maps_every_library_to_an_allowed_owner(tmp_path):
    root = tmp_path / "root"
    (root / cbr.STATE_DIR).mkdir(parents=True)
    (root / "usr/lib").mkdir(parents=True)
    (root / "usr/lib64").symlink_to("lib")
    manifest = [
        cbr.record_package(root, "glibc", "2.44-1", "host-cache(core)", Path("glibc.pkg"), "x",
                           ["usr/lib/libc.so.6", "usr/lib/ld-linux-x86-64.so.2"]),
        cbr.record_package(root, "hip-runtime-amd-gfx1151", "7.14.1-1", "found", Path("hip.pkg"), "y",
                           ["opt/rocm/lib/libamdhip64.so.7"]),
    ]
    cbr.save_manifest(root, manifest)
    rows, violations = cbr.check_linkage(root, cbr.ldd_paths(LDD), foundation=["found"], forbidden_repos=["old"])
    owners = {r["path"]: r["owner"] for r in rows}
    assert owners["/opt/rocm/lib/libamdhip64.so.7"] == "hip-runtime-amd-gfx1151"
    assert owners["/usr/lib64/ld-linux-x86-64.so.2"] == "glibc"
    assert "/build/cmakelib/prefix/bin/../lib/libsaxpy.so" not in owners
    assert violations == ["unresolved library: libmagma.so not found"]

    cbr.save_manifest(root, [dict(manifest[0]), dict(manifest[1], source="host-cache(old)")])
    _, violations = cbr.check_linkage(root, ["/opt/rocm/lib/libamdhip64.so.7"], foundation=["found"],
                                      forbidden_repos=["old"])
    assert violations == ["/opt/rocm/lib/libamdhip64.so.7: owned by forbidden source host-cache(old)"]


# --- enter / publish / makepkg.conf ------------------------------------------


def test_bwrap_args_never_expose_host_rocm_or_usr(tmp_path):
    opts = cbr.EnterOptions(work=tmp_path / "w", gpu=True, net=True, pkgdest=tmp_path / "out",
                            ccache=tmp_path / "cc", makepkg_conf=cbr.DEFAULT_MAKEPKG_CONF)
    args = cbr.bwrap_args(tmp_path / "root", opts)
    binds = [(args[i], args[i + 1], args[i + 2]) for i, a in enumerate(args)
             if a in ("--bind", "--ro-bind", "--dev-bind")]
    sources = {b[1] for b in binds}
    assert ("--ro-bind", str(tmp_path / "root"), "/") in binds
    assert not any(s.startswith(("/opt", "/usr", "/home")) and "root" not in s for s in sources if s != str(tmp_path / "root"))
    assert "/opt/rocm" not in sources and "/usr" not in sources
    assert ("--ro-bind", str(cbr.DEFAULT_MAKEPKG_CONF.resolve()), "/etc/makepkg.conf") in binds
    assert "--clearenv" in args and "--unshare-all" in args
    env = {args[i + 1]: args[i + 2] for i, a in enumerate(args) if a == "--setenv"}
    assert env["PKGDEST"] == "/pkgdest" and env["CCACHE_DIR"] == "/ccache"
    assert "LD_LIBRARY_PATH" not in env and "ROCM_PATH" not in env
    assert args[-1] == "--"


def test_enter_flags_stay_out_of_the_command():
    own, command = cbr.split_command(["enter", "root", "--gpu", "--", "makepkg", "-Cf", "--nodeps"])
    assert own == ["enter", "root", "--gpu"]
    assert command == ["makepkg", "-Cf", "--nodeps"]
    a = cbr.build_parser().parse_args(own)
    assert a.gpu and a.command == []


def test_bwrap_rw_only_when_asked(tmp_path):
    assert cbr.bwrap_args(tmp_path, cbr.EnterOptions())[1] == "--ro-bind"
    assert cbr.bwrap_args(tmp_path, cbr.EnterOptions(rw=True))[1] == "--bind"


def test_publish_refuses_host_repos_and_runs_repo_add(tmp_path):
    served = tmp_path / "srv"
    host = ({"strix-halo-gfx1151"}, {served})
    with pytest.raises(cbr.BuildRootError, match="host's pacman uses"):
        cbr.publish(tmp_path / "r", "strix-halo-gfx1151", [], host_repos=host)
    with pytest.raises(cbr.BuildRootError, match="served from"):
        cbr.publish(served / "x86_64", "ashp-w2a", [], host_repos=host)

    db = cbr.publish(tmp_path / "r", "ashp-w2a", [], host_repos=host)
    assert db.exists() and (tmp_path / "r/ashp-w2a.db").is_symlink()
    assert cbr.read_db(db, "ashp-w2a") == {}

    pkg = tmp_path / "a-1-1-x86_64.pkg.tar.zst"
    pkg.write_text("a")
    calls = []
    cbr.publish(tmp_path / "r", "ashp-w2a", [pkg], host_repos=host, runner=lambda cmd, check: calls.append(cmd))
    assert (tmp_path / "r" / pkg.name).exists()
    assert calls == [["repo-add", "-q", "-R", str(db), str(tmp_path / "r" / pkg.name)]]


def test_pinned_makepkg_conf_values():
    script = f'source "{cbr.DEFAULT_MAKEPKG_CONF}"; ' \
             'printf "%s\\n" "$MAKEFLAGS" "$NINJAFLAGS" "$MAX_JOBS" "$CMAKE_BUILD_PARALLEL_LEVEL" ' \
             '"${INTEGRITY_CHECK[*]}" "${BUILDENV[*]}" "$PKGEXT" "${PKGDEST-unset}"'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.splitlines()
    assert out[:4] == ["-j14", "-j14", "14", "14"]
    assert out[4] == "b2"
    assert "ccache" in out[5].split() and "!distcc" in out[5].split()
    assert out[6] == ".pkg.tar.zst"
    assert out[7] == "unset", "PKGDEST comes from `enter --pkgdest`, not the pinned conf"


def test_repo_files_hold_no_private_paths():
    for path in [MODULE_PATH, *sorted((REPO_ROOT / "tools/buildroot").rglob("*"))]:
        if path.is_file():
            text = path.read_text()
            for needle in ("/home/",):
                assert needle not in text, f"{path} mentions {needle}"


@needs_bsdtar
def test_remove_drops_only_files_no_other_package_owns(tmp_path):
    root = base_root(tmp_path)
    (root / cbr.STATE_DIR).mkdir()
    cbr.save_manifest(root, [])
    a = make_pkg(tmp_path / "python-numpy-2.5.3-1.pkg.tar.gz", "python-numpy", "2.5.3-1",
                 {"usr/lib/python3.14/site-packages/numpy/__init__.py": "arch"})
    b = make_pkg(tmp_path / "other-1-1.pkg.tar.gz", "other", "1-1", {"usr/share/other.txt": "o"})
    cbr.add_packages(root, [a, b], "core", post_install=False)
    cbr.remove_packages(root, ["python-numpy"], post_install=False)
    assert not (root / "usr/lib/python3.14/site-packages/numpy/__init__.py").exists()
    assert (root / "usr/share/other.txt").exists()
    assert [e["name"] for e in cbr.load_manifest(root)] == ["other"]
    with pytest.raises(cbr.BuildRootError, match="not in the root"):
        cbr.remove_packages(root, ["python-numpy"], post_install=False)

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


def make_pkg(path: Path, name: str, version: str, files: dict[str, str], provides=(), depends=()) -> Path:
    """Write a minimal package archive with a .PKGINFO and the given files."""
    with tarfile.open(path, "w:gz") as tf:
        pkginfo = f"pkgname = {name}\npkgver = {version}\narch = x86_64\n"
        pkginfo += "".join(f"provides = {p}\n" for p in provides)
        pkginfo = (pkginfo + "".join(f"depend = {d}\n" for d in depends)).encode()
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


@needs_bsdtar
def test_host_version_is_taken_from_host_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    make_pkg(cache / "glibc-2.43-2-x86_64.pkg.tar.zst", "glibc", "2.43-2", {})
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


@needs_bsdtar
def test_exact_pins_from_host_locked_packages_do_not_evict_host_versions(tmp_path):
    # The DB's systemd 2 pins systemd-libs=2, but the host runs systemd 1 with
    # systemd-libs 1. Both come from the host cache as a consistent pair.
    db = write_db(tmp_path / "core.db", [
        desc("systemd", "2-1", depends=["systemd-libs=2"], sha256="s2"),
        desc("systemd-libs", "2-1", sha256="l2"),
    ])
    cache = tmp_path / "cache"
    cache.mkdir()
    make_pkg(cache / "systemd-1-1-x86_64.pkg.tar.zst", "systemd", "1-1", {}, depends=["systemd-libs=1"])
    make_pkg(cache / "systemd-libs-1-1-x86_64.pkg.tar.zst", "systemd-libs", "1-1", {})
    cfg = cbr.ResolveConfig(repos=[("core", cbr.read_db(db, "core"))], foundation=[], host_cache=cache,
                            installed={"systemd": "1-1", "systemd-libs": "1-1"})
    pkgs = by_name(cbr.resolve(["systemd"], cfg))
    assert pkgs["systemd"]["version"] == "1-1"
    assert pkgs["systemd-libs"]["version"] == "1-1"


def soname_config(tmp_path, host_version, host_provides):
    # A foundation package pins a soname that only the newer sync protobuf
    # provides, as migraphx-gfx1151 pins libprotobuf.so=36.1.0-64 (#108).
    found = write_db(tmp_path / "found.db", [
        desc("migraphx-gfx1151", "7.14.1-1", depends=["libprotobuf.so=36.1.0-64"], sha256="mg"),
    ])
    core = write_db(tmp_path / "core.db", [
        desc("protobuf", "36.1-2", provides=["libprotobuf.so=36.1.0-64"], sha256="pb"),
    ])
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "migraphx-gfx1151-7.14.1-1-x86_64.pkg.tar.zst").touch()
    cache = tmp_path / "cache"
    cache.mkdir()
    make_pkg(cache / f"protobuf-{host_version}-x86_64.pkg.tar.zst", "protobuf", host_version, {},
             provides=host_provides)
    (cache / "protobuf-36.1-2-x86_64.pkg.tar.zst").touch()
    return cbr.ResolveConfig(
        repos=[("found", cbr.read_db(found, "found")), ("core", cbr.read_db(core, "core"))],
        foundation=["found"], pools={"found": pool}, host_cache=cache,
        installed={"protobuf": host_version},
    )


@needs_bsdtar
def test_host_version_is_not_used_when_its_own_provides_miss_a_soname_pin(tmp_path):
    cfg = soname_config(tmp_path, "35.1-1", ["libprotobuf.so=35.1.0-64"])
    lock = cbr.resolve(["migraphx-gfx1151"], cfg)
    protobuf = by_name(lock)["protobuf"]
    assert protobuf["version"] == "36.1-2", "host protobuf 35.1 provides libprotobuf.so=35.1.0-64 only"
    assert protobuf["source"] == "core"
    assert protobuf["path"].endswith("protobuf-36.1-2-x86_64.pkg.tar.zst")
    assert protobuf["sha256_db"] == "pb"
    assert lock["problems"] == []


@needs_bsdtar
def test_host_version_is_used_when_its_own_provides_meet_a_soname_pin(tmp_path):
    cfg = soname_config(tmp_path, "36.1-1", ["libprotobuf.so=36.1.0-64"])
    protobuf = by_name(cbr.resolve(["migraphx-gfx1151"], cfg))["protobuf"]
    assert protobuf["version"] == "36.1-1"
    assert protobuf["source"] == "host-cache(core)"
    assert protobuf["path"].endswith("protobuf-36.1-1-x86_64.pkg.tar.zst")


def test_host_version_without_readable_provides_is_not_used_for_a_soname_pin(tmp_path):
    cfg = soname_config(tmp_path, "36.1-1", ["libprotobuf.so=36.1.0-64"])
    (tmp_path / "cache" / "protobuf-36.1-1-x86_64.pkg.tar.zst").write_bytes(b"")
    protobuf = by_name(cbr.resolve(["migraphx-gfx1151"], cfg))["protobuf"]
    assert protobuf["version"] == "36.1-2", "unreadable host metadata cannot prove the soname"
    assert protobuf["source"] == "core"


# The W2A protobuf/Abseil move (#108, #118): the lock moves protobuf and Abseil
# off the host versions, so every host package whose dependency cone includes
# them must come at its sync-DB version instead.
CONE_HOST = {
    # name: (host version, host .PKGINFO depends, host provides)
    "protobuf": ("35.1-1", ["abseil-cpp"], ["libprotobuf.so=35.1.0-64"]),
    "python-protobuf": ("35.1-1", ["protobuf=35.1"], []),
    "abseil-cpp": ("20260526.0-1", [], []),
    "re2": ("2:2025.11.05-5", ["abseil-cpp"], []),
    "python-grpcio": ("1.83.0-1", ["re2"], []),
    "python-grpcio-tools": ("1.83.0-1", ["python-grpcio"], []),
    "zlib": ("1.3-1", [], []),
    "libpng": ("1.6-1", ["zlib"], []),
}
CONE_DB = {
    "protobuf": ("36.1-1", ["abseil-cpp"], ["libprotobuf.so=36.1.0-64"]),
    "python-protobuf": ("36.1-1", ["protobuf=36.1"], []),
    "abseil-cpp": ("20260817.0-2", [], []),
    "re2": ("2:2025.11.05-6", ["abseil-cpp"], []),
    "python-grpcio": ("1.84.0-1", ["re2", "abseil-cpp"], []),
    "python-grpcio-tools": ("1.84.0-1", ["python-grpcio", "protobuf"], []),
    "zlib": ("1.3.1-1", [], []),
    "libpng": ("1.7-1", ["zlib"], []),
}


def cone_lock(tmp_path, *, unreadable=()):
    db = write_db(tmp_path / "core.db", [
        desc(n, v, depends=d, provides=pr, sha256=f"sha-{n}") for n, (v, d, pr) in CONE_DB.items()
    ])
    cache = tmp_path / "cache"
    cache.mkdir()
    for name, (version, depends, provides) in CONE_HOST.items():
        archive = cache / f"{name}-{version}-x86_64.pkg.tar.zst"
        if name in unreadable:
            archive.write_bytes(b"")
        else:
            make_pkg(archive, name, version, {}, provides=provides, depends=depends)
    for name, (version, _, _) in CONE_DB.items():
        (cache / f"{name}-{version}-x86_64.pkg.tar.zst").touch()
    cfg = cbr.ResolveConfig(repos=[("core", cbr.read_db(db, "core"))], foundation=[], host_cache=cache,
                            installed={n: v for n, (v, _, _) in CONE_HOST.items()})
    targets = ["protobuf>=36.1", "abseil-cpp>=20260817.0", "python-protobuf", "python-grpcio-tools", "libpng"]
    lock = cbr.resolve(targets, cfg)
    assert lock["problems"] == []
    return by_name(lock)


def assert_sync(entry, version):
    assert (entry["version"], entry["source"]) == (version, "core")
    assert entry["path"].endswith(f"-{version}-x86_64.pkg.tar.zst")
    assert entry["sha256_db"] == f"sha-{entry['name']}"


@needs_bsdtar
def test_host_package_with_a_versioned_depend_on_a_moved_package_falls_back(tmp_path):
    # Host python-protobuf 35.1 declares depend = protobuf=35.1; the lock has protobuf 36.1.
    pkgs = cone_lock(tmp_path)
    assert_sync(pkgs["protobuf"], "36.1-1")
    assert_sync(pkgs["python-protobuf"], "36.1-1")


@needs_bsdtar
def test_host_package_with_an_unversioned_depend_on_a_moved_package_falls_back(tmp_path):
    # Host re2 links the host Abseil 20260526, which the lock replaces with 20260817.
    pkgs = cone_lock(tmp_path)
    assert_sync(pkgs["abseil-cpp"], "20260817.0-2")
    assert_sync(pkgs["re2"], "2:2025.11.05-6")


@needs_bsdtar
def test_fallbacks_cascade_through_host_packages(tmp_path):
    # grpcio depends only on re2 and grpcio-tools only on grpcio in the host
    # files, so each moves only because the one below it moved.
    pkgs = cone_lock(tmp_path)
    assert_sync(pkgs["python-grpcio"], "1.84.0-1")
    assert_sync(pkgs["python-grpcio-tools"], "1.84.0-1")


@needs_bsdtar
def test_host_package_with_an_unchanged_cone_is_still_substituted(tmp_path):
    pkgs = cone_lock(tmp_path)
    assert (pkgs["zlib"]["version"], pkgs["zlib"]["source"]) == ("1.3-1", "host-cache(core)")
    assert (pkgs["libpng"]["version"], pkgs["libpng"]["source"]) == ("1.6-1", "host-cache(core)")
    assert pkgs["libpng"]["path"].endswith("libpng-1.6-1-x86_64.pkg.tar.zst")


@needs_bsdtar
def test_host_package_with_unreadable_metadata_is_not_substituted(tmp_path):
    pkgs = cone_lock(tmp_path, unreadable={"zlib"})
    assert_sync(pkgs["zlib"], "1.3.1-1")
    assert_sync(pkgs["libpng"], "1.7-1"), "libpng's zlib moved with it"


def test_host_package_at_the_db_version_uses_the_db_metadata(tmp_path):
    # The file is the DB's own, checked by sha256 at populate, so its DB depends stand.
    db = write_db(tmp_path / "core.db", [desc("zlib", "1.3-1", sha256="z"),
                                         desc("libpng", "1.6-1", depends=["zlib"], sha256="p")])
    cache = tmp_path / "cache"
    cache.mkdir()
    for name in ("zlib-1.3-1", "libpng-1.6-1"):
        (cache / f"{name}-x86_64.pkg.tar.zst").touch()
    cfg = cbr.ResolveConfig(repos=[("core", cbr.read_db(db, "core"))], foundation=[], host_cache=cache,
                            installed={"zlib": "1.3-1", "libpng": "1.6-1"})
    pkgs = by_name(cbr.resolve(["libpng"], cfg))
    assert pkgs["libpng"]["source"] == "host-cache(core)" and pkgs["libpng"]["sha256_db"] == "p"


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


# --- root-wide ELF NEEDED check ----------------------------------------------


def make_elf(path: Path, needed=(), runpath=None, rpath=None, machine=62) -> Path:
    """Write a minimal little-endian ELF64 shared object with a dynamic section."""
    import struct

    strtab = b"\0"
    offsets = {}
    for s in [*needed, *(x for x in (runpath, rpath) if x)]:
        offsets[s] = len(strtab)
        strtab += s.encode() + b"\0"
    base, str_off = 0x400000, 64 + 2 * 56
    dyn_off = (str_off + len(strtab) + 7) & ~7
    dyn = [(1, offsets[n]) for n in needed]
    if runpath:
        dyn.append((29, offsets[runpath]))
    if rpath:
        dyn.append((15, offsets[rpath]))
    dyn += [(5, base + str_off), (10, len(strtab)), (0, 0)]
    dyn_bytes = b"".join(struct.pack("<qQ", t, v) for t, v in dyn)
    size = dyn_off + len(dyn_bytes)
    ident = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header = ident + struct.pack("<HHIQQQIHHHHHH", 3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 64, 0, 0)
    load = struct.pack("<IIQQQQQQ", 1, 5, 0, base, base, size, size, 0x1000)
    dynamic = struct.pack("<IIQQQQQQ", 2, 6, dyn_off, base + dyn_off, base + dyn_off,
                          len(dyn_bytes), len(dyn_bytes), 8)
    body = header + load + dynamic + strtab
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body + bytes(dyn_off - len(body)) + dyn_bytes)
    return path


def write_ld_cache(path: Path, entries: dict[str, str]) -> Path:
    """Write a glibc 'ld.so.cache1.1' file mapping sonames to paths."""
    import struct

    header_size, entry_size = 48, 24
    strings = b""
    rows = []
    base = header_size + entry_size * len(entries)
    for name, target in entries.items():
        key = base + len(strings)
        strings += name.encode() + b"\0"
        value = base + len(strings)
        strings += target.encode() + b"\0"
        rows.append(struct.pack("<iIIIQ", 0x0303, key, value, 0, 0))
    header = b"glibc-ld.so.cache1.1" + struct.pack("<IIB3xI12x", len(entries), len(strings), 2, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"".join(rows) + strings)
    return path


def needed_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / cbr.STATE_DIR).mkdir(parents=True)
    site = "usr/lib/python3.14/site-packages"
    make_elf(root / "usr/bin/app", needed=["libgood.so.1", "libmissing.so.9"])
    make_elf(root / "usr/lib/libgood.so.1")
    (root / "usr/lib/libgood.so").symlink_to("libgood.so.1")
    make_elf(root / site / "pkg/_ext.so", needed=["libbundled.so.2", "libgood.so.1"],
             runpath="$ORIGIN/../pkg.libs")
    make_elf(root / site / "pkg.libs/libbundled.so.2")
    (root / site / "pkg/__init__.py").write_text("")
    make_elf(root / "opt/rocm/lib/libcached.so.3")
    make_elf(root / "opt/rocm/bin/tool", needed=["libcached.so.3"])
    make_elf(root / "opt/rocm/lib/code.hsaco", needed=["libnothing.so"], machine=224)  # an AMDGPU object
    write_ld_cache(root / "etc/ld.so.cache", {"libcached.so.3": "/opt/rocm/lib/libcached.so.3"})
    manifest = [
        cbr.record_package(root, "app", "1-1", "core", Path("app.pkg"), "a", ["usr/bin/app"]),
        cbr.record_package(root, "good", "1-1", "core", Path("good.pkg"), "g",
                           ["usr/lib/libgood.so.1", "usr/lib/libgood.so"]),
        cbr.record_package(root, "python-pkg", "1-1", "core", Path("pkg.pkg"), "p",
                           [f"{site}/pkg/_ext.so", f"{site}/pkg/__init__.py", f"{site}/pkg.libs/libbundled.so.2"]),
        cbr.record_package(root, "rocm-thing", "1-1", "found", Path("r.pkg"), "r",
                           ["opt/rocm/lib/libcached.so.3", "opt/rocm/bin/tool", "opt/rocm/lib/code.hsaco"]),
    ]
    cbr.save_manifest(root, manifest)
    return root


def test_verify_reports_unresolved_needed_entries_by_owning_package(tmp_path):
    report = cbr.verify_root(needed_root(tmp_path), foundation=["found"], forbidden_repos=[], expect_rocm=None)
    # _ext.so resolves libbundled.so.2 through $ORIGIN, tool resolves through
    # the root's ld.so.cache, and libgood.so.1 through the default /usr/lib.
    assert report["unresolved_needed"] == {"app": ["/usr/bin/app: libmissing.so.9"]}
    assert report["elf_files_checked"] == 6
    assert [v for v in report["violations"] if "NEEDED" in v] == [
        "unresolved NEEDED in app: /usr/bin/app: libmissing.so.9"]


def test_origin_runpath_is_relative_to_the_object_not_the_host(tmp_path):
    root = needed_root(tmp_path)
    (root / "usr/lib/python3.14/site-packages/pkg.libs/libbundled.so.2").unlink()
    report = cbr.verify_root(root, foundation=["found"], forbidden_repos=[], expect_rocm=None)
    assert report["unresolved_needed"] == {
        "app": ["/usr/bin/app: libmissing.so.9"],
        "python-pkg": ["/usr/lib/python3.14/site-packages/pkg/_ext.so: libbundled.so.2"],
    }


@pytest.mark.skipif(not Path("/etc/ld.so.cache").exists() or shutil.which("ldconfig") is None,
                    reason="no host ld.so.cache")
def test_ld_cache_parser_agrees_with_ldconfig():
    out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, check=True).stdout
    want = {(line.split(" (", 1)[0].strip(), line.rsplit(" => ", 1)[1].strip())
            for line in out.splitlines()[1:] if " => " in line}
    got = {(name, path) for name, paths in cbr.read_ld_cache(Path("/etc/ld.so.cache")).items() for path in paths}
    assert got == want


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
    def run(**env):
        return subprocess.run(["bash", "-c", script], env={"PATH": "/usr/bin:/bin", **env},
                              capture_output=True, text=True, check=True).stdout.splitlines()

    # The default fits builds.slice; `enter --setenv ASHP_BUILD_JOBS=N` overrides it.
    assert run(ASHP_BUILD_JOBS="8")[:4] == ["-j8", "-j8", "8", "8"]
    out = run()
    assert out[:4] == ["-j6", "-j6", "6", "6"]
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


def _systemctl(stdout: str, returncode: int = 0):
    def runner(argv, **kwargs):
        assert argv[:4] == ["systemctl", "--user", "show", "builds.slice"]
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")
    return runner


CAPPED = _systemctl("LoadState=loaded\nMemoryMax=34359738368\n")
OUTSIDE = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-x.scope"
INSIDE = "/user.slice/user-1000.slice/user@1000.service/builds.slice/run-r1.scope"


def test_enter_starts_a_scope_in_the_build_slice_with_a_raised_oom_score():
    wrapped = cbr.slice_wrapped(["bwrap", "--", "makepkg"], cgroup=OUTSIDE, runner=CAPPED)
    assert wrapped == ["systemd-run", "--user", "--scope", "--slice=builds.slice",
                       "choom", "-n", "500", "--", "bwrap", "--", "makepkg"]


def test_enter_inside_the_build_slice_only_raises_the_oom_score():
    wrapped = cbr.slice_wrapped(["bwrap", "--", "makepkg"], cgroup=INSIDE, runner=CAPPED)
    assert wrapped == ["choom", "-n", "500", "--", "bwrap", "--", "makepkg"]


@pytest.mark.parametrize("runner", [
    _systemctl("LoadState=not-found\nMemoryMax=infinity\n"),
    _systemctl("LoadState=loaded\nMemoryMax=infinity\n"),
    _systemctl("", returncode=1),
])
def test_enter_refuses_without_a_capped_build_slice(runner):
    # An uncapped or missing slice must fail before any wrapping, even inside it.
    for cgroup in (OUTSIDE, INSIDE):
        with pytest.raises(cbr.BuildRootError, match="builds.slice"):
            cbr.slice_wrapped(["bwrap"], cgroup=cgroup, runner=runner)


def test_current_cgroup_reads_the_v2_entry(tmp_path):
    proc = tmp_path / "cgroup"
    proc.write_text(f"0::{INSIDE}\n")
    assert cbr.current_cgroup(proc) == INSIDE
    proc.write_text("1:name=systemd:/x\n")
    with pytest.raises(cbr.BuildRootError):
        cbr.current_cgroup(proc)

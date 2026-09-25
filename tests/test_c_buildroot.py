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


# The host cache is a download cache only: a file in it is used when it is
# the exact file the sync DB names and its sha256 matches the DB entry. The
# host's installed versions never enter the lock, because the W2A root models
# the host after W5, which is a full `pacman -Syu`.


def cache_world(tmp_path, db, host, targets, *, found=None, cached=None):
    """Resolve TARGETS over a core DB with the host cache holding both versions.

    DB and HOST map a package name to (version, depends, provides). The cache
    holds every host-version file (with a real .PKGINFO) and every DB-version
    file named in CACHED (default: all); the DB entries carry the sha256 of
    those DB-version files. FOUND is an optional foundation DB of the same shape.
    """
    import hashlib

    cache = tmp_path / "cache"
    cache.mkdir()
    for name, (version, depends, provides) in host.items():
        make_pkg(cache / f"{name}-{version}-x86_64.pkg.tar.zst", name, version, {},
                 provides=provides, depends=depends)
    entries = []
    for name, (version, depends, provides) in db.items():
        content = f"db file {name} {version}".encode()
        if cached is None or name in cached:
            (cache / f"{name}-{version}-x86_64.pkg.tar.zst").write_bytes(content)
        entries.append(desc(name, version, depends=depends, provides=provides,
                            sha256=hashlib.sha256(content).hexdigest()))
    repos = [("core", cbr.read_db(write_db(tmp_path / "core.db", entries), "core"))]
    pools = {}
    if found:
        pool = tmp_path / "pool"
        pool.mkdir()
        for name, (version, _, _) in found.items():
            (pool / f"{name}-{version}-x86_64.pkg.tar.zst").touch()
        fdb = write_db(tmp_path / "found.db", [
            desc(n, v, depends=d, provides=p, sha256=f"sha-{n}") for n, (v, d, p) in found.items()])
        repos.insert(0, ("found", cbr.read_db(fdb, "found")))
        pools = {"found": pool}
    cfg = cbr.ResolveConfig(repos=repos, foundation=["found"] if found else [], pools=pools,
                            host_cache=cache, installed={n: v for n, (v, _, _) in host.items()})
    return cbr.resolve(targets, cfg)


def assert_all_at_db_version(lock, db):
    assert lock["problems"] == []
    for entry in lock["packages"]:
        if entry["repo"] != "core":
            continue
        version = db[entry["name"]][0]
        assert entry["version"] == version, entry["name"]
        assert entry["source"] == "core"
        assert entry["path"].endswith(f"/{entry['name']}-{version}-x86_64.pkg.tar.zst")
        assert entry["sha256_db"] and cbr.sha256_file(Path(entry["path"])) == entry["sha256_db"]


# Each case is a bug the earlier host-substitution rules let through: the
# host ran older versions, and the lock mixed them with sync-DB packages.
REGRESSIONS = {
    # python-protobuf 35.1 declares depend = protobuf=35.1; the lock needs protobuf 36.1.
    "versioned-depend": (
        {"protobuf": ("36.1-1", ["abseil-cpp"], ["libprotobuf.so=36.1.0-64"]),
         "python-protobuf": ("36.1-1", ["protobuf=36.1"], []),
         "abseil-cpp": ("20260817.0-2", [], [])},
        {"protobuf": ("35.1-1", ["abseil-cpp"], ["libprotobuf.so=35.1.0-64"]),
         "python-protobuf": ("35.1-1", ["protobuf=35.1"], []),
         "abseil-cpp": ("20260526.0-1", [], [])},
        ["protobuf>=36.1", "python-protobuf"],
    ),
    # Host re2 and grpcio link the host Abseil 20260526 through an unversioned depend.
    "unversioned-abseil": (
        {"abseil-cpp": ("20260817.0-2", [], []),
         "re2": ("2:2025.11.05-6", ["abseil-cpp"], []),
         "python-grpcio": ("1.84.0-1", ["re2", "abseil-cpp"], [])},
        {"abseil-cpp": ("20260526.0-1", [], []),
         "re2": ("2:2025.11.05-5", ["abseil-cpp"], []),
         "python-grpcio": ("1.83.0-1", ["re2"], [])},
        ["abseil-cpp>=20260817.0", "python-grpcio"],
    ),
    # grpcio-tools depends only on grpcio in the host file, so it moved only
    # because the package below it moved.
    "cascade": (
        {"abseil-cpp": ("20260817.0-2", [], []),
         "re2": ("2:2025.11.05-6", ["abseil-cpp"], []),
         "python-grpcio": ("1.84.0-1", ["re2", "abseil-cpp"], []),
         "python-grpcio-tools": ("1.84.0-1", ["python-grpcio"], [])},
        {"abseil-cpp": ("20260526.0-1", [], []),
         "re2": ("2:2025.11.05-5", ["abseil-cpp"], []),
         "python-grpcio": ("1.83.0-1", ["re2"], []),
         "python-grpcio-tools": ("1.83.0-1", ["python-grpcio"], [])},
        ["abseil-cpp>=20260817.0", "python-grpcio-tools"],
    ),
    # The reverse direction: a package at its DB version links a library the
    # host file of its unversioned depend does not ship (ffmpeg needs
    # libbluray.so.4, the host libbluray 1.4 ships .so.3).
    "reverse-ffmpeg-libbluray": (
        {"ffmpeg": ("2:9.0.2-1", ["libbluray", "x264"], []),
         "libbluray": ("1.5.1-1", [], ["libbluray.so=4-64"]),
         "x264": ("3:0.166-1", [], [])},
        {"ffmpeg": ("2:8.0-1", ["libbluray", "x264"], []),
         "libbluray": ("1.4.1-1", [], ["libbluray.so=3-64"]),
         "x264": ("3:0.165-1", [], [])},
        ["ffmpeg"],
    ),
    "reverse-opencv-openexr": (
        {"opencv": ("5.0.0-12", ["openexr", "protobuf"], []),
         "openexr": ("3.5.0-2", ["imath"], []),
         "imath": ("3.2.3-1", [], []),
         "protobuf": ("36.1-1", [], [])},
        {"opencv": ("5.0.0-11", ["openexr", "protobuf"], []),
         "openexr": ("3.4.14-1", ["imath"], []),
         "imath": ("3.2.2-6", [], []),
         "protobuf": ("35.1-1", [], [])},
        ["opencv", "protobuf>=36.1"],
    ),
    # The foundation's python-gfx1151 3.14.7 is newer than the host's 3.14.6.
    "python-patch-bump": (
        {"python-regex": ("2026.9.1-2", ["python"], [])},
        {"python-regex": ("2026.9.1-1", ["python"], [])},
        ["python-regex"],
    ),
}


@needs_bsdtar
@pytest.mark.parametrize("case", sorted(REGRESSIONS))
def test_host_versions_never_enter_the_lock(tmp_path, case):
    db, host, targets = REGRESSIONS[case]
    found = {"python-gfx1151": ("3.14.7-1", [], ["python=3.14.7"])} if case == "python-patch-bump" else None
    if found:
        host = {**host, "python": ("3.14.6-1", [], [])}
    lock = cache_world(tmp_path, db, host, targets, found=found)
    assert {e["name"] for e in lock["packages"]} == set(db) | set(found or ())
    assert_all_at_db_version(lock, db)


@needs_bsdtar
def test_a_soname_pin_takes_the_db_protobuf(tmp_path):
    # migraphx-gfx1151 pins libprotobuf.so=36.1.0-64 (#108); the host runs 35.1.
    lock = cache_world(
        tmp_path,
        {"protobuf": ("36.1-1", [], ["libprotobuf.so=36.1.0-64"])},
        {"protobuf": ("35.1-1", [], ["libprotobuf.so=35.1.0-64"])},
        ["migraphx-gfx1151"],
        found={"migraphx-gfx1151": ("7.14.1-1", ["libprotobuf.so=36.1.0-64"], [])},
    )
    assert_all_at_db_version(lock, {"protobuf": ("36.1-1",)})


def zlib_cache(tmp_path, content, **cfg_extra):
    import hashlib

    good = b"db file zlib 1.3.1-1"
    db = write_db(tmp_path / "core.db", [desc("zlib", "1.3.1-1", sha256=hashlib.sha256(good).hexdigest())])
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "zlib-1.3.1-1-x86_64.pkg.tar.zst").write_bytes(content)
    cfg = cbr.ResolveConfig(repos=[("core", cbr.read_db(db, "core"))], foundation=[], host_cache=cache,
                            installed={"zlib": "1.3.1-1"}, **cfg_extra)
    return cbr.resolve(["zlib"], cfg), good


def test_exact_hash_matching_host_file_is_reused_without_a_download(tmp_path):
    lock, good = zlib_cache(tmp_path, b"db file zlib 1.3.1-1")
    zlib = by_name(lock)["zlib"]
    assert zlib["path"] == str(tmp_path / "cache/zlib-1.3.1-1-x86_64.pkg.tar.zst")
    assert (zlib["version"], zlib["source"]) == ("1.3.1-1", "core")
    assert lock["problems"] == []

    def no_download(url, dest):
        raise AssertionError(f"downloaded {url}")

    assert cbr.fetch_missing(lock, tmp_path / "dl", {}, downloader=no_download,
                             servers_for=lambda repo: ["https://x.example"]) == []


def test_version_match_with_a_hash_mismatch_is_refused(tmp_path):
    # A file at the DB file name whose bytes differ from the DB entry, as a
    # local rebuild at the same pkgrel would leave.
    lock, good = zlib_cache(tmp_path, b"rebuilt locally")
    zlib = by_name(lock)["zlib"]
    assert zlib["path"] is None and zlib["sha256_db"]
    assert lock["problems"] == [{"kind": "missing-file", "package": "zlib",
                                 "detail": "zlib-1.3.1-1-x86_64.pkg.tar.zst"}]
    fetched = cbr.fetch_missing(lock, tmp_path / "dl", {}, downloader=lambda u, d: d.write_bytes(good),
                                servers_for=lambda repo: ["https://x.example/core"])
    assert fetched == ["zlib"] and lock["problems"] == []


def test_every_lock_entry_records_the_db_sha256(tmp_path):
    lock = cbr.resolve(["hip-runtime-amd-gfx1151", "python-numpy", "cmake"], config(tmp_path))
    assert {p["name"]: p["sha256_db"] for p in lock["packages"]} == {
        "hip-runtime-amd-gfx1151": "bb", "rocm-core-gfx1151": "aa", "python-numpy-gfx1151": "cc",
        "glibc": "dd", "cmake": "11"}


def test_forbidden_repo_names_never_come_from_host_cache(tmp_path):
    lock, _ = zlib_cache(tmp_path, b"db file zlib 1.3.1-1", forbidden_names={"zlib"})
    assert by_name(lock)["zlib"]["path"] is None
    assert [p["kind"] for p in lock["problems"]] == ["missing-file"]


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
    extra = tmp_path / "fetched"
    extra.mkdir()
    (extra / "zlib-1.3.1-1-x86_64.pkg.tar.zst").write_bytes(b"db file zlib 1.3.1-1")
    lock, _ = zlib_cache(tmp_path, b"stale", extra_caches=[extra])
    assert lock["problems"] == []
    assert by_name(lock)["zlib"]["path"] == str(extra / "zlib-1.3.1-1-x86_64.pkg.tar.zst")


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


def write_allowlist(tmp_path: Path, text: str) -> "cbr.Allowlist":
    path = tmp_path / "allow.toml"
    path.write_text(text)
    return cbr.load_allowlist(path)


def test_allowlisted_needed_miss_does_not_fail_verify_but_is_still_reported(tmp_path):
    allow = write_allowlist(tmp_path, '''
[[needed]]
package = "app"
object = "/usr/bin/app"
soname = "libmissing.so.*"
reason = "optional plugin"
issue = 7
''')
    report = cbr.verify_root(needed_root(tmp_path), foundation=["found"], forbidden_repos=[], expect_rocm=None,
                             allowlist=allow)
    assert report["unresolved_needed"] == {"app": ["/usr/bin/app: libmissing.so.9"]}
    assert report["violations"] == []
    assert report["allowlist"]["needed_allowed"] == 1


@pytest.mark.parametrize("field,value", [("package", "other"), ("object", "/usr/bin/other"),
                                         ("soname", "libother.so.9")])
def test_needed_entry_must_match_package_object_and_soname(tmp_path, field, value):
    entry = {"package": "app", "object": "/usr/bin/app", "soname": "libmissing.so.9", "reason": "r", field: value}
    allow = write_allowlist(tmp_path, "[[needed]]\n" + "".join(f'{k} = "{v}"\n' for k, v in entry.items()))
    report = cbr.verify_root(needed_root(tmp_path), foundation=["found"], forbidden_repos=[], expect_rocm=None,
                             allowlist=allow)
    assert "unresolved NEEDED in app: /usr/bin/app: libmissing.so.9" in report["violations"]
    # An entry that covers nothing is stale, which also fails verify.
    assert any(v.startswith("stale allowlist entry [needed]") and value in v for v in report["violations"])


def test_stale_needed_entry_fails_verify(tmp_path):
    allow = write_allowlist(tmp_path, '''
[[needed]]
package = "app"
object = "/usr/bin/app"
soname = "libmissing.so.9"
reason = "optional plugin"

[[needed]]
package = "python-pkg"
object = "/usr/lib/python3.14/site-packages/pkg/_ext.so"
soname = "libbundled.so.2"
reason = "fixed since"
''')
    report = cbr.verify_root(needed_root(tmp_path), foundation=["found"], forbidden_repos=[], expect_rocm=None,
                             allowlist=allow)
    assert report["violations"] == [
        "stale allowlist entry [needed] python-pkg /usr/lib/python3.14/site-packages/pkg/_ext.so "
        "libbundled.so.2: matches nothing in this root"]
    assert report["allowlist"]["stale"] == 1


def runpath_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / cbr.STATE_DIR).mkdir(parents=True)
    make_elf(root / "usr/lib/libok.so.1", runpath="$ORIGIN/../lib/ok:${ORIGIN}:/usr/lib/ok:/opt/rocm/lib")
    make_elf(root / "usr/bin/leaky", runpath="/build/src/torch/lib:/usr/lib")
    make_elf(root / "usr/lib/libold.so.1", rpath="/__w/TheRock/build/lib")
    make_elf(root / "opt/rocm/lib/libdots.so.1", runpath="/usr/../tmp/x:/opt/rocmx/lib:lib")
    make_elf(root / "opt/rocm/lib/code.hsaco", runpath="/build/gpu", machine=224)  # an AMDGPU object
    cbr.save_manifest(root, [
        cbr.record_package(root, "ok", "1-1", "core", Path("ok.pkg"), "o", ["usr/lib/libok.so.1"]),
        cbr.record_package(root, "leaky", "1-1", "core", Path("l.pkg"), "l", ["usr/bin/leaky"]),
        cbr.record_package(root, "old", "1-1", "core", Path("o.pkg"), "o", ["usr/lib/libold.so.1"]),
        cbr.record_package(root, "rocm-dots", "1-1", "found", Path("d.pkg"), "d",
                           ["opt/rocm/lib/libdots.so.1", "opt/rocm/lib/code.hsaco"]),
    ])
    return root


def test_verify_fails_on_runpath_entries_outside_usr_opt_rocm_and_origin(tmp_path):
    report = cbr.verify_root(runpath_root(tmp_path), foundation=["found"], forbidden_repos=[], expect_rocm=None)
    assert report["foreign_runpath"] == {
        "leaky": ["/usr/bin/leaky: RUNPATH /build/src/torch/lib"],
        "old": ["/usr/lib/libold.so.1: RPATH /__w/TheRock/build/lib"],
        "rocm-dots": ["/opt/rocm/lib/libdots.so.1: RUNPATH /opt/rocmx/lib",
                      "/opt/rocm/lib/libdots.so.1: RUNPATH /usr/../tmp/x",
                      "/opt/rocm/lib/libdots.so.1: RUNPATH lib"],
    }
    assert sorted(v for v in report["violations"] if "RUNPATH" in v or "RPATH" in v) == [
        "foreign RUNPATH in leaky: /usr/bin/leaky: RUNPATH /build/src/torch/lib",
        "foreign RUNPATH in old: /usr/lib/libold.so.1: RPATH /__w/TheRock/build/lib",
        "foreign RUNPATH in rocm-dots: /opt/rocm/lib/libdots.so.1: RUNPATH /opt/rocmx/lib; "
        "/opt/rocm/lib/libdots.so.1: RUNPATH /usr/../tmp/x; /opt/rocm/lib/libdots.so.1: RUNPATH lib",
    ]


def test_allowlisted_runpath_hits_pass_and_stale_ones_fail(tmp_path):
    allow = write_allowlist(tmp_path, '''
[[runpath]]
package = "leaky"
object = "/usr/bin/leaky"
entry = "/build/*"
reason = "build dir baked in"
issue = 109

[[runpath]]
package = "old"
object = "/usr/lib/libold.so.1"
entry = "/__w/*"
reason = "CI dir baked in"
issue = 108

[[runpath]]
package = "rocm-dots"
object = "/opt/rocm/lib/libdots.so.1"
entry = "*"
reason = "test"

[[runpath]]
package = "ok"
object = "/usr/lib/libok.so.1"
entry = "/build/*"
reason = "no longer there"
''')
    report = cbr.verify_root(runpath_root(tmp_path), foundation=["found"], forbidden_repos=[], expect_rocm=None,
                             allowlist=allow)
    assert report["violations"] == [
        "stale allowlist entry [runpath] ok /usr/lib/libok.so.1 /build/*: matches nothing in this root"]
    assert report["allowlist"]["runpath_allowed"] == 5


@pytest.mark.parametrize("text,match", [
    ('[[needed]]\npackage = "a"\nobject = "/x"\nsoname = "b"\n', "reason"),
    ('[[needed]]\npackage = "a"\nobject = "/x"\nsoname = "b"\nreason = "r"\nextra = 1\n', "extra"),
    ('[[runpath]]\npackage = "a"\nobject = "/x"\nsoname = "b"\nreason = "r"\n', "entry"),
    ('[[needed]]\npackage = "a"\nobject = "/x"\nsoname = "b"\nreason = "r"\nissue = "#1"\n', "issue"),
    ('[[other]]\npackage = "a"\n', "other"),
])
def test_allowlist_entries_are_validated(tmp_path, text, match):
    with pytest.raises(cbr.BuildRootError, match=match):
        write_allowlist(tmp_path, text)


def test_committed_allowlist_is_valid_and_every_entry_is_explained():
    allow = cbr.load_allowlist(cbr.DEFAULT_ALLOWLIST)
    assert allow.needed and allow.runpath
    for entry in allow.needed + allow.runpath:
        assert entry.reason.strip() and entry.package and entry.object.startswith("/")
    # Known real defects stay tracked by an issue rather than silently allowed.
    tracked = {e.package: e.issue for e in allow.needed + allow.runpath if e.issue}
    assert tracked["python-pytorch-opt-rocm-gfx1151"] == 109
    assert tracked["amdsmi-gfx1151"] == 108


def test_verify_cli_uses_the_committed_allowlist_by_default():
    a = cbr.build_parser().parse_args(["verify", "root", "--foundation-repo", "f"])
    assert Path(a.allowlist) == cbr.DEFAULT_ALLOWLIST


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

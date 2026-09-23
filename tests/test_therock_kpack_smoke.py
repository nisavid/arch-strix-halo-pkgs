from __future__ import annotations

import shutil
import sys
import tarfile
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
TESTS_DIR = REPO_ROOT / "tests"
for path in (TOOLS_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import therock_kpack_smoke as smoke
from test_therock_split import kpack_marker, make_elf

ARCH = "gfx1151"
ALL_ARCHIVES = [f"{family}_{ARCH}.kpack" for family in smoke.KPACK_FAMILY_PROBES]


def passing(*probes: str) -> list[dict]:
    return [
        {"probe": probe, "family": smoke.probe_family(probe), "ok": True, "detail": {}}
        for probe in probes
    ]


def failing(probe: str, error: str = "ProbeFailure: rc 107", stderr: str = "") -> dict:
    result = {
        "probe": probe,
        "family": smoke.probe_family(probe),
        "ok": False,
        "error": error,
    }
    if stderr:
        result["stderr_tail"] = stderr
    return result


GAP_STDERR = ":0:hip_global.cpp:209 : Cannot create GlobalVar Obj for symbol: _ZL30store_cb_default_complex_float.static.53976c5a245d922c"


def test_every_policy_kpack_archive_has_a_default_probe():
    policy = tomllib.loads((REPO_ROOT / "policies/therock-packages.toml").read_text())
    archives = [
        path.rsplit("/", 1)[1]
        for path in policy["overrides"]["path_owners"]
        if path.startswith("opt/rocm/.kpack/")
    ]
    families = {
        smoke.archive_family(name.replace("@GFXARCH@", ARCH), ARCH) for name in archives
    }

    assert families == set(smoke.KPACK_FAMILY_PROBES)
    for family, probes in smoke.KPACK_FAMILY_PROBES.items():
        assert probes, family
        assert set(probes) <= set(smoke.DEFAULT_PROBES), family
    assert set(smoke.ALL_PROBES) == set(smoke.PROBE_FUNCTIONS)


def test_archive_family_strips_the_arch_suffix_only():
    assert smoke.archive_family("blas_lib_gfx1151.kpack", ARCH) == "blas_lib"
    assert smoke.archive_family("blas_lib_gfx942.kpack", ARCH) is None
    assert smoke.archive_family("README", ARCH) is None


def test_all_probes_passing_cover_every_family():
    results = passing(*smoke.DEFAULT_PROBES)
    coverage = smoke.kpack_coverage(ALL_ARCHIVES, results, ARCH)

    assert coverage["uncovered"] == []
    assert coverage["missing_archives"] == []
    assert coverage["covered"]["blas_lib"] == ["rocblas", "rocsolver"]
    ok, lines = smoke.summarize(results, coverage)
    assert ok
    assert any(line.startswith("XPASS rocfft-callback") for line in lines)


def test_a_failed_kernel_launch_leaves_its_family_uncovered():
    results = passing(
        "hip",
        "rocblas",
        "rocsolver",
        "rocfft-callback",
        "rccl",
        "hiptensor",
        "rocalution",
    )
    results.append(failing("rocrand"))
    coverage = smoke.kpack_coverage(ALL_ARCHIVES, results, ARCH)

    assert coverage["uncovered"] == ["rand_lib"]
    ok, lines = smoke.summarize(results, coverage)
    assert not ok
    assert "FAIL rocrand [rand_lib]: ProbeFailure: rc 107" in lines
    assert "FAIL kpack family rand_lib: no probe launched a kernel from it" in lines


def test_one_passing_probe_covers_a_shared_family():
    results = passing("rocblas") + [failing("rocsolver")]
    coverage = smoke.kpack_coverage(["blas_lib_gfx1151.kpack"], results, ARCH)

    assert coverage["covered"]["blas_lib"] == ["rocblas"]
    assert coverage["uncovered"] == []
    ok, _lines = smoke.summarize(results, coverage)
    assert not ok  # the rocsolver failure still fails the run


def test_known_gap_with_its_signature_is_xfail_and_does_not_fail_the_run():
    results = [
        failing("rocfft-callback", "child exited -6 without a result", GAP_STDERR)
    ]
    coverage = smoke.kpack_coverage(["fft_lib_gfx1151.kpack"], results, ARCH)

    assert smoke.classify(results[0]) == "XFAIL"
    assert coverage["known_gap"] == {"fft_lib": ["rocfft-callback"]}
    assert coverage["uncovered"] == []
    ok, lines = smoke.summarize(results, coverage | {"missing_archives": []})
    assert ok
    assert lines[0].startswith("XFAIL rocfft-callback [fft_lib]")
    assert "ROCm/TheRock#5444" in lines[0]


def test_known_gap_probe_failing_another_way_is_a_real_failure():
    results = [failing("rocfft-callback", "ProbeFailure: rocfft_execute returned 1")]
    coverage = smoke.kpack_coverage(["fft_lib_gfx1151.kpack"], results, ARCH)

    assert smoke.classify(results[0]) == "FAIL"
    assert coverage["uncovered"] == ["fft_lib"]


def test_missing_and_unknown_archives_fail_a_full_run():
    archives = [name for name in ALL_ARCHIVES if not name.startswith("rccl_lib")] + [
        f"new_lib_{ARCH}.kpack"
    ]
    coverage = smoke.kpack_coverage(archives, passing(*smoke.DEFAULT_PROBES), ARCH)

    assert coverage["missing_archives"] == ["rccl_lib"]
    assert coverage["unknown_families"] == ["new_lib"]
    ok, lines = smoke.summarize(passing(*smoke.DEFAULT_PROBES), coverage)
    assert not ok
    assert (
        "FAIL kpack family new_lib: staged archive has no probe in this tool" in lines
    )
    assert (
        "FAIL kpack family rccl_lib: no rccl_lib_<arch>.kpack archive in the ROCm tree"
        in lines
    )


def test_probe_exceptions_become_result_rows(monkeypatch, tmp_path: Path):
    def boom(lib_dir, arch, workdir):
        raise smoke.ProbeFailure("rocrand_generate_uniform returned 107")

    monkeypatch.setitem(smoke.PROBE_FUNCTIONS, "rocrand", boom)
    result = smoke.run_probe_in_process("rocrand", tmp_path, ARCH, tmp_path)

    assert result == {
        "probe": "rocrand",
        "family": "rand_lib",
        "ok": False,
        "error": "ProbeFailure: rocrand_generate_uniform returned 107",
    }


def test_bwrap_overlays_the_staged_rocm_and_keeps_gpu_and_tmp_usable(tmp_path: Path):
    root, workdir = tmp_path / "root", tmp_path / "work"
    cmd = smoke.bwrap_command(root, workdir, ["python3", "x.py"])

    joined = " ".join(cmd)
    assert cmd[0] == "bwrap"
    assert f"--ro-bind {root}/opt/rocm /opt/rocm" in joined
    assert "--dev-bind /dev /dev" in joined
    assert f"--bind {workdir}/tmp /tmp" in joined
    assert joined.index("--ro-bind / /") < joined.index("/opt/rocm")
    assert cmd[-3:] == ["--", "python3", "x.py"]
    assert "python3.14" not in joined


def test_bwrap_python_overlay_keeps_the_host_site_packages(tmp_path: Path):
    root = tmp_path / "root"
    site = Path("/usr/lib/python3.14/site-packages")
    cmd = smoke.bwrap_command(
        root,
        tmp_path / "work",
        ["python3"],
        sandbox_python=True,
        host_site_packages=site,
    )
    joined = " ".join(cmd)

    assert f"--ro-bind {root}/usr/bin/python3.14 /usr/bin/python3.14" in joined
    assert (
        f"--ro-bind {root}/usr/lib/libpython3.14.so.1.0 /usr/lib/libpython3.14.so.1.0"
        in joined
    )
    staged_stdlib = joined.index(
        f"--ro-bind {root}/usr/lib/python3.14 /usr/lib/python3.14"
    )
    host_site = joined.index(f"--ro-bind {site} /usr/lib/python3.14/site-packages")
    assert staged_stdlib < host_site


def package(
    name: str, files: list[str], depends: list[str] | None = None
) -> smoke.PackageArchive:
    return smoke.PackageArchive(name=name, depends=depends or [], files=files)


def test_duplicate_owners_reports_paths_in_two_packages():
    packages = [
        package(
            "rocprofiler-systems-gfx1151",
            ["opt/rocm/bin/rocprof-compute", "opt/rocm/bin/rocprof-sys-run"],
        ),
        package("rocprofiler-compute-gfx1151", ["opt/rocm/bin/rocprof-compute"]),
    ]

    assert smoke.duplicate_owners(packages) == {
        "opt/rocm/bin/rocprof-compute": [
            "rocprofiler-systems-gfx1151",
            "rocprofiler-compute-gfx1151",
        ],
    }


def test_compare_root_finds_unlisted_and_missing_paths(tmp_path: Path):
    (tmp_path / "opt/rocm/lib").mkdir(parents=True)
    (tmp_path / "opt/rocm/lib/librocfoo.so.1").write_bytes(b"")
    (tmp_path / "opt/rocm/lib/stray.txt").write_text("x")
    (tmp_path / "opt/rocm/lib/linked").symlink_to("..")
    packages = [
        package(
            "rocfoo-gfx1151",
            ["opt/rocm/lib/librocfoo.so.1", "opt/rocm/lib/linked", "opt/rocm/lib/gone"],
        )
    ]

    assert smoke.compare_root(packages, tmp_path) == {
        "unlisted": ["opt/rocm/lib/stray.txt"],
        "missing": ["opt/rocm/lib/gone"],
    }


def test_kpack_failures_use_the_built_package_depends(tmp_path: Path):
    make_elf(
        tmp_path / "opt/rocm/lib/librocfoo.so.1",
        kpack_ref=kpack_marker("../.kpack/foo_lib_@GFXARCH@.kpack"),
    )
    (tmp_path / "opt/rocm/.kpack").mkdir(parents=True)
    (tmp_path / "opt/rocm/.kpack/foo_lib_gfx1151.kpack").write_bytes(b"KPAK")
    archive = package("rocbar-gfx1151", ["opt/rocm/.kpack/foo_lib_gfx1151.kpack"])

    linked = [
        package("rocfoo-gfx1151", ["opt/rocm/lib/librocfoo.so.1"], ["rocbar-gfx1151"]),
        archive,
    ]
    assert smoke.kpack_failures(linked, tmp_path, ARCH) == []

    unlinked = [
        package("rocfoo-gfx1151", ["opt/rocm/lib/librocfoo.so.1"], ["glibc"]),
        archive,
    ]
    [failure] = smoke.kpack_failures(unlinked, tmp_path, ARCH)
    assert failure.startswith(
        "opt/rocm/lib/librocfoo.so.1: kpack archive opt/rocm/.kpack/foo_lib_gfx1151.kpack is owned by rocbar-gfx1151"
    )


def write_package(
    path: Path, pkgname: str, depends: list[str], files: dict[str, bytes]
) -> Path:
    staging = path.parent / f"{pkgname}.staging"
    staging.mkdir()
    pkginfo = [f"pkgname = {pkgname}", "pkgver = 1-1"] + [
        f"depend = {depend}" for depend in depends
    ]
    (staging / ".PKGINFO").write_text("\n".join(pkginfo) + "\n")
    for relpath, data in files.items():
        (staging / relpath).parent.mkdir(parents=True, exist_ok=True)
        (staging / relpath).write_bytes(data)
    with tarfile.open(path, "w:gz") as tar:
        tar.add(staging / ".PKGINFO", ".PKGINFO")
        for relpath in files:
            tar.add(staging / relpath, relpath)
    shutil.rmtree(staging)
    return path


@pytest.mark.skipif(shutil.which("bsdtar") is None, reason="needs bsdtar")
def test_check_packages_fails_on_a_path_owned_twice(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_package(
        repo / "a-gfx1151-1-1-x86_64.pkg.tar.gz",
        "a-gfx1151",
        ["glibc>=2.40"],
        {"opt/rocm/bin/tool": b"a"},
    )
    write_package(
        repo / "b-gfx1151-1-1-x86_64.pkg.tar.gz",
        "b-gfx1151",
        [],
        {"opt/rocm/bin/tool": b"b"},
    )

    assert smoke.main(["check-packages", "--repo", str(repo)]) == 1
    assert (
        "FAIL opt/rocm/bin/tool is owned by a-gfx1151, b-gfx1151"
        in capsys.readouterr().out
    )
    assert smoke.read_package_archive(
        repo / "a-gfx1151-1-1-x86_64.pkg.tar.gz"
    ).depends == ["glibc"]

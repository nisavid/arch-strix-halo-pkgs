import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "generators/therock_split.py"
SPEC = importlib.util.spec_from_file_location("therock_split", MODULE_PATH)
assert SPEC and SPEC.loader
therock_split = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = therock_split
SPEC.loader.exec_module(therock_split)


def test_render_pkgbuild_preserves_literal_quotes_in_synthetic_file_text(tmp_path: Path):
    policy = {
        "repo": {
            "pkgbase": "therock-gfx1151",
            "pkgver": "7.13.0pre",
            "pkgrel": 1,
            "license": ["custom:AMD"],
            "url": "https://github.com/ROCm/TheRock",
            "bundle_conflict": "rocm-gfx1151-bin",
        },
        "packages": {
            "rocm-core-gfx1151": {
                "desc": "ROCm core runtime files from TheRock for gfx1151",
                "provides": ["rocm-core"],
            }
        },
        "synthetic_files": {
            "rocm-core-gfx1151": [
                {
                    "path": "etc/profile.d/rocm.sh",
                    "text": "append_path '/opt/rocm/bin'\n",
                }
            ]
        },
    }
    package_files = {"rocm-core-gfx1151": ["opt/rocm/.info/version"]}
    template = tmp_path / "PKGBUILD.in"
    template.write_text(
        "\n".join(
            [
                "pkgbase='{{pkgbase}}'",
                "pkgname=(",
                "{{pkgname_block}}",
                ")",
                "pkgver='{{pkgver}}'",
                "pkgrel={{pkgrel}}",
                "license=({{license_block}})",
                "url='{{url}}'",
                "{{package_functions}}",
            ]
        )
    )

    therock_split.render_pkgbuild(
        policy,
        package_files,
        tmp_path,
        template,
        {
            "pkgver": "7.13.0pre",
            "recipe_repo_url": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
            "recipe_commit": "ad42886",
            "recipe_date": "20260317",
        },
    )

    text = (tmp_path / "PKGBUILD").read_text()
    assert "append_path '/opt/rocm/bin'" in text
    assert """append_path '"'"'/opt/rocm/bin'"'"'""" not in text


def test_render_pkgbuild_and_manifest_include_declared_replacements(tmp_path: Path):
    policy = {
        "repo": {
            "pkgbase": "therock-gfx1151",
            "pkgver": "7.13.0pre",
            "pkgrel": 1,
            "license": ["custom:AMD"],
            "url": "https://github.com/ROCm/TheRock",
            "bundle_conflict": "rocm-gfx1151-bin",
        },
        "packages": {
            "magma-gfx1151": {
                "desc": "MAGMA from TheRock for gfx1151",
                "provides": ["magma-hip", "hipmagma"],
                "replaces": ["magma-hip", "hipmagma"],
            }
        },
    }
    package_files = {"magma-gfx1151": ["opt/rocm/lib/libmagma.so"]}
    render_meta = {
        "pkgver": "7.13.0pre",
        "recipe_repo_url": "https://github.com/paudley/ai-notes",
        "recipe_subdir": "strix-halo",
        "recipe_author": "Blackcat Informatics Inc.",
        "recipe_commit": "ad42886",
        "recipe_date": "20260317",
    }

    therock_split.render_pkgbuild(
        policy,
        package_files,
        tmp_path,
        REPO_ROOT / "templates/PKGBUILD.in",
        render_meta,
    )
    therock_split.write_manifest(policy, package_files, tmp_path, render_meta)

    text = (tmp_path / "PKGBUILD").read_text()
    assert "    provides=('magma-hip' 'hipmagma')" in text
    assert "    replaces=('magma-hip' 'hipmagma')" in text

    manifest = (tmp_path / "manifest.json").read_text()
    assert '"replaces": [\n        "magma-hip",\n        "hipmagma"\n      ]' in manifest


def test_rocm_debug_agent_tracks_arch_rocr_debug_agent_baseline():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    debug_agent = policy["packages"]["rocm-debug-agent-gfx1151"]

    assert debug_agent["provides"] == ["rocm-debug-agent", "rocr-debug-agent"]
    assert debug_agent["replaces"] == ["rocr-debug-agent"]
    assert debug_agent["depends"] == [
        "rocm-core-gfx1151",
        "hip-runtime-amd-gfx1151",
        "rocm-dbgapi-gfx1151",
    ]


def test_payload_packages_are_not_fileless_compat_packages():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")

    for name in ("hiptensor-gfx1151", "rpp-gfx1151", "rocalution-gfx1151", "hipfile-gfx1151"):
        assert "fileless" not in policy["packages"][name]
    # rpp has no payload in the TheRock 7.14.1 stage, so no meta package may pull it.
    assert "rpp-gfx1151" not in policy["packages"]["rocm-ml-libraries-gfx1151"]["depends"]


def test_hip_libraries_meta_pulls_the_7_14_1_payload_libraries():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    depends = policy["packages"]["rocm-hip-libraries-gfx1151"]["depends"]

    for name in ("hiptensor-gfx1151", "rocalution-gfx1151", "hipfile-gfx1151"):
        assert name in depends


def test_core_runtime_dependency_policy_tracks_arch_baseline_shape():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    packages = policy["packages"]

    assert packages["comgr-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "rocm-core-gfx1151",
        "rocm-llvm-gfx1151",
        "rocm-device-libs-gfx1151",
        "rocm-sysdeps-gfx1151",
    ]
    assert packages["hsa-rocr-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "rocm-core-gfx1151",
        "rocm-device-libs-gfx1151",
        "rocprofiler-register-gfx1151",
        "rocm-sysdeps-gfx1151",
    ]
    assert packages["rocm-opencl-runtime-gfx1151"]["provides"] == [
        "rocm-opencl-runtime",
        "opencl-driver",
    ]
    assert packages["rocm-opencl-runtime-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "mesa",
        "opencl-headers",
        "opencl-icd-loader",
        "rocm-core-gfx1151",
        "comgr-gfx1151",
        "hsa-rocr-gfx1151",
        "rocm-sysdeps-gfx1151",
    ]
    assert packages["rocm-dbgapi-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "rocm-core-gfx1151",
        "comgr-gfx1151",
        "hsa-rocr-gfx1151",
    ]
    assert packages["rocm-developer-tools-gfx1151"]["depends"] == [
        "rocm-llvm-gfx1151",
        "rocm-cmake-gfx1151",
        "rocm-gdb-gfx1151",
        "rocprofiler-compute-gfx1151",
        "rocprofiler-systems-gfx1151",
        "rocprofiler-sdk-gfx1151",
        "roctracer-gfx1151",
    ]
    assert packages["rocm-gdb-gfx1151"]["depends"] == [
        "bash",
        "expat",
        "gcc-libs",
        "glibc",
        "gmp",
        "guile",
        "libelf",
        "mpfr",
        "ncurses",
        "python-gfx1151",
        "readline",
        "rocm-dbgapi-gfx1151",
        "rocm-debug-agent-gfx1151",
        "xz",
        "zlib",
        "zstd",
    ]


def test_math_and_ml_dependency_policy_tracks_arch_baseline_shape():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    packages = policy["packages"]
    assert (policy["repo"]["pkgver"], policy["repo"]["pkgrel"]) == ("7.14.1", 2)

    assert packages["rocblas-gfx1151"]["depends"] == [
        "cblas",
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "openmp",
        "rocm-core-gfx1151",
        "roctracer-gfx1151",
    ]
    assert packages["hipblaslt-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "hipblas-gfx1151",
        "msgpack-cxx",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "rocm-smi-lib-gfx1151",
        "yaml-cpp",
        "composable-kernel-gfx1151",
    ]
    assert packages["migraphx-gfx1151"]["depends"] == [
        "abseil-cpp>=20260817.0",
        "abseil-cpp<20260818",
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "miopen-hip-gfx1151",
        "msgpack-cxx",
        "python-gfx1151",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "sqlite",
    ]
    assert packages["migraphx-gfx1151"]["soname_depends"] == [
        {"library": "opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so", "needed": "libprotobuf.so"},
    ]
    assert packages["hipsparselt-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "hipsparse-gfx1151",
        "lapack",
        "msgpack-cxx",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "rocm-smi-lib-gfx1151",
        "rocminfo-gfx1151",
        "roctracer-gfx1151",
    ]
    assert packages["rocalution-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "openmp",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "rocprim-gfx1151",
        "rocrand-gfx1151",
        "rocsolver-gfx1151",
        "rocsparse-gfx1151",
    ]
    assert packages["rocprofiler-compute-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "python-gfx1151",
        "python-astunparse",
        "python-numpy-gfx1151",
        "python-pandas",
        "python-pyyaml-gfx1151",
        "python-sqlalchemy",
        "python-tabulate",
        "python-textual",
        "rocprofiler-sdk-gfx1151",
        "rocprofiler-systems-gfx1151",
    ]
    assert packages["miopen-gfx1151"]["depends"] == [
        "bzip2",
        "comgr-gfx1151",
        "composable-kernel-gfx1151",
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "hipblas-gfx1151",
        "hipblaslt-gfx1151",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "rocrand-gfx1151",
        "roctracer-gfx1151",
        "sqlite",
    ]


def test_live_root_render_ignores_rocm_core_overlay_files():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    classifier = therock_split.Classifier(policy)

    assert classifier.classify("opt/rocm/bin/rdhc") == "__ignored__"
    assert classifier.classify("opt/rocm/share/rdhc/README.md") == "__ignored__"
    assert classifier.classify("opt/rocm/share/rdhc/requirements.txt") == "__ignored__"


def test_live_root_render_ignores_post_copy_symlinks():
    # A stage copied from an installed /opt/rocm already holds the symlinks
    # that post_copy_commands create; classifying them would make a second
    # split package own the same path.
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    classifier = therock_split.Classifier(policy)
    link_re = re.compile(r'ln -s \S+ "\$\{pkgdir\}/([^"]+)"')
    created = [
        match.group(1)
        for meta in policy["packages"].values()
        for command in meta.get("post_copy_commands", [])
        for match in [link_re.search(command)]
        if match
    ]

    # 7.14.1 ships bin/rocprof-compute in the payload, so no post-copy symlink
    # creates it; rdhc is the remaining synthesized link.
    assert "opt/rocm/bin/rdhc" in created
    assert "opt/rocm/bin/rocprof-compute" not in created
    assert {path: classifier.classify(path) for path in created} == {
        path: "__ignored__" for path in created
    }


def test_migraphx_payloads_map_to_migraphx_split_package():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    classifier = therock_split.Classifier(policy)
    site_module = "opt/rocm/lib/python3.14/site-packages/migraphx.cpython-314-x86_64-linux-gnu.so"

    assert classifier.classify("opt/rocm/bin/migraphx-driver") == "migraphx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libmigraphx.so") == "migraphx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libmigraphx_py.so") == "migraphx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libmigraphx_py_3.14.so") == "migraphx-gfx1151"
    assert classifier.classify("opt/rocm/lib/migraphx.cpython-314-x86_64-linux-gnu.so") == "migraphx-gfx1151"
    assert classifier.classify("opt/rocm/lib/migraphx/include/migraphx/program.hpp") == "migraphx-gfx1151"
    assert classifier.classify("opt/rocm/lib/migraphx/lib/libmigraphx_gpu.so") == "migraphx-gfx1151"
    assert classifier.classify(site_module) == "migraphx-gfx1151"
    assert classifier.failures == []


def test_hipfort_payloads_map_to_hipfort_split_package():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    classifier = therock_split.Classifier(policy)

    assert classifier.classify("opt/rocm/bin/hipfc") == "hipfort-gfx1151"
    assert classifier.classify("opt/rocm/include/hipfort/amdgcn/hipfort.mod") == "hipfort-gfx1151"
    assert classifier.classify("opt/rocm/lib/cmake/hipfort/hipfort-config.cmake") == "hipfort-gfx1151"
    assert classifier.classify("opt/rocm/lib/libhipfort-amdgcn.a") == "hipfort-gfx1151"
    assert classifier.classify("opt/rocm/libexec/hipfort/mygpu") == "hipfort-gfx1151"
    assert classifier.classify("opt/rocm/share/hipfort/Makefile.hipfort") == "hipfort-gfx1151"
    assert classifier.failures == []


def test_mivisionx_payloads_map_to_mivisionx_split_package():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    classifier = therock_split.Classifier(policy)

    assert classifier.classify("opt/rocm/bin/mv_compile") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/bin/runvx") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/include/mivisionx/VX/vx.h") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libopenvx.so") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libvx_amd_custom.so") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libvx_nn.so") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libvx_rpp.so") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/lib/libvxu.so") == "mivisionx-gfx1151"
    assert classifier.classify("opt/rocm/libexec/mivisionx/model_compiler/README.md") == "mivisionx-gfx1151"
    assert classifier.failures == []


def test_write_filelists_removes_stale_package_filelists(tmp_path: Path):
    filelist_dir = tmp_path / "filelists"
    filelist_dir.mkdir()
    (filelist_dir / "stale-gfx1151.txt").write_text("opt/rocm/lib/libstale.so\n")

    therock_split.write_filelists(
        {"current-gfx1151": ["opt/rocm/lib/libcurrent.so"]},
        tmp_path,
    )

    assert not (filelist_dir / "stale-gfx1151.txt").exists()
    assert (filelist_dir / "current-gfx1151.txt").read_text() == "opt/rocm/lib/libcurrent.so\n"


def test_generated_copy_helper_copies_from_staged_root_without_stage_prefix(tmp_path: Path):
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()
    policy = {
        "repo": {
            "pkgbase": "therock-gfx1151",
            "pkgrel": 1,
            "license": ["custom:AMD"],
            "url": "https://github.com/ROCm/TheRock",
            "bundle_conflict": "rocm-gfx1151-bin",
        },
        "packages": {
            "rocm-core-gfx1151": {
                "desc": "ROCm core runtime files from TheRock for gfx1151",
                "provides": ["rocm-core"],
            }
        },
    }
    package_files = {"rocm-core-gfx1151": ["opt/rocm/lib/libmarker.so"]}
    stage_root = tmp_path / "stage"
    (stage_root / "opt/rocm/lib").mkdir(parents=True)
    (stage_root / "opt/rocm/lib/libmarker.so").write_text("payload\n")
    pkgdir = tmp_path / "pkgdir"

    therock_split.render_pkgbuild(
        policy,
        package_files,
        output_dir,
        REPO_ROOT / "templates/PKGBUILD.in",
        {
            "pkgver": "7.13.0pre",
            "recipe_repo_url": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
            "recipe_commit": "ad42886",
            "recipe_date": "20260317",
        },
    )
    therock_split.write_filelists(package_files, output_dir)

    subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; '
                'pkgdir="$2"; '
                '_therock_root="$3"; '
                '_copy_from_filelist rocm-core-gfx1151; '
                'test -f "$pkgdir/opt/rocm/lib/libmarker.so"; '
                'test ! -e "$pkgdir${_therock_root}"'
            ),
            "bash",
            str(output_dir / "PKGBUILD"),
            str(pkgdir),
            str(stage_root),
        ],
        check=True,
    )


# --- TheRock 7.14.1 payload policy -------------------------------------------------


KPACK_ARCHIVE_OWNERS = {
    "blas_lib": "rocblas-gfx1151",
    "fft_lib": "rocfft-gfx1151",
    "hiptensor_lib": "hiptensor-gfx1151",
    "rand_lib": "rocrand-gfx1151",
    "rccl_lib": "rccl-gfx1151",
    "rocalution_lib": "rocalution-gfx1151",
}

# kpack-split libraries in the TheRock 7.14.1 gfx1151 dist tarball and the
# archive that each one's .rocm_kpack_ref marker names.
KPACK_SPLIT_LIBRARIES = {
    "opt/rocm/lib/librocblas.so.5.5": "blas_lib",
    "opt/rocm/lib/libhipblaslt.so.1.4": "blas_lib",
    "opt/rocm/lib/librocsparse.so.1.0": "blas_lib",
    "opt/rocm/lib/librocsolver.so.0.10": "blas_lib",
    "opt/rocm/lib/libhipsparselt.so.0.2": "blas_lib",
    "opt/rocm/lib/librocfft.so.0.1": "fft_lib",
    "opt/rocm/lib/librocrand.so.1.1": "rand_lib",
    "opt/rocm/lib/librccl.so.1.0": "rccl_lib",
    "opt/rocm/lib/libhiptensor.so.0.1": "hiptensor_lib",
    "opt/rocm/lib/librocalution_hip.so.1.0.0": "rocalution_lib",
}


def repo_policy() -> dict:
    return therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")


def test_policy_owns_every_kpack_archive_through_the_library_dependency_graph():
    policy = repo_policy()
    classifier = therock_split.Classifier(policy)

    for archive, owner in KPACK_ARCHIVE_OWNERS.items():
        assert classifier.classify(f"opt/rocm/.kpack/{archive}_gfx1151.kpack") == owner

    for library, archive in KPACK_SPLIT_LIBRARIES.items():
        library_owner = classifier.classify(library)
        archive_owner = KPACK_ARCHIVE_OWNERS[archive]
        assert library_owner == archive_owner or archive_owner in policy["packages"][library_owner]["depends"], library
    assert classifier.failures == []
    assert not any(".kpack" in pattern for pattern in policy["filters"]["ignore_globs"])


def test_policy_maps_7_14_1_payload_additions():
    classifier = therock_split.Classifier(repo_policy())
    expected = {
        "opt/rocm/include/rocalution/rocalution.hpp": "rocalution-gfx1151",
        "opt/rocm/lib/cmake/rocalution/rocalution-config.cmake": "rocalution-gfx1151",
        "opt/rocm/lib/librocalution.so.1.0": "rocalution-gfx1151",
        "opt/rocm/lib/librocalution_hip.so.1.0.0": "rocalution-gfx1151",
        "opt/rocm/include/hipfile.h": "hipfile-gfx1151",
        "opt/rocm/include/hipfile-api-trace.h": "hipfile-gfx1151",
        "opt/rocm/lib/cmake/hipfile/hipfile-config.cmake": "hipfile-gfx1151",
        "opt/rocm/lib/libhipfile.so.0.3.0": "hipfile-gfx1151",
        "opt/rocm/bin/ais-check": "hipfile-gfx1151",
        "opt/rocm/bin/ais-stats": "hipfile-gfx1151",
        "opt/rocm/include/hiptensor/hiptensor.h": "hiptensor-gfx1151",
        "opt/rocm/lib/cmake/hiptensor/hiptensor-config.cmake": "hiptensor-gfx1151",
        "opt/rocm/lib/libhiptensor.so.0.1": "hiptensor-gfx1151",
        "opt/rocm/include/nccl.h": "rccl-gfx1151",
        "opt/rocm/include/nccl_device.h": "rccl-gfx1151",
        "opt/rocm/include/nccl_device/impl/core__funcs.h": "rccl-gfx1151",
        "opt/rocm/include/rocprof-trace-decoder/rocprof_trace_decoder/cxx/code_printing.hpp": "rocprofiler-systems-gfx1151",
        "opt/rocm/lib/cmake/rocprof-trace-decoder/rocprof-trace-decoder-config.cmake": "rocprofiler-systems-gfx1151",
        "opt/rocm/lib/python/site-packages/rocprofsys/__init__.py": "rocprofiler-systems-gfx1151",
        "opt/rocm/lib/hipdnn_frontend_python.abi3.so": "miopen-hip-gfx1151",
        "opt/rocm/bin/hrr-playback": "hip-runtime-amd-gfx1151",
        "opt/rocm/bin/amdllvm": "rocm-llvm-gfx1151",
        "opt/rocm/bin/rocprof-compute": "rocprofiler-compute-gfx1151",
    }

    for path, owner in expected.items():
        assert classifier.classify(path) == owner, path
    assert classifier.failures == []


def test_rocprof_compute_launcher_is_not_also_synthesized():
    # 7.14.1 ships bin/rocprof-compute; a post-copy symlink to the same path
    # would put it in two packages.
    commands = repo_policy()["packages"]["rocprofiler-compute-gfx1151"].get("post_copy_commands", [])
    assert not any("bin/rocprof-compute" in command for command in commands)


def test_policy_ignores_7_14_1_payload_that_is_not_packaged():
    classifier = therock_split.Classifier(repo_policy())
    ignored = [
        "opt/rocm/include/rocjitsu/rocjitsu.h",
        "opt/rocm/lib/librocjitsu.so",
        "opt/rocm/share/rocjitsu/schemas/config.schema.json",
        "opt/rocm/lib/librocdxg.so.1.1.0",
        "opt/rocm/lib/cmake/rocdxg/rocdxg-config.cmake",
        "opt/rocm/lib/pkgconfig/librocdxg.pc",
        "opt/rocm/lib/cmake/rocprofiler-sdk-tests/rocprofiler-sdk-tests-config.cmake",
        "opt/rocm/share/rocprofiler-sdk-tests/setup-env.sh",
        "opt/rocm/lib/python3.10/site-packages/rocpd/libpyrocpd.cpython-310-x86_64-linux-gnu.so",
        "opt/rocm/lib/python3.13/site-packages/roctx/__init__.py",
        "opt/rocm/lib/python/site-packages/rocprofsys/libpyrocprofsys.cpython-313-x86_64-linux-gnu.so",
    ]

    for path in ignored:
        assert classifier.classify(path) == therock_split.IGNORED, path
    assert classifier.failures == []


def test_policy_drops_removed_iree_and_stale_rocm_smi_rules():
    policy = repo_policy()
    aliases = policy["aliases"]

    for name in ("iree", "IREE", "mlir-c"):
        assert name not in aliases["component_dirs"]
    for name in ("IREECompiler", "iree_compiler"):
        assert name not in aliases["library_prefixes"]
    assert "post_copy_commands" not in policy["packages"]["rocm-smi-lib-gfx1151"]
    for name in ("python3.10", "python3.11", "python3.12", "python3.13"):
        assert f"opt/rocm/lib/{name}" not in policy["overrides"]["path_owners"]


def test_policy_rewrites_ci_build_paths_and_fails_on_leftovers():
    packages = repo_policy()["packages"]
    leaks = {
        "rocprofiler-sdk-gfx1151": "opt/rocm/lib/cmake/rocprofiler-sdk/rocprofiler-sdk-config.cmake",
        "hsa-rocr-gfx1151": "opt/rocm/lib/cmake/hsakmt/hsakmtTargets.cmake",
        "rocm-core-gfx1151": "opt/rocm/share/pkgconfig/nlohmann_json.pc",
        "migraphx-gfx1151": "opt/rocm/lib/pkgconfig/flatbuffers.pc",
    }

    for pkg, path in leaks.items():
        commands = "\n".join(packages[pkg]["post_copy_commands"])
        assert path in commands, pkg
        assert "! grep -n '/__w/'" in commands, pkg
        assert "CI_PATH_LEAK" in commands, pkg


def test_ci_path_fixups_rewrite_the_7_14_1_leaks(tmp_path: Path):
    packages = repo_policy()["packages"]
    pkgdir = tmp_path / "pkg"
    ci = "/__w/rockrel/rockrel/build"
    files = {
        "opt/rocm/lib/cmake/rocprofiler-sdk/rocprofiler-sdk-config.cmake": (
            f"find_package(hip CONFIG HINTS\n        {ci}/core/clr/dist/lib/cmake/hip\n        {ci}/dist/rocm)\n"
        ),
        "opt/rocm/lib/cmake/hsakmt/hsakmtTargets.cmake": (
            f'INTERFACE_LINK_LIBRARIES "-L{ci}/third-party/sysdeps/linux/libdrm/build/stage/lib/rocm_sysdeps/lib/pkgconfig/../../lib;\\$<LINK_ONLY:-ldrm>"\n'
        ),
        "opt/rocm/share/pkgconfig/nlohmann_json.pc": f"prefix={ci}/third-party/nlohmann-json/stage\nincludedir=${{prefix}}/include\n",
        "opt/rocm/lib/pkgconfig/flatbuffers.pc": (
            f"libdir={ci}/third-party/flatbuffers/stage/lib\nincludedir={ci}/third-party/flatbuffers/stage/include\n"
        ),
    }
    for rel, text in files.items():
        (pkgdir / rel).parent.mkdir(parents=True, exist_ok=True)
        (pkgdir / rel).write_text(text)

    script = ["set -e", f'pkgdir="{pkgdir}"', "fixups() {"]
    for pkg in ("rocprofiler-sdk-gfx1151", "hsa-rocr-gfx1151", "migraphx-gfx1151"):
        script.extend(packages[pkg]["post_copy_commands"])
    script.extend(command for command in packages["rocm-core-gfx1151"]["post_copy_commands"] if "nlohmann" in command)
    script.extend(["}", "fixups"])
    subprocess.run(["bash", "-c", "\n".join(script)], check=True)

    rewritten = {rel: (pkgdir / rel).read_text() for rel in files}
    assert all("/__w/" not in text for text in rewritten.values())
    assert "/opt/rocm/lib/cmake/hip\n        /opt/rocm)" in rewritten[
        "opt/rocm/lib/cmake/rocprofiler-sdk/rocprofiler-sdk-config.cmake"
    ]
    assert '"-L${_IMPORT_PREFIX}/lib/rocm_sysdeps/lib;' in rewritten["opt/rocm/lib/cmake/hsakmt/hsakmtTargets.cmake"]
    assert rewritten["opt/rocm/share/pkgconfig/nlohmann_json.pc"].startswith("prefix=/opt/rocm\n")
    assert rewritten["opt/rocm/lib/pkgconfig/flatbuffers.pc"] == "libdir=/opt/rocm/lib\nincludedir=/opt/rocm/include\n"


def test_ci_path_fixups_fail_the_package_when_a_leak_survives(tmp_path: Path):
    commands = repo_policy()["packages"]["migraphx-gfx1151"]["post_copy_commands"]
    pc = tmp_path / "pkg/opt/rocm/lib/pkgconfig/flatbuffers.pc"
    pc.parent.mkdir(parents=True)
    pc.write_text("libdir=/x\nCflags: -I/__w/rockrel/rockrel/build/include\n")

    result = subprocess.run(
        ["bash", "-c", "\n".join([f'pkgdir="{tmp_path / "pkg"}"', "fixups() {", *commands, "}", "fixups"])],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "CI_PATH_LEAK" in result.stderr


# --- ELF helpers, KPACK_REF_UNOWNED and soname depends ---------------------------


def msgpack(value: object) -> bytes:
    import struct

    if isinstance(value, dict):
        return bytes([0x80 | len(value)]) + b"".join(msgpack(k) + msgpack(v) for k, v in value.items())
    if isinstance(value, list):
        return bytes([0x90 | len(value)]) + b"".join(msgpack(item) for item in value)
    data = value.encode()
    if len(data) < 32:
        return bytes([0xA0 | len(data)]) + data
    return struct.pack(">BB", 0xD9, len(data)) + data


def make_elf(
    path: Path,
    *,
    kpack_ref: bytes | None = None,
    needed: list[str] | None = None,
    runpath: str | None = None,
    rpath: str | None = None,
) -> Path:
    """Write a minimal little-endian ELF64 file with the requested sections."""
    import struct

    sections: list[tuple[str, int, bytes, int]] = []
    if kpack_ref is not None:
        sections.append((".rocm_kpack_ref", 1, kpack_ref, 0))
    dynamic_strings = [(1, name) for name in needed or []]
    if runpath is not None:
        dynamic_strings.append((29, runpath))
    if rpath is not None:
        dynamic_strings.append((15, rpath))
    if needed is not None or dynamic_strings:
        dynstr = b"\0"
        entries = []
        for tag, value in dynamic_strings:
            entries.append(struct.pack("<qQ", tag, len(dynstr)))
            dynstr += value.encode() + b"\0"
        sections.append((".dynstr", 3, dynstr, 0))
        dynstr_index = len(sections)
        dynamic = b"".join(entries) + struct.pack("<qQ", 0, 0)
        sections.append((".dynamic", 6, dynamic, dynstr_index))

    shstrtab = b"\0"
    name_offsets = []
    for name, *_rest in sections:
        name_offsets.append(len(shstrtab))
        shstrtab += name.encode() + b"\0"
    shstrtab_name = len(shstrtab)
    shstrtab += b".shstrtab\0"

    body = b""
    offsets = []
    for _name, _type, data, _link in sections:
        offsets.append(64 + len(body))
        body += data
    shstrtab_offset = 64 + len(body)
    body += shstrtab
    shoff = 64 + len(body)
    shnum = len(sections) + 2

    header = b"\x7fELF" + bytes([2, 1, 1]) + b"\0" * 9
    header += struct.pack("<HHIQQQIHHHHHH", 3, 62, 1, 0, 0, shoff, 0, 64, 0, 0, 64, shnum, shnum - 1)
    headers = b"\0" * 64
    for (_name, sh_type, data, link), name_offset, offset in zip(sections, name_offsets, offsets):
        headers += struct.pack("<IIQQQQIIQQ", name_offset, sh_type, 0, 0, offset, len(data), link, 0, 1, 0)
    headers += struct.pack("<IIQQQQIIQQ", shstrtab_name, 3, 0, 0, shstrtab_offset, len(shstrtab), 0, 0, 1, 0)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + body + headers)
    return path


def kpack_marker(*search_paths: str) -> bytes:
    return msgpack({"kpack_search_paths": list(search_paths), "kernel_name": "math-libs/lib/librocfoo.so.1"})


def kpack_policy(**overrides) -> dict:
    policy = {
        "repo": {"suffix": "-gfx1151"},
        "payload": {"gfx_arch": "gfx1151"},
        "packages": {
            "rocfoo-gfx1151": {"depends": ["rocbar-gfx1151"]},
            "rocbar-gfx1151": {"depends": []},
            "rocbaz-gfx1151": {"depends": []},
        },
    }
    policy.update(overrides)
    return policy


def test_elf_reader_matches_the_written_sections(tmp_path: Path):
    marker = kpack_marker("../.kpack/foo_lib_@GFXARCH@.kpack")
    elf = make_elf(tmp_path / "libfoo.so", kpack_ref=marker, needed=["libprotobuf.so.36.1.0", "libc.so.6"])

    assert therock_split.is_elf(elf)
    assert therock_split.read_elf_section(elf, ".rocm_kpack_ref") == marker
    assert therock_split.read_elf_section(elf, ".hip_fatbin") is None
    assert therock_split.read_elf_needed(elf) == ["libprotobuf.so.36.1.0", "libc.so.6"]
    assert therock_split.msgpack_decode(marker)["kpack_search_paths"] == ["../.kpack/foo_lib_@GFXARCH@.kpack"]


def test_kpack_search_paths_resolve_relative_to_the_library_directory():
    resolve = therock_split.resolve_kpack_search_path

    assert resolve("opt/rocm/lib/librocfoo.so.1", "../.kpack/foo_lib_@GFXARCH@.kpack", "gfx1151") == (
        "opt/rocm/.kpack/foo_lib_gfx1151.kpack"
    )
    assert resolve("opt/rocm/lib/librocfoo.so.1", "/opt/rocm/.kpack/foo.kpack", "gfx1151") == "opt/rocm/.kpack/foo.kpack"


def _kpack_failures(tmp_path: Path, owners: dict, policy: dict | None = None) -> list:
    make_elf(tmp_path / "opt/rocm/lib/librocfoo.so.1", kpack_ref=kpack_marker("../.kpack/foo_lib_@GFXARCH@.kpack"))
    make_elf(tmp_path / "opt/rocm/lib/libplain.so.1", needed=["libc.so.6"])
    archive = tmp_path / "opt/rocm/.kpack/foo_lib_gfx1151.kpack"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"KPAK\x01")
    failures: list = []
    therock_split.check_kpack_refs(tmp_path, policy or kpack_policy(), owners, failures)
    return failures


def test_kpack_ref_owned_by_the_library_package_or_a_direct_depend_passes(tmp_path: Path):
    for archive_owner in ("rocfoo-gfx1151", "rocbar-gfx1151"):
        owners = {
            "opt/rocm/lib/librocfoo.so.1": "rocfoo-gfx1151",
            "opt/rocm/lib/libplain.so.1": "rocbaz-gfx1151",
            "opt/rocm/.kpack/foo_lib_gfx1151.kpack": archive_owner,
        }
        assert _kpack_failures(tmp_path, owners) == []


def test_kpack_ref_to_an_ignored_archive_fails(tmp_path: Path):
    owners = {
        "opt/rocm/lib/librocfoo.so.1": "rocfoo-gfx1151",
        "opt/rocm/.kpack/foo_lib_gfx1151.kpack": therock_split.IGNORED,
    }
    failures = _kpack_failures(tmp_path, owners)

    assert [failure.kind for failure in failures] == ["kpack_ref_unowned"]
    rendered = failures[0].render()
    assert rendered.startswith("KPACK_REF_UNOWNED: opt/rocm/lib/librocfoo.so.1")
    assert "ignored by policy filters" in rendered


def test_kpack_ref_to_an_archive_outside_the_dependency_graph_fails(tmp_path: Path):
    owners = {
        "opt/rocm/lib/librocfoo.so.1": "rocfoo-gfx1151",
        "opt/rocm/.kpack/foo_lib_gfx1151.kpack": "rocbaz-gfx1151",
    }
    failures = _kpack_failures(tmp_path, owners)

    assert len(failures) == 1
    assert "owned by rocbaz-gfx1151, which rocfoo-gfx1151 does not depend on" in failures[0].detail


def test_kpack_ref_without_a_staged_archive_fails(tmp_path: Path):
    owners = {"opt/rocm/lib/librocfoo.so.1": "rocfoo-gfx1151"}
    failures = _kpack_failures(tmp_path, owners)

    assert len(failures) == 1
    assert "no kpack archive from opt/rocm/.kpack/foo_lib_gfx1151.kpack" in failures[0].detail


def test_kpack_ref_resolves_the_policy_gfx_arch(tmp_path: Path):
    owners = {
        "opt/rocm/lib/librocfoo.so.1": "rocfoo-gfx1151",
        "opt/rocm/.kpack/foo_lib_gfx1151.kpack": "rocfoo-gfx1151",
    }
    failures = _kpack_failures(tmp_path, owners, kpack_policy(payload={"gfx_arch": "gfx1100"}))

    assert len(failures) == 1
    assert "opt/rocm/.kpack/foo_lib_gfx1100.kpack" in failures[0].detail


def test_soname_depends_are_rendered_from_the_staged_elf(tmp_path: Path):
    library = "opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so"
    make_elf(tmp_path / library, needed=["libprotobuf.so.36.1.0", "libutf8_validity.so.36.1.0"])
    policy = {"packages": {"migraphx-gfx1151": {"soname_depends": [{"library": library, "needed": "libprotobuf.so"}]}}}
    failures: list = []

    derived = therock_split.derive_soname_depends(tmp_path, policy, {"migraphx-gfx1151": [library]}, failures)

    assert failures == []
    assert derived == {"migraphx-gfx1151": ["libprotobuf.so=36.1.0-64"]}
    assert therock_split.derive_soname_depends(tmp_path, policy, {}, failures) == {}


def test_soname_depends_fail_loudly_unless_skipping_for_a_dry_render(tmp_path: Path, capsys):
    library = "opt/rocm/lib/migraphx/lib/libmigraphx_onnx.so"
    policy = {"packages": {"migraphx-gfx1151": {"soname_depends": [{"library": library, "needed": "libprotobuf.so"}]}}}
    files = {"migraphx-gfx1151": ["opt/rocm/include/flatbuffers/base.h"]}

    failures: list = []
    assert therock_split.derive_soname_depends(tmp_path, policy, files, failures) == {}
    assert [failure.render().splitlines()[0] for failure in failures] == ["SONAME_DEPEND_UNRESOLVED: migraphx-gfx1151"]

    failures = []
    assert therock_split.derive_soname_depends(tmp_path, policy, files, failures, skip_missing=True) == {}
    assert failures == []
    assert "SONAME_DEPEND_SKIPPED: migraphx-gfx1151" in capsys.readouterr().err

    make_elf(tmp_path / library, needed=["libprotobuf.so.35.1.0", "libprotobuf.so.36.1.0"])
    failures = []
    assert therock_split.derive_soname_depends(tmp_path, policy, files, failures) == {}
    assert "needs 2 libprotobuf.so SONAMEs" in failures[0].detail


GENERATOR_POLICY = """
[repo]
pkgbase = "therock-gfx1151"
pkgver = "7.14.1"
pkgrel = 1
suffix = "-gfx1151"
url = "https://github.com/ROCm/TheRock"
license = ["custom:AMD"]
scan_roots = ["opt/rocm"]
bundle_conflict = "rocm-gfx1151-bin"

[payload]
gfx_arch = "gfx1151"

[filters]
ignore_globs = [@IGNORE@]

[packages."rocfoo-gfx1151"]
desc = "rocFOO"
provides = ["rocfoo"]
depends = ["glibc"]
soname_depends = [{ library = "opt/rocm/lib/librocfoo.so.1", needed = "libprotobuf.so" }]

[aliases.library_prefixes]
"rocfoo" = "rocfoo-gfx1151"

[overrides.path_owners]
"opt/rocm/.kpack/foo_lib_gfx1151.kpack" = "rocfoo-gfx1151"
"""


def run_generator(tmp_path: Path, root: Path, ignore: str) -> subprocess.CompletedProcess[str]:
    policy = tmp_path / "policy.toml"
    policy.write_text(GENERATOR_POLICY.replace("@IGNORE@", ignore))
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), "--root", str(root), "--policy", str(policy), "--output", str(tmp_path / "out")],
        capture_output=True,
        text=True,
    )


def test_generator_render_enforces_kpack_ownership_and_renders_soname_depends(tmp_path: Path):
    root = tmp_path / "root"
    make_elf(
        root / "opt/rocm/lib/librocfoo.so.1",
        kpack_ref=kpack_marker("../.kpack/foo_lib_@GFXARCH@.kpack"),
        needed=["libprotobuf.so.36.1.0"],
    )
    (root / "opt/rocm/.kpack").mkdir(parents=True)
    (root / "opt/rocm/.kpack/foo_lib_gfx1151.kpack").write_bytes(b"KPAK\x01")

    failed = run_generator(tmp_path, root, '"opt/rocm/.kpack/**"')
    assert failed.returncode == 2
    assert "KPACK_REF_UNOWNED: opt/rocm/lib/librocfoo.so.1" in failed.stderr
    assert not (tmp_path / "out").exists()

    rendered = run_generator(tmp_path, root, "")
    assert rendered.returncode == 0, rendered.stderr
    filelist = (tmp_path / "out/filelists/rocfoo-gfx1151.txt").read_text().splitlines()
    assert "opt/rocm/.kpack/foo_lib_gfx1151.kpack" in filelist
    assert "depends=('glibc' 'libprotobuf.so=36.1.0-64')" in (tmp_path / "out/PKGBUILD").read_text()
    manifest = json.loads((tmp_path / "out/manifest.json").read_text())
    assert manifest["packages"]["rocfoo-gfx1151"]["depends"] == ["glibc", "libprotobuf.so=36.1.0-64"]


# --- RUNPATH rewrites and the foreign search-path check (#108) -------------------


@pytest.mark.parametrize(
    ("relpath", "value", "foreign"),
    [
        ("opt/rocm/lib/libfoo.so", "$ORIGIN", []),
        ("opt/rocm/lib/libfoo.so", "${ORIGIN}/rocm_sysdeps/lib:$ORIGIN/llvm/lib", []),
        ("opt/rocm/share/amd_smi/amdsmi/libamd_smi.so", "$ORIGIN/../../../lib", []),
        ("opt/rocm/bin/tool", "/usr/lib:/opt/rocm/lib:/usr:/opt/rocm", []),
        # $ORIGIN resolves against the installed directory, so climbing out of
        # /opt/rocm is foreign even though the entry text starts with $ORIGIN.
        ("opt/rocm/lib/libfoo.so", "$ORIGIN/../../..", ["$ORIGIN/../../.."]),
        ("opt/rocm/lib/libfoo.so", "$ORIGIN/../../../home/ci/lib", ["$ORIGIN/../../../home/ci/lib"]),
        # Path-boundary counterexamples.
        ("opt/rocm/lib/libfoo.so", "/usrx/lib:/opt/rocmfoo/lib:/opt/rocm2", ["/usrx/lib", "/opt/rocmfoo/lib", "/opt/rocm2"]),
        # CI build trees, foreign interpreter prefixes, relative and empty entries.
        (
            "opt/rocm/lib/libfoo.so",
            "$ORIGIN:/__w/rockrel/rockrel/build/core/clr/dist/lib:",
            ["/__w/rockrel/rockrel/build/core/clr/dist/lib", ""],
        ),
        ("opt/rocm/bin/rocgdb-py3.14", "$ORIGIN/../lib:/opt/python-shared/cp314-cp314/lib", ["/opt/python-shared/cp314-cp314/lib"]),
        ("opt/rocm/lib/libfoo.so", "lib::$LIB/x", ["lib", "", "$LIB/x"]),
    ],
)
def test_foreign_search_path_entries_resolve_origin_and_respect_path_boundaries(relpath, value, foreign):
    assert therock_split.foreign_search_path_entries(relpath, value) == foreign


def runpath_root(tmp_path: Path) -> tuple[Path, dict[str, list[str]]]:
    root = tmp_path / "root"
    ci = "/__w/rockrel/rockrel/build"
    make_elf(root / "opt/rocm/lib/rocsparse/rocsparseio-info", needed=["libamdhip64.so.7"], runpath=f"{ci}/core/clr/dist/lib")
    make_elf(root / "opt/rocm/lib/rocsparse/rocsparseio-convert", needed=["libamdhip64.so.7"], rpath=f"{ci}/core/clr/dist/lib")
    make_elf(root / "opt/rocm/lib/librocsparse.so.1.0", needed=["libamdhip64.so.7"], runpath="$ORIGIN")
    (root / "opt/rocm/lib/rocsparse/rocsparseio-readme").write_text("not an ELF\n")
    (root / "opt/rocm/lib/rocsparse/rocsparseio-link").symlink_to("rocsparseio-info")
    files = {
        "rocsparse-gfx1151": [
            "opt/rocm/lib/librocsparse.so.1.0",
            "opt/rocm/lib/rocsparse/rocsparseio-convert",
            "opt/rocm/lib/rocsparse/rocsparseio-info",
            "opt/rocm/lib/rocsparse/rocsparseio-link",
            "opt/rocm/lib/rocsparse/rocsparseio-readme",
        ]
    }
    return root, files


def rewrite_policy(*entries: dict) -> dict:
    return {"packages": {"rocsparse-gfx1151": {"runpath_rewrites": list(entries)}}}


def failure_lines(failures: list) -> list[str]:
    return [failure.render().splitlines()[0] for failure in failures]


def test_runpath_rewrites_expand_globs_over_regular_elf_files_the_package_ships(tmp_path: Path):
    root, files = runpath_root(tmp_path)
    failures: list = []

    rewrites = therock_split.resolve_runpath_rewrites(
        root, rewrite_policy({"object": "opt/rocm/lib/rocsparse/rocsparseio-*", "runpath": "$ORIGIN/.."}), files, failures
    )

    assert failures == []
    # The symlink and the text file match the glob but are not rewritten.
    assert rewrites == {
        "rocsparse-gfx1151": [
            ("opt/rocm/lib/rocsparse/rocsparseio-convert", "$ORIGIN/.."),
            ("opt/rocm/lib/rocsparse/rocsparseio-info", "$ORIGIN/.."),
        ]
    }
    therock_split.check_search_paths(root, files, rewrites, failures)
    assert failures == []


@pytest.mark.parametrize(
    ("entries", "detail"),
    [
        ([{"object": "opt/rocm/lib/rocsparse/missing-*", "runpath": "$ORIGIN"}], "matches no regular ELF file"),
        ([{"object": "opt/rocm/lib/rocsparse/rocsparseio-readme", "runpath": "$ORIGIN"}], "matches no regular ELF file"),
        ([{"object": "opt/rocm/lib/rocsparse/rocsparseio-info", "runpath": "$ORIGIN/../../../.."}], "leaves /usr and /opt/rocm"),
        ([{"object": "opt/rocm/lib/rocsparse/rocsparseio-info", "runpath": "/__w/rockrel/x"}], "leaves /usr and /opt/rocm"),
        ([{"object": "opt/rocm/lib/rocsparse/rocsparseio-info", "runpath": ""}], "leaves /usr and /opt/rocm"),
        ([{"object": "opt/rocm/lib/rocsparse/rocsparseio-info", "runpath": "$ORIGIN/'x"}], "leaves /usr and /opt/rocm"),
        (
            [
                {"object": "opt/rocm/lib/rocsparse/rocsparseio-*", "runpath": "$ORIGIN/.."},
                {"object": "opt/rocm/lib/rocsparse/rocsparseio-info", "runpath": "$ORIGIN"},
            ],
            "matches both",
        ),
    ],
    ids=["unmatched", "not-elf", "escapes", "foreign", "empty", "quote", "two-entries"],
)
def test_runpath_rewrites_fail_the_render_on_invalid_entries(tmp_path: Path, entries, detail):
    root, files = runpath_root(tmp_path)
    failures: list = []

    therock_split.resolve_runpath_rewrites(root, rewrite_policy(*entries), files, failures)

    assert failure_lines(failures) == ["RUNPATH_REWRITE_INVALID: rocsparse-gfx1151"]
    assert detail in failures[0].detail


def test_foreign_search_path_check_reads_runpath_and_rpath(tmp_path: Path):
    root, files = runpath_root(tmp_path)
    failures: list = []

    therock_split.check_search_paths(root, files, {}, failures)

    assert failure_lines(failures) == [
        "FOREIGN_RUNPATH: opt/rocm/lib/rocsparse/rocsparseio-convert",
        "FOREIGN_RUNPATH: opt/rocm/lib/rocsparse/rocsparseio-info",
    ]
    assert "RPATH '/__w/rockrel/rockrel/build/core/clr/dist/lib'" in failures[0].detail
    assert "RUNPATH '/__w/rockrel/rockrel/build/core/clr/dist/lib'" in failures[1].detail
    assert "runpath_rewrites" in failures[0].hint


def test_elf_reader_returns_runpath_and_rpath(tmp_path: Path):
    elf = make_elf(tmp_path / "libfoo.so", needed=["libc.so.6"], runpath="$ORIGIN", rpath="/usr/lib")

    assert therock_split.read_elf_needed(elf) == ["libc.so.6"]
    assert therock_split.read_elf_search_paths(elf) == [("RUNPATH", "$ORIGIN"), ("RPATH", "/usr/lib")]
    assert therock_split.read_elf_search_paths(make_elf(tmp_path / "libbar.so", needed=[])) == []


RUNPATH_POLICY = """
[packages."rocbar-gfx1151"]
desc = "rocBAR"
provides = ["rocbar"]
runpath_rewrites = [{ object = "opt/rocm/bin/rocbar-*", runpath = "$ORIGIN/../lib" }]

[aliases.binary_prefixes]
"rocbar" = "rocbar-gfx1151"
"""


def test_generator_render_rewrites_runpaths_and_fails_on_foreign_ones(tmp_path: Path):
    root = tmp_path / "root"
    make_elf(root / "opt/rocm/lib/librocfoo.so.1", needed=["libprotobuf.so.36.1.0"], runpath="$ORIGIN")
    make_elf(root / "opt/rocm/bin/rocbar-info", needed=["libamdhip64.so.7"], runpath="/__w/rockrel/rockrel/build/core/clr/dist/lib")
    make_elf(root / "opt/rocm/bin/rocbar-stat", needed=["libamdhip64.so.7"], rpath="/__w/x:$ORIGIN")
    policy = tmp_path / "policy.toml"
    out = tmp_path / "out"

    def render(extra: str) -> subprocess.CompletedProcess[str]:
        policy.write_text(GENERATOR_POLICY.replace("@IGNORE@", "") + extra)
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), "--root", str(root), "--policy", str(policy), "--output", str(out)],
            capture_output=True,
            text=True,
            check=False,
        )

    failed = render(RUNPATH_POLICY.replace('runpath_rewrites = [{ object = "opt/rocm/bin/rocbar-*", runpath = "$ORIGIN/../lib" }]\n', ""))
    assert failed.returncode == 2
    assert "FOREIGN_RUNPATH: opt/rocm/bin/rocbar-info" in failed.stderr
    assert "FOREIGN_RUNPATH: opt/rocm/bin/rocbar-stat" in failed.stderr
    assert not out.exists()

    rendered = render(RUNPATH_POLICY)
    assert rendered.returncode == 0, rendered.stderr
    text = (out / "PKGBUILD").read_text()
    function = text[text.index("package_rocbar-gfx1151()") :]
    function = function[: function.index("\n}\n")]
    assert function.splitlines()[-3:] == [
        "    patchelf --set-rpath '$ORIGIN/../lib' \"${pkgdir}/opt/rocm/bin/rocbar-info\"",
        "    patchelf --set-rpath '$ORIGIN/../lib' \"${pkgdir}/opt/rocm/bin/rocbar-stat\"",
        "    _check_search_paths",
    ]
    # A package without rewrites still runs the check.
    rocfoo = text[text.index("package_rocfoo-gfx1151()") :]
    assert "patchelf" not in rocfoo[: rocfoo.index("\n}\n")]
    assert rocfoo[: rocfoo.index("\n}\n")].endswith("    _check_search_paths")


def test_template_declares_patchelf_and_defines_the_package_time_check():
    template = (REPO_ROOT / "templates/PKGBUILD.in").read_text()

    assert "makedepends=('binutils' 'patchelf')" in template
    assert "_check_search_paths() {" in template
    assert template.index("_check_search_paths() {") < template.index("{{package_functions}}")


def template_check_function() -> str:
    template = (REPO_ROOT / "templates/PKGBUILD.in").read_text()
    start = template.index("_check_search_paths() {")
    return template[start : template.index("\n}\n", start) + 2]


@pytest.mark.skipif(
    not (shutil.which("patchelf") and shutil.which("readelf") and shutil.which("true")),
    reason="needs patchelf, readelf, and a real ELF executable",
)
@pytest.mark.parametrize(
    ("relpath", "args", "foreign"),
    [
        ("opt/rocm/bin/tool", ["--set-rpath", "$ORIGIN/../lib:/usr/lib:/opt/rocm/lib"], None),
        ("opt/rocm/bin/tool", ["--set-rpath", "$ORIGIN:/__w/rockrel/rockrel/build/core/clr/dist/lib"], "/__w/rockrel/rockrel/build/core/clr/dist/lib"),
        ("opt/rocm/bin/tool", ["--force-rpath", "--set-rpath", "/opt/python-shared/cp314-cp314/lib"], "/opt/python-shared/cp314-cp314/lib"),
        ("opt/rocm/bin/tool", ["--set-rpath", "$ORIGIN/../../.."], "$ORIGIN/../../.."),
        ("opt/rocm/bin/tool", ["--set-rpath", "/opt/rocmfoo/lib"], "/opt/rocmfoo/lib"),
        ("opt/rocm/bin/tool", ["--set-rpath", "$ORIGIN:"], ""),
    ],
    ids=["allowed", "ci-runpath", "foreign-rpath", "origin-escape", "boundary", "empty"],
)
def test_package_time_check_reads_real_elf_search_paths(tmp_path: Path, relpath, args, foreign):
    pkgdir = tmp_path / "pkg"
    elf = pkgdir / relpath
    elf.parent.mkdir(parents=True)
    shutil.copyfile(Path(shutil.which("true")).resolve(), elf)
    subprocess.run(["patchelf", *args, str(elf)], check=True)
    (pkgdir / "opt/rocm/share/doc").mkdir(parents=True)
    (pkgdir / "opt/rocm/share/doc/README").write_text("/__w/not-an-elf\n")

    result = subprocess.run(
        ["bash", "-c", f'set -e\n{template_check_function()}\npkgdir="{pkgdir}"\n_check_search_paths'],
        capture_output=True,
        text=True,
        check=False,
    )

    if foreign is None:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
    else:
        assert result.returncode == 1
        assert f"FOREIGN_RUNPATH: /{relpath}: '{foreign}'" in result.stderr


def test_policy_rewrites_every_foreign_runpath_in_the_7_14_1_payload():
    packages = repo_policy()["packages"]
    rewrites = {
        pkg: [entry["object"] for entry in meta.get("runpath_rewrites", [])]
        for pkg, meta in packages.items()
        if meta.get("runpath_rewrites")
    }

    # 22 objects with CI build-tree entries in 11 packages, the five rocgdb
    # interpreter variants, and llvm-omp-kernel-replay's missing rocm_sysdeps.
    assert rewrites == {
        "amdsmi-gfx1151": ["opt/rocm/share/amd_smi/amdsmi/libamd_smi.so"],
        "hipblaslt-gfx1151": ["opt/rocm/share/hipblaslt/tensilelite/rocisa/libstinkytofu.so.0.1.0"],
        "hsa-amd-aqlprofile-gfx1151": ["opt/rocm/lib/libhsa-amd-aqlprofile64.so"],
        "miopen-hip-gfx1151": [
            "opt/rocm/bin/hipdnn_list_engines",
            "opt/rocm/lib/hipdnn_frontend_python.abi3.so",
            "opt/rocm/lib/hipdnn_plugins/engines/libhip_kernel_provider.so",
            "opt/rocm/lib/hipdnn_plugins/engines/libhipblaslt_plugin.so",
            "opt/rocm/lib/hipdnn_plugins/engines/libmiopen_plugin.so",
            "opt/rocm/lib/libhipdnn_backend.so",
        ],
        "rocm-gdb-gfx1151": ["opt/rocm/bin/rocgdb-py3.*"],
        "rocm-language-runtime-gfx1151": [
            "opt/rocm/bin/rdc[di]",
            "opt/rocm/lib/librdc.so.1.3",
            "opt/rocm/lib/librdc_bootstrap.so.1.3",
            "opt/rocm/lib/librdc_client.so.1.3",
            "opt/rocm/lib/rdc/librdc_roc[pr].so.1.3",
        ],
        "rocm-llvm-gfx1151": ["opt/rocm/lib/llvm/bin/llvm-omp-kernel-replay"],
        "rocm-sysdeps-gfx1151": ["opt/rocm/lib/rocm_sysdeps/bin/xmlwf"],
        "rocprofiler-systems-gfx1151": ["opt/rocm/bin/rocprof-sys-instrument"],
        "rocrand-gfx1151": ["opt/rocm/lib/librocrand.so.1.1"],
        "rocshmem-gfx1151": ["opt/rocm/bin/rocshmem_info"],
        "rocsparse-gfx1151": ["opt/rocm/lib/rocsparse/rocsparseio-*"],
    }
    for meta in packages.values():
        for entry in meta.get("runpath_rewrites", []):
            assert therock_split.foreign_search_path_entries(entry["object"], entry["runpath"]) == []
    # llvm-omp-kernel-replay keeps its clean entries and adds rocm_sysdeps.
    replay = packages["rocm-llvm-gfx1151"]["runpath_rewrites"][0]["runpath"]
    assert replay.endswith(":$ORIGIN/../../rocm_sysdeps/lib")


def test_rocprofiler_sdk_depends_on_its_rocpd_and_roctx_components():
    packages = repo_policy()["packages"]

    # The SDK's tool libraries NEED librocprofiler-sdk-rocpd and -roctx; those
    # libraries NEED nothing from the SDK, so the depends run one way only.
    assert packages["rocprofiler-sdk-gfx1151"]["depends"] == [
        "rocprofiler-sdk-rocpd-gfx1151",
        "rocprofiler-sdk-roctx-gfx1151",
    ]
    assert "rocprofiler-sdk-gfx1151" not in packages["rocprofiler-sdk-rocpd-gfx1151"].get("depends", [])
    assert "rocprofiler-sdk-gfx1151" not in packages["rocprofiler-sdk-roctx-gfx1151"].get("depends", [])

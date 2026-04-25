import importlib.util
from pathlib import Path
import subprocess
import sys


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


def test_absent_hiptensor_and_rpp_payloads_do_not_render_fileless_compat_packages():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")

    assert "fileless" not in policy["packages"]["hiptensor-gfx1151"]
    assert "fileless" not in policy["packages"]["rpp-gfx1151"]
    assert "hiptensor-gfx1151" not in policy["packages"]["rocm-hip-libraries-gfx1151"]["depends"]
    assert "rpp-gfx1151" not in policy["packages"]["rocm-ml-libraries-gfx1151"]["depends"]


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


def test_math_and_ml_dependency_policy_tracks_arch_baseline_shape():
    policy = therock_split.load_policy(REPO_ROOT / "policies/therock-packages.toml")
    packages = policy["packages"]

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
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "miopen-hip-gfx1151",
        "msgpack-cxx",
        "protobuf",
        "python-gfx1151",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "sqlite",
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

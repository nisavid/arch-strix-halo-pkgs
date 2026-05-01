import importlib.util
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

MODULE_PATH = TOOLS_DIR / "render_recipe_scaffolds.py"
SPEC = importlib.util.spec_from_file_location("render_recipe_scaffolds", MODULE_PATH)
assert SPEC and SPEC.loader
render_recipe_scaffolds = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_recipe_scaffolds
SPEC.loader.exec_module(render_recipe_scaffolds)


def init_recipe_repo(recipe_root: Path) -> None:
    recipe_dir = recipe_root / "strix-halo"
    recipe_dir.mkdir(parents=True)
    (recipe_dir / "vllm-packages.yaml").write_text(
        """
packages:
  sample:
    repo: https://example.invalid/sample.git
    method: meta
    phase: package
    steps: []
    depends_on: []
    notes: Sample recipe notes.
""".lstrip(),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=recipe_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "agent@example.invalid"], cwd=recipe_root, check=True)
    subprocess.run(["git", "config", "user.name", "Agent"], cwd=recipe_root, check=True)
    subprocess.run(["git", "add", "strix-halo/vllm-packages.yaml"], cwd=recipe_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add sample recipe"],
        cwd=recipe_root,
        check=True,
        capture_output=True,
    )


def test_main_renders_plain_upstream_pkgver_and_recipe_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    packaging_root = tmp_path / "packaging"
    policy_path = packaging_root / "policy.toml"
    output_root = packaging_root / "rendered"
    recipe_root = tmp_path / "ai-notes"
    packaging_root.mkdir()
    init_recipe_repo(recipe_root)
    recipe_commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=recipe_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    policy_path.write_text(
        """
[defaults]
recipe_repo = "https://github.com/paudley/ai-notes"
recipe_subdir = "strix-halo"
recipe_author = "Blackcat Informatics Inc."
repo_subpath = "."
output_root = "packages"

[packages.sample-gfx1151]
recipe_key = "sample"
template = "meta-package"
upstream_version = "1.2.3"
pkgdesc = "Sample package"
url = "https://example.invalid/sample"
license = ["MIT"]
src_subdir = "sample"
""".lstrip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render_recipe_scaffolds.py",
            "--recipe-root",
            str(recipe_root),
            "--policy",
            str(policy_path),
            "--output-root",
            str(output_root),
        ],
    )

    assert render_recipe_scaffolds.main() == 0

    pkgbuild = (output_root / "sample-gfx1151" / "PKGBUILD").read_text(encoding="utf-8")
    recipe_json = json.loads(
        (output_root / "sample-gfx1151" / "recipe.json").read_text(encoding="utf-8")
    )
    readme = (output_root / "sample-gfx1151" / "README.md").read_text(encoding="utf-8")

    assert "pkgver=1.2.3\n" in pkgbuild
    assert ".r1." not in pkgbuild
    assert recipe_json["pkgver"] == "1.2.3"
    assert recipe_json["provenance"]["recipe_commit"] == recipe_commit
    assert recipe_json["provenance"]["recipe_history_count"] == 1
    assert "- Package version: `1.2.3`" in readme
    assert "- Recipe revision:" in readme


def test_native_wheel_renderer_applies_source_patches_and_build_config_settings() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "sample-native-gfx1151",
        {
            "recipe_key": "sample",
            "template": "native-wheel-pypi",
            "upstream_version": "1.2.3",
            "pkgdesc": "Sample native wheel",
            "url": "https://example.invalid/sample-native",
            "license": ["MIT"],
            "pypi_name": "sample-native",
            "src_subdir": "sample-native-1.2.3",
            "source_patches": ["0001-sample.patch"],
            "skip_dependency_check": True,
            "build_config_settings": [
                "setup-args=-Dblas=openblas",
                "setup-args=-Dlapack=openblas",
            ],
        },
        {
            "repo": "",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "1.2.3",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert "0001-sample.patch" in pkgbuild
    assert 'patch --dry-run -R -Np1 -i "$srcdir/0001-sample.patch"' in pkgbuild
    assert "python -m build --wheel --no-isolation --skip-dependency-check \\\n" in pkgbuild
    assert "    -Csetup-args=-Dblas=openblas \\\n" in pkgbuild
    assert "    -Csetup-args=-Dlapack=openblas\n" in pkgbuild


def test_compiler_env_uses_repo_local_ccache_storage() -> None:
    snippet = render_recipe_scaffolds.compiler_env_snippet("/opt/rocm/lib/llvm/bin")

    assert "CCACHE_BASEDIR" in snippet
    assert 'local _ccache_cache="$srcdir/.ccache/cache"' in snippet
    assert 'export CCACHE_DIR="${CCACHE_DIR:-${_ccache_cache}}"' in snippet
    assert "CCACHE_TEMPDIR" not in snippet


def test_vllm_renderer_uses_repo_local_ccache_storage() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "python-vllm-rocm-gfx1151",
        {
            "recipe_key": "vllm",
            "template": "python-project-vllm",
            "upstream_version": "0.20.0",
            "pkgdesc": "vLLM ROCm",
            "url": "https://github.com/vllm-project/vllm",
            "license": ["Apache-2.0"],
            "source_type": "tarball",
            "source_url": "https://github.com/vllm-project/vllm/archive/refs/tags/v0.20.0.tar.gz",
            "source_patches": ["0016-rocm-refresh-local-carry-for-vllm-0.20.0.patch"],
            "src_subdir": "vllm-0.20.0",
        },
        {
            "repo": "https://github.com/vllm-project/vllm",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "0.20.0",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert 'local _ccache_cache="$srcdir/.ccache/cache"' in pkgbuild
    assert 'export CCACHE_DIR="${CCACHE_DIR:-${_ccache_cache}}"' in pkgbuild
    assert '_vllm_srcdir="vllm-${pkgver}"' in pkgbuild
    assert '_vllm_tarball="v${pkgver}.tar.gz"' in pkgbuild
    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in pkgbuild
    assert 'cd "$srcdir/${_vllm_srcdir}"' in pkgbuild
    assert 'export VLLM_VERSION_OVERRIDE="${pkgver}"' in pkgbuild


def test_vllm_renderer_defines_source_variables_without_patches() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "python-vllm-rocm-gfx1151",
        {
            "recipe_key": "vllm",
            "template": "python-project-vllm",
            "upstream_version": "0.20.0",
            "pkgdesc": "vLLM ROCm",
            "url": "https://github.com/vllm-project/vllm",
            "license": ["Apache-2.0"],
            "source_type": "tarball",
            "source_url": "https://github.com/vllm-project/vllm/archive/refs/tags/v0.20.0.tar.gz",
            "source_patches": [],
            "src_subdir": "vllm-0.20.0",
        },
        {
            "repo": "https://github.com/vllm-project/vllm",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "0.20.0",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert '_vllm_srcdir="vllm-${pkgver}"' in pkgbuild
    assert '_vllm_tarball="v${pkgver}.tar.gz"' in pkgbuild
    assert 'cd "$srcdir/${_vllm_srcdir}"' in pkgbuild
    assert "_apply_all_source_patches" not in pkgbuild


def test_rust_wheel_renderer_applies_source_patches() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "sample-rust-gfx1151",
        {
            "recipe_key": "sample",
            "template": "rust-wheel-pypi",
            "upstream_version": "1.2.3",
            "pkgdesc": "Sample rust wheel",
            "url": "https://example.invalid/sample-rust",
            "license": ["MIT"],
            "pypi_name": "sample-rust",
            "src_subdir": "sample-rust-1.2.3",
            "source_patches": ["0001-sample.patch"],
        },
        {
            "repo": "",
            "method": "cargo",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "1.2.3",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert "0001-sample.patch" in pkgbuild
    assert 'patch --dry-run -R -Np1 -i "$srcdir/0001-sample.patch"' in pkgbuild
    assert 'patch -Np1 -i "$srcdir/0001-sample.patch"' in pkgbuild
    assert 'export CARGO_HOME="$srcdir/.cargo"' in pkgbuild
    assert 'mkdir -p "$CARGO_HOME"' in pkgbuild


def test_triton_rocm_renderer_prefers_source_patches_over_inline_sed() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "python-triton-gfx1151",
        {
            "recipe_key": "triton",
            "template": "python-project-triton-rocm",
            "upstream_version": "3.0.0+git0ec280cf",
            "pkgdesc": "Triton",
            "url": "https://triton-lang.org/main/index.html",
            "license": ["MIT"],
            "src_subdir": "triton",
            "source_refs": [
                "triton::git+https://github.com/ROCm/triton.git#commit=0ec280cf80dd91e9a86887981a670f2d4541a32b"
            ],
            "source_patches": [
                "0001-python-3.14-and-pybind11-build-system.patch",
                "0002-disable-werror-with-therock-llvm-headers.patch",
                "0003-attrs-descriptor-repr-for-inductor.patch",
            ],
        },
        {
            "repo": "https://github.com/ROCm/triton.git",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
            "patches": [
                {
                    "type": "sed",
                    "file": "triton/backends/compiler.py",
                    "marker": "__repr__",
                    "marker_absent": True,
                    "sed_command": "/def to_dict(self):/i\\    def __repr__(self):\\n        return f'AttrsDescriptor.from_dict({self.to_dict()!r})'",
                }
            ],
        },
        "3.0.0+git0ec280cf",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert 'patch -Np1 -i "$srcdir/0001-python-3.14-and-pybind11-build-system.patch"' in pkgbuild
    assert 'patch -Np1 -i "$srcdir/0003-attrs-descriptor-repr-for-inductor.patch"' in pkgbuild
    assert "aten/src/ATen/native/hip/linalg/BatchLinearAlgebra.cpp" not in pkgbuild
    assert "sed -i" not in pkgbuild
    assert "git cherry-pick" not in pkgbuild


def test_aocl_libm_renderer_prefers_source_patches_over_inline_sed() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "aocl-libm-gfx1151",
        {
            "recipe_key": "aocl_libm",
            "template": "scons-aocl-libm",
            "upstream_version": "5.2.2",
            "pkgdesc": "AOCL-LibM",
            "url": "https://github.com/amd/aocl-libm-ose.git",
            "license": ["BSD-3-Clause"],
            "src_subdir": "aocl-libm",
            "source_refs": [
                "aocl-libm::git+https://github.com/amd/aocl-libm-ose.git#tag=5.2.2"
            ],
            "source_patches": ["0001-scons-support-arch-amdclang-toolchain.patch"],
            "source_patches_replace_recipe_patches": True,
        },
        {
            "repo": "https://github.com/amd/aocl-libm-ose.git",
            "method": "scons",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
            "patches": [
                {
                    "type": "sed",
                    "file": "src/SConscript",
                    "marker": "muse-unaligned-vector-move",
                    "sed_command": "s/ccflags.append('-muse-unaligned-vector-move')/pass/",
                }
            ],
        },
        "5.2.2",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert 'patch -Np1 -i "$srcdir/0001-scons-support-arch-amdclang-toolchain.patch"' in pkgbuild
    assert "sed -i" not in pkgbuild
    assert "patchelf --set-rpath /usr/lib" in pkgbuild


def test_torch_migraphx_renderer_keeps_rocm_compiler_and_rpath() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "python-torch-migraphx-gfx1151",
        {
            "recipe_key": "native_wheels",
            "template": "python-project-torch-migraphx",
            "upstream_version": "1.2",
            "pkgdesc": "Torch-MIGraphX",
            "url": "https://github.com/ROCm/torch_migraphx",
            "license": ["BSD-3-Clause"],
            "src_subdir": "torch_migraphx",
            "source_refs": [
                "torch_migraphx::git+https://github.com/ROCm/torch_migraphx.git#commit=6b2cd2237e83b675ae671650d08343dfbb0be5f3"
            ],
            "source_patches": [
                "0001-import-pt2e-quantization-from-torchao.patch",
                "0002-keep-dynamo-registration-lazy.patch",
                "0003-relax-numpy-runtime-cap.patch",
            ],
            "makedepends": ["patchelf"],
        },
        {
            "repo": "https://github.com/ROCm/torch_migraphx.git",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "1.2",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert 'cd "$srcdir/torch_migraphx/py"' in pkgbuild
    assert "PYTORCH_ROCM_ARCH=gfx1151" in pkgbuild
    assert "ROCM_HOME=/opt/rocm" in pkgbuild
    assert "-famd-opt" not in pkgbuild
    assert "patchelf --set-rpath" in pkgbuild
    assert "$ORIGIN/torch/lib" in pkgbuild
    assert "0003-relax-numpy-runtime-cap.patch" in pkgbuild


def test_torchao_renderer_preserves_source_build_shape() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "python-torchao-rocm-gfx1151",
        {
            "recipe_key": "native_wheels",
            "template": "python-project-torchao",
            "upstream_version": "0.17.0",
            "pkgdesc": "TorchAO",
            "url": "https://github.com/pytorch/ao",
            "license": ["BSD-3-Clause"],
            "src_subdir": "torchao",
            "source_refs": ["torchao::git+https://github.com/pytorch/ao.git#tag=v0.17.0"],
            "source_patches": [
                "0001-setup.py-honor-pytorch-rocm-arch.patch",
                "0002-python-3.14-pt2e-union-aliases.patch",
            ],
            "makedepends": ["git", "patchelf"],
        },
        {
            "repo": "https://github.com/pytorch/ao",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "0.17.0",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert "git submodule update --init --recursive" in pkgbuild
    assert "ROCM_HOME=/opt/rocm" in pkgbuild
    assert "PYTORCH_ROCM_ARCH=gfx1151" in pkgbuild
    assert "VERSION_SUFFIX=" in pkgbuild
    assert "patchelf --set-rpath" in pkgbuild
    assert "$ORIGIN/../torch/lib" in pkgbuild


def test_torch_migraphx_readme_uses_policy_notes_override() -> None:
    readme = render_recipe_scaffolds.render_readme(
        "python-torch-migraphx-gfx1151",
        {
            "recipe_key": "native_wheels",
            "template": "python-project-torch-migraphx",
            "upstream_version": "1.2",
            "recipe_notes_override": "host-device FX lowering smoke",
            "pkgdesc": "Torch-MIGraphX",
            "url": "https://github.com/ROCm/torch_migraphx",
            "license": ["BSD-3-Clause"],
            "arch_reference": [],
            "source_patches": ["0001.patch"],
        },
        {
            "repo": "https://github.com/ROCm/torch_migraphx",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "unrelated native wheel recipe notes",
        },
        "1.2",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert "host-device FX lowering smoke" in readme
    assert "unrelated native wheel recipe notes" not in readme


def test_pytorch_rocm_renderer_uses_source_patches_for_magma_fix() -> None:
    pkgbuild = render_recipe_scaffolds.render_pkgbuild(
        "python-pytorch-opt-rocm-gfx1151",
        {
            "recipe_key": "pytorch",
            "template": "python-project-pytorch-rocm",
            "upstream_version": "2.11.0",
            "pkgdesc": "PyTorch ROCm",
            "url": "https://pytorch.org",
            "license": ["BSD-3-Clause-Modification"],
            "src_subdir": "pytorch",
            "source_refs": [
                "pytorch::git+https://github.com/ROCm/pytorch.git#commit=8543095e3275db694084a6679bd5b61f7d2ece76"
            ],
            "source_patches": [
                "0001-setup-allow-skipping-build-deps.patch",
                "0002-use-wide-magma-version-encoding.patch",
                "0003-target-numpy-2-c-api.patch",
                "0004-drop-hip-clang-abi-compat-flag.patch",
                "0005-enable-ck-gemm-on-gfx1151.patch",
            ],
        },
        {
            "repo": "https://github.com/ROCm/pytorch.git",
            "method": "pip",
            "phase": "package",
            "steps": [],
            "depends_on": [],
            "notes": "",
        },
        "2.11.0",
        {
            "recipe_repo": "https://github.com/paudley/ai-notes",
            "recipe_subdir": "strix-halo",
            "recipe_author": "Blackcat Informatics Inc.",
        },
    )

    assert "0002-use-wide-magma-version-encoding.patch" in pkgbuild
    assert '_apply_patch_if_needed "0001-setup-allow-skipping-build-deps.patch"' in pkgbuild
    assert '_apply_patch_if_needed "0002-use-wide-magma-version-encoding.patch"' in pkgbuild
    assert '_apply_patch_if_needed "0003-target-numpy-2-c-api.patch"' in pkgbuild
    assert '_apply_patch_if_needed "0004-drop-hip-clang-abi-compat-flag.patch"' in pkgbuild
    assert '_apply_patch_if_needed "0005-enable-ck-gemm-on-gfx1151.patch"' in pkgbuild
    assert "patch --dry-run -R -Np1" in pkgbuild
    assert "aten/src/ATen/native/hip/linalg/BatchLinearAlgebra.cpp" not in pkgbuild
    assert "text = text.replace(" in pkgbuild
    assert "hip: Optional[str] = {hip!r}" in pkgbuild
    assert "rocm: Optional[str] = {rocm!r}" in pkgbuild
    assert "PYTORCH_VERSION_METADATA_MISSING" in pkgbuild
    assert "PYTORCH_HIP_VERSION_REWRITE_FAILED" in pkgbuild
    assert "PYTORCH_ROCM_VERSION_REWRITE_FAILED" in pkgbuild
    assert "NPY_TARGET_VERSION" not in pkgbuild
    assert "cmake -P build/torch/headeronly/cmake_install.cmake" in pkgbuild
    assert "cmake -P build/c10/cmake_install.cmake" in pkgbuild
    assert "cmake -P build/caffe2/cmake_install.cmake" in pkgbuild
    assert "cmake -DCMAKE_INSTALL_COMPONENT=dev -P build/cmake_install.cmake" in pkgbuild


def test_render_recipe_json_keeps_source_patches_in_one_place() -> None:
    recipe_json = json.loads(
        render_recipe_scaffolds.render_recipe_json(
            "sample-gfx1151",
            {
                "recipe_key": "sample",
                "upstream_version": "1.2.3",
                "pkgdesc": "Sample",
                "url": "https://example.invalid/sample",
                "license": ["MIT"],
                "source_patches": ["0001-sample.patch"],
                "extra_sha256sums": ["abc123"],
            },
            {
                "repo": "",
                "method": "pip",
                "phase": "package",
                "steps": [],
                "depends_on": [],
                "notes": "",
            },
            "1.2.3",
            {
                "recipe_repo": "https://github.com/paudley/ai-notes",
                "recipe_subdir": "strix-halo",
                "recipe_author": "Blackcat Informatics Inc.",
            },
        )
    )

    assert recipe_json["maintenance"]["source_patches"] == ["0001-sample.patch"]
    assert recipe_json["maintenance"]["source_patch_sha256sums"] == ["abc123"]
    assert "source_patches" not in recipe_json["policy"]
    assert "extra_sha256sums" not in recipe_json["policy"]


def test_render_recipe_json_can_override_stale_recipe_branch() -> None:
    recipe_json = json.loads(
        render_recipe_scaffolds.render_recipe_json(
            "sample-gfx1151",
            {
                "recipe_key": "sample",
                "upstream_version": "1.2.3",
                "pkgdesc": "Sample",
                "url": "https://example.invalid/sample",
                "license": ["MIT"],
                "recipe_branch_override": "v1.2.3",
            },
            {
                "repo": "https://example.invalid/sample.git",
                "branch": "v1.0.0",
                "method": "pip",
                "phase": "package",
                "steps": [],
                "depends_on": [],
                "notes": "",
            },
            "1.2.3",
            {
                "recipe_repo": "https://github.com/paudley/ai-notes",
                "recipe_subdir": "strix-halo",
                "recipe_author": "Blackcat Informatics Inc.",
            },
        )
    )

    assert recipe_json["recipe"]["branch"] == "v1.2.3"
    assert "recipe_branch_override" not in recipe_json["policy"]


def test_render_recipe_json_treats_empty_extra_sources_as_patch_checksums() -> None:
    recipe_json = json.loads(
        render_recipe_scaffolds.render_recipe_json(
            "sample-gfx1151",
            {
                "recipe_key": "sample",
                "upstream_version": "1.2.3",
                "pkgdesc": "Sample",
                "url": "https://example.invalid/sample",
                "license": ["MIT"],
                "source_patches": ["0001-sample.patch"],
                "extra_sources": [],
                "extra_sha256sums": ["abc123"],
            },
            {
                "repo": "",
                "method": "pip",
                "phase": "package",
                "steps": [],
                "depends_on": [],
                "notes": "",
            },
            "1.2.3",
            {
                "recipe_repo": "https://github.com/paudley/ai-notes",
                "recipe_subdir": "strix-halo",
                "recipe_author": "Blackcat Informatics Inc.",
            },
        )
    )

    assert recipe_json["maintenance"]["source_patches"] == ["0001-sample.patch"]
    assert recipe_json["maintenance"]["source_patch_sha256sums"] == ["abc123"]
    assert "extra_sources" in recipe_json["policy"]
    assert "extra_sha256sums" not in recipe_json["policy"]


def test_render_source_refs_treats_empty_extra_sources_as_source_patches() -> None:
    source_refs, sha256sums = render_recipe_scaffolds.render_source_refs(
        {
            "template": "python-project",
            "src_subdir": "sample",
            "source_patches": ["0001-sample.patch"],
            "extra_sources": [],
            "extra_sha256sums": ["abc123"],
        },
        {"repo": "https://example.invalid/sample.git"},
    )

    assert source_refs == "(sample::git+https://example.invalid/sample.git 0001-sample.patch)"
    assert sha256sums == "(SKIP abc123)"


def test_render_recipe_json_keeps_explicit_extra_source_checksums_in_policy() -> None:
    recipe_json = json.loads(
        render_recipe_scaffolds.render_recipe_json(
            "sample-gfx1151",
            {
                "recipe_key": "sample",
                "upstream_version": "1.2.3",
                "pkgdesc": "Sample",
                "url": "https://example.invalid/sample",
                "license": ["MIT"],
                "source_patches": ["0001-sample.patch"],
                "extra_sources": ["extra-data.tar.gz"],
                "extra_sha256sums": ["abc123"],
            },
            {
                "repo": "",
                "method": "pip",
                "phase": "package",
                "steps": [],
                "depends_on": [],
                "notes": "",
            },
            "1.2.3",
            {
                "recipe_repo": "https://github.com/paudley/ai-notes",
                "recipe_subdir": "strix-halo",
                "recipe_author": "Blackcat Informatics Inc.",
            },
        )
    )

    assert recipe_json["maintenance"]["source_patches"] == ["0001-sample.patch"]
    assert "source_patch_sha256sums" not in recipe_json["maintenance"]
    assert recipe_json["policy"]["extra_sources"] == ["extra-data.tar.gz"]
    assert recipe_json["policy"]["extra_sha256sums"] == ["abc123"]

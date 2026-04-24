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


def test_compiler_env_leaves_ccache_storage_to_host_configuration() -> None:
    snippet = render_recipe_scaffolds.compiler_env_snippet("/opt/rocm/lib/llvm/bin")

    assert "CCACHE_BASEDIR" in snippet
    assert "CCACHE_DIR" not in snippet
    assert "CCACHE_TEMPDIR" not in snippet


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
    assert "patch --dry-run -R -Np1" in pkgbuild
    assert "aten/src/ATen/native/hip/linalg/BatchLinearAlgebra.cpp" not in pkgbuild
    assert "cmake -P build/torch/headeronly/cmake_install.cmake" in pkgbuild
    assert "cmake -P build/c10/cmake_install.cmake" in pkgbuild
    assert "cmake -P build/caffe2/cmake_install.cmake" in pkgbuild
    assert "cmake -DCMAKE_INSTALL_COMPONENT=dev -P build/cmake_install.cmake" in pkgbuild

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools/repo_package_graph.py"
SPEC = importlib.util.spec_from_file_location("repo_package_graph", MODULE_PATH)
assert SPEC and SPEC.loader


def load_module():
    module = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = module
    SPEC.loader.exec_module(module)
    return module


def write_recipe_package(
    tmp_path: Path,
    name: str,
    *,
    depends: list[str],
    makedepends: list[str],
) -> Path:
    package_dir = tmp_path / "packages" / name
    package_dir.mkdir(parents=True)
    (package_dir / "recipe.json").write_text(
        json.dumps(
            {
                "name": name,
                "package_name": name,
                "policy": {"depends": depends},
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "PKGBUILD").write_text(
        "\n".join(
            [
                f"pkgname={name}",
                f"depends=({' '.join(depends)})" if depends else "depends=()",
                (
                    f"makedepends=({' '.join(makedepends)})"
                    if makedepends
                    else "makedepends=()"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return package_dir


def write_therock_pkgbase(tmp_path: Path) -> Path:
    package_dir = tmp_path / "packages" / "therock-gfx1151"
    package_dir.mkdir(parents=True)
    (package_dir / "PKGBUILD").write_text(
        "\n".join(
            [
                "pkgbase=therock-gfx1151",
                "pkgname=(",
                "  'rocm-core-gfx1151'",
                "  'rocblas-gfx1151'",
                "  'rocm-llvm-gfx1151'",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "manifest.json").write_text(
        json.dumps(
            {
                "pkgbase": "therock-gfx1151",
                "packages": {
                    "rocm-core-gfx1151": {"depends": []},
                    "rocblas-gfx1151": {"depends": []},
                    "rocm-llvm-gfx1151": {"depends": []},
                },
            }
        ),
        encoding="utf-8",
    )
    return package_dir


def test_discover_repo_package_roots_reads_single_and_multi_output_roots(tmp_path: Path):
    write_therock_pkgbase(tmp_path)
    write_recipe_package(
        tmp_path,
        "python-vllm-rocm-gfx1151",
        depends=["rocblas-gfx1151"],
        makedepends=["rocm-llvm-gfx1151"],
    )

    module = load_module()
    roots = module.discover_repo_package_roots(tmp_path / "packages")

    assert sorted(roots) == ["python-vllm-rocm-gfx1151", "therock-gfx1151"]
    assert roots["therock-gfx1151"].outputs == (
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "rocm-llvm-gfx1151",
    )
    assert roots["python-vllm-rocm-gfx1151"].repo_dependency_roots == {
        "therock-gfx1151"
    }


def test_discover_repo_package_roots_ignores_unrendered_therock_manifest_entries(tmp_path: Path):
    package_dir = write_therock_pkgbase(tmp_path)
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["packages"]["hipfort-gfx1151"] = {
        "depends": [],
        "files": 0,
        "rendered": False,
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    module = load_module()
    roots = module.discover_repo_package_roots(tmp_path / "packages")

    assert "hipfort-gfx1151" not in roots["therock-gfx1151"].outputs
    assert roots["therock-gfx1151"].outputs == (
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "rocm-llvm-gfx1151",
    )


def test_topologically_sort_package_roots_orders_repo_dependencies_first(tmp_path: Path):
    write_therock_pkgbase(tmp_path)
    write_recipe_package(
        tmp_path,
        "python-gfx1151",
        depends=[],
        makedepends=["rocm-llvm-gfx1151"],
    )
    write_recipe_package(
        tmp_path,
        "python-triton-gfx1151",
        depends=["python-gfx1151"],
        makedepends=[],
    )
    write_recipe_package(
        tmp_path,
        "python-vllm-rocm-gfx1151",
        depends=["python-gfx1151", "python-triton-gfx1151", "rocblas-gfx1151"],
        makedepends=[],
    )

    module = load_module()
    roots = module.discover_repo_package_roots(tmp_path / "packages")

    ordered = module.topologically_sort_package_roots(roots)

    assert ordered == [
        "therock-gfx1151",
        "python-gfx1151",
        "python-triton-gfx1151",
        "python-vllm-rocm-gfx1151",
    ]


def test_select_root_closure_for_outputs_includes_repo_local_dependencies(tmp_path: Path):
    write_therock_pkgbase(tmp_path)
    write_recipe_package(
        tmp_path,
        "python-gfx1151",
        depends=[],
        makedepends=["rocm-llvm-gfx1151"],
    )
    write_recipe_package(
        tmp_path,
        "python-vllm-rocm-gfx1151",
        depends=["python-gfx1151", "rocblas-gfx1151"],
        makedepends=[],
    )

    module = load_module()
    roots = module.discover_repo_package_roots(tmp_path / "packages")

    closure = module.select_root_closure_for_outputs(
        roots,
        ["python-vllm-rocm-gfx1151"],
    )

    assert closure == {
        "therock-gfx1151",
        "python-gfx1151",
        "python-vllm-rocm-gfx1151",
    }

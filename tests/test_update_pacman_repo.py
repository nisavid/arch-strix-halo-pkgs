import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools/update_pacman_repo.py"
SPEC = importlib.util.spec_from_file_location("update_pacman_repo", MODULE_PATH)
assert SPEC and SPEC.loader
update_pacman_repo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_pacman_repo)


def pkg(path: Path, name: str, version: str) -> update_pacman_repo.PackageInfo:
    path.touch()
    return update_pacman_repo.PackageInfo(path=path, pkgname=name, pkgver=version)


def test_merge_preserves_unrelated_existing_repo_packages(tmp_path: Path):
    incoming = [
        pkg(
            tmp_path / "python-vllm-rocm-gfx1151-0.19.0-2-x86_64.pkg.tar.zst",
            "python-vllm-rocm-gfx1151",
            "0.19.0-2",
        )
    ]
    existing = [
        pkg(
            tmp_path / "lemonade-server-10.2.0-1-x86_64.pkg.tar.zst",
            "lemonade-server",
            "10.2.0-1",
        )
    ]

    selected = update_pacman_repo.merge_package_sets(incoming, existing)

    assert set(selected) == {"python-vllm-rocm-gfx1151", "lemonade-server"}
    assert selected["lemonade-server"].path == existing[0].path


def test_merge_keeps_newer_existing_version_when_incoming_is_stale(tmp_path: Path):
    incoming = [
        pkg(
            tmp_path / "python-vllm-rocm-gfx1151-0.19.0-1-x86_64.pkg.tar.zst",
            "python-vllm-rocm-gfx1151",
            "0.19.0-1",
        )
    ]
    existing = [
        pkg(
            tmp_path / "python-vllm-rocm-gfx1151-0.19.0-2-x86_64.pkg.tar.zst",
            "python-vllm-rocm-gfx1151",
            "0.19.0-2",
        )
    ]

    selected = update_pacman_repo.merge_package_sets(incoming, existing)

    assert selected["python-vllm-rocm-gfx1151"].path == existing[0].path


def test_link_or_copy_noops_when_repo_file_is_already_selected(tmp_path: Path):
    package_path = tmp_path / "python-vllm-rocm-gfx1151-0.19.0-2-x86_64.pkg.tar.zst"
    package_path.write_text("package")

    update_pacman_repo.link_or_copy(package_path, package_path)

    assert package_path.read_text() == "package"

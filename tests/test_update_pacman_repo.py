import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
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


def test_expected_package_paths_come_from_makepkg_packagelist(tmp_path: Path, monkeypatch):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    expected_archive = package_dir / "demo-1-1-x86_64.pkg.tar.zst"
    expected_archive.touch()

    def fake_run(argv, **kwargs):
        assert argv == ["makepkg", "--packagelist"]
        assert kwargs["cwd"] == str(package_dir)
        return subprocess.CompletedProcess(argv, 0, stdout=f"{expected_archive}\n", stderr="")

    monkeypatch.setattr(update_pacman_repo.subprocess, "run", fake_run)

    assert update_pacman_repo.expected_package_paths(package_dir) == [expected_archive]


def test_expected_package_paths_fail_when_current_archive_is_missing(
    tmp_path: Path,
    monkeypatch,
):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    expected_archive = package_dir / "demo-1-2-x86_64.pkg.tar.zst"

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=f"{expected_archive}\n", stderr="")

    monkeypatch.setattr(update_pacman_repo.subprocess, "run", fake_run)

    try:
        update_pacman_repo.expected_package_paths(package_dir)
    except RuntimeError as exc:
        assert "PACKAGE_ARCHIVE_MISSING" in str(exc)
        assert str(expected_archive) in str(exc)
    else:
        raise AssertionError("expected missing current archive to fail")


def test_main_reports_missing_current_archive_without_traceback(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    package_dir = tmp_path / "pkg"
    repo_dir = tmp_path / "repo"
    package_dir.mkdir()
    expected_archive = package_dir / "demo-1-2-x86_64.pkg.tar.zst"

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=f"{expected_archive}\n", stderr="")

    monkeypatch.setattr(update_pacman_repo.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_pacman_repo.py",
            "--package-dir",
            str(package_dir),
            "--repo-dir",
            str(repo_dir),
            "--require-packagelist",
        ],
    )

    assert update_pacman_repo.main() == 2
    captured = capsys.readouterr()
    assert "PACKAGE_ARCHIVE_MISSING" in captured.err
    assert "Traceback" not in captured.err

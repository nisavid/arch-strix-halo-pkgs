from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from package_archives import PackageInfo, select_latest_by_name


def test_select_latest_by_name_uses_pacman_version_order_not_filename_order() -> None:
    older = PackageInfo(
        path=Path("python-vllm-rocm-gfx1151-0.19.0.r8.d20260317.gad42886-9-x86_64.pkg.tar.zst"),
        pkgname="python-vllm-rocm-gfx1151",
        pkgver="0.19.0.r8.d20260317.gad42886-9",
    )
    newer = PackageInfo(
        path=Path("python-vllm-rocm-gfx1151-0.19.0.r8.d20260317.gad42886-25-x86_64.pkg.tar.zst"),
        pkgname="python-vllm-rocm-gfx1151",
        pkgver="0.19.0.r8.d20260317.gad42886-25",
    )

    selected = select_latest_by_name([older, newer])

    assert selected["python-vllm-rocm-gfx1151"] == newer


def test_select_latest_by_name_keeps_each_package_independent() -> None:
    aiter = PackageInfo(
        path=Path("python-amd-aiter-gfx1151-0.1.0.r8.d20260317.gad42886-7-x86_64.pkg.tar.zst"),
        pkgname="python-amd-aiter-gfx1151",
        pkgver="0.1.0.r8.d20260317.gad42886-7",
    )
    vllm = PackageInfo(
        path=Path("python-vllm-rocm-gfx1151-0.19.0.r8.d20260317.gad42886-25-x86_64.pkg.tar.zst"),
        pkgname="python-vllm-rocm-gfx1151",
        pkgver="0.19.0.r8.d20260317.gad42886-25",
    )

    selected = select_latest_by_name([aiter, vllm])

    assert selected == {
        "python-amd-aiter-gfx1151": aiter,
        "python-vllm-rocm-gfx1151": vllm,
    }

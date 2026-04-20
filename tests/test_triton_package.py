from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_triton_pkgbuild_applies_attrs_descriptor_repr_patch() -> None:
    pkgbuild = (REPO_ROOT / "packages/python-triton-gfx1151/PKGBUILD").read_text()

    assert "def __repr__(self)" in pkgbuild
    assert "AttrsDescriptor.from_dict" in pkgbuild
    assert "python/triton/backends/compiler.py" in pkgbuild
    assert " triton/backends/compiler.py" not in pkgbuild

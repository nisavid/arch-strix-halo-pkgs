from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_triton_pkgbuild_applies_attrs_descriptor_repr_patch() -> None:
    pkgbuild = (REPO_ROOT / "packages/python-triton-gfx1151/PKGBUILD").read_text()
    repr_patch = (
        REPO_ROOT
        / "packages/python-triton-gfx1151/0003-attrs-descriptor-repr-for-inductor.patch"
    ).read_text()

    assert "pkgver=3.0.0+git0ec280cf" in pkgbuild
    assert "provides=(python-triton=3.0.0+git0ec280cf)" in pkgbuild
    assert 'patch -Np1 -i "$srcdir/0003-attrs-descriptor-repr-for-inductor.patch"' in pkgbuild
    assert "sed -i" not in pkgbuild
    assert "git cherry-pick" not in pkgbuild
    assert "def __repr__(self)" in repr_patch
    assert "AttrsDescriptor.from_dict" in repr_patch

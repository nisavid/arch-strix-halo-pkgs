from __future__ import annotations

import subprocess
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent.parent
PKGBUILD = PACKAGE_DIR / "PKGBUILD"
EXTENSION = (
    PACKAGE_DIR
    / "pkg/python-sentencepiece-gfx1151/usr/lib/python3.14/site-packages/sentencepiece/_sentencepiece.cpython-314-x86_64-linux-gnu.so"
)


def test_pkgbuild_depends_on_local_sentencepiece_runtime() -> None:
    text = PKGBUILD.read_text()
    assert "pkgrel=2" in text
    assert "depends=(gcc-libs glibc python-gfx1151)" in text


def test_built_extension_is_self_contained() -> None:
    assert EXTENSION.exists(), "build the package before validating runtime linkage"
    result = subprocess.run(
        ["readelf", "-d", str(EXTENSION)],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout
    assert "libsentencepiece.so.0" not in output
    assert "libsentencepiece_train.so.0" not in output
    assert "libprotobuf-lite" not in output

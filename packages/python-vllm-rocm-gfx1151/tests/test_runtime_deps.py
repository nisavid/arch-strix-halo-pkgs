import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"


def pkgbuild_array(name: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" "${{{name}[@]}}"'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def optdepends_by_name() -> dict[str, str]:
    entries = {}
    for entry in pkgbuild_array("optdepends"):
        name, _, reason = entry.partition(":")
        entries[name.strip()] = reason.strip()
    return entries


def test_vllm_depends_on_local_transformers_lane():
    text = PKGBUILD.read_text()
    assert "python-transformers-gfx1151" in text
    assert "python-transformers " not in text


def test_vllm_depends_on_local_mistral_common_lane():
    text = PKGBUILD.read_text()
    assert "python-mistral-common-gfx1151" in text
    assert "python-mistral-common " not in text


def test_vllm_depends_on_the_new_0_30_common_requirements():
    # vLLM 0.30.0 requirements/common.txt adds jsonschema >= 4.23.0 and
    # safetensors >= 0.6.2 as explicit entries.
    depends = pkgbuild_array("depends")

    assert "python-jsonschema" in depends
    assert "python-safetensors-gfx1151" in depends
    assert "python-safetensors" not in depends


def test_vllm_moves_gguf_to_optdepends_with_reason():
    # vLLM 0.30.0 dropped gguf from requirements/common.txt and no longer
    # imports it; GGUF loading moved to the out-of-tree vllm-gguf-plugin.
    depends = pkgbuild_array("depends")
    optdepends = optdepends_by_name()

    assert "python-gguf" not in depends
    assert "vllm-gguf-plugin" in optdepends.get("python-gguf", "")


def test_vllm_drops_diskcache_entirely():
    # vLLM 0.30.0 at ced6857a has no diskcache user: the outlines index cache
    # is vLLM's own SQLite-backed OutlinesDiskCache.
    assert "python-diskcache" not in pkgbuild_array("depends")
    assert "python-diskcache" not in optdepends_by_name()


def test_vllm_depends_carry_no_version_operators():
    # The repo package graph matches depends by exact name, so a versioned
    # entry would drop the edge to a local lane. vLLM 0.30.0 floors are
    # recorded in the package update notes instead.
    for entry in pkgbuild_array("depends") + pkgbuild_array("makedepends"):
        assert not any(op in entry for op in "<>="), entry


def test_vllm_readme_records_the_0_30_requirement_floors():
    readme = (PKGBUILD.parent / "README.md").read_text()

    assert "prometheus-fastapi-instrumentator >=8.0.0" in readme
    assert "fastapi[standard] >=0.133.0,<0.137.0" in readme
    assert "transformers >=5.10.4" in readme

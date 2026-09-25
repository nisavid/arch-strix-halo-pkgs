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


def test_vllm_depends_on_the_local_instrumentator_v8_lane():
    # vLLM 0.30.0 requires prometheus-fastapi-instrumentator >= 8.0.0, and the
    # AUR package is 7.0.0, so the dependency must name the W2A closure lane.
    depends = pkgbuild_array("depends")

    assert "python-prometheus-fastapi-instrumentator-gfx1151" in depends
    assert "python-prometheus-fastapi-instrumentator" not in depends


def test_vllm_depends_on_the_pinned_compressed_tensors_lane():
    # vLLM 0.30.0 pins compressed-tensors == 0.17.0, which the W2A closure
    # builds as python-compressed-tensors-gfx1151 0.17.0.
    depends = pkgbuild_array("depends")

    assert "python-compressed-tensors-gfx1151" in depends
    assert "python-compressed-tensors" not in depends


def test_vllm_leaves_mcp_and_llguidance_out_of_depends():
    # mcp >=2,<3 and llguidance >=1.7,<1.8 are tracked #110 gaps: Arch has
    # mcp 1.29.0 and nothing packages llguidance. vLLM 0.30.0 imports neither
    # on the `vllm serve` startup path.
    depends = pkgbuild_array("depends")

    assert "python-mcp" not in depends
    assert "python-llguidance" not in depends


def test_vllm_readme_records_the_mcp_and_llguidance_gaps():
    readme = " ".join((PKGBUILD.parent / "README.md").read_text().split())

    assert "mcp >=2.0.0,<3.0.0" in readme
    assert "llguidance >=1.7.0,<1.8.0" in readme
    assert "optdepends once packaged" in readme


def test_vllm_depends_on_the_local_w2a_closure_lanes():
    # einops, py-cpuinfo and pybase64 have no Arch sync-repo package; the
    # W2A closure builds them as -gfx1151 lanes that provide the old names.
    depends = pkgbuild_array("depends")

    for name in ("python-einops", "python-py-cpuinfo", "python-pybase64"):
        assert f"{name}-gfx1151" in depends
        assert name not in depends


def test_vllm_depends_on_its_undeclared_startup_imports():
    # At ced6857a, `vllm serve` imports these at module level before it
    # serves a request: regex (vllm/v1/worker/gpu_worker.py and others),
    # partial_json_parser (vllm/tool_parsers/utils.py through the tool parser
    # manager) and model_hosting_container_standards
    # (vllm/entrypoints/serve/sagemaker/api_router.py through
    # vllm/entrypoints/launchers/app.py).
    depends = pkgbuild_array("depends")

    assert "python-regex" in depends
    assert "python-partial-json-parser" in depends
    assert "python-model-hosting-container-standards-gfx1151" in depends


def test_vllm_leaves_optional_common_requirements_as_optdepends():
    # These common.txt entries are not imported on the startup path or on the
    # request paths the W2A scenarios exercise: OpenTelemetry is a guarded
    # import for --otlp-traces-endpoint, setproctitle is a guarded import,
    # python-json-logger is only named by a user logging config, tiktoken is
    # imported only by the Kimi-Audio tokenizer, and vLLM itself never
    # imports protobuf.
    depends = pkgbuild_array("depends")
    optdepends = optdepends_by_name()

    for name in (
        "python-opentelemetry-sdk",
        "python-opentelemetry-api",
        "python-opentelemetry-exporter-otlp",
        "python-setproctitle",
        "python-json-logger",
        "python-tiktoken",
        "python-protobuf",
    ):
        assert name not in depends
        assert optdepends.get(name), name


def test_vllm_readme_records_the_xgrammar_startup_blocker():
    readme = " ".join((PKGBUILD.parent / "README.md").read_text().split())

    assert "xgrammar >=0.2.1,<1.0.0" in readme
    assert "vllm/parser/harmony.py" in readme

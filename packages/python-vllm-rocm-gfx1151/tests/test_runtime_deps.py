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
    # serves a request: regex (vllm/v1/worker/gpu_worker.py and others) and
    # partial_json_parser (vllm/tool_parsers/utils.py through the tool parser
    # manager).
    depends = pkgbuild_array("depends")

    assert "python-regex" in depends
    assert "python-partial-json-parser" in depends


def test_vllm_depends_on_the_local_xgrammar_lane():
    # vllm/parser/__init__.py imports vllm/parser/harmony.py, which imports
    # xgrammar at module level, and the engine core, the offline LLM and the
    # API server all reach vllm.parser. No Arch package provides xgrammar, so
    # the dependency names the W2A closure lane.
    depends = pkgbuild_array("depends")

    assert "python-xgrammar-gfx1151" in depends
    assert "python-xgrammar" not in depends


def test_vllm_leaves_sagemaker_standards_out_of_depends():
    # The 0016 carry makes the model_hosting_container_standards import
    # optional, so `vllm serve` starts without it. Packaging it would pull in
    # the supervisor daemon for routes W2A does not use.
    depends = pkgbuild_array("depends")

    assert "python-model-hosting-container-standards-gfx1151" not in depends
    assert "python-model-hosting-container-standards" not in depends


def test_vllm_readme_records_the_sagemaker_standards_gap():
    readme = " ".join((PKGBUILD.parent / "README.md").read_text().split())

    assert "model-hosting-container-standards >=0.1.14,<1.0.0" in readme
    assert "SageMaker container standards are not installed" in readme


def test_0016_keeps_the_sagemaker_standards_import_optional():
    # This hunk is what lets the depends leave model-hosting-container-standards
    # out: without it, vllm/entrypoints/launchers/app.py fails to import the
    # SageMaker router and `vllm serve` cannot build its app.
    patch = (
        PKGBUILD.parent / "0016-rocm-refresh-local-carry-for-vllm-0.30.0.patch"
    ).read_text()
    router = patch.split(
        "diff --git a/vllm/entrypoints/serve/sagemaker/api_router.py", 1
    )[1].split("diff --git", 1)[0]

    assert "-import model_hosting_container_standards.sagemaker as sagemaker_standards" in router
    assert "+try:\n+    import model_hosting_container_standards.sagemaker as sagemaker_standards\n+except ModuleNotFoundError:\n+    sagemaker_standards = None" in router
    assert '+            "SageMaker container standards are not installed; skipping "\n+            "SageMaker-specific API routes."' in router
    assert "+    if sagemaker_standards is None:\n+        return app\n     return sagemaker_standards.bootstrap(app)" in router


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


def test_vllm_readme_records_the_xgrammar_lane():
    readme = " ".join((PKGBUILD.parent / "README.md").read_text().split())

    assert "xgrammar >=0.2.1,<1.0.0" in readme
    assert "vllm/parser/harmony.py" in readme
    assert "python-xgrammar-gfx1151 0.2.3" in readme
    assert "Startup blocker" not in readme


def test_vllm_readme_records_the_exploratory_scenario_gaps():
    # torchaudio (Gemma 4 audio resampling), amd-quark (Quark MXFP4
    # emulation) and aiter (moe-aiter and the Triton AMD ViT wrapper) are on
    # exploratory scenario request paths only.
    readme = " ".join((PKGBUILD.parent / "README.md").read_text().split())

    for text in ("torchaudio", "amd-quark", "python-amd-aiter-gfx1151"):
        assert text in readme

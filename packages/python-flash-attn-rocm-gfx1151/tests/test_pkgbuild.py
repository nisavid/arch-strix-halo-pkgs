import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPO_ROOT / "packages/python-flash-attn-rocm-gfx1151"
PKGBUILD = PACKAGE / "PKGBUILD"
README = PACKAGE / "README.md"
RECIPE_JSON = PACKAGE / "recipe.json"
FRESHNESS_POLICY = REPO_ROOT / "policies/package-freshness.toml"
SKIP_AITER_PATCH = PACKAGE / "0001-skip-bundled-aiter-install.patch"
AMDSMI_PATCH = PACKAGE / "0002-import-amdsmi-before-torch.patch"
SYSTEM_TRITON_PATCH = PACKAGE / "0003-use-system-triton-package.patch"
GFX1151_CK_PATCH = PACKAGE / "0004-enable-gfx1151-ck-codegen.patch"
PRESERVE_CK_PATCH = PACKAGE / "0005-preserve-packaged-ck-submodule-checkout.patch"
CK_SMOKE_BUILD_PATCH = PACKAGE / "0006-limit-ck-smoke-build-to-forward-d32.patch"
CK_FWD_ARGS_PATCH = PACKAGE / "0007-adapt-ck-fwd-args-layout.patch"
CK_DISABLE_PAGED_KV_PATCH = PACKAGE / "0008-disable-ck-varlen-paged-kv-in-forward-smoke.patch"
CK_VLLM_WRAPPER_PATCH = PACKAGE / "0009-accept-vllm-varlen-wrapper-keywords.patch"


def test_pkgbuild_tracks_rocm_flash_attention_ck_experiment():
    text = PKGBUILD.read_text(encoding="utf-8")

    assert "pkgname=python-flash-attn-rocm-gfx1151" in text
    assert "pkgver=2.8.4" in text
    assert "pkgrel=10" in text
    assert "3f94643fb41bcedded28c85185a8e11d42ef1592" in text
    assert "url=https://github.com/ROCm/flash-attention" in text
    assert "FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE" in text
    assert "FLASH_ATTENTION_SKIP_CUDA_BUILD=FALSE" in text
    assert "FLASH_ATTENTION_FORCE_BUILD=TRUE" in text
    assert "FLASH_ATTENTION_CK_GENERATORS=fwd,fwd_splitkv" in text
    assert "FLASH_ATTENTION_CK_FILTER='*fp16*nbias_nmask*ndropout*'" in text
    assert "FLASH_ATTENTION_CK_NO_BWD_KVCACHE_API=TRUE" in text
    assert "FLASH_ATTENTION_CK_FORWARD_ONLY" not in text
    assert "GPU_ARCHS=gfx1151" in text
    assert "OPT_DIM=32,256" in text
    assert "pip wheel . --no-build-isolation --no-deps" in text
    assert "python -m installer --destdir=\"$pkgdir\"" in text


def test_pkgbuild_carries_gfx1151_ck_experiment():
    text = PKGBUILD.read_text(encoding="utf-8")
    ck_patch = GFX1151_CK_PATCH.read_text(encoding="utf-8")
    preserve_ck_patch = PRESERVE_CK_PATCH.read_text(encoding="utf-8")
    ck_smoke_build_patch = CK_SMOKE_BUILD_PATCH.read_text(encoding="utf-8")
    ck_fwd_args_patch = CK_FWD_ARGS_PATCH.read_text(encoding="utf-8")
    ck_disable_paged_kv_patch = CK_DISABLE_PAGED_KV_PATCH.read_text(encoding="utf-8")
    ck_vllm_wrapper_patch = CK_VLLM_WRAPPER_PATCH.read_text(encoding="utf-8")

    assert "0004-enable-gfx1151-ck-codegen.patch" in text
    assert "0005-preserve-packaged-ck-submodule-checkout.patch" in text
    assert "0006-limit-ck-smoke-build-to-forward-d32.patch" in text
    assert "0007-adapt-ck-fwd-args-layout.patch" in text
    assert "0008-disable-ck-varlen-paged-kv-in-forward-smoke.patch" in text
    assert "0009-accept-vllm-varlen-wrapper-keywords.patch" in text
    assert "FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE" in text
    assert "FLASH_ATTENTION_SKIP_CUDA_BUILD=FALSE" in text
    assert "FLASH_ATTENTION_CK_GENERATORS=fwd,fwd_splitkv" in text
    assert "FLASH_ATTENTION_CK_FILTER='*fp16*nbias_nmask*ndropout*'" in text
    assert "FLASH_ATTENTION_CK_NO_BWD_KVCACHE_API=TRUE" in text
    assert "FLASH_ATTENTION_CK_FORWARD_ONLY" not in text
    assert "GPU_ARCHS=gfx1151" in text
    assert "03ce21ddcbb75c5ac8630628a913d0b2ced4979a" in text
    assert "git reset --hard 3f94643fb41bcedded28c85185a8e11d42ef1592" in text
    assert "git clean -fdx" in text
    assert '"gfx90a", "gfx950", "gfx942", "gfx1151"' in ck_patch
    assert "--targets" in ck_patch
    assert "gfx11" in ck_patch
    assert "if not os.path.exists" in preserve_ck_patch
    assert "csrc/composable_kernel" in preserve_ck_patch
    assert "FLASH_ATTENTION_CK_GENERATORS" in ck_smoke_build_patch
    assert "FLASH_ATTENTION_CK_FILTER" in ck_smoke_build_patch
    assert "FLASH_ATTENTION_CK_NO_BWD_KVCACHE_API" in ck_smoke_build_patch
    assert "FLASH_ATTENTION_CK_HAS_SPLITKV" in ck_smoke_build_patch
    assert "FLASH_ATTENTION_CK_FORWARD_ONLY" not in ck_smoke_build_patch
    assert 'if os.path.exists("./build"):' in ck_smoke_build_patch
    assert 'shutil.rmtree("build")' in ck_smoke_build_patch
    assert 'os.makedirs("build")' in ck_smoke_build_patch
    assert 'if ck_generator == "fwd" and ck_filter:' in ck_smoke_build_patch
    assert "gen_args = list(gen_common)" in ck_smoke_build_patch
    assert 'gen_args += ["--filter", ck_filter]' in ck_smoke_build_patch
    assert 'subprocess.run(gen_args + ["-d", ck_generator], check=True)' in ck_smoke_build_patch
    assert "gen_args = gen_common" not in ck_smoke_build_patch
    assert 'gen_common += ["--filter", ck_filter]' not in ck_smoke_build_patch
    assert "int num_splits);\n-\n+#endif" in ck_smoke_build_patch
    assert "+#ifndef FLASH_ATTENTION_CK_NO_BWD_KVCACHE_API\n         m.def(\"bwd\"" in ck_smoke_build_patch
    assert "m.def(\"fwd\", &mha_fwd" in ck_smoke_build_patch
    assert "m.def(\"varlen_fwd\", &mha_varlen_fwd" in ck_smoke_build_patch
    assert '"csrc/flash_attn_ck/mha_fwd.cpp", "csrc/flash_attn_ck/mha_varlen_fwd.cpp"' in ck_smoke_build_patch
    assert 'if "fwd_appendkv" in ck_generators:' in ck_smoke_build_patch
    assert 'if "fwd_splitkv" in ck_generators:' in ck_smoke_build_patch
    assert "path uses flash_attn_varlen_func" in ck_smoke_build_patch
    assert "m.def(\"bwd\", &mha_bwd" in ck_smoke_build_patch
    assert "block_scale_seqstart_q_ptr" in ck_fwd_args_patch
    assert "batch_stride_q_descale" in ck_fwd_args_patch
    assert "block_scale_size_q" in ck_fwd_args_patch
    assert "csrc/flash_attn_ck/mha_varlen_fwd.cpp" in ck_fwd_args_patch
    assert "FLASH_ATTENTION_CK_HAS_SPLITKV" in ck_disable_paged_kv_patch
    assert "does not include generated split-KV kernels" in ck_disable_paged_kv_patch
    assert "fmha_fwd_splitkv" in ck_disable_paged_kv_patch
    for keyword in [
        "cu_seqlens_k=None",
        "out=None",
        "seqused_k=None",
        "leftpad_k=None",
        "return_softmax_lse=False",
        "scheduler_metadata=None",
        "fa_version=None",
        "q_descale=None",
        "k_descale=None",
        "v_descale=None",
        "num_splits=None",
        "s_aux=None",
    ]:
        assert keyword in ck_vllm_wrapper_patch
    assert "-    cu_seqlens_k," in ck_vllm_wrapper_patch
    assert "-    max_seqlen_q," in ck_vllm_wrapper_patch
    assert "-    max_seqlen_k," in ck_vllm_wrapper_patch
    assert "+    cu_seqlens_k=None," in ck_vllm_wrapper_patch
    assert "+    max_seqlen_q=None," in ck_vllm_wrapper_patch
    assert "+    max_seqlen_k=None," in ck_vllm_wrapper_patch
    assert "return_softmax_lse=True is not supported" in ck_vllm_wrapper_patch
    assert "scheduler_metadata is not supported" in ck_vllm_wrapper_patch
    assert "fa_version values other than 2 are not supported" in ck_vllm_wrapper_patch
    assert "for descale_name, descale in (" in ck_vllm_wrapper_patch
    assert '("q_descale", q_descale)' in ck_vllm_wrapper_patch
    assert '("k_descale", k_descale)' in ck_vllm_wrapper_patch
    assert '("v_descale", v_descale)' in ck_vllm_wrapper_patch
    assert "if not torch.all(descale == 1):" in ck_vllm_wrapper_patch
    assert "tensors other than all-ones are not supported" in ck_vllm_wrapper_patch
    assert "num_splits values other than 0 or 1 are not supported" in ck_vllm_wrapper_patch
    assert "s_aux is not supported" in ck_vllm_wrapper_patch
    assert "max_seqlen_q and max_seqlen_k are required" in ck_vllm_wrapper_patch
    assert 'raise ValueError("cu_seqlens_k or seqused_k must be provided")' in ck_vllm_wrapper_patch
    assert "torch.zeros_like(cu_seqlens_q)" in ck_vllm_wrapper_patch
    assert "if block_table is not None:" in ck_vllm_wrapper_patch
    assert "torch.cumsum(seqused_k, dim=0)" in ck_vllm_wrapper_patch
    assert "seqused_k=seqused_k" in ck_vllm_wrapper_patch
    assert "leftpad_k=leftpad_k" in ck_vllm_wrapper_patch
    assert "        seqused_k," in ck_vllm_wrapper_patch
    assert "        leftpad_k," in ck_vllm_wrapper_patch
    assert "        block_table," in ck_vllm_wrapper_patch
    assert "        torch.is_grad_enabled()," in ck_vllm_wrapper_patch
    assert "result = FlashAttnVarlenFunc.apply(" in ck_vllm_wrapper_patch
    assert "        block_table,\n+        seqused_k,\n+        leftpad_k,\n         torch.is_grad_enabled()," in ck_vllm_wrapper_patch
    assert "out.copy_(result)" in ck_vllm_wrapper_patch


def test_pkgbuild_uses_repo_owned_rocm_runtime_instead_of_bundled_deps():
    text = PKGBUILD.read_text(encoding="utf-8")

    for dependency in [
        "python-gfx1151",
        "python-pytorch-opt-rocm-gfx1151",
        "python-triton-gfx1151",
        "python-amd-aiter-gfx1151",
        "python-einops",
        "python-packaging",
    ]:
        assert dependency in text

    assert "pip install" not in text
    assert "third_party/aiter" not in text
    assert "triton==3.5.1" not in text


def test_patch_carry_records_rocm_runtime_boundaries():
    skip_aiter = SKIP_AITER_PATCH.read_text(encoding="utf-8")
    amdsmi = AMDSMI_PATCH.read_text(encoding="utf-8")
    system_triton = SYSTEM_TRITON_PATCH.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    recipe = json.loads(RECIPE_JSON.read_text(encoding="utf-8"))

    assert "skip bundled AITER install" in skip_aiter
    assert "third_party/aiter" in skip_aiter
    assert "import amdsmi" in amdsmi
    assert "triton==3.5.1" in system_triton
    assert '"triton"' in system_triton
    assert "FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE" in readme
    assert "FLASH_ATTENTION_TRITON_AMD_AUTOTUNE=TRUE" in readme
    assert "python-amd-aiter-gfx1151" in readme
    assert "python-flash-attn-rocm-gfx1151 2.8.4-10" in readme
    assert "flash-attn.ck.varlen-paged-kv" in readme
    assert "Qwen3.5 vLLM CK consumer remains blocked" in json.dumps(recipe)
    assert recipe["package_name"] == "python-flash-attn-rocm-gfx1151"
    assert recipe["upstream"]["commit"] == "3f94643fb41bcedded28c85185a8e11d42ef1592"
    assert "0001-skip-bundled-aiter-install.patch" in recipe["source_patches"]
    assert "0002-import-amdsmi-before-torch.patch" in recipe["source_patches"]
    assert "0003-use-system-triton-package.patch" in recipe["source_patches"]
    assert "0004-enable-gfx1151-ck-codegen.patch" in recipe["source_patches"]
    assert "0005-preserve-packaged-ck-submodule-checkout.patch" in recipe["source_patches"]
    assert "0006-limit-ck-smoke-build-to-forward-d32.patch" in recipe["source_patches"]
    assert "0007-adapt-ck-fwd-args-layout.patch" in recipe["source_patches"]
    assert "0008-disable-ck-varlen-paged-kv-in-forward-smoke.patch" in recipe["source_patches"]
    assert "0009-accept-vllm-varlen-wrapper-keywords.patch" in recipe["source_patches"]
    assert any(
        "keeping the bounded CK filter only on plain fwd generation" in note
        for note in recipe["divergence_notes"]
    )
    assert any(
        "Clears generated build/ FMHA output before CK codegen runs" in note
        for note in recipe["divergence_notes"]
    )


def test_freshness_policy_covers_flash_attention_branch():
    policy = tomllib.loads(FRESHNESS_POLICY.read_text(encoding="utf-8"))
    family = policy["families"]["flash_attention"]

    assert family["packages"] == ["python-flash-attn-rocm-gfx1151"]
    assert family["workflow"] == "upstream_source_update"
    assert family["checks"] == [
        {
            "id": "main-perf",
            "role": "primary",
            "kind": "git_ref",
            "repo": "https://github.com/ROCm/flash-attention.git",
            "ref": "refs/heads/main_perf",
            "recorded": "3f94643fb41bcedded28c85185a8e11d42ef1592",
            "comparison": "sha",
        }
    ]

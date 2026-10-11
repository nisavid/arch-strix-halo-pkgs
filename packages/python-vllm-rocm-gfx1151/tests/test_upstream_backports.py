"""Upstream backports carried on top of the 0016 carry (#183).

Patches 0017-0024 are the source hunks of eight upstream vLLM pull requests,
all in v0.31.0, ported onto v0.30.0. These tests pin which patches are
carried, what each one touches, and that the PKGBUILD applies the series in
order and detects a source tree that predates any of them.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PKGBUILD = PKG_DIR / "PKGBUILD"
README = PKG_DIR / "README.md"
RECIPE_JSON = PKG_DIR / "recipe.json"
PATCHES_DOC = REPO_ROOT / "docs/patches.md"
CARRY = "0016-rocm-refresh-local-carry-for-vllm-0.30.0.patch"
SOURCE_TARBALL_ENV = "VLLM_SOURCE_TARBALL"
REQUIRE_SOURCE_TARBALL_ENV = "REQUIRE_VLLM_SOURCE_TARBALL"


@dataclass(frozen=True)
class Backport:
    patch: str
    pull_request: int
    merge_commit: str
    files: tuple[str, ...]
    # (fixed string, path) the PKGBUILD greps for; None when the patch only
    # deletes lines.
    sentinel: tuple[str, str] | None


BACKPORTS = (
    Backport(
        "0017-backport-pixtral-axial-rope-for-transformers-5.17.patch",
        56108,
        "ec4a3a537068db40afbc9374a67da719c8c9b964",
        ("vllm/model_executor/models/pixtral.py",),
        ("def position_ids_in_meshgrid(", "vllm/model_executor/models/pixtral.py"),
    ),
    Backport(
        "0018-backport-minimax-m3-video-processor-for-transformers-5.18.patch",
        59613,
        "b558f160a2c0abcb5902acc3c91a14c38a4af173",
        ("vllm/transformers_utils/processors/minimax_m3.py",),
        None,
    ),
    Backport(
        "0019-backport-gate-per-request-multimodal-kwargs.patch",
        58830,
        "31f2e70cd3e403aaa471fb7fe3d33a7207aaf3cc",
        (
            "vllm/entrypoints/chat_utils.py",
            "vllm/entrypoints/generate/base/protocol.py",
            "vllm/entrypoints/launchers/api_server/app_state.py",
            "vllm/entrypoints/launchers/cli_args.py",
            "vllm/entrypoints/launchers/render/app_state.py",
            "vllm/entrypoints/pooling/base/serving.py",
            "vllm/entrypoints/pooling/factories.py",
            "vllm/renderers/online_renderer.py",
        ),
        (
            "def validate_request_mm_kwargs(",
            "vllm/entrypoints/generate/base/protocol.py",
        ),
    ),
    Backport(
        "0020-backport-redact-upper-case-addresses-in-error-messages.patch",
        58832,
        "379e9a1ea8a5995464d9bf775bcd36bb03a0995f",
        ("vllm/entrypoints/serve/exception_handling/utils.py",),
        ("0x[0-9a-fA-F]+>", "vllm/entrypoints/serve/exception_handling/utils.py"),
    ),
    Backport(
        "0021-backport-prefer-fresh-multimodal-payloads-over-stale-receiver-cache.patch",
        57833,
        "7268f6e38ebbb3d61700f16c638c6eba0c88bb0c",
        ("vllm/multimodal/cache.py",),
        ("Never keep a stale cached tensor under this", "vllm/multimodal/cache.py"),
    ),
    Backport(
        "0022-backport-reject-encoder-cache-hits-with-mismatched-embed-counts.patch",
        57696,
        "bbc4ddeca9ece9851aad26f03afc4bab37c6e8df",
        (
            "vllm/v1/core/encoder_cache_manager.py",
            "vllm/v1/core/sched/scheduler.py",
        ),
        (
            "def get_cached_num_encoder_embeds(",
            "vllm/v1/core/encoder_cache_manager.py",
        ),
    ),
    Backport(
        "0023-backport-frame-the-multimodal-hash-digest-input.patch",
        54283,
        "a8d1aa9c99b8698a2a78b611b7a10c30e6b3995b",
        ("vllm/multimodal/hasher.py",),
        ("def iter_value_to_bytes(", "vllm/multimodal/hasher.py"),
    ),
    Backport(
        "0024-backport-fix-incremental-multimodal-block-hashing.patch",
        51694,
        "e6c07ea5763bada5da789ed437851ee1526fd5a8",
        ("vllm/v1/core/kv_cache_utils.py",),
        (
            "from vllm.multimodal.utils import get_mm_features_in_window",
            "vllm/v1/core/kv_cache_utils.py",
        ),
    ),
)
SERIES = [CARRY, *(backport.patch for backport in BACKPORTS)]
BY_PULL_REQUEST = {backport.pull_request: backport for backport in BACKPORTS}

backports = pytest.mark.parametrize(
    "backport", BACKPORTS, ids=[f"pr{b.pull_request}" for b in BACKPORTS]
)


def pkgbuild_array(name: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" "${{{name}[@]}}"'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def header(patch: str) -> str:
    return (PKG_DIR / patch).read_text().split("\n---\n", 1)[0]


def diff_body(patch: str) -> str:
    return (PKG_DIR / patch).read_text().split("\n---\n", 1)[1]


def patched_files(patch: str) -> list[str]:
    return [
        line.split(" b/", 1)[1]
        for line in diff_body(patch).splitlines()
        if line.startswith("diff --git a/")
    ]


def changed_lines(patch: str, path: str, sign: str) -> list[str]:
    """Added ("+") or removed ("-") lines of one file's diff, without the sign."""
    section = diff_body(patch).split(f"diff --git a/{path} b/{path}\n", 1)[1]
    section = section.split("\ndiff --git ", 1)[0]
    return [
        line[1:]
        for line in section.splitlines()
        if line.startswith(sign) and not line.startswith(sign * 3)
    ]


def sentinel_function() -> str:
    text = PKGBUILD.read_text()
    start = text.index("_source_tree_has_all_source_patches() {")
    return text[start : text.index("\n}\n", start)]


def test_package_carries_the_local_carry_and_eight_backports():
    assert sorted(path.name for path in PKG_DIR.glob("*.patch")) == SERIES


def test_pkgbuild_keeps_the_release_and_bumps_pkgrel():
    script = 'source "$1" && printf "%s-%s\\n" "$pkgver" "$pkgrel"'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert out.strip() == "0.30.0-2"


def test_pkgbuild_and_recipe_list_the_series_in_order():
    recipe = json.loads(RECIPE_JSON.read_text())

    assert pkgbuild_array("source")[1:] == SERIES
    assert recipe["maintenance"]["source_patches"] == SERIES
    assert recipe["policy"]["extra_sources"] == SERIES


def test_pkgbuild_applies_the_series_in_order_on_a_clean_tree():
    text = PKGBUILD.read_text()
    start = text.index("_apply_all_source_patches() {")
    function = text[start : text.index("\n}\n", start)]
    applied = [
        line.split('"')[1]
        for line in function.splitlines()
        if line.strip().startswith("_apply_patch_if_needed ")
    ]

    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in text
    assert applied == ["${_vllm_source_patch}", *SERIES[1:]]
    assert function.index("_reset_source_tree\n  cd ") < function.index(
        "_apply_patch_if_needed "
    )


def test_backport_checksums_are_pinned_and_match_the_files():
    sums = pkgbuild_array("sha256sums")[1:]

    assert len(sums) == len(SERIES)
    assert sums[0] == "SKIP"
    for backport, pinned in zip(BACKPORTS, sums[1:], strict=True):
        actual = hashlib.sha256((PKG_DIR / backport.patch).read_bytes()).hexdigest()
        assert pinned == actual, backport.patch


@backports
def test_backport_header_names_its_upstream_change(backport):
    text = header(backport.patch)

    assert f"Upstream: vllm-project/vllm#{backport.pull_request}," in text
    assert backport.merge_commit in text
    assert "Subject: [PATCH] Backport: " in text
    assert "\nDrop at the first packaged vLLM release " in text


@backports
def test_backport_carries_only_its_source_hunks(backport):
    files = patched_files(backport.patch)

    assert files == list(backport.files)
    for path in files:
        assert path.startswith("vllm/")
        assert path.endswith(".py")


def test_no_two_patches_in_the_series_touch_the_same_file():
    owners: dict[str, str] = {}
    for patch in SERIES:
        for path in patched_files(patch):
            assert path not in owners, f"{path}: {owners[path]} and {patch}"
            owners[path] = patch


def test_pixtral_backport_leaves_out_the_rest_of_the_transformers_bump():
    # Owner decision for #183: only the pixtral.py hunks of upstream #56108.
    # Laguna stays unsupported on Transformers 5.18.
    patch = BY_PULL_REQUEST[56108].patch
    body = diff_body(patch)
    added = changed_lines(patch, "vllm/model_executor/models/pixtral.py", "+")

    assert "validate_rope" not in body
    assert "laguna" not in body.lower()
    assert "PixtralVisionRotaryEmbedding," in "\n".join(added)
    assert any(
        line.startswith("TRANSFORMERS_WITH_AXIAL_ROPE = ") and "5.17.0.dev0" in line
        for line in added
    )
    for other in SERIES:
        for path in patched_files(other):
            assert "laguna" not in path
            assert path != "vllm/transformers_utils/config.py"
            assert not path.startswith("vllm/transformers_utils/configs/")


def test_minimax_backport_only_drops_the_unused_parameter():
    backport = BY_PULL_REQUEST[59613]

    assert changed_lines(backport.patch, backport.files[0], "-") == [
        "        do_convert_rgb: bool,"
    ]
    assert changed_lines(backport.patch, backport.files[0], "+") == []


def test_mm_kwargs_backport_adds_the_opt_in_flag_and_gates_both_entry_points():
    patch = BY_PULL_REQUEST[58830].patch
    call = "        validate_request_mm_kwargs("

    assert "    trust_request_mm_kwargs: bool = False" in changed_lines(
        patch, "vllm/entrypoints/launchers/cli_args.py", "+"
    )
    # preprocess_cmpl and preprocess_chat
    assert changed_lines(patch, "vllm/renderers/online_renderer.py", "+").count(call) == 2
    # PoolingBaseServing._init_ctx
    assert (
        changed_lines(patch, "vllm/entrypoints/pooling/base/serving.py", "+").count(call)
        == 1
    )
    protocol = "\n".join(
        changed_lines(patch, "vllm/entrypoints/generate/base/protocol.py", "+")
    )
    assert "    if trust_request_mm_kwargs:\n        return\n" in protocol
    assert 'parameter="mm_processor_kwargs"' in protocol
    assert 'parameter="media_io_kwargs"' in protocol


def test_sanitization_backport_matches_upper_case_hex_digits():
    backport = BY_PULL_REQUEST[58832]

    assert changed_lines(backport.patch, backport.files[0], "-") == [
        '    message = re.sub(r" at 0x[0-9a-f]+>", ">", message)'
    ]
    assert changed_lines(backport.patch, backport.files[0], "+") == [
        '    message = re.sub(r" at 0x[0-9a-fA-F]+>", ">", message)'
    ]


def test_hasher_backport_frames_the_inline_exif_image_id():
    # v0.30.0 predates upstream #56576 (_get_image_id_bytes), so the two
    # ImageID returns are framed in place.
    backport = BY_PULL_REQUEST[54283]
    added = changed_lines(backport.patch, backport.files[0], "+")
    removed = changed_lines(backport.patch, backport.files[0], "-")
    framed = "                return _framed(exif[Image.ExifTags.Base.ImageID].bytes)"
    unframed = "                return (exif[Image.ExifTags.Base.ImageID].bytes,)"

    assert added.count(framed) == 2
    assert removed.count(unframed) == 2
    assert "_get_image_id_bytes" not in diff_body(backport.patch)
    assert "        return _framed(pickle.dumps(obj))" in added


@backports
def test_pkgbuild_sentinel_is_introduced_by_the_patch_it_guards(backport):
    if backport.sentinel is None:
        # A deletion-only patch has nothing to grep for; the neighbouring
        # patches' sentinels bracket it in the ordered series.
        assert backport.pull_request == 59613
        return
    text, path = backport.sentinel

    assert f"grep -Fq '{text}' {path}" in sentinel_function()
    assert any(text in line for line in changed_lines(backport.patch, path, "+"))
    for patch in SERIES:
        if patch == backport.patch:
            continue
        for other_path in patched_files(patch):
            assert not any(
                text in line for line in changed_lines(patch, other_path, "+")
            )


def test_readme_and_patch_inventory_describe_every_backport():
    readme = README.read_text()
    inventory = PATCHES_DOC.read_text()

    for backport in BACKPORTS:
        assert f"#{backport.pull_request}" in readme, backport.patch
        assert (
            f"(../packages/python-vllm-rocm-gfx1151/{backport.patch})" in inventory
        ), backport.patch
        assert f"#{backport.pull_request}" in inventory, backport.patch
        assert backport.merge_commit[:8] in inventory, backport.patch
    assert "--trust-request-mm-kwargs" in readme
    assert "--trust-request-mm-kwargs" in inventory
    assert "Laguna stays unsupported on Transformers 5.18" in readme


def _source_tarball() -> Path:
    candidates = [PKG_DIR / "v0.30.0.tar.gz"]
    if os.getenv(SOURCE_TARBALL_ENV):
        candidates.insert(0, Path(os.environ[SOURCE_TARBALL_ENV]))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if os.getenv(REQUIRE_SOURCE_TARBALL_ENV) == "1":
        pytest.fail("expected the vLLM v0.30.0 release tarball")
    pytest.skip(
        f"vLLM v0.30.0 release tarball is not present; set {SOURCE_TARBALL_ENV}"
    )


def _sentinels_pass(tree: Path) -> bool:
    script = 'source "$1" && cd "$2" && _source_tree_has_all_source_patches'
    return (
        subprocess.run(["bash", "-c", script, "bash", str(PKGBUILD), str(tree)]).returncode
        == 0
    )


@pytest.mark.skipif(shutil.which("patch") is None, reason="patch is not installed")
def test_series_applies_in_order_to_the_release_source(tmp_path):
    tarball = _source_tarball()
    assert hashlib.sha256(tarball.read_bytes()).hexdigest() == pkgbuild_array(
        "sha256sums"
    )[0]
    with tarfile.open(tarball) as archive:
        archive.extractall(tmp_path, filter="data")
    tree = tmp_path / "vllm-0.30.0"

    for patch in SERIES:
        # A tree that still lacks this patch, and so every later one, must be
        # detected as stale: the PKGBUILD then re-extracts and repatches.
        assert not _sentinels_pass(tree), f"before {patch}"
        result = subprocess.run(
            ["patch", "-Np1", "-i", str(PKG_DIR / patch)],
            cwd=tree,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{patch}:\n{result.stdout}{result.stderr}"
        assert "fuzz" not in result.stdout, f"{patch}:\n{result.stdout}"
        assert "offset" not in result.stdout, f"{patch}:\n{result.stdout}"

    assert _sentinels_pass(tree)
    assert not list(tree.rglob("*.rej"))
    assert not list(tree.rglob("*.orig"))
    minimax = (tree / "vllm/transformers_utils/processors/minimax_m3.py").read_text()
    preprocess = minimax.split("class MiniMaxM3VLVideoProcessor(", 1)[1]
    assert "do_convert_rgb: bool," not in preprocess

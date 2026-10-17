import hashlib
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/PKGBUILD"
RECIPE_JSON = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/recipe.json"
PACKAGE_PATCH_LINK = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/0001-server-return-selected-token-logits.patch"
PATCH_FILE = REPO_ROOT / "patches/llama.cpp-common/0001-server-return-selected-token-logits.patch"

EXPECTED_VERSION = "0.4.1"
EXPECTED_TAG = "v0.4.1"
EXPECTED_BUILD_NUMBER = 10964
EXPECTED_COMMIT = "b29c606e28a01b1bc8c1351026a0fa6e616bf6c4"
# sha256 of the GitHub archive of EXPECTED_COMMIT, recorded from the archive
# bytes; makepkg fails closed if GitHub ever serves different bytes.
EXPECTED_ARCHIVE_SHA256 = "03fb04316eb32a7b7347004a79a8dd60531c02f5a064d853fed3b53828951723"
SELECTED_LOGITS_PATCH = "0001-server-return-selected-token-logits.patch"


def test_pkgbuild_tracks_recorded_llamacpp_release():
    text = PKGBUILD.read_text()
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert EXPECTED_COMMIT in text
    assert "ggml-org/llama.cpp/archive/" in text
    assert 'rm -f "$pkgdir${install_root}/bin"/test-*' in text
    assert "$pkgdir$/opt" not in text


def _build_body(text):
    return text[text.index("build() {") : text.index("package() {")]


def test_pkgbuild_pins_llamacpp_build_identity():
    body = _build_body(PKGBUILD.read_text())
    assert f"-DLLAMA_BUILD_NUMBER={EXPECTED_BUILD_NUMBER}" in body
    assert f"-DLLAMA_BUILD_COMMIT={EXPECTED_COMMIT[:7]}" in body
    assert "-DLLAMA_BUILD_IS_DEV=OFF" in body
    recipe = json.loads(RECIPE_JSON.read_text())
    assert recipe["policy"]["upstream_tag"] == EXPECTED_TAG
    assert recipe["policy"]["upstream_revision"] == EXPECTED_COMMIT
    assert recipe["policy"]["upstream_build_number"] == EXPECTED_BUILD_NUMBER
    assert recipe["maintenance"]["authoritative_reference"] == "extra/llama-cpp"
    assert not any(ref.startswith("aur/") for ref in recipe["policy"]["arch_reference"])


def test_pkgbuild_builds_the_web_ui_from_source_like_extra_llama_cpp():
    text = PKGBUILD.read_text()
    body = _build_body(text)
    steps = ["pushd tools/ui", "npm ci --ignore-scripts", "npm run build", "popd"]
    positions = [body.index(f"\n  {step}\n") for step in steps]
    assert positions == sorted(positions)
    assert positions[0] > body.index(f'cd "$srcdir/llama.cpp-{EXPECTED_COMMIT}"')
    assert positions[-1] < body.index('cmake -B "${build_root}"')
    assert "-DLLAMA_BUILD_UI=ON" in body
    # A missing npm-built dist must not become a prebuilt-UI download.
    assert "-DLLAMA_USE_PREBUILT_UI=OFF" in body
    assert "-DLLAMA_BUILD_UI=OFF" not in text
    makedepends = re.search(r"^makedepends=\((.*)\)$", text, re.MULTILINE).group(1).split()
    assert "npm" in makedepends
    recipe = json.loads(RECIPE_JSON.read_text())
    assert "npm" in recipe["policy"]["makedepends"]
    assert any(
        "lockfile integrity hash" in note and "not a silent prebuilt download" in note
        for note in recipe["policy"]["scaffold_notes"]
    )


def test_pkgbuild_checksums_the_archive_and_the_shared_patch():
    text = PKGBUILD.read_text()
    patch_sha256 = hashlib.sha256(PATCH_FILE.read_bytes()).hexdigest()
    assert f"sha256sums=({EXPECTED_ARCHIVE_SHA256} {patch_sha256})" in text
    recipe = json.loads(RECIPE_JSON.read_text())
    assert recipe["policy"]["sha256sums"] == [EXPECTED_ARCHIVE_SHA256]
    assert recipe["maintenance"]["source_patch_sha256sums"] == [patch_sha256]


def test_pkgbuild_declares_runtime_libraries_and_moves_with_lemonade_server():
    text = PKGBUILD.read_text()
    depends = re.search(r"^depends=\((.*)\)$", text, re.MULTILINE).group(1).split()
    for dependency in ("hipblas-gfx1151", "openmp", "openssl", "rocblas-gfx1151"):
        assert dependency in depends
    # The server's --load-mode none defaults need v0.4.1, and v0.4.1 rejects
    # the --no-mmap that older servers pass.
    assert "'lemonade-server<11.9.0-2'" in re.search(r"^conflicts=\((.*)\)$", text, re.MULTILINE).group(1)


def test_pkgbuild_applies_selected_token_logits_patch():
    text = PKGBUILD.read_text()
    assert SELECTED_LOGITS_PATCH in text
    assert PACKAGE_PATCH_LINK.is_symlink()
    assert PACKAGE_PATCH_LINK.resolve() == PATCH_FILE
    assert f'patch --dry-run -R -Np1 -i "$srcdir/{SELECTED_LOGITS_PATCH}"' in text
    assert f'patch -Np1 -i "$srcdir/{SELECTED_LOGITS_PATCH}"' in text
    assert text.index("prepare()") < text.index("build()")


def test_recipe_records_selected_token_logits_patch():
    recipe = json.loads(RECIPE_JSON.read_text())
    assert recipe["maintenance"]["source_patches"] == [SELECTED_LOGITS_PATCH]


def test_selected_token_logits_patch_exposes_generic_completion_contract():
    text = PATCH_FILE.read_text()
    assert '"token_logits"' in text
    assert "selected_token_logit_output" in text
    assert "populate_selected_token_logits" in text
    assert "max_token_logits = 1024" in text
    assert '{"token", txt_valid}' in text
    assert "completion_token_output::str_to_bytes(txt)" in text
    assert "if (!slot.has_budget())" in text
    assert 'new field_json("token_logits")' in text
    assert "use_backend_sampling &= task.params.token_logits.empty();" in text
    populate_body = text[
        text.index("void populate_selected_token_logits") : text.index("void send_error")
    ]
    assert "flat token_logits array for the first" in populate_body
    assert "if (!slot.selected_token_logits.empty() || slot.task->params.token_logits.empty())" in populate_body
    assert "const int n_vocab = llama_vocab_n_tokens(vocab);" in populate_body
    assert "if (token < 0 || token >= n_vocab)" in populate_body
    assert "continue;" in populate_body
    assert "llama_get_sampled_candidates_ith" not in text
    assert "bool found" not in text
    assert "zeroentropy" not in text.lower()
    assert "9454" not in text

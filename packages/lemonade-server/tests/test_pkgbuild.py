from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/lemonade-server/PKGBUILD"
CONF = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf"
)


def test_pkgbuild_exports_system_managed_llamacpp_metadata():
    text = PKGBUILD.read_text()
    assert "LEMONADE_LLAMACPP_ROCM_VERSION=" in text
    assert "LEMONADE_LLAMACPP_VULKAN_VERSION=" in text
    assert "LEMONADE_LLAMACPP_ROCM_RELEASE_URL=" in text
    assert "LEMONADE_LLAMACPP_VULKAN_RELEASE_URL=" in text
    assert "ggml-org/llama.cpp/releases/tag/" in text


def test_built_package_installs_system_managed_llamacpp_metadata():
    text = CONF.read_text()
    assert "LEMONADE_LLAMACPP_ROCM_VERSION=b8611" in text
    assert "LEMONADE_LLAMACPP_VULKAN_VERSION=b8611" in text
    assert "LEMONADE_LLAMACPP_ROCM_RELEASE_URL=https://github.com/ggml-org/llama.cpp/releases/tag/b8611" in text
    assert "LEMONADE_LLAMACPP_VULKAN_RELEASE_URL=https://github.com/ggml-org/llama.cpp/releases/tag/b8611" in text

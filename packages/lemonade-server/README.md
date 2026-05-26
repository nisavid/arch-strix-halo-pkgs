# lemonade-server

## Maintenance Snapshot

- Role: `server-runtime`
- Optional backends:
  - `llama.cpp-hip-gfx1151`
  - `llama.cpp-vulkan-gfx1151`
- Recipe package key: `lemonade`
- Scaffold template: `lemonade-server`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/nisavid/lemonade.git`
- Package version: `10.6.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `34, 35, 36`
- Recipe dependencies: `therock, llamacpp`
- Recorded reference packages: `aur/lemonade-server, aur/lemonade-desktop`
- Authoritative reference package: `aur/lemonade-server`
- Advisory reference packages: `aur/lemonade-desktop`
- Applied source patch files/actions: `5`

## Recipe notes

Lemonade is a unified inference server wrapping llama.cpp (GPU/CPU),
FLM (NPU), and ONNX backends behind an OpenAI-compatible API.

The project split in v10: the git repo (v10.0.0) is a C++ server,
while the Python SDK is published separately as lemonade-sdk on PyPI
(v9.1.4). The SDK handles llama-server process management, model
downloads, .env loading, and hardware detection.

Version pin fixes: lemonade-sdk pins huggingface-hub==0.33.0,
onnx==1.18.0, transformers<=4.53.2 which conflict with vLLM.
Reinstalling at compatible versions resolves conflicts.

## Scaffold notes

- Server/runtime package; llama.cpp backends are optdepends, not hard deps.
- Pinned to nisavid/lemonade main commit b608a74d0604f96786de59d65cb0ba27b05db0c6, whose CMake project version is 10.6.0.
- Uses upstream's lemond.service unit name; do not ship the pre-10.3 lemonade-server.service name in this package.
- Installs /etc/lemonade/conf.d/10-llamacpp-gfx1151.conf so the packaged ROCm and Vulkan llama.cpp wrapper binaries are exposed to the service as system-managed backends.
- The system-managed backend patch also folds in the config-load and CLI/backend-table changes needed for those service-provided overrides to stay visible after config.json already exists.
- Export the packaged llama.cpp revision and ggml release URL in the system-managed backend env overlay so the GUI shows the packaged backend metadata instead of upstream downloader defaults.
- Pkgrel 2 replaces shell-interpolated llama.cpp --version probing with Lemonade's argv-based ProcessManager capture path in the system-managed backend patch.
- Temporarily carries config-load diagnostics to verify the service cache path, config existence checks, and parse/merge path while debugging config reset behavior.
- Keeps legacy environment migration as a sparse overlay so service-provided backend paths override config.json without resetting unrelated user config keys to defaults.

## Intentional Divergences

- This custom build treats the ROCm and Vulkan llama.cpp backends as packaged system-managed backends rather than Lemonade-managed runtime downloads.
- Carries local patches for Linux XDNA2 detection and the system-managed llama.cpp backend story that are specific to this Strix Halo packaging lane.
- Builds from the nisavid/lemonade fork so this package can consume local upstream fixes before they are available from the canonical Lemonade repository.

## Update Notes

- Track the nisavid/lemonade fork's main branch as the package source lane; use canonical upstream releases and AUR packages as baselines for compatibility review.
- Keep packaging and app/server split aligned with upstream naming changes; do not drift back toward the old lemonade-desktop era naming model.
- Re-test that LEMONADE_LLAMACPP_*_BIN service overrides still apply even when /var/lib/lemonade/config.json already exists.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

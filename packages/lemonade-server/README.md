# lemonade-server

## Maintenance Snapshot

- Role: `server-runtime`
- Optional backends:
  - `llama.cpp-hip-gfx1151`
  - `llama.cpp-vulkan-gfx1151`
- Recipe package key: `lemonade`
- Scaffold template: `lemonade-server`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/lemonade-sdk/lemonade.git`
- Package version: `10.2.0`
- Recipe revision: `ad42886 (20260317, 8 path commits)`
- Recipe steps: `33, 34, 35`
- Recipe dependencies: `therock, llamacpp`
- Recorded reference packages: `aur/lemonade-server, aur/lemonade-desktop`
- Authoritative reference package: `aur/lemonade-server`
- Advisory reference packages: `aur/lemonade-desktop`
- Applied source patch files/actions: `4`

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
- Pinned to the v10.2.0 upstream release tarball to keep the first-pass metadata reproducible.
- Installs /etc/lemonade/conf.d/10-llamacpp-gfx1151.conf so the packaged ROCm and Vulkan llama.cpp wrapper binaries are exposed to the service as system-managed backends.
- The system-managed backend patch also folds in the config-load and CLI/backend-table changes needed for those service-provided overrides to stay visible after config.json already exists.
- Export the packaged llama.cpp revision and ggml release URL in the system-managed backend env overlay so the GUI shows the packaged backend metadata instead of upstream downloader defaults.

## Intentional Divergences

- This custom build treats the ROCm and Vulkan llama.cpp backends as packaged system-managed backends rather than Lemonade-managed runtime downloads.
- Carries local patches for Linux XDNA2 detection and the system-managed llama.cpp backend story that are specific to this Strix Halo packaging lane.

## Update Notes

- Update against the current upstream monorepo release and the AUR server package first, then re-check whether any local backend-management or NPU-detection patches are still needed.
- Keep packaging and app/server split aligned with upstream naming changes; do not drift back toward the old lemonade-desktop era naming model.
- Re-test that LEMONADE_LLAMACPP_*_BIN service overrides still apply even when /var/lib/lemonade/config.json already exists.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

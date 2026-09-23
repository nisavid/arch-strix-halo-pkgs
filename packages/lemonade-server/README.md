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
- Package version: `11.7.0`
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
- Pinned to nisavid/lemonade main commit 3d5991033e4cb28152ace4013f7f22a52c3bd617, whose CMake project version is 11.7.0. The pin is the lemonade entry in the [source_pins] table of policies/recipe-packages.toml, so lemonade-server and lemonade-app always build the same fork commit.
- Configures with BUILD_TESTING=OFF; upstream 11.7 includes CTest, and the distro build does not need its C++ test binaries.
- Uses upstream's lemond.service unit name; do not ship the pre-10.3 lemonade-server.service name in this package.
- Installs /etc/lemonade/conf.d/10-llamacpp-gfx1151.conf so the packaged ROCm and Vulkan llama.cpp wrapper binaries are exposed to the service as system-managed backends. lemond reads LEMONADE_LLAMACPP_*_BIN from the environment ahead of config.json on every backend lookup, so the refreshed system-managed backend patch no longer carries the older config-load environment overlay or the CLI backend-table change.
- Exports the packaged llama.cpp revision and ggml release URL in the same conf.d file so the GUI shows the packaged backend metadata instead of upstream downloader defaults.
- The system-managed backend patch probes llama-server --version through Lemonade's argv-based ProcessManager capture path, not a shell.
- Marks /etc/lemonade/conf.d/zz-secrets.conf as a backup file so an upgrade keeps local API-key edits. 10-llamacpp-gfx1151.conf stays package-owned so each release refreshes the backend metadata.
- Replaces upstream's full /usr/share/lemonade/defaults.json with a sparse distro overlay: offline, no_fetch_executables, an explicit ROCm llama.cpp backend, prefer_system off, the packaged rocm_bin and vulkan_bin paths, and --no-mmap llama.cpp args. With --no-mmap set, lemond omits its iGPU --load-mode default, which the packaged llama.cpp b9442 does not accept. lemond merges the overlay over its built-in defaults and under config.json, so keys an existing config.json already sets still win. The overlay leaves host, port, broadcast, and API-key settings to the host.
- Installs /usr/lib/systemd/system/lemond.service.d/20-no-remote-model-fetch.conf, which sets HF_ENDPOINT, MODELSCOPE_ENDPOINT, and MODEL_ENDPOINT to a refused loopback port. lemond's model registry reads HF_ENDPOINT and MODELSCOPE_ENDPOINT on every request, and llama-server children inherit all three. MODEL_ENDPOINT is required because llama-server reads it ahead of HF_ENDPOINT, so an inherited MODEL_ENDPOINT would otherwise bypass the HF_ENDPOINT blackhole. A value set in /etc/lemonade/conf.d overrides the drop-in, because systemd applies EnvironmentFile after Environment.
- Removes /usr/share/metainfo because the web-app MetaInfo names lemonade-web-app.desktop as its launchable, and this package removes that desktop entry.

## Intentional Divergences

- This custom build treats the ROCm and Vulkan llama.cpp backends as packaged system-managed backends rather than Lemonade-managed runtime downloads.
- Carries local patches for Linux XDNA2 detection and the system-managed llama.cpp backend story that are specific to this Strix Halo packaging lane.
- Builds from the nisavid/lemonade fork so this package can consume local upstream fixes before they are available from the canonical Lemonade repository.
- Ships offline, no-fetch distro defaults and a systemd drop-in that points the Hugging Face, ModelScope, and llama.cpp model endpoints (HF_ENDPOINT, MODELSCOPE_ENDPOINT, and MODEL_ENDPOINT) at a refused loopback port, so lemond does not download models or backend executables on its own.

## Update Notes

- Track the nisavid/lemonade fork's main branch as the package source lane; use canonical upstream releases and AUR packages as baselines for compatibility review.
- Keep packaging and app/server split aligned with upstream naming changes; do not drift back toward the old lemonade-desktop era naming model.
- Re-test that LEMONADE_LLAMACPP_*_BIN service overrides still apply even when /var/lib/lemonade/config.json already exists.
- On 2026-05-26, adopted nisavid/lemonade fork main 13b1af25f84cf08ad5f8bf0ec58980bdfc09c9e7 so the server and app packages stay pinned to the same fork source while the app hides adapter controls for base llamacpp models.
- On 2026-05-27, bumped the server package release to refresh packaged system-managed llama.cpp backend metadata for the b9352 HIP and Vulkan backends.
- On 2026-05-28, bumped the server package release to refresh packaged system-managed llama.cpp backend metadata for the b9357 HIP and Vulkan backends.
- On 2026-05-31, bumped the server package release to refresh packaged system-managed llama.cpp backend metadata for the b9442 HIP and Vulkan backends.
- On 2026-06-15, adopted nisavid/lemonade fork main e18b9c1e352df8ab5aff2ff353402f1ec77c47f2, which syncs upstream Lemonade v10.7.0.
- On 2026-09-22, repinned the source to nisavid/lemonade fork main at Lemonade 11.7.0; the fork commit contains upstream v11.7.0 (2b6a7d7), and the lemonade entry in [source_pins] holds the selected commit. Refreshed patches 0002-0004 for the new base, and added the zz-secrets.conf backup entry, the offline distro defaults, and the model-endpoint drop-in. Issue 137 pins the frozen fork commit 3d5991033; issue 139 tracks the build, publish, install, and host validation.
- On 2026-09-23, released 11.7.0-2 with patch 0005, which makes RecipeOptions::inherit tokenize merged *_args without keeping quotes. At 3d5991033 the merge wrapped quoted values in their quote characters and then quoted them again, so llama-server received a literal '{"preserve_thinking":true}' for the qwen35 and qwen35moe --chat-template-kwargs architecture default and exited. The distro defaults always set --no-mmap, so every qwen35 and qwen35moe model failed to load. The regression is fork-only: fork commit e3d08ffa6 added quote_custom_arg_value to map_to_args_string, which stacks on upstream's keep_quotes=true merge (lemonade-sdk/lemonade#1920), while upstream v11.6.0, v11.7.0, and v11.9.0 produce the correct argv. The fork fix is nisavid/lemonade#168; drop patch 0005 at the Lemonade repin to a fork commit that contains #168, which is the upstream-synced fork main that the issue 141 (M6) repackage adopts. Upstream #3265 (7b5657d80, first released in v11.8.0) is context only: it moves the merge to recipe_arg_resolver.h, which still keeps quotes, so it does not fix the fork. Issues 139 and 140 track the regression.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

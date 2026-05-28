# stable-diffusion.cpp-vulkan-gfx1151

## Maintenance Snapshot

- Recipe package key: `stable_diffusion_cpp`
- Scaffold template: `stable-diffusion-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/leejet/stable-diffusion.cpp.git`
- Package version: `r656.g0e4ee04`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `35, 37`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/stable-diffusion.cpp-vulkan-git, aur/stable-diffusion.cpp-git`
- Authoritative reference package: `aur/stable-diffusion.cpp-vulkan-git`
- Advisory reference packages: `aur/stable-diffusion.cpp-git`
- Applied source patch files/actions: `1`

## Recipe notes

This package supplies stable-diffusion.cpp as the Blackcat Vulkan image
generation engine for the Strix Halo stack. The source follows
leejet/stable-diffusion.cpp master at
`0e4ee04488159b81d95a9ffcd983a077fd5dcb77` (`r656.g0e4ee04`).
The current source includes Microsoft Lens support, GPT-OSS tokenizer and
vocabulary additions used by Lens prompts, LTX temporal and rational latent
upscaling, LTX audio and VAE decoding improvements, highres custom sigma
support, extra VAE tiling arguments, Longcat image/edit support, TAESD preview
fixes, LoRA directory scans that skip permission-denied entries, a simplified
diffusion-model runner parameter flow, architecture-specific LLM norm
tensor-name resolution, and Flux2 VAE TAE selection.

The package builds the Vulkan backend with ggml, WebP, WebM, and server frontend
inputs modeled as explicit package sources and staged into the upstream
submodule paths during prepare().
At this pin, the upstream recursive git tree records mode-160000 gitlinks for
`ggml` (`0ce7ad348a3151e1da9f65d962044546bcaad421`),
`examples/server/frontend` (`797ccf80825cc035508ba9b599b2a21953e7f835`),
`thirdparty/libwebm` (`5bf12267eea773a32fcf4949de52b0add158a8d5`), and
`thirdparty/libwebp` (`0c9546f7efc61eac7f79ae115c3f99c91c21c443`), matching
the explicit package source pins.
It uses the repo's amdclang/Zen 5 lane, ThinLTO, AOCL-LibM
linkage, OpenMP CPU fallback, WebP/WebM output support, and release-mode
Vulkan settings. Runtime payloads live under
`/opt/stable-diffusion.cpp-vulkan-gfx1151`, with
`sd-cli-vulkan-gfx1151` and `sd-server-vulkan-gfx1151` wrappers under
`/usr/bin`.

The SDXL CLIP-G prefix patch comes from Blackcat's recipe notes and keeps
diffusers SDXL checkpoint loading from misclassifying CLIP-G tensors as SD 1.x
unknown tensors.


## Scaffold notes

- Blackcat Vulkan engine lane for local image generation; this is an engine package, not a Python wheel.
- Models upstream's ggml, WebP, WebM, and server frontend submodule inputs as explicit package sources, then stages them into the expected submodule paths during prepare(); do not reintroduce prepare-time network submodule fetches.
- Closest current packaging reference is AUR stable-diffusion.cpp-vulkan-git, but that package is out of date and installs generic command names; keep the local package backend-specific.
- Keep the SDXL CLIP-G source patch as a package-local patch file until upstream carries an equivalent deterministic prefix rewrite.
- Use suffixed wrapper names so this package can coexist with other stable-diffusion.cpp backend variants.

## Intentional Divergences

- Installs into /opt/stable-diffusion.cpp-vulkan-gfx1151 with suffixed wrapper binaries instead of taking over generic sd-cli or sd-server names.
- Uses the Blackcat Vulkan lane with amdclang, Zen 5 flags, ThinLTO, AOCL-LibM linkage, WebP/WebM output support, and release-mode Vulkan diagnostics disabled.
- Carries Blackcat's SDXL CLIP-G prefix mapping patch because upstream master still needs the deterministic te.1 prefix rewrite for SDXL diffusers checkpoints.

## Update Notes

- Track upstream master as a pinned git snapshot until leejet/stable-diffusion.cpp publishes release tags suitable for package versioning.
- Diff against aur/stable-diffusion.cpp-vulkan-git for package layout and dependency conventions, but keep the local /opt install and suffixed wrappers to avoid CLI name collisions.
- When updating the pinned commit, re-check that 0001-sdxl-clipg-prefix-mapping.patch still applies and still guards the SDXL diffusers CLIP-G load path.
- After publish/install, smoke sd-cli-vulkan-gfx1151 and sd-server-vulkan-gfx1151 with --help or equivalent no-model startup checks before any model-generation validation claim.
- On 2026-05-15, adopted upstream master at 0b8296915c4094090cff6bd2e09a5e98288c3c7d for MultiLora handling, flow-model sampler behavior, max-VRAM segmented parameter offload support, HiDream O1 image support, model-weight mmap support, Euler CFG++ sampler support, WebP/WebM pkg-config handling, and server URL display cleanup.
- On 2026-05-19, adopted upstream master at caa823a8c06a51288f0a01bb29e9bd8bcec30a8a for LTX 2.3 support, Gradient Estimation sampler support, negative max_vram spare-VRAM budgeting, module backend assignment, restored LLM singleton dimensions, and ROCm 7.13 CI target updates.
- On 2026-05-26, adopted upstream master at 1ceb5bd9df7784bcdf67dd9ed8bf0198b542ebc9 for LTX temporal and rational latent upscaling, Longcat image/edit support, highres custom sigma and VAE tiling arguments, TAESD preview fixes, macOS rpath fixes, and Windows ROCm BLAS artifact packaging.
- On 2026-05-26 review follow-up, verified the upstream mode-160000 gitlinks at 1ceb5bd9df7784bcdf67dd9ed8bf0198b542ebc9 match the explicit ggml, sdcpp-webui, libwebm, and libwebp package source pins and are unchanged from caa823a8c06a51288f0a01bb29e9bd8bcec30a8a.
- On 2026-05-27, updated package source metadata to upstream master at 92dc7268fc4ffb0c0cc0bd52dfcefea91326e797 for Microsoft Lens support, GPT-OSS tokenizer and vocabulary additions used by Lens prompts, and permission-denied skipping in recursive LoRA directory scans.
- On 2026-05-27 source review, verified the upstream mode-160000 gitlinks at 92dc7268fc4ffb0c0cc0bd52dfcefea91326e797 match the explicit ggml, examples/server/frontend, thirdparty/libwebm, and thirdparty/libwebp package source pins, and refreshed the CLIP-G patch context so both the prefix-ordering change and Flux te1 remap apply without ignored patch hunks.
- On 2026-05-28, updated package source metadata to upstream master at 0e4ee04488159b81d95a9ffcd983a077fd5dcb77 for ROCm CI frontend-tooling preservation, diffusion-model runner parameter simplification, architecture-specific LLM norm tensor-name resolution, and Flux2 VAE TAE selection.
- On 2026-05-28 source review, verified the upstream mode-160000 gitlinks at 0e4ee04488159b81d95a9ffcd983a077fd5dcb77 match the explicit ggml, examples/server/frontend, thirdparty/libwebm, and thirdparty/libwebp package source pins, and verified the CLIP-G patch still applies without refresh.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

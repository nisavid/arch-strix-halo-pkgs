# stable-diffusion.cpp-vulkan-gfx1151

## Maintenance Snapshot

- Recipe package key: `stable_diffusion_cpp`
- Scaffold template: `stable-diffusion-cpp`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/leejet/stable-diffusion.cpp.git`
- Package version: `r593.g3d6064b`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `35, 37`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/stable-diffusion.cpp-vulkan-git, aur/stable-diffusion.cpp-git`
- Authoritative reference package: `aur/stable-diffusion.cpp-vulkan-git`
- Advisory reference packages: `aur/stable-diffusion.cpp-git`
- Applied source patch files/actions: `2`

## Recipe notes

This package supplies stable-diffusion.cpp as the Blackcat Vulkan image
generation engine for the Strix Halo stack. The source follows
leejet/stable-diffusion.cpp master at
`3d6064b37ef4607917f8acf2ca8c8906d5087413` (`r593.g3d6064b`, 2026-04-30).
The reviewed `b8bdffc..3d6064b` range includes runtime backend discovery,
VAE buffer lifetime cleanup, image metadata output, and tensor-to-image
conversion speed work.

The package builds the Vulkan backend with recursive ggml, WebP, and WebM
submodules. It uses the repo's amdclang/Zen 5 lane, ThinLTO, AOCL-LibM
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
- Uses recursive git submodules because upstream's ggml, WebP, WebM, and server frontend inputs are submodules and GitHub tarballs do not include them.
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

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

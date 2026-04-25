# lemonade-app

## Maintenance Snapshot

- Role: `desktop-app`
- Recipe package key: `lemonade`
- Scaffold template: `lemonade-app`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/lemonade-sdk/lemonade.git`
- Package version: `10.2.0`
- Recipe revision: `a188f9e (20260424, 10 path commits)`
- Recipe steps: `34, 35, 36`
- Recipe dependencies: `therock, llamacpp`
- Recorded reference packages: `aur/lemonade-desktop, aur/lemonade-server`
- Authoritative reference package: `aur/lemonade-desktop`
- Advisory reference packages: `aur/lemonade-server`
- Applied source patch files/actions: `0`

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

- Electron desktop package split from the same lemonade monorepo.
- Install a /usr/bin/lemonade-app wrapper that launches the packaged Electron binary from /usr/share/lemonade-app so the shipped desktop entry resolves on PATH.
- Pinned to the v10.2.0 upstream release tarball to keep the first-pass metadata reproducible.

## Intentional Divergences

- Tracks the renamed upstream lemonade-app payload while still providing lemonade-desktop compatibility for local package replacement.
- Builds the Electron app from the upstream monorepo release tarball rather than relying on an auto-updated runtime payload.

## Update Notes

- Update against the closest desktop/app packaging lane first, then re-check any server-side shared assets the app package expects from the monorepo build.
- Keep the provides/conflicts story accurate while Arch/AUR naming remains in transition.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

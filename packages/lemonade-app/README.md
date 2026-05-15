# lemonade-app

## Maintenance Snapshot

- Role: `desktop-app`
- Recipe package key: `lemonade`
- Scaffold template: `lemonade-app`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/nisavid/lemonade.git`
- Package version: `10.4.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
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

- Tauri desktop package split from the same lemonade monorepo.
- Install a /usr/bin/lemonade-app wrapper that launches the packaged Tauri binary from /usr/share/lemonade-app so the shipped desktop entry resolves on PATH.
- Pinned to nisavid/lemonade main commit 8bb0f7408e37c764d7172b24ad190a5014bc6a4d, whose CMake project version remains 10.4.0.

## Intentional Divergences

- Tracks the renamed upstream lemonade-app payload while still providing lemonade-desktop compatibility for local package replacement.
- Builds the Tauri app from the maintained forked monorepo source rather than relying on an auto-updated runtime payload.

## Update Notes

- Track the nisavid/lemonade fork's main branch as the package source lane; use the closest desktop/app packages as packaging baselines only.
- Keep the provides/conflicts story accurate while Arch/AUR naming remains in transition.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

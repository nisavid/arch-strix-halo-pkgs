# python-triton-gfx1151

## Maintenance Snapshot

- Recipe package key: `triton`
- Scaffold template: `python-project-triton-rocm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/triton.git`
- Package version: `3.0.0+git0ec280cf`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `15, 16, 17`
- Recipe dependencies: `therock, pytorch`
- Recorded reference packages: `extra/python-triton, cachyos-extra-znver4/python-triton`
- Authoritative reference package: `extra/python-triton`
- Advisory reference packages: `cachyos-extra-znver4/python-triton`
- Applied source patch files/actions: `3`

## Recipe notes

ROCm performance fork of Triton. Keep this package on ROCm/triton main_perf
and its compatible sidecar LLVM path; do not point it at TheRock LLVM.

The gfx1151 Inductor carry is `0003-attrs-descriptor-repr-for-inductor.patch`,
listed in `maintenance.source_patches` and applied by the renderer in
`prepare()`. Without that patch, torch Inductor can serialize
`AttrsDescriptor` with the default angle-bracket object repr and emit invalid
generated Python.

When switching compilation configurations, clear stale Inductor and Triton
caches before diagnosing mismatched guard-expression failures. The vLLM
compile cache is config-hash-keyed and does not require routine manual
clearing.


## Scaffold notes

- Authoritative base: Arch python-triton 3.5.1-4 for distro integration and Python-3.14 carry patches.
- The recipe intentionally swaps in ROCm/triton main_perf instead of upstream triton-lang/triton. That makes Arch's package an advisory base rather than a source-identical one.
- Do not point Triton at TheRock's LLVM. The recipe notes that this ROCm fork still expects an older LLVM API line and must use its own compatible LLVM path instead.
- The renderer must include the package source patches in `prepare()` for this package. The `AttrsDescriptor.__repr__` edit is a runtime correctness patch, not cosmetic metadata; if it is absent from the installed package, torch.compile / Inductor can emit syntactically invalid generated Python.
- Rebuild and reinstall `python-triton-gfx1151` after patch-carry changes before treating compiled vLLM probes as repaired on the host.

## Intentional Divergences

- Uses Arch's Python packaging and integration baseline but deliberately swaps in ROCm/triton main_perf for the source lane.
- Builds Triton's compatible sidecar LLVM instead of trying to force the ROCm fork onto TheRock's installed LLVM API line.

## Update Notes

- Check Arch's current Triton Python packaging first for Python-version fixes and install layout changes, then re-evaluate whether ROCm/triton still needs its separate LLVM lane.
- Keep pkgver and provides aligned with the ROCm fork's generated wheel metadata from python/setup.py; do not reuse Arch's triton-lang release version when the source lane is ROCm/triton main_perf.
- Keep local source edits as patch files; this package is a likely upstream-candidate area.
- The `AttrsDescriptor.__repr__` patch is runtime correctness carry. If it is absent from the installed package, torch.compile / Inductor can emit syntactically invalid generated Python.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.

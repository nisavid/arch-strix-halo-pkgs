# python-pybase64-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/mayeut/pybase64`
- Package version: `1.5.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `aur/python-pybase64`
- Authoritative reference package: `aur/python-pybase64`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

pybase64 supplies the SIMD Base64 codec that vLLM uses for embedded media,
pooling outputs and prompt embeddings. vLLM 0.30.0 imports it while `vllm
serve` starts. The package builds the C extension and the bundled libbase64
static library on the local amdclang native-wheel lane.

Upstream setup.py marks the extension optional unless `CIBUILDWHEEL=1`, and
silently installs a pure-Python fallback when libbase64 fails to build. This
package sets `CIBUILDWHEEL=1` so that fallback can never ship.


## Scaffold notes

- Part of the vLLM runtime dependency closure (#110).
- Renders through the Blackcat native-wheel lane; Blackcat's recipe does not name this package.
- setup.py drives cmake for the bundled libbase64, so cmake is a makedepend.

## Intentional Divergences

- Tracks upstream pybase64 1.5.0 from PyPI instead of the AUR 1.4.2 package, so the vLLM package does not depend on a foreign AUR provider.
- Builds the C extension and its bundled libbase64 through the Blackcat native-wheel compiler lane with amdclang and Zen 5 flags; libbase64 still picks its SIMD codec at run time.
- Sets CIBUILDWHEEL=1 so a failed libbase64 or extension build fails the package instead of falling back to pure Python.
- Depends on glibc and python-gfx1151 only. Upstream 1.5.0 declares no runtime requirements; the AUR package's python-typing_extensions dependency is not needed.

## Update Notes

- Check vLLM's requirements/common.txt (pybase64 with no version bound at vLLM 0.30.0) and the upstream changelog together before updating.
- Re-check setup.py before updating: the extension must stay mandatory under CIBUILDWHEEL=1, and libbase64 must still build with cmake.
- After publishing a rebuilt package, verify `import pybase64`, that `pybase64._pybase64` loads, and a `pybase64.b64encode` and `b64decode` round trip through the installed local Python lane.
- On 2026-09-25, added at 1.5.0 for the generation-C W2A closure (#110, #111). vLLM 0.30.0 imports pybase64 from `vllm/renderers/embed_utils.py`, which `vllm serve` imports at startup, and in its media and pooling paths. It is built in the rootless C build root in the vLLM lease job.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.

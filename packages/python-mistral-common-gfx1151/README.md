# python-mistral-common-gfx1151

## Maintenance Snapshot

- Package origin: local closure package
- Build method: `python -m build`
- Upstream repo: `https://github.com/mistralai/mistral-common`
- Upstream version: `1.11.1`
- Recorded reference packages: `aur/python-mistral-common`
- Authoritative reference package: `aur/python-mistral-common`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Why This Package Exists

The host `python-mistral-common 1.8.6-1` package is too old for the local
`python-transformers-gfx1151 5.5.4` lane. Transformers now imports
`ReasoningEffort` from `mistral_common.protocol.instruct.request`, and that
symbol first appears in the `mistral-common >= 1.10.0` lane. The package now
tracks the newer PyPI `1.11.1` release while preserving that compatibility
boundary.

Without a local closure package, Gemma 4 safetensors smoke tests in vLLM get
all the way through model load and then fail during processor initialization.

## Intentional Divergences

- Tracks upstream `mistral-common 1.11.1` from PyPI instead of the older AUR
  baseline because the older lane does not export `ReasoningEffort`.
- Keeps the package pure-Python and architecture-independent; there are no
  applicable Strix-specific native optimization flags to carry here.
- Depends explicitly on `python-gfx1151`, `python-numpy-gfx1151`, and
  `python-pillow-gfx1151` so the local inference stack stays on the
  repo-managed Python and multimodal preprocessing closure.

## Update Notes

- Before updating, confirm that the chosen release still exports
  `mistral_common.protocol.instruct.request.ReasoningEffort`; that is the
  concrete compatibility boundary that blocked Gemma 4 on the host.
- Re-check runtime dependency metadata against the chosen baseline package and
  the published PyPI metadata. Keep optional extras such as `opencv`,
  `sentencepiece`, `soundfile`, and `soxr` optional unless the local closure
  story intentionally changes.
- After any update, rerun the Gemma 4 vLLM smoke test on the host rather than
  stopping at `import mistral_common`.

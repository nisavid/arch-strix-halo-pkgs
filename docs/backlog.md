# Backlog

GitHub Issues is the active execution tracker. This file is a compact discovery
index, not a work queue or source of completion evidence. Package-candidate
identity and disposition live in
`docs/maintainers/update-candidates.toml`; validated and blocked outcomes live
in `docs/maintainers/current-state.md`.

## Stack Convergence

The [stack-convergence umbrella](https://github.com/nisavid/arch-strix-halo-pkgs/issues/95)
owns the dependency-ordered route. Its blocking spine is:

- [W0: freeze the control plane and exact inputs](https://github.com/nisavid/arch-strix-halo-pkgs/issues/96)
- [W1: establish the Python and TheRock foundation](https://github.com/nisavid/arch-strix-halo-pkgs/issues/97)
- [W2A: build the PyTorch and vLLM runtime](https://github.com/nisavid/arch-strix-halo-pkgs/issues/98)
- [W2B: build the Lemonade and llama.cpp runtime](https://github.com/nisavid/arch-strix-halo-pkgs/issues/99)
- [W3: assemble the coherent candidate generation](https://github.com/nisavid/arch-strix-halo-pkgs/issues/100)
- [W4: prove preactivation and recovery](https://github.com/nisavid/arch-strix-halo-pkgs/issues/101)
- [W5: activate prevalidated exact C atomically](https://github.com/nisavid/arch-strix-halo-pkgs/issues/102)
- [W6: complete acceptance and closeout](https://github.com/nisavid/arch-strix-halo-pkgs/issues/103)

### Blocking work units

- W0: [control schemas and authority adapters](https://github.com/nisavid/arch-strix-halo-pkgs/issues/104),
  [source and dynamic dependency closure](https://github.com/nisavid/arch-strix-halo-pkgs/issues/105),
  [exact B0 capture](https://github.com/nisavid/arch-strix-halo-pkgs/issues/106), and
  [fixtures, probes, Kokoro, and operating bounds](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107)
- W1: [CPython 3.14.7 and TheRock 7.14 foundation](https://github.com/nisavid/arch-strix-halo-pkgs/issues/108)
- W2A: [compiler and PyTorch foundation](https://github.com/nisavid/arch-strix-halo-pkgs/issues/109),
  [model dependency closure](https://github.com/nisavid/arch-strix-halo-pkgs/issues/110), and
  [TorchVision and vLLM consumers](https://github.com/nisavid/arch-strix-halo-pkgs/issues/111)
- W2B: [production-qualified Lemonade fork source](https://github.com/nisavid/arch-strix-halo-pkgs/issues/112) and
  [build and validate the coherent Lemonade package family](https://github.com/nisavid/arch-strix-halo-pkgs/issues/113)
- W3-W6: [candidate assembly](https://github.com/nisavid/arch-strix-halo-pkgs/issues/114),
  [preactivation and recovery](https://github.com/nisavid/arch-strix-halo-pkgs/issues/115),
  [activation](https://github.com/nisavid/arch-strix-halo-pkgs/issues/116), and
  [acceptance](https://github.com/nisavid/arch-strix-halo-pkgs/issues/117)

### Retained nonblocking work

These issues remain visible under the umbrella but do not block the critical
spine:

- [TorchAO and Torch-MIGraphX supported extensions](https://github.com/nisavid/arch-strix-halo-pkgs/issues/118)
- [AITER and FlyDSL experimental closure](https://github.com/nisavid/arch-strix-halo-pkgs/issues/119)
- [independent CTranslate2 refresh](https://github.com/nisavid/arch-strix-halo-pkgs/issues/120)
- [independent stable-diffusion.cpp refresh](https://github.com/nisavid/arch-strix-halo-pkgs/issues/121)
- [amd-quark authoring](https://github.com/nisavid/arch-strix-halo-pkgs/issues/77),
  which remains separate and deferred rather than a convergence dependency

## Explicit Non-Issue Dispositions

- GPTQ, native AWQ, Quark-consumer, FP8, NVFP4, speculative-decoding,
  multimodal, and performance scenarios that are not named as blocking W6
  gates remain advisory or exploratory. They are unscheduled and do not block
  convergence. Promotion requires a new or existing execution issue with an
  accepted fixture, runtime prerequisite, and validation contract.
- bitsandbytes, FBGEMM, xFormers, and other package experiments without a
  selected source closure and current consumer remain deferred. Their research
  documents preserve reopening criteria; no package implementation is active.
- FlashAttention CK paged-KV repair, optional FlashAttention autotuning, full
  Torch-MIGraphX model flows, and other bounded follow-ups remain deferred
  experiments. Existing passing and blocked evidence remains in the package
  documentation and current-state record.
- Benchmarking, broader documentation polish, local-repository ergonomics, and
  embedded-build-path cleanup are unscheduled maintenance themes, not active
  gates. Create an issue before beginning a session-spanning change.
- Adopted, rejected, or superseded refresh narratives are intentionally absent
  here. Consult the candidate ledger and current-state evidence instead of
  reopening historical backlog prose.

## Tracker Maintenance

[Issue #74](https://github.com/nisavid/arch-strix-halo-pkgs/issues/74) owns the
one-time issue-primary cutover. After that cutover, an active ledger record may
reference only an open issue in this repository. Before closing or repurposing
an execution issue, transition every referenced candidate to a terminal
disposition or rehome it to an open successor issue.

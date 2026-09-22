# Lemonade Live Validation

This page maps the live-validation bar for the standalone Lemonade family
(`lemonade`, `lemonade-server`, `lemonade-app`, `llama.cpp-hip-gfx1151`, and
`llama.cpp-vulkan-gfx1151`) to tracked scenarios. Run it after the family is
built, published, and installed on the host. Record the results in
[Current State](current-state.md), keeping the built, installed, installed-smoked,
and live-validated states separate.

The scenarios are in `inference/scenarios/lemonade-live-validation.toml`. The
work is tracked in issue #138.

## Coverage

| Bar item | Scenario or check |
| --- | --- |
| GGUF text on HIP, direct | `llama.cpp.hip.qwen3-0.6b-q8-0.completion` |
| GGUF text on Vulkan, direct | `llama.cpp.vulkan.qwen3-0.6b-q8-0.completion` |
| GGUF text on HIP, via Lemonade | `lemonade.llamacpp.rocm.qwen3-0.6b-q8-0.completion` |
| GGUF text on Vulkan, via Lemonade | `lemonade.llamacpp.vulkan.qwen3-0.6b-q8-0.completion` |
| Start and restart with config preserved; HIP discovery | `lemonade.lifecycle.restart-config-hip-discovery` |
| Pin persistence and startup restore | `lemonade.pins.persistence-startup-restore` |
| Budget admit and refuse, with APU GTT counted | `lemonade.budget.gtt-admit-refuse` |
| Pinned and in-use models never displaced | `lemonade.residency.pinned-busy-not-displaced` |
| Package provenance; no silent downloader, bundled-backend fallback, or foreign or mixed package | `lemonade.provenance.family-no-fallback` |
| Embeddings, both rerankers, and selected-logit | the existing `lemonade.pooling.*` and `lemonade.reranking.zerank-2.selected-logit` scenarios |
| App launch with pin and startup controls, plus one text interaction | the `lemonade.app.pin-startup-text` operator checklist in the same TOML file |
| Kokoro TTS and the app's TTS interaction | deferred to generation C W2B (#113); see below |

All four text scenarios use the same file:
`Qwen/Qwen3-0.6B-GGUF` at revision `23749fefcc72300e3a2ad315e1317431b06b590a`,
`Qwen3-0.6B-Q8_0.gguf`. The Lemonade scenarios compare the backend
process's executable against `pacman -Qo`, so they fail if Lemonade serves the
model from anything other than the packaged llama.cpp.

## Scenario Classes

- `mutates-service`: loads and unloads the test model on the running
  `lemond.service`. It unloads the model on exit if the model was not already
  resident. It never changes pins or config.
- `isolated-lemond`: starts a private `lemond` from `/usr/bin/lemond` with a
  temporary cache directory. The config is offline, backend fetching is
  disabled, and the packaged llama.cpp backends are used. The scenario reaches
  the test GGUF through a temporary `extra_models_dir`. The service's pins and
  config are never touched, and the temporary state is removed on exit. These
  scenarios still load models on the shared GPU.
- `read-only`: the provenance scenario only reads pacman, systemd, and the
  service's `/internal/config`.

All of these scenarios carry `validation-window`. Broad selections skip them,
so select them explicitly:

```bash
python tools/run_inference_scenarios.py --tag validation-window \
  --model-path Qwen/Qwen3-0.6B-GGUF=<testing HF hub cache>/models--Qwen--Qwen3-0.6B-GGUF/snapshots/<revision>/Qwen3-0.6B-Q8_0.gguf
```

`--include-validation-window` adds them to an `--engine` or `--model`
selection. `--scenario <id>` always selects the named scenario.

## Operator Inputs

- Download the GGUF into the testing Hugging Face cache described in
  [Testing Model Cache](testing-model-cache.md), and bind it with
  `--model-path`. The direct and isolated scenarios never download anything.
- Register the same checkpoint with the service before the window, as a
  deliberate step:

  ```bash
  lemonade pull user.Qwen3-0.6B-Q8_0-GGUF --checkpoint main Qwen/Qwen3-0.6B-GGUF:Q8_0 --recipe llamacpp
  ```

  The text scenarios fail with `model_not_provisioned` rather than let a load
  download the model.
- When the service requires a loopback API key, set `LEMONADE_API_KEY` or
  `LEMONADE_API_KEY_FILE` in the runner's environment. For `/internal/*`, set
  `LEMONADE_ADMIN_API_KEY` or `LEMONADE_ADMIN_API_KEY_FILE`; if neither is
  set, the regular key is used. A `*_FILE` variable can name a systemd
  credential. Never put keys or credential paths in scenario files.
- The provenance scenario expects the service config to have `offline` and
  `no_fetch_executables` set to true. It also expects `llamacpp.rocm_bin` and
  `llamacpp.vulkan_bin` to be absolute paths owned by the packaged backends.

## Kokoro TTS Decision

The pinned Lemonade candidate (`nisavid/lemonade` fork main `187b4a25f`) can
run Kokoro with a local backend directory and `no_fetch_executables`. However,
its `backend_versions.json` records no digest for the `lemonade-sdk/Kokoros`
runtime asset, so a pre-provisioned runtime cannot have its version and digest
recorded without a fork change. Kokoro TTS and the app's TTS interaction are
therefore deferred to generation C W2B (#113), and this catalog has no TTS
scenario.

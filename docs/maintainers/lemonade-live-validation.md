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
| No fetch on load: journal, cache-diff, and network evidence, plus a missing model that fails loudly | `lemonade.nofetch.preplaced-load-missing-model` |
| The service keeps the consumer models `zembed-1` Q4_K_M and `zerank-2` Q8_0 pinned and loaded | `lemonade.pins.service-consumer-pins` |
| Embeddings, both rerankers, and selected-logit | the existing `lemonade.pooling.*` and `lemonade.reranking.zerank-2.selected-logit` scenarios |
| App launch with pin and startup controls, plus one text interaction | the `lemonade.app.pin-startup-text` operator checklist in the same TOML file |
| Kokoro TTS and the app's TTS interaction | deferred to generation C W2B (#113); see below |

All four text scenarios use the same file:
`Qwen/Qwen3-0.6B-GGUF` at revision `23749fefcc72300e3a2ad315e1317431b06b590a`,
`Qwen3-0.6B-Q8_0.gguf`. Every scenario that exercises it checks the file's
SHA-256 against the pinned digest before reporting success. The direct and
isolated scenarios hash the bound file. The service scenarios require the exact
`Qwen/Qwen3-0.6B-GGUF:Q8_0` checkpoint and hash the service's resolved main
file, so the runner must be able to read that file. The Lemonade scenarios also
compare the backend
process's executable against `pacman -Qo`, so they fail if Lemonade serves the
model from anything other than the packaged llama.cpp.

## Loaded-Library Provenance

A packaged executable is not enough: with `backend=rocm`, `lemond` prepends
cached TheRock library directories to the backend's `LD_LIBRARY_PATH`, so a
cached runtime can shadow the packaged one. After the completion, while the
backend `llama-server` is still running, the Lemonade text scenarios and the
no-fetch pre-placed phase read `/proc/<pid>/maps`. They select every mapped
ROCm, HIP, ggml, llama, or mtmd shared object and require:

- none of them lies under `lemond`'s cache `bin/` directory;
- each one resolves to an owner with `pacman -Qo`;
- every owner is listed in the local repo (`pacman -Slq strix-halo-gfx1151`);
- the ggml and llama objects are owned by the selected backend package; and
- the ROCm backend maps the HIP runtime (`libamdhip64`).

Output reports counts and package names only, never library or cache paths.
Reading another user's `maps` needs the same privileges as reading that
process's memory map, so run these scenarios with access to the service's
processes; otherwise they fail with `backend_maps_unreadable`.

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
  service's `/internal/config`. The consumer-pins scenario only reads the
  service's `/pins`, `/health`, and `/models/<id>`.

The pins, budget, and displacement scenarios use an isolated `lemond` rather
than the service. Each one pins and unpins models, changes
`max_gpu_memory_occupancy_gb`, restarts `lemond`, or needs a one-slot
configuration so that it can force a displacement. On the service, those steps
would rewrite the host's `config.json` and `pinned_models`. They would also
unload models that clients are using. The isolated `lemond` runs the same
packaged binary and backends. Its private config makes the admission and
displacement results deterministic. The service's own pins are checked
read-only by `lemonade.pins.service-consumer-pins`.

## No-Fetch Evidence

`lemonade.nofetch.preplaced-load-missing-model` runs two phases against the
service. Each phase collects three kinds of evidence:

- Journal: `journalctl -u lemond.service` over the phase window must contain
  no download or install lines. The phase must also show a line naming the
  loaded model, which proves that the journal is readable.
- Caches: the model cache and the backend cache (`<cache dir>/bin`) are listed
  before and after the phase. Every path, type, size, mtime, and symlink target
  must match. The model cache path comes from the service's `/system-info`
  `model_storage.path`. The cache dir comes from `lemond`'s argv, then
  `LEMONADE_CACHE_DIR`, then the service user's `~/.cache/lemonade`. Output
  reports only entry counts, never paths.
- Network: `ss -tanp` is sampled throughout the phase. No socket owned by
  `lemond` or its children may have a non-loopback peer. In the pre-placed
  phase, none may connect to the download blackhole's port either. Connections accepted on one of `lemond`'s
  listening ports are client traffic, such as LAN consumers, and are ignored.

In the first phase, the service loads and completes with the pre-placed test
GGUF, using the same checks as the text scenario. In the second phase, the
scenario loads `Tiny-Test-Model-GGUF`, a small catalog model that must not be
downloaded. The phase passes when all of these hold:

- the load fails loudly, with a non-2xx status or an explicit error, and the
  model does not become resident;
- the model and backend caches are unchanged; and
- `lemond` and its children made no non-loopback connection.

Preconditions are checked before anything is loaded. The service config must
have `offline` and `no_fetch_executables` set to true. `HF_ENDPOINT` and
`MODELSCOPE_ENDPOINT` must both name loopback endpoints. `ss -p` must be able
to attribute the service's listening socket to `lemond`.

On candidate `187b4a25f`, `/load` of a registered model that is not
downloaded calls the download path even when `offline` is true. The blackhole
stops the bytes, but the attempt is logged as `Model not downloaded,
downloading...`. Under the lead's ruling for #138, a logged, blackholed attempt
in the missing phase is an observation, not a failure. The scenario prints
`missing_blackholed_fetch_attempt_recorded` with the log-line and blackhole
connect counts, and does not print `missing_no_fetch_log_ok`. The pre-placed
phase keeps the strict check: any download or install line, or any blackhole
connect, fails it. When the fork refuses that load offline, the missing phase
prints `missing_no_fetch_log_ok` again, and the recorded marker disappears.

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
- For the no-fetch scenario, set `HF_ENDPOINT` and `MODELSCOPE_ENDPOINT` to a
  loopback blackhole in a `lemond.service` drop-in `Environment=` line.
  `systemctl show` exposes that line, so the scenario can verify it. Values in
  `EnvironmentFile=` are visible only when the runner can read the service's
  `/proc/<pid>/environ`, and the scenario reads only those two keys. Run the
  scenario with privileges that let it read the system journal, the service's
  model and backend caches, and the process owner of `lemond`'s sockets in
  `ss -p`.
- Pre-place the consumer models `user.zembed-1-Q4_K_M-GGUF-Q4_K_M` and
  `zerank-2-GGUF` (`mradermacher/zerank-2-GGUF:Q8_0`), and pin them in the
  service config. The consumer-pins scenario only reads them.
- When the host's service configuration carries an API key, set `LEMONADE_API_KEY` or
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

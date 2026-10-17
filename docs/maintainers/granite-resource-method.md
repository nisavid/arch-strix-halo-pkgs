# Granite resource admission and fault stops

Granite admission joins the pinned corpus, accepted sizing inputs, qualifying immutable C, normal Lemonade state, and a serialized window. This maintained-method proposal grants no provisioning, service-write, hold-clear, or GPU authority. The common two-decimal grid and mandatory-minimum/preferred-target branches are selected; the broader allocation semantics, numerical envelope, and runtime contract remain unaccepted.

## Entry conditions and bindings

For fit admission, runtime integration, or fault resume, load and record the reviewed revision. Bind required lanes, C identity/digest, package/runtime/template/parser identities, model closure, envelope, observations, and window owner. Changed inputs or relevant dependencies invalidate affected evidence.

Keep `inference/fixtures/granite-3.1-1b-a400m-instruct.json` unchanged: model `ibm-granite/granite-3.1-1b-a400m-instruct`, revision `0da7a48b0276d500ce5922fd2b33944091fc6c09`, SHA-256 `cfc8740cdf71455fea91064caf3c8545763344c9b71803abf115323a6e98d094`. Basic, tool, and structured results are required. One response choice defines neither concurrency nor KV capacity. Granite has no completion-token minimum; E2B's gate is inapplicable.

Accepted inputs carry value, unit, provenance, subject/revision, and acceptance:

- Weights/loading: selected files, precision/layout, padding/packing, expert placement and residency, ties, and loading/conversion/staging peaks. Count all owned expert storage; top-k routing does not establish a smaller resident set. Disk safetensors size is not resident demand.
- KV: normalized model/runtime-backed owned/shared layers, local heads/dimensions, datatype, cache layout/block rounding, partitioning, sequence capacity, lifetime, and extra state.
- Profile: context/output limits, tokenized pinned requests under the bound template, batch/concurrency and scheduling, activation/runtime/graph/workspace peaks, and host RSS allowance.
- Policy: headroom/margins, utilization floor/range/default/override permission, execution mode, continuation, invocation budget, timeouts, and cleanup deadlines.

Slots remain unaccepted until recorded. Other models' constants, architecture fallbacks, and adapter defaults supply no Granite value. Missing measurements remain unknown, never zero. Logical config geometry, constructor arguments, and conditional parameter counts belong in the source evidence. Physical allocation estimates require the selected normalized runtime, imported allocation/loading/cache implementations, placement choices, and peak accounting. A provider dtype label or a matching logical parameter total establishes neither concrete runtime dtype nor resident/loading bytes. A requested weight tie establishes neither actual aliasing nor its transient peak.

## Proposed sizing arithmetic

The selected arithmetic branches use one grid, `k/100` for integer `k`, for defaults and calculated overrides. Keep source byte counts and finite decimal values exact as integers/rationals through conversion, products, sums, and comparisons. Use `GiB = bytes / 2^30`, and decimal occupancy `GB * 10^9 / 2^30`. Define `floor2(x) = floor(100*x)/100` and `ceil2(x) = ceil(100*x)/100` on those exact values. Round displays separately; an epsilon or rounded display cannot lower a minimum or increase capacity. An implementation that cannot preserve these meanings needs review before application.

`T` and `U` are total/used GPU-addressable GTT on one identified device; `A` is host MemAvailable, all GiB. Bind GTT/host-RAM overlap and runtime reservation semantics. Require successful finite reads, `T > 0`, `0 <= U <= T`, `A >= 0`, and valid Lemonade health/schema/occupancy. Resources must describe one compatible observation interval and device. Occupancy is a cross-check already represented in `U`, not another subtraction.

Policy slots are `h_abs` and `P_host` (GiB); `h_frac`, `m_need`, `m_target`, `u_floor`, and runtime utilization bounds (dimensionless). Required values need acceptance and valid units/provenance. Allowances and floors are finite and nonnegative; margins are finite and at least one. The runtime interval and policy schema must be supported and coherent. Accepted default/override permission must identify a usable route. A present default `d` must be finite, runtime-valid, and on the grid (`100*d` is an integer). A finer default such as `0.705` is `REFUSED`, even when a rounded value or override might fit. Require an explicitly configured, valid `m_target` before arithmetic; missing or invalid `m_target` is `REFUSED`, including when an accepted default or override would otherwise fit. No numerical defaults exist.

Validate these requirements and complete demand before assigning a mathematical fit outcome. A known failed identity, authority, hold, acceptance, policy, or input-validity condition yields `REFUSED`. A missing required policy or a present invalid default is a refusal. Otherwise, a missing/failed observation with no usable value, or unavailable demand derivation, yields `UNAVAILABLE`. An invalid observed value is a refusal. Retain every known defect; neither outcome becomes `NOFIT` merely because a partial budget is nonpositive.

```text
H = max(h_abs, h_frac * T)
F = T - U
R_host = A - P_host
B = min(F, R_host) - H

K = sum(2 * b_l * h_l * d_l * t_l * s_l + q_l) / 2^30
N = W_peak + A_peak + S_runtime + K + G_workspace + E_state
```

Each KV term represents one supported physical owned allocation. `b_l` is bytes/element, `h_l` local KV heads, `d_l` head dimension, `t_l` rounded allocated tokens/sequence, `s_l` allocated sequences, and `q_l` overhead bytes. The factor two requires evidence for both key and value at that geometry. Sharing and partition ownership prevent double-counting; scales, metadata, alignment, and extra state need one owner. Unsupported geometry leaves `K` unavailable. Context limits, `use_cache`, logical head widths, or sequential requests alone establish no cache reservation or sequence capacity.

Other `N` terms are GiB peaks for weights/loading, activations, runtime/non-Torch slack, graph/workspace, and extra state. A phase-and-ownership ledger must cover simultaneous peaks and account for overlap; a deliberately conservative sum of separate-phase peaks needs that label. Demand must be complete, finite, and nonnegative, with `N > 0`. Zero terms, including eager graph demand, need evidence. The ledger must show what the runtime's `u*T` reservation covers and how host-only demand enters `P_host`; these meanings are prerequisites, not facts inferred from an allocator flag.

After validation, `B <= 0` gives policy `NOFIT`. For `B > 0`, intersect all mandatory lower bounds and capacity/runtime upper bounds with the grid. For included runtime endpoints:

```text
u_min = ceil2(max(runtime_u_min, u_floor, m_need * N / T))
u_max = floor2(min(runtime_u_max, B / T))
```

Thus non-grid runtime/floor lower bounds round up, and non-grid runtime/capacity upper bounds round down. If a supported runtime excludes an endpoint, move its grid bound one step inside when that endpoint itself lies on the grid, then intersect the bounds. Enforce the runtime's accepted endpoint predicate in the final check. `u_min > u_max` gives policy `NOFIT`; it does not prove physical impossibility outside the selected grid and model. A mathematical outcome requires all prior validation, including an accepted selection route.

The demand minimum is mandatory. Keep a valid accepted default only when `u_min <= d <= u_max` and the exact `d*T <= B`. An unmet preferred target does not invalidate that fit. If the default does not fit, use a separately accepted override route; without one, `REFUSED` records the unusable default branch rather than claiming the feasible interval is empty. A missing default is usable only through an accepted override route.

For an accepted override, the configured target is a preference. Calculate the preferred grid target:

```text
u_pref = max(u_min, ceil2(m_target * N / T))
u = min(u_max, u_pref)
reservation = u * T
```

Check `u_min <= u <= u_max`, exact grid membership, runtime validity, `reservation >= m_need*N`, and `reservation <= B`. Clipping may reduce only the preferred target, never the mandatory minimum. Record whether the configured target was met or clipped. Record the default/override branch, raw bounds, grid bounds, reservation, and binding side: host RAM when `R_host < F`, GTT when `F < R_host`, and both at equality.

`ADMITTED` is conditional numerical fit under the accepted meanings and current observations. It establishes no allocation, request, cleanup success, or execution permit. Reobserve service/resources immediately before each lane; preflight reserves nothing. Serialize actual window participants, not just cooperating wrappers. No outcome authorizes model unloading.

## Lane results and stop evidence

Freeze required lanes before admission. Partial fit, skips, insufficient time, or missing results cannot pass. Bind command/envelope to admission; retain before/after measurements, requests/responses, server log, backend selection, and runner assertions.

Record wrapper status, actual command status, and runner result separately through a reviewed adapter. Wrapper success does not establish child success; nonzero/timed-out children fail. Runner `ok` cannot override command failure, resource stops, or missing lanes. Missing/malformed statuses or contradictions block a pass and further admission. Backend selection proves neither every kernel nor absence of fallback.

Observe kernel/service state before/after lanes and at close; retain query status and intervals. Unavailable logs are not an empty fault set. Page faults, reset/ring-timeout/device loss, unsafe service state, and outer timeout stop invocations. Record both fault and unsafe dispositions despite exit-status precedence. Ordinary failures can continue only under accepted predeclared policy and still fail the lane.

Normal Lemonade binds service identity/version, health, active state, pins/order/residency, persisted configuration, and restarts. Verify postconditions after lanes and between groups. An authorized stopped-service contract cannot satisfy the normal-state join.

## Cleanup, holds, and resume

Accept startup, request, lane, group/window, stop-grace, reap, restoration, and closing-verification deadlines before execution. Timeout/attempted TERM/KILL does not prove termination. Cleanup requires no leftover lane/server work under reviewed process ownership and proved service/configuration restoration or unchanged stopped state. Restoration cannot erase faults/holds.

Retain fault/unsafe observations and holds through cleanup. Lane resume requires diagnosis/disposition, hold-owner clearance authorization, no leftovers, restored normal state, current C/preparation/runtime closure, window/budget, and fresh fit admission. Marker absence is not clearance. An unchanged authorized stopped state can satisfy its cleanup postcondition, but cannot satisfy fresh Granite admission or lane-resume eligibility.

## Acceptance and current boundary

Independent final-source/pointer review covers arithmetic, demand, statuses, lane completeness, service/window joins, cleanup/fault/resume branches, discovery, and privacy. Required constructed-check coverage includes exact grid boundaries, non-grid lower/upper constraints, finer-default refusal, mandatory minimum, missing-preference refusal in both otherwise-valid default and override branches, invalid targets, configured targets met or clipped, default fallback, validation-before-no-fit, and fit/refused/unavailable/no-fit outcomes. Apply and independently grade finite instruction cases through the owning route, recording the consumed revision, inputs, decisions, and results. Operational coverage includes partial lanes, malformed status, failed/timed-out child behind wrapper success, skips, observation failure, kernel/service stops, restoration failure, and authorized resume. Static examination and worked calculations alone do not establish instruction-application behavior.

Keep instruction applications separate from executable checks and runtime procedures. Finite instruction cases evaluate only the exercised instruction branches; they do not establish physical allocation, service/kernel behavior, automatic installed-client discovery, or GPU qualification. No executable checks or runtime procedures have been run for this proposal. The [revision-bound verification record](https://github.com/nisavid/arch-strix-halo-pkgs/issues/179#issuecomment-6143143768) holds the historical source review and finite case results. Changed instructions or relevant dependencies require renewed affected applications, independent grading, and final-source review; historical grades do not qualify a successor.

`run-local-inference-scenarios` consumers load the reviewed source, record its revision and accepted bindings, and verify outputs. Check fit/runtime/resume discovery and unrelated non-invocation separately. Exercise the owning instruction route; this document is not a skill package. Verify publication/route readback and acyclic dependencies. Producer self-use binds the candidate revision without depending on itself. Authorized targeted installation/projection readback is required when that route changes; otherwise record its unchanged status. Consumers feed useful corrections back to this one maintained source.

The [gate reference](granite-vllm-gates.md) documents preparation-only output and planning failure `GRANITE_RUNTIME_JOIN_REQUIRED`, not an executable plan. This proposal does not qualify C, accept an envelope, implement integration, or clear GPU work. Capture/adoption remains incomplete until decisions, final review, behavior/discovery checks, authorized publication and route readback, and consumer-revision checks are complete. Live validation requires every accepted current join. Report source preparation, package build, deployment/installation, installed smoke, and live scenario validation separately.

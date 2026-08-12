# Convergence Control Plane

The convergence control plane is the repository-side contract that makes stack
evidence immutable, attributable, privacy-safe, and fail-closed before package
or host mutation begins. It implements the repository-owned portion of
[the accepted evidence model](https://github.com/nisavid/arch-strix-halo-pkgs/issues/90#issuecomment-5262370436)
and the critical-operation rules in
[the dependency-ordered route](https://github.com/nisavid/arch-strix-halo-pkgs/issues/89#issuecomment-5261383591).

This layer does not turn the repository into a production authority. Production
signing, immutable evidence storage, append-only journaling, the composite
register and quorum, witness policy, fencing, trusted time, and recovery roots
remain independently operated substrates. Until the operator selects and
records those substrates, production construction fails closed.

## Module Boundary

`tools/control_plane/` is one deep module with four public capabilities:

1. build, parse, validate, canonically encode, and identify control records;
2. derive applicability, outcome, currency, and invalidation evaluations from
   immutable evidence;
3. produce privacy-safe public envelopes for restricted evidence; and
4. exercise the authority interface with deterministic nonpromotional adapters
   while rejecting unbound production authority.

Callers and tests cross the same interface exported by `control_plane`. Internal
record registries, evaluation helpers, and adapter receipts are implementation
details.

## Record Families

The schema registry is closed and versioned. Its families cover:

- identities, subjects, input closures, artifacts, and generation coordinates;
- requirements, gate definitions, contract or profile assignments, and tagged
  validation contexts;
- occurrence intents, admission attempts, run and evaluation attestations,
  approvals, and invalidation episodes;
- exceptions, fixtures, protected-state projections and snapshots;
- critical-operation intents, capabilities, transitions, terminals, rollback
  targets, and recovery links; and
- authorization policy, composite authority manifests, closed change sets,
  register observations, readiness, witness/quorum records, restricted
  references, public envelopes, and retention leases.

A content-addressed record proves identity and integrity for its canonical
bytes. It does not prove who produced the record, whether the complete attempt
set was observed, or whether the record can authorize promotion.

## Canonical JSON v1

The repository profile uses strict UTF-8 canonical JSON and SHA-256 with record
kind and schema domain separation. Canonical payloads:

- contain one supported schema ID, schema version, record kind, and payload;
- use normalized Unicode strings and lowercase snake-case object keys;
- allow only null, booleans, bounded integers, strings, arrays, and objects;
- reject floats, non-finite values, duplicate keys, unknown record fields,
  unsupported kinds or versions, unsafe Unicode, excessive depth or size, and
  malformed typed digest references; and
- exclude their digest and detached signature from the bytes being hashed.

The encoded bytes have sorted keys, compact separators, no trailing newline,
and a digest formatted as `sha256:<64 lowercase hex characters>`.

Schema migration creates a new schema version. It never silently changes the
meaning or canonical bytes of an existing record.

## Evaluation Model

An attestation is immutable history. An evaluation is a new immutable decision
about that history under an exact validation context and dependency state.

Evaluation uses a constrained state machine:

- `not_due` for an occurrence that is not scheduled;
- `not_applicable` only with current proof of a predeclared conditional
  predicate;
- `applicable` with `blocked`, `pass`, or `fail`; or
- `applicable_unknown` when evidence is missing, stale, partial, mismatched, or
  unverifiable.

Blocking and advisory are assignment roles, separate from applicability. An
applicable blocking assignment is satisfied only by a current pass. An advisory
failure remains recorded but does not block promotion. A conditional
non-applicability proof cannot waive an unconditional assignment.

Invalidation is dependency-scoped. A source, artifact, ABI, fixture, validator,
scenario, protected-state, authorization, target, driver/device, contract, or
generation change makes only mapped evaluations stale. It never edits the
attestations from which they were derived. Preassembly evidence remains
nonpromotional and bound to its candidate context; a verified inclusion edge
may make it relevant to a later generation without changing its identity.

## Authority Interface

The authority interface is deliberately high-level. It exposes active-state
observation, append-before-work intent registration, guarded state transition,
and an evidence view. A future production adapter must implement those
operations using the complete operator-approved substrate, not a collection of
caller-selected trust flags.

`control_plane.testing.InMemoryAuthority` is memory-only, requires explicit
observations, records intent before transition, compares exact expected state,
and issues deterministic test receipts. Its evidence view is a distinct
nonpromotional type and promotion admission always rejects it.

Production construction rejects Git, mutable local files, and target-host logs
as authority. It also rejects every otherwise plausible configuration until a
concrete adapter independently verifies the selected signer, immutable store,
journal, register/quorum, witness roster, fence, recovery root, and trusted-time
proofs. There is no permissive fallback.

## Privacy Boundary

Canonical restricted records stay in controlled storage. A public envelope is
an explicit schema-owned allowlist, not a serialized record with a deny-list
applied afterward. It may expose stable record type, nonprivate audit facts,
and an opaque restricted reference or keyed commitment. It does not expose raw
logs, arbitrary exception text, filesystem paths, host identity, substrate
locators, secrets, or a guessable raw-content digest of private payloads.

Raw-payload retention and durable metadata retention are separate. Expiring a
raw-payload lease does not remove the signed reference metadata, key version, or
rotation history required to understand the surviving attestation.

## Current Completion Boundary

[W0 work unit #104](https://github.com/nisavid/arch-strix-halo-pkgs/issues/104)
can complete its repository schemas, behavioral adapters, privacy tests, and
fail-closed production interface without selecting a substrate. W0 cannot close
until the operator-approved production topology and recovery authorities are
recorded durably. Repository tests, source review, and a successful pull request
do not satisfy that final gate.

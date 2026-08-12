# Stack Convergence Domain

This context names the evidence and authority concepts used to move the local
inference stack from reviewed inputs to one accepted, continuously coherent
generation.

## Language

**Control record**:
An immutable, schema-versioned statement whose identity is derived from its
canonical content. A control record may be structurally valid without being
authoritative.
_Avoid_: Evidence blob, metadata object

**Gate definition**:
The reusable assertion, validator contract, fixture requirements, and evidence
shape for one validation capability. Whether the gate blocks a lifecycle step
belongs to its assignment, not to the definition.
_Avoid_: Check, test case

**Requirements baseline**:
The immutable, approved definition and complete requirement set under which a
validation contract is interpreted. The composite authority manifest points to
the requirements record; the requirements record points outward to its
definition and never back to the composite manifest.
_Avoid_: Manifest, policy file

**Assignment**:
The lifecycle-specific use of a gate, including applicability, blocking or
advisory role, dependency projection, validity, invalidation, authorization,
and separation rules.
_Avoid_: Gate configuration

**Validation context**:
The exact requirements and assignment authority under which a gate occurrence
is admitted and evaluated. A validation context is either an active contract
context or an independent preassembly profile context.
_Avoid_: Environment, run context

**Attempt**:
One journaled decision to admit, block, or run a scheduled gate occurrence. An
attempt exists before any prerequisite check or validator work begins.
_Avoid_: Test run

**Attestation**:
An immutable statement of what an identified principal admitted, executed,
observed, or approved. Later changes never edit an attestation.
_Avoid_: Current result, status

**Evaluation**:
A derived determination of applicability, outcome, currency, and admissibility
for exact attestations under an exact validation context.
_Avoid_: Attestation, result

**Invalidation episode**:
One continuous interval in which a mapped dependency change makes affected
evaluations inadmissible. Re-observing the same unresolved change does not
restart the episode.
_Avoid_: Cache expiry

**Preassembly evidence**:
Evidence bound to an immutable source/input closure and its produced artifacts
before a generation exists. Incorporation into a generation never relabels the
original evidence.
_Avoid_: Generation evidence

**Verified inclusion edge**:
An immutable approval that binds exact preassembly context, source closure,
artifacts, assignments, and evaluations into one active contract and generation
without relabeling the source evidence.
_Avoid_: Copy, promotion by reference

**Generation**:
An immutable manifest of one coherent stack state and its generation class. B0
is the captured recovery class, F is the isolated foundation-validation class,
and C is the complete convergence class. Captured, published, foundation
validation, prevalidated, active, and accepted are lifecycle phases.
_Avoid_: Build, release

**Critical operation**:
A journaled, fenced mutation of protected state with exact origin, destination,
rollback or recovery target, and terminal validation.
_Avoid_: Command, transaction

**Composite authority manifest**:
The immutable control state that names the active requirements and contract,
inventory, generation, rollback registry, recovery policy, and witness roster.
Exactly one rollback-resistant register selects it.
_Avoid_: Configuration file, active pointer

**Promotional evidence**:
Evidence admitted through independently verified production authority and
therefore eligible to support a lifecycle promotion. Content identity, Git
history, local files, tests, or target-host logs alone never make evidence
promotional.
_Avoid_: Passing evidence

**Public evidence envelope**:
A privacy-safe, allowlisted projection that lets maintainers identify and audit
a restricted control record without exposing its sensitive payload or a
guessable digest of that payload.
_Avoid_: Redacted record

**Convergence**:
The current condition in which the accepted generation, active generation,
target state, and every continuing requirement agree and remain admissible.
Historical acceptance alone is not convergence.
_Avoid_: Deployment complete, accepted once

**Recovery incident**:
The fail-closed state entered when protected state or its restoration cannot be
proven exact. Serving remains drained until an authorized recovery path proves
a complete target generation.
_Avoid_: Rollback failure

**Recovery successor**:
A distinct guarded operation authorized by the named recovery owner after a
proven failed terminal. It inherits the failed target exclusively, binds that
terminal and fence, advances the fence, and must validate the exact recovery
target before ordinary work can resume.
_Avoid_: Retry, manual fix

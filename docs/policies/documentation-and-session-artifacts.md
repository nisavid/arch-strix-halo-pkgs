# Documentation And Session Artifact Policy

This repo treats documentation as part of the package surface. A future
maintainer should be able to understand package logic, patch carry, validation
state, and next work from tracked files without reading chat history.

## Keep Durable Docs Durable

Tracked docs explain stable architecture, policy, workflow, package state,
patch rationale, and backlog decisions.

Use tracked docs for:

- architecture that will matter in later sessions
- maintainer workflows another agent should be able to follow
- package policy and baseline rationale
- patch inventory and durable source-level divergence notes
- backlog items that should survive beyond one work session
- validated host state that changes what maintainers should believe

Keep the user-facing overview in the README. Put deeper operational and
maintainer material under `docs/`. Put package-specific context in
`packages/<name>/README.md` and `packages/<name>/recipe.json`.

## Keep Session Artifacts Out Of Git

Prompts, specs, plans, work logs, scratch notes, and handoff docs are transient
until their useful content has been extracted into durable docs or code.

Use ignored locations for session artifacts:

- `.agents/session/`
- `docs/worklog/`
- any future ignored session-only directory that follows the same rule

Do not commit those files. Keep ignored forensic worklogs when they are useful
for local investigation, but do not treat them as durable project state.

## Finish A Substantial Session Properly

Before ending a substantial session:

1. Move durable insight into tracked docs or code comments where it belongs.
2. Update canonical docs whose statements are now stale.
3. Delete consumed session-only inputs after their durable content has been extracted.

A work plan is not finished until its session-only plan, prompt, and scratch
inputs are gone.

## Choose The Smallest Durable Artifact

Do not promote a whole session file because one paragraph mattered.

Instead:

- lift enduring policy into `docs/policies/`
- lift operational flow into `docs/usage/` or `docs/maintainers/`
- lift package-specific context into `packages/*/README.md` or
  `packages/*/recipe.json`
- leave transient reasoning in ignored session artifacts until it is no longer
  needed

## Protect Private Context

Never commit:

- private filesystem paths, including home directories, cache roots, and host-local mount points
- private hostnames or local-only service addresses
- machine-specific IDs that do not help another maintainer
- secrets, keys, or tokens

Replace private context with neutral placeholders or generic examples before
committing.

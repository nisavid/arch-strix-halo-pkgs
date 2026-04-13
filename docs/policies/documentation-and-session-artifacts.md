# Documentation And Session Artifact Policy

## Keep Durable Docs Durable

Tracked docs explain the repository's stable architecture, policy, workflow,
package state, and patch story.

Use tracked docs for:

- architecture that will matter in later sessions
- maintainer workflows that another agent should be able to follow
- package policy and baseline rationale
- patch inventory and other durable source-level divergence notes
- backlog items that should survive beyond one work session

Keep the user-facing overview in the README. Put the deeper operational and
maintainer story under `docs/`.

## Keep Session Artifacts Out Of Git

Treat prompts, specs, plans, work logs, scratch notes, and handoff docs as
transient unless and until their useful content has been extracted into durable
docs or code.

Use ignored locations for session artifacts:

- `.agents/session/`
- `docs/worklog/`
- any future ignored session-only directory that follows the same rule

Do not commit those files, and do not keep stale finished-session files around
just because they are ignored.

## Finish The Session Properly

Before you end a substantial session:

1. move durable insights into tracked docs or code comments where they belong
2. update the canonical docs whose statements are now stale
3. delete the session-only docs that were consumed by the work

A work plan is not finished until its session-only plan, prompt, and scratch
inputs are gone.

## Choose The Smallest Durable Artifact

Do not promote a whole session file just because one paragraph mattered.

Instead:

- lift the enduring policy into `docs/policies/`
- lift the enduring operational flow into `docs/usage/` or
  `docs/maintainers/`
- lift package-specific maintenance context into `packages/*/README.md` or
  `packages/*/recipe.json`
- leave transient reasoning in ignored session artifacts until the work is done

## Protect Private Context

Never commit:

- local home-directory paths
- private hostnames or local-only service addresses
- machine-specific IDs that do not help another maintainer
- secrets, keys, or tokens

Replace them with neutral placeholders or generic examples before committing.

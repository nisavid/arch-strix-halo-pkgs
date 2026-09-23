# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all
operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a
  heredoc for multi-line bodies.
- **Read an issue**:
  `gh issue view <number> --json number,title,body,labels,comments`, adding
  `--jq '<expr>'` to filter. Don't use `--comments` here: without a terminal it
  prints only the comment text, with no title, body, or labels.
- **List issues**:
  `gh issue list --state open --limit 1000 --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`
  with appropriate `--label` and `--state` filters. Without `--limit`, `gh`
  stops at 30 issues.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` /
  `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run
inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external
PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using
the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for
  the diff.
- **List external PRs for triage**:
  `gh search prs --repo <owner>/<repo> --state open --limit 1000 --json number,title,body,labels,author,authorAssociation,commentsCount`
  then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`,
  or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`). `gh pr list` has no
  `authorAssociation` field; read a PR's comments with
  `gh pr view <number> --json comments`.
- **Comment / label / close**: `gh pr comment`,
  `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be
either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --json number,title,body,labels,comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as
tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes /
  Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api`
  on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to
  a task list in the map body and put `Part of #<map>` at the top of the child
  body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`).
  Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical,
  UI-visible representation. Add an edge with
  `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`,
  where `<blocker-db-id>` is the blocker's numeric **database id**
  (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or
  `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open
  blockers only, the live gate). Where dependencies aren't available, fall back
  to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is
  unblocked when every blocker is closed.
- **Frontier query**: read the map's children in map order from the sub-issues
  endpoint, keep the open ones with no assignee and no open blocker, and take
  the first:
  `gh api repos/<owner>/<repo>/issues/<map>/sub_issues --paginate --jq '.[] | select(.state == "open" and (.assignees | length) == 0 and .issue_dependencies_summary.blocked_by == 0) | .number' | head -n 1`.
  No output means the frontier is empty. Where sub-issues aren't enabled, walk
  the map body's task list in order instead, dropping tickets that are closed,
  assigned, or have an open issue in their `Blocked by` line.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then
  `gh issue close <n>`, then append a context pointer (gist + link) to the map's
  Decisions-so-far.

## Execution tickets

This repo runs dependency-ordered execution work through its own labels, wired
with GitHub's native sub-issues and issue dependencies:

- `execution:umbrella`: a convergence program; its waves are sub-issues (for
  example #95, itself a child of the resurrection map #135).
- `execution:wave`: a dependency-ordered wave; its work units are sub-issues,
  and waves block one another through native dependencies (for example W2A #98).
- `execution:work-unit`: a claimable unit of execution work, a sub-issue of its
  wave (for example #109).
- `execution:incident`: a guarded recovery or execution incident.

Triage roles apply to issues that arrive as requests or findings; execution
tickets created by planning carry `execution:*` labels instead.

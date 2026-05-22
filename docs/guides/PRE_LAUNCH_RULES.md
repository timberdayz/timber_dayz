# Pre-Launch Development Rules

These rules apply until the first production launch is stable.

## Goal

Ship the current system with controlled change scope. Do not use the launch period to clean up historical architecture debt unless that debt directly blocks launch.

## Allowed Changes

- Fix launch-blocking bugs.
- Complete required user flows, API behavior, and data paths.
- Add minimal logging, error handling, and observability needed for launch confidence.
- Add focused tests or verification scripts for the changed behavior.
- Update documentation directly tied to launch operation or validation.

## Prohibited Changes

- Broad refactors that are not required for launch.
- Large directory moves or cross-module renames.
- Rewriting stable legacy logic for style or elegance.
- Mixing architecture cleanup with unrelated business changes.
- Adding new duplicate implementations for existing responsibilities.
- Adding temporary reports, screenshots, or one-off scripts at the repository root.

## Change Scope

Every pre-launch task should state:

- The launch problem being solved
- The files or modules expected to change
- The modules intentionally left untouched
- The validation command or manual verification path

If a task crosses more than three major modules, split it before implementation unless the cross-module change is itself the launch blocker.

## Debt Handling

Record non-blocking technical debt for the post-launch V2 rebuild. Do not hide opportunistic cleanup inside launch fixes.

Preferred destinations:

- `findings.md` for investigation notes
- `progress.md` for current work state
- `docs/superpowers/plans/` for durable post-launch plans

## Agent Rules

- One agent task should handle one explicit outcome.
- Agents must not fix unrequested issues unless they block the requested task.
- Agents must verify changed behavior before claiming completion.
- If validation cannot run, state the blocker and the residual risk.

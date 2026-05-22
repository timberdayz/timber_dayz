# Change Control

This file is a repository adapter for `superpowers`, not a replacement workflow.

## Pre-Launch Phase

- Prioritize launch-blocking work.
- Avoid broad refactors unless required to unblock launch.
- Keep changes tied to a clear validation path.
- Do not add new root-level temporary reports, screenshots, or one-off scripts.

## Stable Launch Phase

- Prefer incremental hardening, observability, and bug fixes.
- Keep release risk low by separating product changes from cleanup.

## V2 Rebuild Phase

- Use the post-launch rebuild to reset architecture baselines.
- Move large cleanup, folder restructuring, and contract rewrites into explicit rebuild plans.
- Capture decisions in ADRs when they change long-term architecture direction.

## Agent Rules

- Identify the current phase before proposing a broad change.
- If a cleanup is not needed for launch, document it for V2 instead of mixing it into launch work.

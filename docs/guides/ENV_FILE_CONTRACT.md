# Environment File Contract

This file defines how agents should read, edit, and reference environment files.

## File Classes

- `.env`: local developer runtime values. Read when needed for local debugging, but do not copy secrets into code, docs, tests, or chat output.
- `.env.local`: optional local override file. It is local-only and must not be treated as a shared baseline.
- `.env.production`: production runtime values. Do not edit unless the task explicitly targets production configuration.
- `.env.production.passwords.txt`: sensitive production password material. Do not read, print, summarize, or modify unless the user explicitly requests a secret-handling task.
- `.env.backup` and `.env.cleaned`: local recovery or cleanup artifacts. Do not use them as active configuration sources.
- `.env.limiter`: specialized local limiter configuration. Do not generalize it into the default runtime unless the task targets limiter behavior.
- `.env.example`, `env.example`, `env.development.example`, `env.docker.example`, `env.production.example`, `env.production.cloud.example`: shared templates. Prefer editing these when documenting required variables.

## Source Of Truth

- Runtime behavior comes from the actual environment and active `.env` files.
- Shared documentation should describe variables through example files, not by copying local secret-bearing values.
- Local development Redis values are defined in `docs/guides/DEVELOPMENT_ENVIRONMENT.md` and `docs/guides/LOCAL_DEV_RUNTIME_GUIDE.md`.

## Edit Rules

- Do not commit real secrets, account credentials, cookies, tokens, or production passwords.
- Do not replace a local `.env` with an example file during agent work.
- Do not change production environment files as part of local debugging.
- If adding a new required variable, update the relevant `env*.example` file and the owning guide.
- If a variable differs across local, Docker, collection, and production environments, document the difference instead of forcing one value globally.

## Agent Rules

- Before editing environment files, state which environment is affected.
- Prefer changing examples and documentation over changing local secret-bearing files.
- If a task requires inspecting sensitive files, ask for explicit confirmation and avoid echoing values.
- Treat missing or conflicting environment variables as configuration issues, not reasons to invent new startup paths.

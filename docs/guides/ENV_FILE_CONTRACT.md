# Environment File Contract

This file defines how agents should read, edit, and reference environment files.

## File Classes

- `.env`: local developer runtime values. Read when needed for local debugging, but do not copy secrets into code, docs, tests, or chat output.
- `.env.local`: optional local override file. It is local-only and must not be treated as a shared baseline.
- `.env.collection.local`: optional local-only collection takeover overlay. Use it only when a development machine temporarily takes over collection, sync, and cloud-sync duties.
- `.env.production`: production runtime values. Do not edit unless the task explicitly targets production configuration.
- `.env.production.passwords.txt`: sensitive production password material. Do not read, print, summarize, or modify unless the user explicitly requests a secret-handling task.
- `.env.backup` and `.env.cleaned`: local recovery or cleanup artifacts. Do not use them as active configuration sources.
- `.env.limiter`: specialized local limiter configuration. Do not generalize it into the default runtime unless the task targets limiter behavior.
- `.env.example`, `env.example`, `env.development.example`, `env.docker.example`, `env.production.example`, `env.production.cloud.example`, `env.collection.local.example`: shared templates. Prefer editing these when documenting required variables.

## Repository Tracking Policy

Added 2026-11-13 (batch C2). The GitHub repository `timberdayz/timber_dayz` is **PUBLIC**, so "it is in the repository" means "anyone on the internet can read it".

**Never tracked** (a tracked copy is a disclosure, not a convenience):

- `.env` and the whole `.env.*` family, except the exceptions listed below;
- `*.passwords.txt` — production password backups (`.env.production.passwords.txt`);
- `*.enc` — encrypted credential stores (`accounts.enc` holds the shop account archive);
- `*.key`, `*.pem`, `*.crt`, `*.p12`, `*.pfx` — keys and certificates.

**Tracked on purpose** (no secrets inside):

- `.env.example`, `.env.template`, `env*.example`, `env.template` — templates;
- `.env.limiter` — the rate limiter's runtime configuration. `backend/middleware/rate_limiter.py` reads it directly and it must stay pure ASCII (reading a UTF-8 `.env` with gbk on Windows raises `UnicodeDecodeError`). It holds a single `RATE_LIMIT_ENABLED` switch, no credentials.

**Enforcement** (all three layers must agree):

- `.gitignore` — `.env.*` with negations for the allowed files, plus `*.passwords.txt` and `*.enc`;
- `scripts/check_precommit_secrets.py` — the pre-commit gate; `is_blocked()` decides by rule, not by a hand-written filename list;
- `tests/test_secret_files_not_tracked.py` — the contract test: the files above must not be tracked, the gate must block them, and the gate must **not** block templates, docs, or scripts.

**Untracking does not withdraw history.** `git filter-repo` would rewrite every published tag, so it is not part of routine work. Anything that was tracked in the past must be treated as **disclosed** and rotated.

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

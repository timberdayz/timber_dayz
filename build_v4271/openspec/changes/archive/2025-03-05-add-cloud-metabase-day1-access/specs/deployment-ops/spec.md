## ADDED Requirements

### Requirement: Deployment documentation SHALL describe cloud Metabase access URL and first-time setup
Deployment and operations documentation SHALL include a dedicated section or document describing how to access Metabase on a cloud deployment and how to complete first-time setup so that Metabase and backend proxy (e.g. Dashboard KPI, init_metabase.py) become usable.

#### Scenario: Maintainer follows doc to access and initialize cloud Metabase
- **WHEN** a maintainer or operator reads the deployment documentation after a first-time cloud deployment
- **THEN** the documentation SHALL state that cloud Metabase is only reachable at `http://<domain-or-IP>/metabase/` (no separate host port; Nginx reverse proxy)
- **AND** the documentation SHALL list the steps to complete first-time setup in the browser: setup wizard, create admin account, add PostgreSQL data source (same as backend business DB), create API Key in Metabase admin, and set `METABASE_API_KEY` in server `.env`
- **AND** the documentation SHALL describe that when using IP or a non-default domain, `MB_SITE_URL` and Nginx `proxy_set_header Host` SHALL match the actual access URL to avoid white screen or redirect errors
- **AND** the documentation SHALL warn about the Nginx variable `proxy_pass` trap: when using `set $var` + `proxy_pass http://$var` (for delayed DNS resolution), a `rewrite` directive MUST be used to strip the location prefix manually; otherwise the upstream receives the original path with prefix and returns wrong content (e.g. SPA HTML fallback with `Content-Type: text/html` for JS requests, causing MIME type white screen)

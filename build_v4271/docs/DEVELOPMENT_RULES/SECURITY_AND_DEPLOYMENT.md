# Security, Deployment & Monitoring

**Version**: v4.20.0
**Standard**: OWASP Top 10 + Enterprise deployment and observability standards

---

## Part A: Security

### 1. User Authentication

#### JWT Token
- Format: Bearer Token (`Authorization: Bearer <token>`)
- Access Token: 15 minutes, Refresh Token: 7 days
- Auto-refresh via Refresh Token
- Token blacklist on logout and password change

#### Password Security
- Min 8 chars, must include: uppercase, lowercase, digit, special char
- Cannot match username or be a common password
- Storage: bcrypt hash (never plaintext), min 10 rounds
- Reset: email link, 30-minute expiry

### 2. RBAC Permission Control

#### Roles
| Role | Description |
|------|-------------|
| Admin | Full system access |
| Manager | View + edit |
| Operator | View + partial edit |
| Viewer | Read-only |

#### Permission Granularity
- Resource permissions: `finance.read`, `finance.write`
- Data permissions: access only own shop data
- Operation permissions: `export`, `import`
- Redis cache for permissions; invalidate on change

### 3. Data Encryption

- **At rest**: bcrypt for passwords; AES-256-GCM for sensitive fields (credit cards, bank accounts); key management via KMS/Vault
- **In transit**: HTTPS mandatory (TLS 1.2+); valid SSL cert; HSTS enabled

### 4. OWASP Top 10 Summary

| Threat | Mitigation |
|--------|-----------|
| A01 Broken Access Control | Least-privilege RBAC, per-endpoint permission checks, resource-level auth |
| A02 Cryptographic Failures | Encrypt sensitive data at rest and in transit; use KMS |
| A03 Injection | Parameterized queries (SQLAlchemy ORM); input validation; output encoding |
| A04 Insecure Design | Threat modeling at design phase; security design review |
| A05 Security Misconfiguration | Disable unnecessary features; minimize attack surface; periodic config audit |
| A06 Vulnerable Components | `safety` (Python) + `npm audit` (Node) in CI; regular dependency updates; CVE monitoring |
| A07 Auth Failures | Strong password policy; optional 2FA; lock after 5 failed logins (30min) |
| A08 Integrity Failures | Code signing; dependency integrity verification; data checksums |
| A09 Logging Failures | Log all critical ops (login, data changes, permission changes); audit fields; permanent retention |
| A10 SSRF | URL whitelist; input URL validation; network isolation |

### 5. Security Audit

- Audit log for: login, data modification, permission changes, config changes
- Audit fields: created_by, updated_by, deleted_by
- Independent audit table (immutable)
- Compliance: GDPR, SOC 2, ISO 27001

### 6. Security Testing

| Type | Tool | Frequency |
|------|------|-----------|
| Dependency scan | safety (Python), npm audit (Node) | Every CI run |
| Code scan | bandit (Python), ESLint (JS) | Every commit |
| Penetration test | Third-party security firm | Quarterly |

### 7. Security Incident Response

1. **Detect** -> 2. **Isolate** -> 3. **Assess** impact -> 4. **Fix** -> 5. **Restore** -> 6. **Post-mortem**

Severity levels: Critical (data breach, intrusion), High (unauthorized access, privilege escalation), Medium (potential vulnerability), Low (warnings, config issues).

### 8. Security Checklist

**Development**:
- [ ] Parameterized queries (prevent SQL injection)
- [ ] Input validation + output encoding (prevent XSS)
- [ ] Permission checks on every endpoint
- [ ] Sensitive data encrypted
- [ ] HTTPS for all traffic

**Deployment**:
- [ ] Secure defaults
- [ ] Minimal attack surface
- [ ] Dependency vulnerability scan
- [ ] Security config review
- [ ] Audit logging configured

**Operations**:
- [ ] Periodic security scans
- [ ] Log monitoring and alerting
- [ ] Incident response process
- [ ] Periodic penetration tests
- [ ] Security training

---

## Part B: Deployment & CI/CD

### 1. CI/CD Pipeline

**Continuous Integration**:
- Auto-run unit tests, integration tests on PR
- Auto-run Ruff, Pylint, mypy, bandit
- Coverage check (fail if below target)
- Auto-build Docker images

**Continuous Deployment**:
- Auto-deploy to Staging environment
- Production: approval required
- One-click rollback support

### 2. GitHub Actions Workflow Rules

#### SSH Remote Commands: Require pinned host keys

Do not disable host verification with `StrictHostKeyChecking=no`.
Store the server host key in a GitHub Actions secret such as `PRODUCTION_HOST_KEY` or `STAGING_HOST_KEY`, write it to `~/.ssh/known_hosts`, and keep strict host checking enabled.

For complex remote commands, prefer a checked-in remote script or a carefully quoted `bash -c '...'` block:

```yaml
- name: Deploy
  run: |
    ssh -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=10 \
        ${PRODUCTION_USER}@${PRODUCTION_HOST} \
      "bash -c '
      set -e
      cd \"${PRODUCTION_PATH}\"
      IMAGE_TAG_VAL=\"${IMAGE_TAG}\"
      echo \"[INFO] Pulling images with tag: \${IMAGE_TAG_VAL}\"
      docker pull image:\${IMAGE_TAG_VAL}
      '"
```

#### Variable Expansion Rules

| Variable Type | Example | Escape | Expands Where |
|--------------|---------|--------|---------------|
| GitHub Actions var | `${PRODUCTION_PATH}` | No escape | Local (GHA runtime) |
| GHA expression | `${{ secrets.TOKEN }}` | No escape | Local (GHA runtime) |
| Remote shell var | `\$retry` | Escape `$` | Remote (SSH server) |
| Remote quotes | `\"text\"` | Escape `"` | Remote (SSH server) |
| Command substitution | `\$(date ...)` | Escape `$` | Remote (SSH server) |

### 3. Deployment Strategies

**Blue-green** (zero downtime):
- Dual environments running simultaneously
- Gradual traffic switch to new version
- Fast rollback by switching back

**Canary release** (progressive):
- Deploy to small traffic slice first
- Monitor health
- Gradually expand traffic

**Rollback**:
- One-click rollback to previous version
- Keep last 5 versions
- Ensure data compatibility

### 4. Operations Standards

#### Health Checks

| Endpoint | Purpose | K8s Probe |
|----------|---------|-----------|
| `/health/ready` | Service readiness (DB, deps) | readiness |
| `/health/live` | Process alive | liveness |
| `/health` | Comprehensive health | monitoring |

#### Graceful Shutdown
- Handle SIGTERM properly
- Wait for in-flight requests to complete
- Clean up DB connections, file handles

#### Configuration
- Environment variables for all config
- Validate config completeness at startup
- Support hot-reload where possible

---

## Part C: Monitoring & Observability

### 1. Metrics

**System metrics**:
- CPU usage (alert > 80%)
- Memory usage (alert > 80%)
- Disk I/O (alert > 80%)
- Network traffic
- Disk space (alert > 85%)

**Application metrics**:
- QPS (requests per second)
- Response time: P50, P95, P99
- Error rate (alert > 5%)
- Concurrent requests
- Throughput

**Business metrics**:
- GMV (real-time)
- Order volume (real-time)
- Conversion rate (real-time)
- Inventory levels
- Active users

**Prometheus export**: `/metrics` endpoint with standard naming (`http_requests_total`, `http_request_duration_seconds`).

### 2. Distributed Tracing

- **Request ID**: UUID per request, propagated across API calls, DB queries, message queues. All logs include request_id.
- **OpenTelemetry + Jaeger**: distributed tracing with span recording
- **Performance analysis**: identify slow queries (>100ms), slow APIs (>500ms), bottlenecks

### 3. Alert Rules

| Condition | Level | Notification |
|-----------|-------|-------------|
| API error rate > 5% | Critical | Email, SMS, WeChat |
| P95 response > 2s | Warning | Email, WeChat |
| CPU/Memory > 80% | Warning | Email |
| GMV drops > 10% | Warning | Email, WeChat |
| Order volume anomaly | Warning | Email, WeChat |
| Conversion rate drops > 5% | Warning | Email |

Alert levels: Critical (immediate), Warning (30min), Info (log only).

### 4. Component-Specific Monitoring

#### Celery Workers
- Task execution time (alert > 30min)
- Task failure rate (alert > 10%)
- Queue length (alert > 100)
- Worker status

```bash
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect active
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect stats
```

#### Nginx
- Request count, response time
- Rate limit triggers (429 status)
- 5xx error rate (alert > 1%)

#### Redis
- Memory usage (alert > 80%)
- Connection count (alert > 1000)
- Command execution time (alert > 100ms)
- AOF/RDB persistence status

```bash
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO clients
```

### 5. Troubleshooting Guide

#### Celery: Task failures
```bash
docker-compose -f docker-compose.prod.yml logs celery-worker | grep -i error
```

#### Celery: Queue backlog
Increase concurrency via `CELERY_WORKER_CONCURRENCY` env var.

#### Nginx: 502 Bad Gateway
Check backend is running: `docker-compose ps backend`
Check backend logs: `docker-compose logs backend | tail -50`
Validate config: `docker-compose exec nginx nginx -t`

#### Nginx: Rate limiting too strict
Review `nginx/nginx.prod.conf` limit_req settings, reload with `nginx -s reload`.

#### Redis: Out of memory
```bash
docker-compose exec redis redis-cli CONFIG SET maxmemory 2gb
docker-compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

#### Redis: Connection failure
```bash
docker-compose exec redis redis-cli -a <password> ping
```

### 6. Performance Optimization

#### Celery
- Adjust `CELERY_WORKER_CONCURRENCY` based on CPU cores
- Use task priorities (10=high, 5=normal, 1=low)
- Batch small tasks with `chord` and `group`

#### Nginx
- Enable proxy cache: `proxy_cache_path` + `proxy_cache_valid 200 5m`
- Enable gzip compression for text/css/json/js
- Connection pool: `keepalive 32` in upstream

#### Redis
- Set `maxmemory` and `maxmemory-policy allkeys-lru`
- AOF sync: `appendfsync everysec` (recommended balance)
- Use connection pools, set reasonable timeouts

### 7. Monitoring Tools

| Category | Options |
|----------|---------|
| Open source | Prometheus + Grafana, ELK Stack, Jaeger |
| Commercial | Datadog, New Relic, Splunk |
| Cloud | AWS CloudWatch, Azure Monitor, Google Cloud Monitoring |
| APM | New Relic, Datadog, AWS X-Ray |

### 8. Database Monitoring

- Slow queries > 100ms
- Connection pool utilization
- Lock wait monitoring

### 9. Frontend Monitoring

- Page load time
- Frontend error rate
- UX metrics (first paint, interaction response time)

---

**Last updated**: 2026-03-16
**Status**: Production-ready (v4.20.0)

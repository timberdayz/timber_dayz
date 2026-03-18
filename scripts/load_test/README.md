# Load Test Scripts

This directory contains k6 load test scripts for the XiHong ERP system.

## Prerequisites

Install k6: https://k6.io/docs/get-started/installation/

```bash
# Windows (via chocolatey)
choco install k6

# macOS
brew install k6

# Or download binary from https://github.com/grafana/k6/releases
```

## Scripts

| Script | Purpose |
|---|---|
| `baseline.js` | Baseline: Login + paginated list reads (50 VUs, 2 min) |
| `write_ops.js` | Write operations: create/update targets and performance scores |
| `full_scenario.js` | Combined scenario: all critical paths |

## Running Tests

```bash
# Baseline test (recommended before/after each major release)
k6 run --env BASE_URL=http://localhost:8000 --env USERNAME=admin --env PASSWORD=yourpassword scripts/load_test/baseline.js

# With output to file
k6 run --out json=scripts/load_test/reports/baseline_$(date +%Y%m%d).json scripts/load_test/baseline.js

# Custom VUs and duration
k6 run --vus 50 --duration 120s scripts/load_test/baseline.js
```

## Pass Criteria (from PRODUCTION_READINESS.md D1/D2)

| Metric | Threshold |
|---|---|
| Concurrent users | 50 VUs sustained for 2 minutes |
| Error rate | < 1% |
| Critical read p95 | < 300ms |
| Critical write p95 | < 800ms |
| Complex report p95 | < 3s |
| DB connection pool | No overflow errors |

## Report Template

After each test run, save a report to `scripts/load_test/reports/` with:
- Test date and version
- VUs and duration
- Error rate
- p95/p99 per scenario
- Peak DB connection count (from application logs)
- Pass/Fail verdict per SLO

Example: `reports/baseline_20260317_v4.20.0.md`

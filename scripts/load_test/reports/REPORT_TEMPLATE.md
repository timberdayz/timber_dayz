# Load Test Report — XiHong ERP

**Date**: YYYY-MM-DD
**Version**: vX.Y.Z
**Tester**: [name]
**Trigger**: [reason — e.g., "DB schema change: add index on orders.created_at"]

## Test Configuration

| Parameter | Value |
|---|---|
| Target environment | staging / local |
| Script | baseline.js / write_ops.js / full_scenario.js |
| Virtual users | 50 |
| Duration | 2 minutes |
| Base URL | http://... |

## Results

| Metric | Measured | Threshold | Status |
|---|---|---|---|
| Error rate | X.XX% | < 1% | PASS / FAIL |
| Login p95 | XXXms | < 800ms | PASS / FAIL |
| List read p95 | XXXms | < 300ms | PASS / FAIL |
| Write operation p95 | XXXms | < 800ms | PASS / FAIL |
| Complex report p95 | XXXXms | < 3000ms | PASS / FAIL |
| DB connection overflow | None / XX errors | 0 | PASS / FAIL |

## Overall Verdict: PASS / FAIL

## Observations

(Any notable findings, spikes, patterns)

## Action Items

- [ ] (If FAIL: describe what needs to be fixed)
- [ ] (Performance optimization items, if any)

## Raw Output

```
(paste k6 stdout here)
```

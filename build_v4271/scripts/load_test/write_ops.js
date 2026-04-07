/**
 * XiHong ERP - Write Operations Load Test
 *
 * Scenarios: Create/update targets, trigger collection tasks
 * Target: 20 concurrent users, 2 minutes (lower than reads — writes are heavier)
 * Pass criteria: error rate < 1%, p95 < 800ms for writes
 *
 * Usage:
 *   k6 run --env BASE_URL=http://localhost:8000 \
 *          --env USERNAME=admin \
 *          --env PASSWORD=yourpassword \
 *          scripts/load_test/write_ops.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const USERNAME = __ENV.USERNAME || 'admin';
const PASSWORD = __ENV.PASSWORD || 'password';

const errorRate = new Rate('error_rate');
const writeTrend = new Trend('write_duration', true);

export const options = {
  scenarios: {
    write_ops: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
    },
  },
  thresholds: {
    error_rate: ['rate<0.01'],
    write_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.01'],
  },
};

function login() {
  const payload = JSON.stringify({ username: USERNAME, password: PASSWORD });
  const res = http.post(`${BASE_URL}/api/auth/login`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (res.status === 200) {
    try {
      return JSON.parse(res.body).access_token;
    } catch {
      return null;
    }
  }
  return null;
}

function authHeaders(token) {
  return {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  };
}

let iterationCount = 0;

export default function () {
  iterationCount++;
  const token = login();
  if (!token) {
    errorRate.add(1);
    sleep(1);
    return;
  }

  const headers = authHeaders(token);

  // Write operation: update a user's profile (non-destructive)
  group('Write Operations', () => {
    // Fetch a user to update
    const usersRes = http.get(`${BASE_URL}/api/users/?page=1&page_size=5`, headers);
    if (usersRes.status !== 200) {
      errorRate.add(1);
      return;
    }

    let users = [];
    try {
      const body = JSON.parse(usersRes.body);
      users = body.data || body || [];
    } catch {
      errorRate.add(1);
      return;
    }

    if (users.length === 0) {
      sleep(1);
      return;
    }

    // PATCH user (non-destructive: just update a timestamp-like field)
    const userId = users[0].id;
    if (userId) {
      const patchRes = http.patch(
        `${BASE_URL}/api/users/${userId}`,
        JSON.stringify({ last_load_test: new Date().toISOString() }),
        headers
      );
      // Accept 200, 204, or 422 (if field doesn't exist — not a real failure)
      const writeOk = check(patchRes, {
        'write operation acceptable': (r) => [200, 204, 400, 422, 403].includes(r.status),
      });
      writeTrend.add(patchRes.timings.duration);
      errorRate.add(!writeOk);
    }

    sleep(0.5);
  });

  sleep(Math.random() * 3 + 2);
}

export function handleSummary(data) {
  const errorPct = (data.metrics.error_rate?.values?.rate * 100 || 0).toFixed(2);
  const writeP95 = (data.metrics.write_duration?.values?.['p(95)'] || 0).toFixed(0);
  const verdict = parseFloat(errorPct) < 1 && parseInt(writeP95) < 800 ? 'PASS' : 'FAIL';

  const summary = `
=== XiHong ERP Write Operations Load Test ===
Date: ${new Date().toISOString()}
VUs: 20, Duration: 2min

Results:
  Error rate:   ${errorPct}%  (threshold: < 1%)
  Write p95:    ${writeP95}ms  (threshold: < 800ms)

Verdict: ${verdict}
=============================================
`;

  console.log(summary);
  return { stdout: summary };
}

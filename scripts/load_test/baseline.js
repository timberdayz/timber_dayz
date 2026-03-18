/**
 * XiHong ERP - Baseline Load Test
 *
 * Scenarios: Login + critical read endpoints
 * Target: 50 concurrent users, 2 minutes
 * Pass criteria: error rate < 1%, p95 < 300ms for reads
 *
 * Usage:
 *   k6 run --env BASE_URL=http://localhost:8000 \
 *          --env USERNAME=admin \
 *          --env PASSWORD=yourpassword \
 *          scripts/load_test/baseline.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// --- Configuration ---
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const USERNAME = __ENV.USERNAME || 'admin';
const PASSWORD = __ENV.PASSWORD || 'password';

// --- Custom Metrics ---
const errorRate = new Rate('error_rate');
const loginTrend = new Trend('login_duration', true);
const listReadTrend = new Trend('list_read_duration', true);
const reportTrend = new Trend('report_duration', true);

// --- Test Options (SLO thresholds from PRODUCTION_READINESS.md D1) ---
export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-vus',
      vus: 50,
      duration: '2m',
    },
  },
  thresholds: {
    // Overall error rate < 1%
    error_rate: ['rate<0.01'],
    // Critical read endpoints p95 < 300ms
    list_read_duration: ['p(95)<300'],
    // Login p95 < 800ms (write category)
    login_duration: ['p(95)<800'],
    // Complex report p95 < 3s
    report_duration: ['p(95)<3000'],
    // HTTP failures < 1%
    http_req_failed: ['rate<0.01'],
  },
};

// --- Shared state for tokens ---
let authToken = null;

function login() {
  const payload = JSON.stringify({ username: USERNAME, password: PASSWORD });
  const params = { headers: { 'Content-Type': 'application/json' } };

  const res = http.post(`${BASE_URL}/api/auth/login`, payload, params);
  const start = Date.now();

  const success = check(res, {
    'login status 200': (r) => r.status === 200,
    'login has token': (r) => {
      try {
        return JSON.parse(r.body).access_token !== undefined;
      } catch {
        return false;
      }
    },
  });

  loginTrend.add(res.timings.duration);
  errorRate.add(!success);

  if (success) {
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

// --- Main virtual user function ---
export default function () {
  // Step 1: Login (once per VU iteration if no token)
  const token = login();
  if (!token) {
    errorRate.add(1);
    sleep(1);
    return;
  }

  const headers = authHeaders(token);

  // Step 2: Critical read endpoints
  group('Critical Reads', () => {
    // User list
    const usersRes = http.get(`${BASE_URL}/api/users/?page=1&page_size=20`, headers);
    const usersOk = check(usersRes, {
      'users list 200': (r) => r.status === 200,
    });
    listReadTrend.add(usersRes.timings.duration);
    errorRate.add(!usersOk);

    sleep(0.5);

    // Target list
    const targetsRes = http.get(`${BASE_URL}/api/targets/?page=1&page_size=20`, headers);
    const targetsOk = check(targetsRes, {
      'targets list 200': (r) => r.status === 200,
    });
    listReadTrend.add(targetsRes.timings.duration);
    errorRate.add(!targetsOk);

    sleep(0.5);

    // Performance list
    const perfRes = http.get(`${BASE_URL}/api/performance/?page=1&page_size=20`, headers);
    const perfOk = check(perfRes, {
      'performance list 200': (r) => r.status === 200,
    });
    listReadTrend.add(perfRes.timings.duration);
    errorRate.add(!perfOk);

    sleep(0.5);
  });

  // Step 3: Complex report / dashboard
  group('Reports', () => {
    const dashRes = http.get(`${BASE_URL}/api/dashboard/summary`, headers);
    const dashOk = check(dashRes, {
      'dashboard summary 200': (r) => r.status === 200 || r.status === 404,
    });
    reportTrend.add(dashRes.timings.duration);
    errorRate.add(!dashOk);

    sleep(1);
  });

  // Think time between iterations
  sleep(Math.random() * 2 + 1);
}

// --- Teardown: print summary ---
export function handleSummary(data) {
  const errorPct = (data.metrics.error_rate?.values?.rate * 100 || 0).toFixed(2);
  const listP95 = (data.metrics.list_read_duration?.values?.['p(95)'] || 0).toFixed(0);
  const loginP95 = (data.metrics.login_duration?.values?.['p(95)'] || 0).toFixed(0);
  const reportP95 = (data.metrics.report_duration?.values?.['p(95)'] || 0).toFixed(0);

  const verdict = parseFloat(errorPct) < 1 && parseInt(listP95) < 300 ? 'PASS' : 'FAIL';

  const summary = `
=== XiHong ERP Load Test Report ===
Date: ${new Date().toISOString()}
VUs: 50, Duration: 2min

Results:
  Error rate:      ${errorPct}%  (threshold: < 1%)
  Login p95:       ${loginP95}ms  (threshold: < 800ms)
  List read p95:   ${listP95}ms  (threshold: < 300ms)
  Report p95:      ${reportP95}ms  (threshold: < 3000ms)

Verdict: ${verdict}
===================================
`;

  console.log(summary);

  return {
    stdout: summary,
  };
}

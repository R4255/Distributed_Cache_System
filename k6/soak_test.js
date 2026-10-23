// soak_test.js — 100 VUs for 30 minutes. Detects memory leaks & degradation.
// Run: k6 run k6/soak_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus:      100,
  duration: '30m',
  thresholds: {
    http_req_duration: ['p(99)<500'],    // even after 30m, p99 must stay < 500ms
    http_req_failed:   ['rate<0.001'],   // < 0.1% failures throughout
  },
};

// A 404 is a cache miss, not a failure: only 5xx/timeouts should count toward http_req_failed.
http.setResponseCallback(http.expectedStatuses(200, 404));

const BASE    = 'http://localhost:8000';
const HEADERS = { 'Content-Type': 'application/json' };

export default function () {
  const key  = `soak:${Math.floor(Math.random() * 5000)}`;
  const roll = Math.random();

  if (roll < 0.70) {
    // 70% GET
    http.get(`${BASE}/cache/${key}`);
  } else if (roll < 0.90) {
    // 20% SET (with TTL so keys expire and keep memory bounded)
    http.put(`${BASE}/cache/${key}`,
      JSON.stringify({ value: 'x'.repeat(256), ttl: 300 }),
      { headers: HEADERS });
  } else if (roll < 0.95) {
    // 5% DELETE
    http.del(`${BASE}/cache/${key}`);
  } else {
    // 5% STATS (observability polling)
    const res = http.get(`${BASE}/stats`);
    check(res, { 'stats ok': (r) => r.status === 200 });
  }
  sleep(0.01);
}

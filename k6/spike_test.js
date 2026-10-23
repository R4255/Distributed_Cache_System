// spike_test.js — Sudden burst from 10 → 1000 VUs to test resilience.
// Run: k6 run k6/spike_test.js
import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const errRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '10s', target: 10   },  // baseline
    { duration: '5s',  target: 1000 },  // SPIKE — instant 100x surge
    { duration: '30s', target: 1000 },  // hold spike
    { duration: '10s', target: 10   },  // recovery
    { duration: '10s', target: 0    },  // done
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],     // tolerate up to 5% errors during spike
    errors:          ['rate<0.05'],
  },
};

// A 404 is a cache miss, not a failure: only 5xx/timeouts should count toward http_req_failed.
http.setResponseCallback(http.expectedStatuses(200, 404));

const BASE = 'http://localhost:8000';

export default function () {
  const key = `spike:${Math.floor(Math.random() * 500)}`;
  const res = http.get(`${BASE}/cache/${key}`);
  const ok  = check(res, {
    'not a 5xx': (r) => r.status < 500,
    'responded': (r) => r.timings.duration < 2000,
  });
  if (!ok) errRate.add(1);
}

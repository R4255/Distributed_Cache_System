// smoke_test.js — 1 VU, 30s. Confirms baseline correctness & latency.
// Run: k6 run k6/smoke_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(99)<100'],
    http_req_failed:   ['rate<0.01'],
  },
};

const BASE = 'http://localhost:8000';
const HEADERS = { 'Content-Type': 'application/json' };

export function setup() {
  // Seed 50 keys before the test starts
  for (let i = 0; i < 50; i++) {
    http.put(`${BASE}/cache/smoke:${i}`,
      JSON.stringify({ value: `val_${i}`, ttl: 120 }), { headers: HEADERS });
  }
}

export default function () {
  const key = `smoke:${Math.floor(Math.random() * 50)}`;

  // GET
  const get = http.get(`${BASE}/cache/${key}`);
  check(get, {
    'GET 200 or 404': (r) => r.status === 200 || r.status === 404,
    'GET < 50ms':     (r) => r.timings.duration < 50,
  });

  // SET
  const set = http.put(`${BASE}/cache/${key}`,
    JSON.stringify({ value: 'updated', ttl: 60 }), { headers: HEADERS });
  check(set, { 'SET 200': (r) => r.status === 200 });

  sleep(0.1);
}

// load_test.js — Ramps to 500 VUs with 80/20 read-write mix.
// Tracks cache hits, misses, hit rate as custom metrics.
// Run: k6 run k6/load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics — visible in k6 summary and InfluxDB/Grafana
const cacheHits   = new Counter('cache_hits');
const cacheMisses = new Counter('cache_misses');
const setOps      = new Counter('cache_sets');
const getLatency  = new Trend('get_latency_ms', true);
const setLatency  = new Trend('set_latency_ms', true);
const errRate     = new Rate('error_rate');

export const options = {
  stages: [
    { duration: '30s', target: 50   },  // warm up
    { duration: '60s', target: 200  },  // ramp
    { duration: '30s', target: 500  },  // stress
    { duration: '60s', target: 500  },  // sustain
    { duration: '30s', target: 0    },  // cool down
  ],
  thresholds: {
    http_req_duration:       ['p(95)<100', 'p(99)<250'],
    error_rate:              ['rate<0.01'],
    get_latency_ms:          ['p(99)<200'],
  },
};

// A 404 is a cache miss, not a failure: only 5xx/timeouts should count toward http_req_failed.
http.setResponseCallback(http.expectedStatuses(200, 404));

const BASE    = 'http://localhost:8000';
const HEADERS = { 'Content-Type': 'application/json' };
const KEY_SPACE = 10_000;

export function setup() {
  // Pre-warm 1000 keys so GETs produce real hits
  for (let i = 0; i < 1000; i++) {
    http.put(`${BASE}/cache/key:${i}`,
      JSON.stringify({ value: `value_${i}`, ttl: 300 }), { headers: HEADERS });
  }
  console.log('Setup: 1000 keys pre-warmed');
}

export default function () {
  const isWrite = Math.random() < 0.20;   // 80% reads, 20% writes (realistic prod ratio)
  const key     = `key:${Math.floor(Math.random() * KEY_SPACE)}`;

  if (isWrite) {
    const t   = Date.now();
    const res = http.put(`${BASE}/cache/${key}`,
      JSON.stringify({ value: `v_${__VU}_${__ITER}`, ttl: 120 }),
      { headers: HEADERS });
    setLatency.add(Date.now() - t);
    check(res, { 'SET ok': (r) => r.status === 200 }) ? setOps.add(1) : errRate.add(1);
  } else {
    const t   = Date.now();
    const res = http.get(`${BASE}/cache/${key}`);
    getLatency.add(Date.now() - t);
    if      (res.status === 200) { cacheHits.add(1); }
    else if (res.status === 404) { cacheMisses.add(1); }
    else                         { errRate.add(1); }
  }
}

export function teardown() {
  const stats = http.get(`${BASE}/stats`);
  if (stats.status === 200) {
    const body = JSON.parse(stats.body);
    console.log('Final hit rate:', body.aggregate.overall_hit_rate);
  }
}

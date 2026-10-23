# Distributed Cache System

An in-memory key-value cache written from scratch in Python: **consistent-hash routing across nodes**, three eviction policies (**O(1) LRU, O(log n) LFU, TTL**), lazy and background expiry, a **Redis-style TCP protocol**, a **FastAPI REST API**, **Prometheus metrics**, and a **k6 load-testing suite**.

I built it to understand what Redis and Memcached clusters actually do underneath: how keys find their node, why adding a server doesn't reshuffle everything, which data structure makes eviction cheap, and how it all behaves under load.

## At a glance

All numbers measured on an Apple M2 (16 GB), one process, one uvicorn worker. Method and raw output are in [Results](#results).

| | |
|---|---|
| **8,644 req/s** at 500 concurrent users | p95 **62 ms**, p99 **73 ms**, 0 errors, 1.82 M requests (k6 load test, 80/20 read/write) |
| **18.6%** of keys move when a 5th node joins | ideal is 20%; plain `hash % N` moves **80.1%** |
| **~636,000 GET/s** per node | in-process, single thread, LRU, full cache |
| **1.4 µs** to route a key | binary search over 600 ring positions (4 nodes × 150 virtual nodes) |

## Architecture

```
                         ┌──────────────────────────── api.py (FastAPI) ─────────────────────────────┐
  HTTP :8000  ─────────► │  PUT/GET/DELETE /cache/{key}                                               │
  (curl, k6, apps)       │          │                                                                 │
                         │          ▼                                                                 │
                         │  ConsistentHashRing.get_node(key)   MD5 → 128-bit ring position,           │
                         │          │                          bisect to the next virtual node        │
                         │   ┌──────┼──────────────┬──────────────┐                                   │
                         │   ▼      ▼              ▼              ▼                                   │
                         │ CacheNode "node:0"   "node:1"   …   "node:N"    (in-process shards)        │
                         │   ├─ store: LRUStore | LFUStore | TTLStore                                 │
                         │   ├─ threading.RLock around every operation                                │
                         │   └─ daemon thread: sweeps expired keys every 30 s                         │
                         │                                                                            │
                         │  /metrics ──► Prometheus (scrapes every 5 s) ──► Grafana                   │
                         └────────────────────────────────────────────────────────────────────────────┘

  TCP :6379  ──► server.py (asyncio.start_server) ──► protocol.py (GET/SET/DEL/STATS/KEYS) ──► one CacheNode
  (client.py, telnet, nc)
```

There are two ways in:

- **The REST API (`api.py`)** is the "cluster": every key is routed through the hash ring to one of several cache nodes, and nodes can be added or removed at runtime.
- **The TCP server (`main.py` → `server.py`)** serves a single cache node over a Redis-like line protocol. It's the simplest way to poke at eviction and TTL behaviour by hand.

## How it works

### Consistent hashing

With naive `hash(key) % N`, changing `N` remaps almost every key, so adding one cache server wipes out most of the hit rate. A consistent-hash ring fixes that:

1. Each node is hashed onto a ring (MD5 → a position in `[0, 2^128)`) **150 times**, as virtual nodes (`node:1#vn:0` … `node:1#vn:149`).
2. Ring positions are kept in a sorted list, so a key is routed by hashing it and binary-searching (`bisect`) for the next virtual node clockwise: **O(log V)**.
3. When a node joins, it only takes over the arcs just before its virtual nodes, so only about **1/N** of keys change owner.

Measured over 100,000 keys:

| Cluster change | Keys that changed node (ring) | Ideal (1/N) | With `hash % N` |
|---|---|---|---|
| 3 → 4 nodes | 26.2% | 25.0% | 75.0% |
| 4 → 5 nodes | **18.6%** | 20.0% | 80.1% |
| 5 → 6 nodes | 16.5% | 16.7% | 83.4% |
| 8 → 9 nodes | 11.3% | 11.1% | 88.7% |

Virtual nodes are what make the load even. Key share per node with 4 nodes:

| Virtual nodes per node | Smallest share | Largest share | Std. dev. |
|---|---|---|---|
| 1 | 5.0% | 59.4% | 20.5 pp |
| 10 | 22.2% | 27.6% | 2.2 pp |
| 50 | 23.3% | 27.8% | 1.7 pp |
| **150 (default)** | 20.5% | 26.8% | 2.6 pp |
| 500 | 24.3% | 25.7% | 0.6 pp |

With a single position per node, one node owned 59% of the keys. Beyond a few dozen virtual nodes the spread depends on MD5's luck with the particular node names; 500 virtual nodes tighten it to ±0.7 pp at the cost of a bigger ring.

The ring also exposes `get_replica_nodes(key, n)` (the next *n* distinct physical nodes clockwise), and `GET /ring/debug/{key}` shows exactly where any key lands.

### Eviction policies

Each node takes one policy, and each policy is a store with the data structure that makes its eviction cheap:

| Policy | Evicts | Data structure | GET | Evict |
|---|---|---|---|---|
| **LRU** | least recently used | `OrderedDict`: `move_to_end` on access, `popitem(last=False)` to evict | O(1) | O(1) |
| **LFU** | least frequently used (ties: oldest access) | min-heap of `(freq, last_access, key, version)` + per-key version | O(log n) push | O(log n) amortised |
| **TTL** | the entry that expires soonest | min-heap of `(expires_at, key)` | O(1) | O(log n) amortised |

The LRU store replaced an earlier version that scanned every entry with `min()` (O(n) per eviction). The LFU store uses **lazy deletion**: instead of updating an entry inside the heap (O(n)), every access pushes a new versioned entry, and stale ones are discarded when they reach the top.

Measured correctness (each passes): LRU keeps a recently read key and evicts the oldest untouched one; LFU keeps the two hot keys and evicts the cold one; TTL evicts the soonest-expiring key; an expired key reads as a miss.

### Expiry

Keys can carry a TTL in seconds. Expiry happens in two places:

- **Lazily on read:** `get` checks `is_expired()` and deletes the entry on the spot, so a reader never sees a stale value.
- **In the background:** a daemon thread wakes every 30 seconds and removes expired entries that nobody has read, so memory doesn't fill with dead keys.

### Concurrency

The TCP server runs on an asyncio event loop (many connections, one thread), while the cleanup sweeper is a real OS thread. That's why each node guards its store with a `threading.RLock` rather than an `asyncio.Lock`: an asyncio lock is only safe between coroutines, not between threads. The REST handlers are plain `def` functions, so FastAPI runs them in its thread pool and the same lock protects them.

### Observability

`GET /metrics` serves Prometheus text format:

| Metric | Type |
|---|---|
| `cache_hits_total`, `cache_misses_total` | counter |
| `cache_sets_total`, `cache_deletes_total` | counter |
| `cache_evictions_total{policy}` | counter |
| `cache_current_size` | gauge |
| `cache_get_latency_seconds`, `cache_set_latency_seconds` | histogram (50 µs – 500 ms buckets) |

`GET /stats` adds per-node hit rate, evictions, fill percentage and uptime, plus cluster totals. Docker Compose runs Prometheus (scraping every 5 s) and Grafana next to the API.

## Results

Measured on 2026-10-24, Apple M2, 16 GB RAM, Python 3.14, one `uvicorn` worker, k6 running on the same machine. The k6 scripts are in [`k6/`](k6/). They treat `404` as an expected response, because a 404 is a cache miss rather than a failure, so `http_req_failed` counts only real errors (5xx, timeouts).

### Load test: `k6/load_test.js`

Ramps 50 → 200 → 500 virtual users over 3.5 minutes, holding 500 for a minute; 80% GETs, 20% SETs, over a 10,000-key space with 1,000 keys pre-warmed.

| Metric | Result | Threshold |
|---|---|---|
| Throughput | **8,644 req/s** (1,817,651 requests) | |
| Latency p50 / p95 / p99 | 23.3 ms / **62.2 ms** / **72.7 ms** | p95 < 100 ms ✓, p99 < 250 ms ✓ |
| Max latency | 113.6 ms | |
| Failed requests | **0%** | < 1% ✓ |
| Hit rate (GETs) | 97.5% (1,417,047 hits, 36,370 misses) | |

### Smoke test: `k6/smoke_test.js`

One user for 30 seconds: p99 **2.8 ms**, 626 requests, 0% failed, 100% of checks passed.

### Spike test: `k6/spike_test.js`

10 → **1,000 users in 5 seconds**, held for 30 seconds: **6,835 req/s** (444,287 requests), p95 159 ms, p99 168 ms, **0% failed**, no 5xx responses, and every request answered well under the 2 s check. All thresholds passed.

### Soak test: `k6/soak_test.js`

100 users for 30 minutes with a GET/SET/DELETE/STATS mix, written to catch memory growth and slow degradation. Not part of this run.

### Single node, in-process

100,000 operations against a full 10,000-entry node, single thread (no HTTP):

| Policy | GET ops/s | SET ops/s (every SET evicts) |
|---|---|---|
| LRU | 635,859 | 228,708 |
| LFU | 557,750 | 182,050 |
| TTL | 646,647 | 206,856 |

The gap between ~600,000 ops/s in-process and ~8,000 req/s over HTTP is the cost of HTTP parsing, JSON and the Python web stack, not the cache. That's why production caches use compact binary protocols and native code.

## Getting started

### Run everything with Docker

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Cache API + Swagger UI | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana (admin / admin) | http://localhost:3000 (add Prometheus at `http://prometheus:9090` as a data source) |

### Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --port 8000 --workers 1      # REST API
```

Keep `--workers 1`: cache state lives in process memory, so several workers would each hold a separate cache.

### Try the REST API

```bash
# write, read, delete
curl -X PUT localhost:8000/cache/user:42 -H 'Content-Type: application/json' -d '{"value": "Rohit", "ttl": 60}'
curl localhost:8000/cache/user:42                 # {"key":"user:42","value":"Rohit","node":"node:0"}
curl -X DELETE localhost:8000/cache/user:42

# grow the cluster and watch keys spread out
curl -X POST "localhost:8000/admin/node/node:1?max_size=10000&policy=lfu"
curl localhost:8000/ring                          # nodes and virtual nodes per node
curl localhost:8000/ring/debug/user:42            # owner node, ring position, replica candidates

# batch operations, stats, metrics
curl -X POST localhost:8000/cache/batch/get -H 'Content-Type: application/json' -d '{"keys": ["a", "b"]}'
curl localhost:8000/stats
curl localhost:8000/metrics
```

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/cache/{key}` | read (200 hit, 404 miss or expired) |
| `PUT` | `/cache/{key}` | write `{"value": "...", "ttl": seconds?}` (507 if the cache is full and eviction fails) |
| `DELETE` | `/cache/{key}` | delete |
| `GET` | `/cache?limit=` | list live keys across all nodes |
| `POST` | `/cache/batch/get`, `/cache/batch/set` | MGET / MSET equivalents |
| `GET` | `/ring`, `/ring/debug/{key}` | ring layout, and where a key routes |
| `GET` | `/stats`, `/metrics`, `/health` | per-node stats, Prometheus metrics, liveness |
| `POST` / `DELETE` | `/admin/node/{id}` | add (with `max_size`, `policy`) or remove a node; `node:0` can't be removed |
| `POST` | `/admin/flush` | wipe every node |

### Try the TCP protocol

```bash
python main.py --port 6379 --max-size 1000 --eviction lru     # lru | lfu | ttl
python client.py            # interactive prompt
python client.py demo       # scripted tour, including a key expiring
```

Or talk to it with any line-based tool, such as `nc localhost 6379`:

```
SET greeting hello world        → OK
SET answer 42                   → OK            (stored as "42")
SET session abc123 EX 30        → OK            (EX = TTL in seconds, as in Redis)
GET greeting                    → OK "hello world"
DEL greeting                    → OK
STATS                           → OK {"total_entries": 1, "hit_rate": 1.0, ...}
KEYS                            → OK ["session"]
```

### Run the load tests

```bash
k6 run k6/smoke_test.js     # 1 user, 30 s
k6 run k6/load_test.js      # up to 500 users, 3.5 min
k6 run k6/spike_test.js     # 10 → 1,000 users
k6 run k6/soak_test.js      # 100 users, 30 min
```

## Project layout

```
api.py              FastAPI app: ring routing, CRUD, batch ops, admin, /stats, /metrics
consistent_hash.py  ConsistentHashRing: MD5 positions, virtual nodes, bisect lookup, replicas
cache_node.py       CacheNode + LRUStore / LFUStore / TTLStore, expiry sweeper, Prometheus metrics
server.py           asyncio TCP server (one connection per client, line protocol)
protocol.py         GET / SET / DEL / STATS / KEYS command parsing
main.py             CLI entrypoint for the TCP server
client.py           async TCP client: interactive and demo modes
k6/                 smoke, load, soak and spike tests
docker-compose.yml  API + Prometheus + Grafana
prometheus.yml      scrape config
```

## Known limitations and what I'd do next

This is a learning build, so here is where it stops short of a production cache. Each point was checked by running the code.

1. **The nodes are in-process shards, not separate servers.** The ring routing, eviction and rebalancing logic are real, but all nodes live in one Python process, so this models a cluster rather than being one. *Next:* run each `CacheNode` behind its own TCP server and move the ring into a client-side router.
2. **Changing membership doesn't move data.** When a node joins, keys that now route to it miss once (measured: 521 of 2,000 keys after adding a 4th node), which is acceptable for a cache. When a node is removed, its keys fall back to their previous owner, which may still hold an **older value** if the key was updated in between. *Next:* invalidate or hand off moved keys on every membership change.
3. **Replicas are computed but not written.** `get_replica_nodes` picks the next distinct nodes on the ring, but values are only stored on the primary.
4. **`/ring` "distribution" counts virtual nodes, not keys.** It always shows an even split (e.g. 33.33% each), while the measured key share varies (20.5–26.8% with 4 nodes).
5. **The LFU heap grows with every read.** Lazy deletion keeps stale heap entries until they're popped. *Fix:* rebuild the heap when stale entries exceed a multiple of the live keys.
6. **One process, one worker.** State is process-local, Prometheus counters are shared across all in-process nodes (use `/stats` for per-node numbers), and `/admin/flush` leaves the old nodes' sweeper threads running.
7. **Grafana starts empty**: no dashboard is provisioned yet.

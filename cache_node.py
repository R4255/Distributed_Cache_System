"""
cache_node.py — Core cache logic.
Phase 2 upgrades:
  - O(1) LRU via OrderedDict (was O(n) min() scan)
  - O(log n) LFU via min-heap + lazy deletion
  - Prometheus metrics: hits, misses, evictions, latency histograms
  - Hit-rate tracking
  - Fixed: trailing colons in stats keys, explicit access_count=0
"""
import time
import heapq
import threading
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from prometheus_client import Counter, Histogram, Gauge
    CACHE_HITS      = Counter('cache_hits_total', 'Total cache hits')
    CACHE_MISSES    = Counter('cache_misses_total', 'Total cache misses')
    CACHE_SETS      = Counter('cache_sets_total', 'Total SET operations')
    CACHE_DELETES   = Counter('cache_deletes_total', 'Total DELETE operations')
    CACHE_EVICTIONS = Counter('cache_evictions_total', 'Evictions', ['policy'])
    CACHE_SIZE      = Gauge('cache_current_size', 'Live entries in cache')
    CACHE_GET_LAT   = Histogram('cache_get_latency_seconds', 'GET latency',
                                buckets=[.00005,.0001,.0005,.001,.005,.01,.05,.1,.5])
    CACHE_SET_LAT   = Histogram('cache_set_latency_seconds', 'SET latency',
                                buckets=[.00005,.0001,.0005,.001,.005,.01,.05,.1,.5])
    _PROM = True
except ImportError:
    _PROM = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


class EvictionPolicy(Enum):
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float
    accessed_at: float
    access_count: int = 0
    ttl: Optional[float] = None

    def is_expired(self) -> bool:
        return self.ttl is not None and time.time() > self.created_at + self.ttl

    def touch(self):
        self.accessed_at = time.time()
        self.access_count += 1


# ─── O(1) Store implementations ────────────────────────────────────────────────

class LRUStore:
    """O(1) LRU backed by OrderedDict. move_to_end = O(1), popitem(last=False) = O(1)."""
    def __init__(self):
        self._od: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> Optional[CacheEntry]:
        return self._od.get(key)

    def mark_accessed(self, key: str):
        if key in self._od:
            self._od.move_to_end(key)               # O(1)

    def set(self, key: str, entry: CacheEntry):
        self._od[key] = entry
        self._od.move_to_end(key)

    def on_update(self, key: str):
        self.mark_accessed(key)                     # overwrite counts as a use

    def evict_one(self) -> Optional[str]:
        if self._od:
            key, _ = self._od.popitem(last=False)   # O(1) — remove LRU
            return key
        return None

    def delete(self, key: str) -> bool:
        if key in self._od:
            del self._od[key]
            return True
        return False

    def __contains__(self, key): return key in self._od
    def __len__(self):           return len(self._od)
    def items(self):             return list(self._od.items())
    def keys(self):              return list(self._od.keys())


class LFUStore:
    """O(log n) LFU via min-heap + version-based lazy deletion."""
    def __init__(self):
        self._data: Dict[str, CacheEntry] = {}
        self._freq: Dict[str, int] = {}
        self._ver:  Dict[str, int] = {}         # current version per key
        self._heap: List[Tuple] = []            # (freq, ts, key, ver)

    def get(self, key: str) -> Optional[CacheEntry]:
        return self._data.get(key)

    def mark_accessed(self, key: str):
        if key in self._data:
            self._freq[key] = self._freq.get(key, 0) + 1
            ver = self._ver.get(key, 0) + 1
            self._ver[key] = ver
            heapq.heappush(self._heap, (self._freq[key], self._data[key].accessed_at, key, ver))

    def set(self, key: str, entry: CacheEntry):
        self._data[key] = entry
        self._freq[key] = 1
        self._ver[key]  = 1
        heapq.heappush(self._heap, (1, entry.accessed_at, key, 1))

    def on_update(self, key: str):
        self.mark_accessed(key)                 # overwrite keeps (and bumps) the frequency

    def evict_one(self) -> Optional[str]:
        while self._heap:
            freq, ts, key, ver = heapq.heappop(self._heap)
            if key not in self._data:
                continue                         # already deleted
            if self._ver.get(key) != ver:
                continue                         # stale heap entry (freq changed)
            del self._data[key]; del self._freq[key]; del self._ver[key]
            return key
        return None

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]; del self._freq[key]; del self._ver[key]
            return True
        return False

    def __contains__(self, key): return key in self._data
    def __len__(self):           return len(self._data)
    def items(self):             return list(self._data.items())
    def keys(self):              return list(self._data.keys())


class TTLStore:
    """Evicts entry expiring soonest (min-heap on expires_at). O(log n)."""
    def __init__(self):
        self._data: Dict[str, CacheEntry] = {}
        self._heap: List[Tuple[float, str]] = []    # (expires_at, key)

    def get(self, key: str) -> Optional[CacheEntry]:
        return self._data.get(key)

    def mark_accessed(self, key: str):
        pass  # TTL doesn't track access recency

    def set(self, key: str, entry: CacheEntry):
        self._data[key] = entry
        self._push(entry)

    def on_update(self, key: str):
        # The entry's TTL/created_at changed: push its new expiry. The old heap
        # entry no longer matches and is skipped as stale in evict_one.
        if key in self._data:
            self._push(self._data[key])

    def _push(self, entry: CacheEntry):
        expires_at = (entry.created_at + entry.ttl) if entry.ttl else float('inf')
        heapq.heappush(self._heap, (expires_at, entry.key))

    def evict_one(self) -> Optional[str]:
        while self._heap:
            expires_at, key = heapq.heappop(self._heap)
            if key not in self._data:
                continue
            entry = self._data[key]
            expected = (entry.created_at + entry.ttl) if entry.ttl else float('inf')
            if abs(expected - expires_at) > 0.001:
                continue                         # stale heap entry (key was re-set)
            del self._data[key]
            return key
        return None

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def __contains__(self, key): return key in self._data
    def __len__(self):           return len(self._data)
    def items(self):             return list(self._data.items())
    def keys(self):              return list(self._data.keys())


# ─── CacheNode ──────────────────────────────────────────────────────────────────

class CacheNode:
    """
    Thread-safe cache node with pluggable O(1)/O(log n) eviction stores.

    Concurrency model
    -----------------
    asyncio event loop  ──→  handle_client (concurrent I/O, single thread)
                               └─→ protocol.handle_command (sync)
                                     └─→ CacheNode.get/set (RLock → brief critical section)
    Background cleanup  ──→  threading.Thread (parallel OS thread, blocked by same RLock)

    Why RLock not asyncio.Lock?
    The cleanup thread is a plain OS thread, not a coroutine.
    asyncio.Lock is NOT safe to use from threads — only from coroutines.
    RLock bridges both worlds correctly.
    """

    def __init__(self, max_size: int = 1000, eviction_policy: EvictionPolicy = EvictionPolicy.LRU):
        self.max_size       = max_size
        self.eviction_policy = eviction_policy

        if eviction_policy == EvictionPolicy.LRU:
            self._store = LRUStore()
        elif eviction_policy == EvictionPolicy.LFU:
            self._store = LFUStore()
        else:
            self._store = TTLStore()

        self._lock           = threading.RLock()
        self._hits           = 0
        self._misses         = 0
        self._eviction_count = 0
        self._start_time     = time.time()

        self._cleanup_thread = threading.Thread(target=self._background_cleanup, daemon=True)
        self._cleanup_thread.start()
        logger.info(f"CacheNode ready: max_size={max_size} policy={eviction_policy.value}")

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        t0 = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                if _PROM: CACHE_MISSES.inc()
                return None
            if entry.is_expired():
                self._store.delete(key)
                if _PROM: CACHE_SIZE.dec()
                self._misses += 1
                if _PROM: CACHE_MISSES.inc()
                logger.debug(f"Key '{key}' expired")
                return None
            entry.touch()
            self._store.mark_accessed(key)
            self._hits += 1
            if _PROM:
                CACHE_HITS.inc()
                CACHE_GET_LAT.observe(time.monotonic() - t0)
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> bool:
        t0 = time.monotonic()
        with self._lock:
            if _PROM: CACHE_SETS.inc()
            if key in self._store:
                # Overwrite: like Redis SET, the TTL restarts from now. Keeping the old
                # created_at would make e.g. a re-SET with ttl=60 on a 100 s-old key
                # expire immediately.
                now = time.time()
                entry = self._store.get(key)
                entry.value       = value
                entry.created_at  = now
                entry.accessed_at = now
                entry.ttl         = ttl
                self._store.on_update(key)
                if _PROM: CACHE_SET_LAT.observe(time.monotonic() - t0)
                return True
            if len(self._store) >= self.max_size:
                evicted = self._store.evict_one()
                if evicted is None:
                    logger.warning("Cache full — eviction failed")
                    return False
                self._eviction_count += 1
                if _PROM:
                    CACHE_EVICTIONS.labels(policy=self.eviction_policy.value).inc()
                    CACHE_SIZE.dec()
            entry = CacheEntry(
                key=key, value=value,
                created_at=time.time(), accessed_at=time.time(),
                access_count=0, ttl=ttl,
            )
            self._store.set(key, entry)
            if _PROM:
                CACHE_SIZE.inc()
                CACHE_SET_LAT.observe(time.monotonic() - t0)
            logger.debug(f"SET '{key}'")
            return True

    def delete(self, key: str) -> bool:
        with self._lock:
            ok = self._store.delete(key)
            if ok:
                if _PROM: CACHE_SIZE.dec(); CACHE_DELETES.inc()
                logger.debug(f"DEL '{key}'")
            return ok

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total    = len(self._store)
            ops      = self._hits + self._misses
            hit_rate = self._hits / ops if ops > 0 else 0.0
            return {
                "total_entries":       total,
                "max_size":            self.max_size,
                "eviction_policy":     self.eviction_policy.value,
                "hits":                self._hits,
                "misses":              self._misses,
                "hit_rate":            round(hit_rate, 4),
                "evictions":           self._eviction_count,
                "memory_usage_pct":    round(total / self.max_size * 100, 2),
                "uptime_seconds":      round(time.time() - self._start_time, 2),
            }

    def keys(self) -> List[str]:
        with self._lock:
            return [k for k, e in self._store.items() if not e.is_expired()]

    # ── Background cleanup ────────────────────────────────────────────────────

    def _background_cleanup(self):
        """Runs every 30 s in a daemon thread. Removes expired entries proactively."""
        while True:
            try:
                time.sleep(30)
                with self._lock:
                    expired = [k for k, e in self._store.items() if e.is_expired()]
                    for key in expired:
                        self._store.delete(key)
                        if _PROM: CACHE_SIZE.dec()
                    if expired:
                        logger.info(f"Background cleanup removed {len(expired)} expired keys")
            except Exception as e:
                logger.error(f"Background cleanup error: {e}")
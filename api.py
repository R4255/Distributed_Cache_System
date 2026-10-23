"""
api.py — Phase 1: FastAPI HTTP/REST layer for the Distributed Cache System.

This layer sits on top of CacheNode and ConsistentHashRing to expose:
  - Standard REST endpoints (curl/k6/Prometheus compatible)
  - Consistent-hash routing: every key is deterministically routed to a node
  - Admin endpoints to add/remove nodes and inspect the ring at runtime
  - Prometheus /metrics endpoint (text format, auto-scraped by Prometheus)

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1 --reload
    (use --workers 4 in production; metrics state is process-local)
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from cache_node import CacheNode, EvictionPolicy
from consistent_hash import ConsistentHashRing

logger = logging.getLogger(__name__)

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Distributed Cache API",
    description=(
        "High-performance in-memory cache: O(1) LRU, O(log n) LFU, TTL, "
        "consistent hashing, Prometheus metrics."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Cluster bootstrap ────────────────────────────────────────────────────────

_ring  = ConsistentHashRing(vnodes=150)
_nodes: Dict[str, CacheNode] = {}

def _add_node(node_id: str, max_size: int = 10_000,
              policy: EvictionPolicy = EvictionPolicy.LRU) -> None:
    _nodes[node_id] = CacheNode(max_size=max_size, eviction_policy=policy)
    _ring.add_node(node_id)

# Start with a single local node
_add_node("node:0")


def _cache(key: str) -> CacheNode:
    """Route key → CacheNode via consistent hashing."""
    node_id = _ring.get_node(key) or "node:0"
    return _nodes.get(node_id, _nodes["node:0"])


# ─── Pydantic models ──────────────────────────────────────────────────────────

class SetRequest(BaseModel):
    value: str
    ttl:   Optional[float] = None   # seconds until expiry; None = no expiry

class BatchGetRequest(BaseModel):
    keys: List[str]

class BatchSetItem(BaseModel):
    key:   str
    value: str
    ttl:   Optional[float] = None

class BatchSetRequest(BaseModel):
    items: List[BatchSetItem]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["infra"])
def health():
    """Liveness probe. Returns OK + cluster topology."""
    return {
        "status":    "ok",
        "timestamp": time.time(),
        "nodes":     _ring.get_nodes(),
        "node_count": len(_nodes),
    }


# ── Cache CRUD ────────────────────────────────────────────────────────────────

@app.get("/cache/{key}", tags=["cache"])
def get_key(key: str = Path(..., description="Cache key")):
    """
    GET a value by key.
    - 200 → hit
    - 404 → miss / expired
    """
    value = _cache(key).get(key)
    if value is None:
        raise HTTPException(404, detail=f"Key '{key}' not found or expired")
    return {"key": key, "value": value, "node": _ring.get_node(key)}


@app.put("/cache/{key}", tags=["cache"])
def set_key(key: str, req: SetRequest):
    """
    SET key = value with optional TTL (seconds).
    - 200 → stored
    - 507 → cache full and eviction failed
    """
    ok = _cache(key).set(key, req.value, req.ttl)
    if not ok:
        raise HTTPException(507, detail="Cache full — eviction failed")
    return {"key": key, "status": "set", "ttl": req.ttl, "node": _ring.get_node(key)}


@app.delete("/cache/{key}", tags=["cache"])
def delete_key(key: str):
    """DELETE a key. 404 if not found."""
    ok = _cache(key).delete(key)
    if not ok:
        raise HTTPException(404, detail=f"Key '{key}' not found")
    return {"key": key, "status": "deleted"}


@app.get("/cache", tags=["cache"])
def list_keys(limit: int = Query(1000, description="Max keys to return")):
    """List all live (non-expired) keys across all nodes."""
    all_keys: List[str] = []
    for node in _nodes.values():
        all_keys.extend(node.keys())
        if len(all_keys) >= limit:
            break
    return {"keys": all_keys[:limit], "count": len(all_keys[:limit])}


# ── Batch endpoints ────────────────────────────────────────────────────────────

@app.post("/cache/batch/get", tags=["cache"])
def batch_get(req: BatchGetRequest):
    """
    MGET equivalent — fetch multiple keys in one request.
    Missing/expired keys return null.
    """
    results: Dict[str, Any] = {}
    for key in req.keys:
        results[key] = _cache(key).get(key)
    hits   = sum(1 for v in results.values() if v is not None)
    misses = len(results) - hits
    return {"results": results, "hits": hits, "misses": misses,
            "hit_rate": round(hits / len(results), 4) if results else 0}


@app.post("/cache/batch/set", tags=["cache"])
def batch_set(req: BatchSetRequest):
    """MSET equivalent — set multiple keys in one request."""
    ok_count = fail_count = 0
    for item in req.items:
        if _cache(item.key).set(item.key, item.value, item.ttl):
            ok_count += 1
        else:
            fail_count += 1
    return {"set": ok_count, "failed": fail_count}


# ── Observability ─────────────────────────────────────────────────────────────

@app.get("/stats", tags=["observability"])
def stats():
    """Per-node stats: hit rate, evictions, memory %, uptime."""
    cluster_stats = {nid: n.stats() for nid, n in _nodes.items()}
    # Aggregate totals
    agg_hits   = sum(s["hits"]   for s in cluster_stats.values())
    agg_misses = sum(s["misses"] for s in cluster_stats.values())
    total_ops  = agg_hits + agg_misses
    return {
        "nodes":             cluster_stats,
        "ring_distribution": _ring.distribution(),
        "aggregate": {
            "total_nodes":   len(_nodes),
            "total_hits":    agg_hits,
            "total_misses":  agg_misses,
            "overall_hit_rate": round(agg_hits / total_ops, 4) if total_ops else 0,
        },
    }


@app.get("/ring", tags=["observability"])
def ring_info():
    """Inspect the consistent hash ring — distribution, vnodes, node list."""
    return {
        "nodes":        _ring.get_nodes(),
        "distribution": _ring.distribution(),
        "vnodes_per_node": _ring.vnodes,
    }


@app.get("/ring/debug/{key}", tags=["observability"])
def ring_debug(key: str):
    """Show which node owns a key and its ring position."""
    return _ring.key_debug(key)


@app.get("/metrics", response_class=PlainTextResponse, tags=["observability"])
def prometheus_metrics():
    """
    Prometheus text-format metrics endpoint.
    Add to prometheus.yml:
        - targets: ['localhost:8000']
          metrics_path: /metrics
    """
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        return PlainTextResponse("# prometheus_client not installed\n")


# ── Admin / cluster management ────────────────────────────────────────────────

@app.post("/admin/node/{node_id}", tags=["admin"])
def add_node(
    node_id:  str,
    max_size: int            = Query(10_000, description="Max entries for this node"),
    policy:   EvictionPolicy = Query(EvictionPolicy.LRU, description="Eviction policy"),
):
    """
    Add a new in-process cache node to the cluster.
    The ring re-routes ~1/N keys to the new node immediately.
    In a real system this node would be a remote process; here it's in-process
    to demonstrate the consistent hashing mechanics without Docker.
    """
    if node_id in _nodes:
        raise HTTPException(400, detail=f"Node '{node_id}' already exists")
    _add_node(node_id, max_size, policy)
    return {
        "status":       "added",
        "node":         node_id,
        "distribution": _ring.distribution(),
    }


@app.delete("/admin/node/{node_id}", tags=["admin"])
def remove_node(node_id: str):
    """
    Remove a node from the cluster. Its keys route to the next ring node.
    Cannot remove the last node ('node:0').
    """
    if node_id == "node:0":
        raise HTTPException(400, detail="Cannot remove the primary node 'node:0'")
    if node_id not in _nodes:
        raise HTTPException(404, detail=f"Node '{node_id}' not found")
    _ring.remove_node(node_id)
    del _nodes[node_id]
    return {
        "status":       "removed",
        "node":         node_id,
        "remaining":    _ring.get_nodes(),
        "distribution": _ring.distribution(),
    }


@app.post("/admin/flush", tags=["admin"])
def flush_all():
    """⚠️  Danger: wipe all cache nodes. Useful for testing."""
    for nid in list(_nodes):
        _nodes[nid] = CacheNode(
            max_size=_nodes[nid].max_size,
            eviction_policy=_nodes[nid].eviction_policy,
        )
    return {"status": "flushed", "nodes": list(_nodes.keys())}

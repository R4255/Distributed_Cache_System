"""
consistent_hash.py — Phase 3: Consistent hashing for distributed cache routing.

Why consistent hashing?
  - A plain modulo hash (key % N) remaps ALL keys when N changes.
  - A consistent hash ring only remaps ~1/N keys when a node is added/removed.
  - Virtual nodes (vnodes) ensure even key distribution across physical nodes.

Ring mechanics
--------------
  1. Hash each vnode label → int position in [0, 2^128)
  2. Positions are kept in a sorted list (self._sorted_keys)
  3. For a key: hash(key) → position, binary-search for the next clockwise vnode
  4. That vnode's physical node is the key's owner

                  0
             ┌────┴────┐
        330° │         │ 30°
             │  Ring   │
        270° │         │ 90°
             └────┬────┘
                 180°
  Node A owns arc [0°–120°], Node B owns [120°–240°], Node C owns [240°–360°]
  Adding Node D only remaps keys near D's insertion point on the ring.
"""
import bisect
import hashlib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConsistentHashRing:
    """
    Consistent hash ring with virtual nodes.

    Parameters
    ----------
    vnodes : int
        Number of virtual nodes per physical node. Higher values → more even
        distribution but more memory. 150 is a good default (Redis Cluster uses
        16384 hash slots for similar effect).
    """

    def __init__(self, vnodes: int = 150):
        self.vnodes        = vnodes
        self._ring: Dict[int, str] = {}         # hash_pos → node_id
        self._sorted_keys: List[int] = []       # sorted ring positions
        self._nodes: set = set()                # physical node IDs

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _hash(key: str) -> int:
        """MD5 → integer ring position. Deterministic & fast."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    # ── Node management ───────────────────────────────────────────────────────

    def add_node(self, node_id: str) -> None:
        """
        Add a physical node. Creates `vnodes` virtual positions on the ring.
        Only ~(vnodes / total_ring_positions) fraction of keys will remap.
        """
        if node_id in self._nodes:
            return
        self._nodes.add(node_id)
        for i in range(self.vnodes):
            pos = self._hash(f"{node_id}#vn:{i}")
            self._ring[pos] = node_id
            bisect.insort(self._sorted_keys, pos)
        logger.info(f"Ring: added '{node_id}' ({self.vnodes} vnodes, {len(self._nodes)} total nodes)")

    def remove_node(self, node_id: str) -> None:
        """
        Remove a physical node. Its keys will route to the next clockwise node.
        """
        if node_id not in self._nodes:
            return
        self._nodes.discard(node_id)
        for i in range(self.vnodes):
            pos = self._hash(f"{node_id}#vn:{i}")
            self._ring.pop(pos, None)
            idx = bisect.bisect_left(self._sorted_keys, pos)
            if idx < len(self._sorted_keys) and self._sorted_keys[idx] == pos:
                self._sorted_keys.pop(idx)
        logger.info(f"Ring: removed '{node_id}' ({len(self._nodes)} nodes remain)")

    # ── Key routing ───────────────────────────────────────────────────────────

    def get_node(self, key: str) -> Optional[str]:
        """
        Return the node responsible for `key`.  O(log N) binary search.
        Returns None if the ring is empty.
        """
        if not self._sorted_keys:
            return None
        pos = self._hash(key)
        # Binary search: first vnode position >= pos (wrap around to 0)
        idx = bisect.bisect_right(self._sorted_keys, pos) % len(self._sorted_keys)
        return self._ring[self._sorted_keys[idx]]

    def get_replica_nodes(self, key: str, replicas: int = 2) -> List[str]:
        """
        Return up to `replicas` distinct physical nodes for a key (for replication).
        """
        if not self._sorted_keys:
            return []
        pos   = self._hash(key)
        start = bisect.bisect_right(self._sorted_keys, pos)
        seen: List[str]  = []
        n = len(self._sorted_keys)
        for i in range(n):
            node = self._ring[self._sorted_keys[(start + i) % n]]
            if node not in seen:
                seen.append(node)
            if len(seen) == replicas:
                break
        return seen

    # ── Introspection ─────────────────────────────────────────────────────────

    def get_nodes(self) -> List[str]:
        return sorted(self._nodes)

    def distribution(self) -> Dict[str, float]:
        """Percentage of ring arcs owned by each node — useful for Grafana."""
        if not self._sorted_keys:
            return {}
        counts: Dict[str, int] = {n: 0 for n in self._nodes}
        for pos in self._sorted_keys:
            counts[self._ring[pos]] += 1
        total = len(self._sorted_keys)
        return {n: round(c / total * 100, 2) for n, c in counts.items()}

    def key_debug(self, key: str) -> Dict:
        """Debug: show which node owns this key and its ring position."""
        pos  = self._hash(key)
        node = self.get_node(key)
        return {"key": key, "ring_position": pos, "owner_node": node,
                "replicas": self.get_replica_nodes(key)}

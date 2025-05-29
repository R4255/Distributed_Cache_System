#It Contains all the Core Cache Logic
import time
import threading
import logging
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

class EvictionPolicy(Enum):
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    
'''
data class auto generates boilerplate code 
__init__(): Constructor for initializing class attributes
__repr__(): String representation of the object
__eq__(): Equality comparison between instances
'''    
@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float
    accessed_at: float
    access_count: int = 0
    ttl: Optional[float] = None
    
    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() > self.created_at + self.ttl
    
    def touch(self):
        self.accessed_at = time.time()
        self.access_count += 1
    
    
class CacheNode:
    '''The Core Cache Node Class that holds the storage, Eviction and Basic Operations'''
    def __init__(self,max_size: int = 1000, eviction_policy: EvictionPolicy = EvictionPolicy.LRU):
        self.max_size = max_size
        self.eviction_policy = eviction_policy
        self.data: Dict[str, CacheEntry] = {}
        self.lock = threading.RLock()
        
        '''Starting the Background Cleanup task'''
        self._cleanup_task = threading.Thread(target=self._background_cleanup, daemon = True)
        self._cleanup_task.start()
        
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return None
            
            if entry.is_expired():
                del self.data[key]
                logger.info(f"Key {key} Expired and Removed")
                return None
            
            entry.touch()
            return entry.value
    
    def set(self, key: str, value: Any, ttl : Optional[float] = None) -> bool:
        with self.lock:
            if key in self.data:
                entry = self.data[key]
                entry.value = value
                entry.accessed_at = time.time()
                entry.ttl = ttl
                return True

            if len(self.data) >= self.max_size:
                evicted = self._evict_one()
                if not evicted:
                    logger.warning('Failed to Evict an Entry, Cache is Full')
                    return False
            
            entry = CacheEntry(
                key = key,
                value = value,
                created_at = time.time(),
                accessed_at = time.time(),
                ttl = ttl
            )
            
            self.data[key] = entry
            logger.info(f"Set Key: {key}")
            return True
    
    def delete(self, key: str) -> bool:
        with self.lock:
            if key in self.data:
                del self.data[key]
                logger.info(f"Deleted Key: {key}")
                return True
            return False
        
    def _evict_one(self) -> bool:
        '''Here we will Evict One Entry based on the Eviction Policy'''
        if not self.data:
            return False
        
        if self.eviction_policy == EvictionPolicy.LRU:
            oldest_key = min(self.data.keys(),
                             key = lambda x: self.data[x].accessed_at
                             )
            del self.data[oldest_key]
            logger.info(f"Evicted {oldest_key} LRU")
        
        elif self.eviction_policy == EvictionPolicy.LFU:
            least_used_key = min(self.data.keys(),
                                 key = lambda x: self.data[x].access_count)
            del self.data[least_used_key]
            logger.info(f"Evicted {least_used_key} LFU")
            
        elif self.eviction_policy == EvictionPolicy.TTL:
            oldest_key = min(self.data.keys(),
                             key = lambda x: self.data[x].created_at
                             )
            del self.data[oldest_key]
            logger.info(f"Evicted {oldest_key} TTL")
            
        return True
    
    def _background_cleanup(self): 
        '''This will cleanup the expired entries'''
        while True:
            try:      
                time.sleep(60) # Runs every 60 seconds
                with self.lock:
                    expired_keys = [
                        key for key, entry in self.data.items()
                        if entry.is_expired()
                    ]
                    for key in expired_keys:
                        del self.data[key]
                        logger.info(f"Background Cleanup: Removed Expired Key {key}")
            except Exception as e:
                logger.error(f"Error in Background Cleanup: {e}")    
            
    def stats(self) -> Dict[str, Any]:
        '''Get Cache Stats'''
        with self.lock:
            total_entries = len(self.data)
            expired_count = sum(1 for entry in self.data.values() if entry.is_expired())
            
            return {
                "total_entries:" : total_entries,
                "max_size:" : self.max_size,
                "expired_count:" : expired_count,
                "eviction_policy:" : self.eviction_policy.value,
                "memory_usage_percentage:" : (total_entries / self.max_size) * 100 
            }
        
    def keys(self) -> List[str]:
        '''Get All Non Expired Keys'''
        with self.lock:
            return [key for key, entry in self.data.items() if not entry.is_expired()]
        
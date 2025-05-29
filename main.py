import asyncio
import argparse
import logging
import signal
from server import CacheServer
from cache_node import CacheNode, EvictionPolicy

logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    parser = argparse.ArgumentParser(description="Distributed Cache Server")
    parser.add_argument('--port', type=int, default=6379, help='Port to run the cache server on')
    parser.add_argument('--host', type=str, default='localhost', help='Host address for the cache server')
    parser.add_argument('--max-size', type=int, default=1000, help='Maximum size of the cache')
    parser.add_argument('--eviction', choices=['lru', 'lfu', 'ttl'], 
                       default='lru', help='Eviction policy')
    
    args = parser.parse_args()
    
    # Create cache node
    eviction_policy = EvictionPolicy(args.eviction)
    cache_node = CacheNode(max_size=args.max_size, eviction_policy=eviction_policy)
    
    # Create and start server
    server = CacheServer(host=args.host, port=args.port, cache_node=cache_node)
    
    try:
        print(f"Starting cache server on {args.host}:{args.port}")
        print(f"Configuration: max_size={args.max_size}, eviction={args.eviction}")
        print("Press Ctrl+C to stop")
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nShutting down...")
        
if __name__ == "__main__":
    main()
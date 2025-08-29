#!/usr/bin/env python3
"""
Example script demonstrating programmatic usage of the Distributed Cache System.

This script shows how to:
1. Connect to the cache server
2. Perform basic operations (SET, GET, DEL)
3. Work with TTL
4. Handle errors
5. Get statistics

Run this after starting the cache server:
python main.py --port 6379
"""

import asyncio
import json
from client import CacheClient

async def demonstrate_cache_operations():
    """Demonstrate various cache operations."""
    print("🚀 Distributed Cache System - Programmatic Example")
    print("=" * 50)
    
    # Create client and connect
    client = CacheClient(host='localhost', port=6379)
    
    try:
        print("📡 Connecting to cache server...")
        await client.connect()
        print("✅ Connected successfully!\n")
        
        # 1. Basic SET/GET operations
        print("1️⃣ Basic Operations:")
        print("-" * 20)
        
        await client.send_command("SET user:1001 Alice")
        print("SET user:1001 Alice -> Stored user data")
        
        response = await client.send_command("GET user:1001")
        print(f"GET user:1001 -> {response}")
        
        await client.send_command("SET product:abc123 'Gaming Laptop'")
        print("SET product:abc123 'Gaming Laptop' -> Stored product")
        
        # 2. TTL operations
        print("\n2️⃣ TTL (Time To Live) Operations:")
        print("-" * 35)
        
        await client.send_command("SET session:temp 'temporary_session_data' 5")
        print("SET session:temp 'temporary_session_data' 5 -> Set with 5 second TTL")
        
        response = await client.send_command("GET session:temp")
        print(f"GET session:temp (immediately) -> {response}")
        
        print("⏰ Waiting 6 seconds for TTL expiration...")
        await asyncio.sleep(6)
        
        response = await client.send_command("GET session:temp")
        print(f"GET session:temp (after TTL) -> {response}")
        
        # 3. List all keys
        print("\n3️⃣ Key Management:")
        print("-" * 18)
        
        response = await client.send_command("KEYS")
        keys = json.loads(response.split(' ', 1)[1])  # Parse JSON from "OK [...]"
        print(f"Current keys: {keys}")
        
        # 4. Cache statistics
        print("\n4️⃣ Cache Statistics:")
        print("-" * 20)
        
        response = await client.send_command("STATS")
        stats = json.loads(response.split(' ', 1)[1])  # Parse JSON from "OK {...}"
        
        print("Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # 5. Delete operations
        print("\n5️⃣ Delete Operations:")
        print("-" * 20)
        
        response = await client.send_command("DEL user:1001")
        print(f"DEL user:1001 -> {response}")
        
        response = await client.send_command("GET user:1001")
        print(f"GET user:1001 (after deletion) -> {response}")
        
        # 6. Error handling
        print("\n6️⃣ Error Handling:")
        print("-" * 18)
        
        response = await client.send_command("INVALID_COMMAND")
        print(f"INVALID_COMMAND -> {response}")
        
        response = await client.send_command("GET")  # Missing key
        print(f"GET (missing key) -> {response}")
        
        # Final key count
        response = await client.send_command("KEYS")
        keys = json.loads(response.split(' ', 1)[1])
        print(f"\nFinal keys remaining: {keys}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        print("\n🔌 Closing connection...")
        await client.close()
        print("✅ Example completed!")

async def benchmark_operations():
    """Simple benchmark of cache operations."""
    print("\n📊 Quick Performance Benchmark")
    print("=" * 35)
    
    client = CacheClient()
    await client.connect()
    
    try:
        import time
        
        # Benchmark SET operations
        start_time = time.time()
        num_operations = 100
        
        print(f"⚡ Performing {num_operations} SET operations...")
        for i in range(num_operations):
            await client.send_command(f"SET benchmark:key:{i} value_{i}")
        
        set_time = time.time() - start_time
        print(f"✅ {num_operations} SETs completed in {set_time:.3f} seconds")
        print(f"📈 Rate: {num_operations/set_time:.1f} operations/second")
        
        # Benchmark GET operations
        start_time = time.time()
        
        print(f"⚡ Performing {num_operations} GET operations...")
        for i in range(num_operations):
            await client.send_command(f"GET benchmark:key:{i}")
        
        get_time = time.time() - start_time
        print(f"✅ {num_operations} GETs completed in {get_time:.3f} seconds")
        print(f"📈 Rate: {num_operations/get_time:.1f} operations/second")
        
        # Clean up benchmark data
        print(f"🧹 Cleaning up benchmark data...")
        for i in range(num_operations):
            await client.send_command(f"DEL benchmark:key:{i}")
            
    except Exception as e:
        print(f"❌ Benchmark error: {e}")
    
    finally:
        await client.close()

async def main():
    """Run the complete example."""
    await demonstrate_cache_operations()
    
    # Uncomment to run benchmark
    # await benchmark_operations()

if __name__ == "__main__":
    print("Make sure the cache server is running:")
    print("python main.py --port 6379\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Example interrupted by user")
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        print("Make sure the cache server is running on localhost:6379")
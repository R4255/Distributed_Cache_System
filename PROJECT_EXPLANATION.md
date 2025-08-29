# Distributed Cache System - Project Explanation

## 🎯 Project Overview

This is a **high-performance, thread-safe distributed cache implementation** written in Python. It's designed to be a learning project that demonstrates modern Python programming concepts including:

- **Asynchronous I/O** with `asyncio`
- **Multi-threading** with proper synchronization
- **Network programming** with TCP sockets
- **Design patterns** and clean architecture
- **Protocol design** similar to Redis

## 🏗️ Architecture Overview

The system follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐
│     Client      │◄──►│     Server      │
│   (client.py)   │    │   (server.py)   │
└─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │    Protocol     │
                       │  (protocol.py)  │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Cache Node    │
                       │ (cache_node.py) │
                       └─────────────────┘
```

## 📁 Core Components

### 1. **Cache Node (`cache_node.py`)**
The heart of the system containing:

#### Data Structures:
- **`EvictionPolicy`**: Enum defining LRU, LFU, TTL policies
- **`CacheEntry`**: Dataclass storing key-value pairs with metadata
- **`CacheNode`**: Main cache implementation

#### Key Features:
- **Thread-safe operations** using `threading.RLock()`
- **Multiple eviction policies**: LRU, LFU, TTL
- **TTL support** with automatic expiration
- **Background cleanup** thread running every 60 seconds
- **Statistics** and key listing capabilities

#### Core Methods:
```python
def get(key: str) -> Optional[Any]     # Retrieve value
def set(key: str, value: Any, ttl: Optional[float] = None) -> bool  # Store value
def delete(key: str) -> bool           # Remove key
def stats() -> Dict[str, Any]          # Get cache statistics
def keys() -> List[str]                # List all non-expired keys
```

### 2. **Protocol Handler (`protocol.py`)**
Implements a **Redis-like text protocol**:

#### Supported Commands:
- `GET key` - Retrieve a value
- `SET key value [ttl]` - Store a value with optional TTL
- `DEL key` - Delete a key
- `STATS` - Get cache statistics
- `KEYS` - List all keys

#### Response Format:
- **Success**: `OK <json_data>` or `OK`
- **Not found**: `NULL`
- **Error**: `ERROR: <message>`

### 3. **TCP Server (`server.py`)**
**Asynchronous TCP server** using `asyncio`:

#### Features:
- **Concurrent client handling** - each client in separate coroutine
- **Clean connection management** with proper cleanup
- **Logging** of all client interactions
- **Graceful shutdown** support

#### Key Methods:
```python
async def handle_client(reader, writer)  # Handle individual client
async def start()                        # Start the server
async def stop()                         # Stop the server
```

### 4. **Client (`client.py`)**
Provides both **interactive** and **programmatic** interfaces:

#### Features:
- **Interactive mode**: Command-line interface
- **Demo mode**: Automated demonstration
- **Async client library**: For programmatic use

### 5. **Main Entry Point (`main.py`)**
Server launcher with **command-line arguments**:

```bash
python main.py --port 6379 --host localhost --max-size 1000 --eviction lru
```

## ✨ Key Features Explained

### 1. **Eviction Policies**

#### LRU (Least Recently Used)
- Evicts the **oldest accessed** item
- Updates access time on every `get()` operation
- Best for **temporal locality** patterns

#### LFU (Least Frequently Used)  
- Evicts the **least accessed** item
- Tracks access count for each entry
- Best for **frequency-based** access patterns

#### TTL (Time To Live)
- Evicts the **oldest created** item
- Independent of access patterns
- Best for **time-based** expiration

### 2. **TTL Support**
- **Per-key TTL**: Each key can have its own expiration time
- **Automatic cleanup**: Background thread removes expired keys
- **Lazy expiration**: Keys are also checked during access

### 3. **Thread Safety**
- **RLock**: Reentrant lock allows same thread multiple acquisitions
- **Atomic operations**: All cache operations are thread-safe
- **Background cleanup**: Safely runs concurrently with main operations

### 4. **Asynchronous I/O**
- **Non-blocking**: Server can handle multiple clients simultaneously
- **Backpressure handling**: Proper flow control with `await writer.drain()`
- **Clean shutdown**: Graceful connection termination

## 🚀 Usage Examples

### Starting the Server
```bash
# Basic usage
python main.py

# Custom configuration
python main.py --port 8080 --max-size 500 --eviction lfu
```

### Using the Client

#### Interactive Mode:
```bash
python client.py
> SET user:123 "John Doe"
OK
> GET user:123
OK "John Doe"
> SET temp:data "expires soon" 30
OK
> STATS
OK {"total_entries:": 2, "max_size:": 1000, "expired_count:": 0, "eviction_policy:": "lru", "memory_usage_percentage:": 0.2}
```

#### Demo Mode:
```bash
python client.py demo
```

### Programmatic Usage:
```python
import asyncio
from client import CacheClient

async def example():
    client = CacheClient()
    await client.connect()
    
    # Store data
    await client.send_command("SET user:1 Alice")
    
    # Retrieve data
    response = await client.send_command("GET user:1")
    print(response)  # OK "Alice"
    
    await client.close()

asyncio.run(example())
```

## 🔧 Design Patterns Used

### 1. **Strategy Pattern**
- Different eviction policies implemented as strategies
- Easy to add new eviction algorithms

### 2. **Command Pattern**
- Protocol commands encapsulated as discrete operations
- Easy to add new commands

### 3. **Observer Pattern**
- Background cleanup observes TTL expiration
- Automatic cleanup without explicit calls

### 4. **Factory Pattern**
- Server creates protocol handlers for each client
- Separation of connection and protocol logic

## 📊 Performance Considerations

### Strengths:
- **Asynchronous I/O**: High concurrency with low resource usage
- **Thread-safe**: Safe for multi-threaded environments
- **Memory efficient**: Only stores essential metadata
- **Fast lookups**: O(1) hash table operations

### Limitations:
- **Single-node**: Not distributed across multiple machines
- **Memory-only**: No persistence to disk
- **Simple protocol**: Not as feature-rich as Redis
- **No clustering**: No replication or sharding

## 🔒 Security Considerations

### Current State:
- **No authentication**: Anyone can connect
- **No authorization**: All clients have full access
- **No encryption**: Data transmitted in plain text
- **Local binding**: Default binding to localhost

### Production Recommendations:
- Add authentication mechanisms
- Implement SSL/TLS encryption
- Add rate limiting
- Use firewall rules for access control

## 🎓 Learning Outcomes

This project demonstrates:

1. **Modern Python**: Type hints, dataclasses, async/await
2. **Concurrency**: Threading vs. async programming
3. **Network programming**: TCP sockets and protocols
4. **System design**: Caching strategies and trade-offs
5. **Testing**: Client/server interaction patterns

## 🚀 Extension Ideas

1. **Persistence**: Add disk storage with write-ahead logging
2. **Clustering**: Implement consistent hashing for distribution
3. **Monitoring**: Add metrics and health endpoints  
4. **Security**: Add authentication and encryption
5. **Advanced features**: Pub/sub, transactions, Lua scripting
6. **Performance**: Connection pooling, compression
7. **Data types**: Lists, sets, sorted sets like Redis

## 💡 Conclusion

This Distributed Cache System is an excellent educational project that showcases modern Python development practices. It provides a solid foundation for understanding caching systems, network programming, and concurrent system design. The clean architecture makes it easy to understand, modify, and extend.

The project successfully balances **simplicity** with **functionality**, making it perfect for learning distributed systems concepts while providing a working cache implementation that could be adapted for real-world use cases.
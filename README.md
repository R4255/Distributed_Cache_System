# Distributed_Cache_System

A high-performance, thread-safe distributed cache implementation in Python with support for multiple eviction policies, TTL-based expiration, and asynchronous I/O operations.

## 🚀 Features

- **Multiple Eviction Policies**: LRU (Least Recently Used), LFU (Least Frequently Used), TTL (Time To Live)
- **Thread-Safe Operations**: Uses `threading.RLock()` for concurrent access
- **Asynchronous I/O**: Built with `asyncio` for high-concurrency client handling
- **TTL Support**: Automatic expiration of cache entries
- **Background Cleanup**: Automatic removal of expired entries
- **Redis-like Protocol**: Simple text-based communication protocol
- **Interactive Client**: Built-in client for testing and interaction
- **Comprehensive Logging**: Detailed operation logging for monitoring

## 📋 Requirements

- Python 3.7+ (uses `dataclasses` and modern `asyncio`)
- No external dependencies - uses only Python standard library

## 🚀 Quick Start

### 1. Start the Cache Server
```bash
# Basic usage (default: localhost:6379, max_size=1000, eviction=lru)
python main.py

# Custom configuration
python main.py --port 8080 --host 0.0.0.0 --max-size 500 --eviction lfu
```

### 2. Test with the Built-in Client

#### Interactive Mode:
```bash
python client.py
> SET user:123 "John Doe"
OK
> GET user:123
OK "John Doe"
> SET temp "expires in 30 seconds" 30
OK
> STATS
OK {"total_entries:": 2, "max_size:": 1000, ...}
> quit
```

#### Demo Mode:
```bash
python client.py demo
```

### 3. Test with Any TCP Client (telnet, netcat, etc.)
```bash
# Using netcat
echo "GET user:123" | nc localhost 6379

# Using telnet
telnet localhost 6379
SET hello world
GET hello
KEYS
quit
```

## 📖 Protocol Commands

| Command | Syntax | Description | Example |
|---------|--------|-------------|---------|
| `GET` | `GET key` | Retrieve value for key | `GET user:1` |
| `SET` | `SET key value [ttl]` | Store key-value with optional TTL | `SET user:1 "Alice" 300` |
| `DEL` | `DEL key` | Delete a key | `DEL user:1` |
| `KEYS` | `KEYS` | List all non-expired keys | `KEYS` |
| `STATS` | `STATS` | Get cache statistics | `STATS` |

## 🏗️ Architecture

For a detailed explanation of the system architecture, design patterns, and implementation details, see [PROJECT_EXPLANATION.md](PROJECT_EXPLANATION.md).

## 🔧 Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `localhost` | Server bind address |
| `--port` | `6379` | Server port (Redis default) |
| `--max-size` | `1000` | Maximum cache entries |
| `--eviction` | `lru` | Eviction policy: `lru`, `lfu`, or `ttl` |

## 📊 Features Demonstration

### TTL (Time To Live) Example:
```bash
> SET session:abc123 "user_data" 60    # Expires in 60 seconds
OK
> GET session:abc123
OK "user_data"
# Wait 60+ seconds...
> GET session:abc123
NULL
```

### Eviction Policy Example:
```bash
# Start server with LFU eviction and size limit of 2
python main.py --eviction lfu --max-size 2

> SET key1 "value1"
OK
> SET key2 "value2"  
OK
> GET key1          # Increases access count for key1
OK "value1"
> SET key3 "value3" # Triggers eviction of key2 (least frequently used)
OK
> KEYS
OK ["key1", "key3"]
```

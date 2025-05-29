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

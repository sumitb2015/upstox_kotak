import os
import json
import redis
from typing import Any, Optional

class RedisManager:
    """
    Centralized Redis Client Manager for the Upstox Algorithmic Trading System.
    Provides safe JSON serialization/deserialization and centralized connection configuration.
    
    Security Note: Bound to 127.0.0.1 by default. In production, ensure REDIS_PASSWORD 
    is set in the environment variables and redis.conf has `requirepass`.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        host = os.getenv("REDIS_HOST", "127.0.0.1")
        port = int(os.getenv("REDIS_PORT", 6379))
        password = os.getenv("REDIS_PASSWORD", None)
        
        # Use decode_responses=True so strings are returned instead of bytes
        pool = redis.ConnectionPool(
            host=host, 
            port=port, 
            password=password, 
            decode_responses=True
        )
        self.client = redis.Redis(connection_pool=pool)

    def ping(self) -> bool:
        """Check if Redis is alive."""
        try:
            return self.client.ping()
        except redis.ConnectionError:
            return False

    def set_json(self, key: str, value: Any, ex: Optional[int] = None):
        """Set a value as a JSON string with optional expiration in seconds."""
        try:
            val_str = json.dumps(value, default=str)
            self.client.set(key, val_str, ex=ex)
        except Exception as e:
            print(f"Redis set_json error for {key}: {e}")

    def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize a JSON string from Redis."""
        try:
            val_str = self.client.get(key)
            if val_str:
                return json.loads(val_str)
            return None
        except Exception as e:
            print(f"Redis get_json error for {key}: {e}")
            return None

    def get_raw(self, key: str) -> Optional[str]:
        """Get raw string from Redis without JSON deserialization."""
        try:
            return self.client.get(key)
        except Exception as e:
            print(f"Redis get_raw error for {key}: {e}")
            return None
            
    def set_raw(self, key: str, value: str, ex: Optional[int] = None):
        """Set raw string to Redis without JSON serialization."""
        try:
            self.client.set(key, value, ex=ex)
        except Exception as e:
            print(f"Redis set_raw error for {key}: {e}")

    def push_json_list(self, key: str, value: Any, max_len: Optional[int] = None):
        """Push a JSON object to a Redis list (RPUSH). Keeps list trimmed to max_len if specified."""
        try:
            val_str = json.dumps(value, default=str)
            self.client.rpush(key, val_str)
            if max_len:
                # Keep only the latest `max_len` elements
                self.client.ltrim(key, -max_len, -1)
        except Exception as e:
            print(f"Redis push_json_list error for {key}: {e}")

    def get_json_list(self, key: str, start: int = 0, end: int = -1) -> list:
        """Fetch elements from a list and deserialize from JSON."""
        try:
            items = self.client.lrange(key, start, end)
            return [json.loads(i) for i in items]
        except Exception as e:
            print(f"Redis get_json_list error for {key}: {e}")
            return []

    def keys(self, pattern: str) -> list:
        """Return all keys matching the regex pattern."""
        try:
            return self.client.keys(pattern)
        except Exception as e:
            print(f"Redis keys error for {pattern}: {e}")
            return []

    def hset_json(self, name: str, key: str, value: Any):
        """Set a value in a Hash map as a JSON string."""
        try:
            val_str = json.dumps(value, default=str)
            self.client.hset(name, key, val_str)
        except Exception as e:
            print(f"Redis hset_json error for {key}: {e}")

    def hget_json(self, name: str, key: str) -> Optional[Any]:
        """Get a value from a Hash map and deserialize from JSON."""
        try:
            val_str = self.client.hget(name, key)
            if val_str:
                return json.loads(val_str)
            return None
        except Exception as e:
            print(f"Redis hget_json error for {key}: {e}")
            return None
            
    def hgetall_json(self, name: str) -> dict:
        """Get all values from a Hash map and deserialize from JSON."""
        try:
            items = self.client.hgetall(name)
            return {k: json.loads(v) for k, v in items.items()}
        except Exception as e:
            print(f"Redis hgetall_json error for {name}: {e}")
            return {}

# Global instance
redis_wrapper = RedisManager()

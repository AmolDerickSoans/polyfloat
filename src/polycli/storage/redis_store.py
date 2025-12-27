import json
from typing import Optional, Any, Dict, List, Union
import structlog
from .base_store import BaseStorage

logger = structlog.get_logger()


class RedisStore(BaseStorage):
    """Redis-based hot storage for real-time data and caching"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0", prefix: str = "polycli:"):
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self.prefix = prefix
        except ImportError:
            logger.warning(
                "Redis package not installed. Install with: pip install redis",
                hint="Use 'pip install redis' to enable Redis storage"
            )
            self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        if not self._redis:
            return None
        
        try:
            value = await self._redis.get(f"{self.prefix}{key}")
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("Redis get error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL in seconds"""
        if not self._redis:
            return False
        
        try:
            json_value = json.dumps(value, default=str)
            if ttl:
                await self._redis.setex(f"{self.prefix}{key}", ttl, json_value)
            else:
                await self._redis.set(f"{self.prefix}{key}", json_value)
            return True
        except Exception as e:
            logger.error("Redis set error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key"""
        if not self._redis:
            return False
        
        try:
            await self._redis.delete(f"{self.prefix}{key}")
            return True
        except Exception as e:
            logger.error("Redis delete error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self._redis:
            return False
        
        try:
            result = await self._redis.exists(f"{self.prefix}{key}")
            return bool(result)
        except Exception as e:
            logger.error("Redis exists error", key=key, error=str(e))
            return False

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """Get hash field"""
        if not self._redis:
            return None
        
        try:
            value = await self._redis.hget(f"{self.prefix}{key}", field)  # type: ignore
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("Redis hget error", key=key, field=field, error=str(e))
            return None

    async def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field"""
        if not self._redis:
            return False
        
        try:
            json_value = json.dumps(value, default=str)
            await self._redis.hset(f"{self.prefix}{key}", field, json_value)  # type: ignore
            return True
        except Exception as e:
            logger.error("Redis hset error", key=key, field=field, error=str(e))
            return False

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        if not self._redis:
            return {}
        
        try:
            data = await self._redis.hgetall(f"{self.prefix}{key}")  # type: ignore
            if not data:
                return {}
            return {k: json.loads(v) for k, v in data.items()}
        except Exception as e:
            logger.error("Redis hgetall error", key=key, error=str(e))
            return {}

    async def hdelete(self, key: str, field: str) -> bool:
        """Delete hash field"""
        if not self._redis:
            return False
        
        try:
            await self._redis.hdel(f"{self.prefix}{key}", field)  # type: ignore
            return True
        except Exception as e:
            logger.error("Redis hdelete error", key=key, field=field, error=str(e))
            return False

    async def lpush(self, key: str, value: Any) -> int:
        """Push to list (left)"""
        if not self._redis:
            return 0
        
        try:
            json_value = json.dumps(value, default=str)
            result = await self._redis.lpush(f"{self.prefix}{key}", json_value)  # type: ignore
            return result if result is not None else 0
        except Exception as e:
            logger.error("Redis lpush error", key=key, error=str(e))
            return 0

    async def rpush(self, key: str, value: Any) -> int:
        """Push to list (right)"""
        if not self._redis:
            return 0
        
        try:
            json_value = json.dumps(value, default=str)
            result = await self._redis.rpush(f"{self.prefix}{key}", json_value)  # type: ignore
            return result if result is not None else 0
        except Exception as e:
            logger.error("Redis rpush error", key=key, error=str(e))
            return 0

    async def lpop(self, key: str) -> Optional[Any]:
        """Pop from list (left)"""
        if not self._redis:
            return None
        
        try:
            value = await self._redis.lpop(f"{self.prefix}{key}")  # type: ignore
            if value and isinstance(value, str):
                return json.loads(value)
            return value
        except Exception as e:
            logger.error("Redis lpop error", key=key, error=str(e))
            return None

    async def rpop(self, key: str) -> Optional[Any]:
        """Pop from list (right)"""
        if not self._redis:
            return None
        
        try:
            value = await self._redis.rpop(f"{self.prefix}{key}")  # type: ignore
            if value and isinstance(value, str):
                return json.loads(value)
            return value
        except Exception as e:
            logger.error("Redis rpop error", key=key, error=str(e))
            return None

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get list range"""
        if not self._redis:
            return []
        
        try:
            values = await self._redis.lrange(f"{self.prefix}{key}", start, end)  # type: ignore
            if not values:
                return []
            return [json.loads(v) for v in values]
        except Exception as e:
            logger.error("Redis lrange error", key=key, error=str(e))
            return []

    async def llen(self, key: str) -> int:
        """Get list length"""
        if not self._redis:
            return 0
        
        try:
            result = await self._redis.llen(f"{self.prefix}{key}")  # type: ignore
            return result if result is not None else 0
        except Exception as e:
            logger.error("Redis llen error", key=key, error=str(e))
            return 0

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()

    async def publish(self, channel: str, message: Any):
        """Publish message to channel"""
        if not self._redis:
            return
        
        try:
            json_message = json.dumps(message, default=str)
            await self._redis.publish(f"{self.prefix}{channel}", json_message)
        except Exception as e:
            logger.error("Redis publish error", channel=channel, error=str(e))

    async def subscribe(self, channel: str):
        """Subscribe to channel and return pubsub"""
        if not self._redis:
            return None
        
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(f"{self.prefix}{channel}")
            return pubsub
        except Exception as e:
            logger.error("Redis subscribe error", channel=channel, error=str(e))
            return None

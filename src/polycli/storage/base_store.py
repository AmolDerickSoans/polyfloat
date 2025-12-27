from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List
from datetime import datetime


class BaseStorage(ABC):
    """Base storage interface for all storage backends"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL in seconds"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        pass

    @abstractmethod
    async def hget(self, key: str, field: str) -> Optional[Any]:
        """Get hash field"""
        pass

    @abstractmethod
    async def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field"""
        pass

    @abstractmethod
    async def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        pass

    @abstractmethod
    async def hdelete(self, key: str, field: str) -> bool:
        """Delete hash field"""
        pass

    @abstractmethod
    async def lpush(self, key: str, value: Any) -> int:
        """Push to list (left)"""
        pass

    @abstractmethod
    async def rpush(self, key: str, value: Any) -> int:
        """Push to list (right)"""
        pass

    @abstractmethod
    async def lpop(self, key: str) -> Optional[Any]:
        """Pop from list (left)"""
        pass

    @abstractmethod
    async def rpop(self, key: str) -> Optional[Any]:
        """Pop from list (right)"""
        pass

    @abstractmethod
    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get list range"""
        pass

    @abstractmethod
    async def llen(self, key: str) -> int:
        """Get list length"""
        pass

    @abstractmethod
    async def close(self):
        """Close storage connection"""
        pass

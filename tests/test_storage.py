"""Tests for Phase 1: Storage Layer (Redis and SQLite)"""
import pytest
import asyncio
from polycli.storage.redis_store import RedisStore
from polycli.storage.sqlite_store import SQLiteStore
from polycli.storage.base_store import BaseStorage


@pytest.fixture
async def redis_store():
    """Create a Redis store instance"""
    store = RedisStore(prefix="test:")
    yield store
    await store.close()


@pytest.fixture
def sqlite_store():
    """Create a SQLite store instance"""
    store = SQLiteStore(":memory:")
    yield store
    asyncio.run(store.close())


class TestRedisStore:
    """Test Redis store operations"""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, redis_store):
        """Test basic set and get operations"""
        await redis_store.set("test_key", {"value": "test_data"})
        result = await redis_store.get("test_key")
        assert result == {"value": "test_data"}
    
    @pytest.mark.asyncio
    async def test_set_with_ttl(self, redis_store):
        """Test set with TTL"""
        await redis_store.set("temp_key", {"value": "temp"}, ttl=2)
        result = await redis_store.get("temp_key")
        assert result is not None
        
        # Wait for TTL to expire
        await asyncio.sleep(3)
        result = await redis_store.get("temp_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete(self, redis_store):
        """Test delete operation"""
        await redis_store.set("delete_key", {"value": "delete_me"})
        assert await redis_store.exists("delete_key")
        
        await redis_store.delete("delete_key")
        assert not await redis_store.exists("delete_key")
    
    @pytest.mark.asyncio
    async def test_exists(self, redis_store):
        """Test exists operation"""
        assert not await redis_store.exists("nonexistent")
        await redis_store.set("exists_key", {"value": "exists"})
        assert await redis_store.exists("exists_key")
    
    @pytest.mark.asyncio
    async def test_hash_operations(self, redis_store):
        """Test hash field operations"""
        key = "hash:test"
        await redis_store.hset(key, "field1", {"data": "value1"})
        await redis_store.hset(key, "field2", {"data": "value2"})
        
        result = await redis_store.hget(key, "field1")
        assert result == {"data": "value1"}
        
        all_data = await redis_store.hgetall(key)
        assert len(all_data) == 2
        assert "field1" in all_data
        assert "field2" in all_data
        
        await redis_store.hdelete(key, "field1")
        result = await redis_store.hget(key, "field1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_list_operations(self, redis_store):
        """Test list operations"""
        import uuid
        key = f"list:test:{uuid.uuid4()}"
        
        # Push to list
        len1 = await redis_store.rpush(key, {"item": "first"})
        len2 = await redis_store.rpush(key, {"item": "second"})
        assert len1 == 1
        assert len2 == 2
        
        # Get list length
        assert await redis_store.llen(key) == 2
        
        # Get list range
        items = await redis_store.lrange(key, 0, -1)
        assert len(items) == 2
        assert items[0] == {"item": "first"}
        assert items[1] == {"item": "second"}
        
        # Pop from list
        item = await redis_store.lpop(key)
        assert item == {"item": "first"}
        assert await redis_store.llen(key) == 1
    
    @pytest.mark.asyncio
    async def test_publish_subscribe(self, redis_store):
        """Test pub/sub functionality"""
        channel = "test:channel"
        message = {"event": "test", "data": "hello"}
        
        # Subscribe
        pubsub = await redis_store.subscribe(channel)
        assert pubsub is not None
        
        # Get subscription confirmation message
        sub_msg = await pubsub.get_message(timeout=1)
        assert sub_msg is not None
        assert sub_msg["type"] == "subscribe"
        
        # Publish
        await redis_store.publish(channel, message)
        
        # Get published message
        msg = await pubsub.get_message(timeout=2)
        assert msg is not None
        assert msg["type"] == "message"
        
        await pubsub.unsubscribe()


class TestSQLiteStore:
    """Test SQLite store operations"""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, sqlite_store):
        """Test basic set and get operations"""
        await sqlite_store.set("test_key", {"value": "test_data"})
        result = await sqlite_store.get("test_key")
        assert result == {"value": "test_data"}
    
    @pytest.mark.asyncio
    async def test_set_with_ttl(self, sqlite_store):
        """Test set with TTL"""
        await sqlite_store.set("temp_key", {"value": "temp"}, ttl=2)
        result = await sqlite_store.get("temp_key")
        assert result is not None
        
        # Wait for TTL to expire
        await asyncio.sleep(3)
        result = await sqlite_store.get("temp_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete(self, sqlite_store):
        """Test delete operation"""
        await sqlite_store.set("delete_key", {"value": "delete_me"})
        assert await sqlite_store.exists("delete_key")
        
        await sqlite_store.delete("delete_key")
        assert not await sqlite_store.exists("delete_key")
    
    @pytest.mark.asyncio
    async def test_exists(self, sqlite_store):
        """Test exists operation"""
        assert not await sqlite_store.exists("nonexistent")
        await sqlite_store.set("exists_key", {"value": "exists"})
        assert await sqlite_store.exists("exists_key")
    
    @pytest.mark.asyncio
    async def test_hash_operations(self, sqlite_store):
        """Test hash field operations"""
        key = "hash:test"
        await sqlite_store.hset(key, "field1", {"data": "value1"})
        await sqlite_store.hset(key, "field2", {"data": "value2"})
        
        result = await sqlite_store.hget(key, "field1")
        assert result == {"data": "value1"}
        
        all_data = await sqlite_store.hgetall(key)
        assert len(all_data) == 2
        assert "field1" in all_data
        assert "field2" in all_data
        
        await sqlite_store.hdelete(key, "field1")
        result = await sqlite_store.hget(key, "field1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_list_operations(self, sqlite_store):
        """Test list operations"""
        key = "list:test"
        
        # Push to list
        len1 = await sqlite_store.rpush(key, {"item": "first"})
        len2 = await sqlite_store.rpush(key, {"item": "second"})
        assert len1 == 1
        assert len2 == 2
        
        # Get list length
        assert await sqlite_store.llen(key) == 2
        
        # Get list range
        items = await sqlite_store.lrange(key, 0, -1)
        assert len(items) == 2
        assert items[0] == {"item": "first"}
        assert items[1] == {"item": "second"}
        
        # Pop from list
        item = await sqlite_store.lpop(key)
        assert item == {"item": "first"}
        assert await sqlite_store.llen(key) == 1
    
    @pytest.mark.asyncio
    async def test_complex_data_types(self, sqlite_store):
        """Test storing complex data types"""
        complex_data = {
            "nested": {
                "deep": {
                    "value": 123
                }
            },
            "list": [1, 2, 3],
            "string": "test"
        }
        await sqlite_store.set("complex", complex_data)
        result = await sqlite_store.get("complex")
        assert result == complex_data


class TestStorageInterface:
    """Test that both stores implement the same interface"""
    
    @pytest.mark.asyncio
    async def test_redis_and_sqlite_consistency(self, redis_store, sqlite_store):
        """Test that both stores behave consistently"""
        test_data = {"test": "data", "number": 42}
        
        # Test both stores with same operations
        for store in [redis_store, sqlite_store]:
            await store.set("consistency:test", test_data)
            result = await store.get("consistency:test")
            assert result == test_data
            
            await store.delete("consistency:test")
            assert not await store.exists("consistency:test")

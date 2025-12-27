import sqlite3
import json
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager
import structlog
from .base_store import BaseStorage

logger = structlog.get_logger()


class SQLiteStore(BaseStorage):
    """SQLite-based persistent storage for historical data"""

    def __init__(self, db_path: str = "polycli.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._get_connection()
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT,
                ttl TEXT,
                created_at REAL
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hash_store (
                key TEXT,
                field TEXT,
                value TEXT,
                updated_at REAL,
                PRIMARY KEY (key, field)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS list_store (
                key TEXT,
                value TEXT,
                position INTEGER,
                created_at REAL,
                PRIMARY KEY (key, position)
            )
        """)
        
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        if self._conn is None:
            # Use shared cache for in-memory databases
            if self.db_path == ":memory:":
                self._conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
            else:
                self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        try:
            import time
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT value, ttl FROM kv_store WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            if row:
                ttl = row[1]
                # Check TTL
                if ttl:
                    expiry_time = float(ttl)
                    if time.time() > expiry_time:
                        # Expired, delete and return None
                        conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
                        conn.commit()
                        return None
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error("SQLite get error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL in seconds"""
        try:
            import time
            conn = self._get_connection()
            json_value = json.dumps(value, default=str)
            
            if ttl:
                expiry_time = time.time() + ttl
            else:
                expiry_time = None
            
            conn.execute(
                """
                INSERT OR REPLACE INTO kv_store (key, value, ttl, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, json_value, str(expiry_time) if expiry_time else None, time.time())
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("SQLite set error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key"""
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            conn.commit()
            return True
        except Exception as e:
            logger.error("SQLite delete error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT 1 FROM kv_store WHERE key = ? LIMIT 1",
                (key,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error("SQLite exists error", key=key, error=str(e))
            return False

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """Get hash field"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT value FROM hash_store WHERE key = ? AND field = ?",
                (key, field)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error("SQLite hget error", key=key, field=field, error=str(e))
            return None

    async def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field"""
        try:
            conn = self._get_connection()
            json_value = json.dumps(value, default=str)
            conn.execute(
                """
                INSERT OR REPLACE INTO hash_store (key, field, value, updated_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
                """,
                (key, field, json_value)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("SQLite hset error", key=key, field=field, error=str(e))
            return False

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT field, value FROM hash_store WHERE key = ?",
                (key,)
            )
            return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error("SQLite hgetall error", key=key, error=str(e))
            return {}

    async def hdelete(self, key: str, field: str) -> bool:
        """Delete hash field"""
        try:
            conn = self._get_connection()
            conn.execute(
                "DELETE FROM hash_store WHERE key = ? AND field = ?",
                (key, field)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("SQLite hdelete error", key=key, field=field, error=str(e))
            return False

    async def lpush(self, key: str, value: Any) -> int:
        """Push to list (left)"""
        try:
            conn = self._get_connection()
            
            cursor = conn.execute(
                "SELECT MAX(position) FROM list_store WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            max_pos = row[0] if row and row[0] is not None else 0
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM list_store WHERE key = ?",
                (key,)
            )
            count = cursor.fetchone()[0]
            
            json_value = json.dumps(value, default=str)
            conn.execute(
                """
                INSERT INTO list_store (key, value, position, created_at)
                VALUES (?, ?, 0, datetime('now', 'localtime'))
                """,
                (key, json_value)
            )
            conn.execute(
                """
                UPDATE list_store SET position = position + 1 WHERE key = ?
                """,
                (key,)
            )
            conn.commit()
            return count + 1
        except Exception as e:
            logger.error("SQLite lpush error", key=key, error=str(e))
            return 0

    async def rpush(self, key: str, value: Any) -> int:
        """Push to list (right)"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT MAX(position) FROM list_store WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            max_pos = row[0] if row and row[0] is not None else -1
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM list_store WHERE key = ?",
                (key,)
            )
            count = cursor.fetchone()[0]
            
            json_value = json.dumps(value, default=str)
            conn.execute(
                """
                INSERT INTO list_store (key, value, position, created_at)
                VALUES (?, ?, ?, datetime('now', 'localtime'))
                """,
                (key, json_value, max_pos + 1)
            )
            conn.commit()
            return count + 1
        except Exception as e:
            logger.error("SQLite rpush error", key=key, error=str(e))
            return 0

    async def lpop(self, key: str) -> Optional[Any]:
        """Pop from list (left)"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT value FROM list_store WHERE key = ? 
                ORDER BY position ASC LIMIT 1
                """,
                (key,)
            )
            row = cursor.fetchone()
            if row:
                value = json.loads(row[0])
                conn.execute(
                    "DELETE FROM list_store WHERE key = ? AND position = (SELECT MIN(position) FROM list_store WHERE key = ?)",
                    (key, key)
                )
                conn.commit()
                return value
            return None
        except Exception as e:
            logger.error("SQLite lpop error", key=key, error=str(e))
            return None

    async def rpop(self, key: str) -> Optional[Any]:
        """Pop from list (right)"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT value FROM list_store WHERE key = ? 
                ORDER BY position DESC LIMIT 1
                """,
                (key,)
            )
            row = cursor.fetchone()
            if row:
                value = json.loads(row[0])
                conn.execute(
                    "DELETE FROM list_store WHERE key = ? AND position = (SELECT MAX(position) FROM list_store WHERE key = ?)",
                    (key, key)
                )
                conn.commit()
                return value
            return None
        except Exception as e:
            logger.error("SQLite rpop error", key=key, error=str(e))
            return None

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get list range"""
        try:
            conn = self._get_connection()
            if end == -1:
                cursor = conn.execute(
                    """
                    SELECT value FROM list_store WHERE key = ? 
                    ORDER BY position ASC
                    """,
                    (key,)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT value FROM list_store WHERE key = ? 
                    ORDER BY position ASC LIMIT ? OFFSET ?
                    """,
                    (key, end - start + 1, start)
                )
            return [json.loads(row[0]) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("SQLite lrange error", key=key, error=str(e))
            return []

    async def llen(self, key: str) -> int:
        """Get list length"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM list_store WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error("SQLite llen error", key=key, error=str(e))
            return 0

    async def close(self):
        """Close database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

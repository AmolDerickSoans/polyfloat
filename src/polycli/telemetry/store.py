"""SQLite storage for telemetry events."""
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

from .models import TelemetryEvent

logger = logging.getLogger(__name__)


class TelemetryStore:
    """Persistent storage for telemetry events."""

    DEFAULT_DB_PATH = Path.home() / ".polycli" / "telemetry.db"

    def __init__(self, db_path: Optional[Path] = None, timeout: float = 1.0):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.timeout = timeout
        self.db_lock = threading.Lock()
        self._init_db()

    @property
    def enabled(self) -> bool:
        """Check if telemetry is enabled via config."""
        try:
            from polycli.utils.config import get_config_value

            return get_config_value("telemetry.enabled", True)
        except Exception:
            return True

    def _init_db(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path, timeout=self.timeout) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
                """
            )

    def emit(self, event: TelemetryEvent) -> None:
        """Emit a telemetry event (non-blocking, best-effort)."""
        if not self.enabled:
            return

        def _write():
            try:
                with sqlite3.connect(self.db_path, timeout=self.timeout) as conn:
                    conn.execute(
                        """
                        INSERT INTO events (event_type, timestamp, session_id, payload)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            event.event_type,
                            event.timestamp,
                            event.session_id,
                            json.dumps(event.payload),
                        ),
                    )
            except Exception as e:
                logger.warning(f"Failed to emit telemetry event: {e}")

        try:
            thread = threading.Thread(target=_write, daemon=True)
            thread.start()
        except Exception as e:
            logger.warning(f"Failed to start telemetry thread: {e}")

    def query(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[TelemetryEvent]:
        """Query telemetry events with optional filters."""
        query = (
            "SELECT event_type, timestamp, session_id, payload FROM events WHERE 1=1"
        )
        params = []

        if filters:
            if "event_type" in filters:
                query += " AND event_type = ?"
                params.append(filters["event_type"])
            if "session_id" in filters:
                query += " AND session_id = ?"
                params.append(filters["session_id"])
            if "since" in filters:
                query += " AND timestamp >= ?"
                params.append(filters["since"])
            if "until" in filters:
                query += " AND timestamp <= ?"
                params.append(filters["until"])

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path, timeout=self.timeout) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                TelemetryEvent(
                    event_type=row[0],
                    timestamp=row[1],
                    session_id=row[2],
                    payload=json.loads(row[3]) if row[3] else {},
                )
                for row in rows
            ]

    def count_events_since(self, since: float) -> int:
        """Count events since a given timestamp."""
        with sqlite3.connect(self.db_path, timeout=self.timeout) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp >= ?",
                (since,),
            ).fetchone()
            return row[0] if row else 0

    def cleanup_old_events(self, retention_days: int = 30) -> int:
        """Remove events older than retention_days. Returns count of deleted events."""
        import time

        cutoff_ts = time.time() - (retention_days * 24 * 60 * 60)

        with sqlite3.connect(self.db_path, timeout=self.timeout) as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (cutoff_ts,),
            )
            return cursor.rowcount

    def get_event_count(self, since: Optional[float] = None) -> int:
        """Get count of events, optionally filtered by timestamp."""
        with sqlite3.connect(self.db_path, timeout=self.timeout) as conn:
            if since:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE timestamp >= ?",
                    (since,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0] if row else 0

    def get_db_size(self) -> int:
        """Get database file size in bytes."""
        try:
            return self.db_path.stat().st_size
        except OSError:
            return 0

    def periodic_cleanup(self, retention_days: int = 30) -> Optional[int]:
        """Run cleanup. Can be called periodically or on demand."""
        try:
            return self.cleanup_old_events(retention_days)
        except Exception as e:
            logger.warning(f"Telemetry cleanup failed: {e}")
            return None

    def close(self) -> None:
        """Close database connection (no-op for SQLite)."""
        pass

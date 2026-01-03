"""Unit tests for telemetry module."""
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from polycli.telemetry import (
    TelemetryEvent,
    TelemetryStore,
    generate_session_id,
    get_session_id,
    set_session_id,
    reset_session_id,
    emit_event,
)


class TestSessionIdGeneration:
    """Test session ID generation."""

    def test_session_id_format(self):
        """Session ID should follow format: hostname_timestamp_random."""
        session_id = generate_session_id()
        parts = session_id.split("_")

        assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}: {session_id}"
        assert len(parts[0]) <= 10, f"Hostname too long: {parts[0]}"
        assert parts[1].isdigit(), f"Timestamp not numeric: {parts[1]}"
        assert len(parts[2]) == 6, f"Random suffix should be 6 hex chars: {parts[2]}"

    def test_session_id_uniqueness(self):
        """Generated session IDs should be unique."""
        ids = {generate_session_id() for _ in range(100)}
        assert len(ids) == 100, "Session IDs should be unique"

    def test_get_session_id_cached(self):
        """get_session_id should return cached value."""
        reset_session_id()
        first = get_session_id()
        second = get_session_id()
        assert first == second, "Session ID should be cached"

    def test_set_session_id(self):
        """set_session_id should override the session ID."""
        reset_session_id()
        set_session_id("custom_session_123")
        assert get_session_id() == "custom_session_123"
        reset_session_id()

    def test_reset_session_id(self):
        """reset_session_id should generate a new ID."""
        reset_session_id()
        first = get_session_id()
        reset_session_id()
        second = get_session_id()
        assert first != second, "Reset should generate new session ID"


class TestTelemetryEvent:
    """Test TelemetryEvent dataclass."""

    def test_create_event(self):
        """Basic event creation."""
        event = TelemetryEvent(
            event_type="test_event",
            session_id="test_session",
            payload={"key": "value"},
        )

        assert event.event_type == "test_event"
        assert event.session_id == "test_session"
        assert event.payload == {"key": "value"}
        assert isinstance(event.timestamp, float)

    def test_default_timestamp(self):
        """Timestamp should be set automatically."""
        before = time.time()
        event = TelemetryEvent(event_type="test", session_id="s1")
        after = time.time()

        assert before <= event.timestamp <= after

    def test_to_dict(self):
        """Event should serialize to dict."""
        event = TelemetryEvent(
            event_type="test_event",
            session_id="sess_123",
            payload={"price": 0.55},
        )

        data = event.to_dict()

        assert data["event_type"] == "test_event"
        assert data["session_id"] == "sess_123"
        assert data["payload"] == {"price": 0.55}
        assert "timestamp" in data

    def test_from_dict(self):
        """Event should deserialize from dict."""
        data = {
            "event_type": "test",
            "timestamp": 1234567890.0,
            "session_id": "abc123",
            "payload": {"foo": "bar"},
        }

        event = TelemetryEvent.from_dict(data)

        assert event.event_type == "test"
        assert event.timestamp == 1234567890.0
        assert event.session_id == "abc123"
        assert event.payload == {"foo": "bar"}


class TestTelemetryStore:
    """Test TelemetryStore functionality."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return tmp_path / "telemetry.db"

    @pytest.fixture
    def store(self, temp_db_path):
        return TelemetryStore(db_path=temp_db_path)

    def test_init_db(self, store, temp_db_path):
        """Store should create database and table."""
        assert temp_db_path.exists()

        with sqlite3.connect(temp_db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
            ).fetchall()
            assert len(rows) == 1

            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='events'"
            ).fetchall()
            assert len(indexes) >= 3

    def test_emit_event(self, store, temp_db_path):
        """Emit should store event in database."""
        event = TelemetryEvent(
            event_type="trade_proposed",
            session_id="sess_abc",
            payload={"amount": 100.0},
        )

        store.emit(event)
        time.sleep(0.1)

        with sqlite3.connect(temp_db_path) as conn:
            rows = conn.execute("SELECT * FROM events").fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "trade_proposed"
            assert rows[0][3] == "sess_abc"

    def test_emit_does_not_block(self, store):
        """Emit should return quickly without blocking."""
        event = TelemetryEvent(event_type="test", session_id="s", payload={})

        start = time.time()
        store.emit(event)
        elapsed = time.time() - start

        assert elapsed < 0.1, "emit() should be non-blocking"

    def test_query_all_events(self, store):
        """Query without filters should return all events."""
        for i in range(5):
            store.emit(
                TelemetryEvent(
                    event_type=f"event_{i}",
                    session_id="sess_x",
                    payload={},
                )
            )
        time.sleep(0.1)

        events = store.query()
        assert len(events) == 5

    def test_query_with_event_type_filter(self, store):
        """Query should filter by event type."""
        store.emit(TelemetryEvent(event_type="buy", session_id="s1", payload={}))
        store.emit(TelemetryEvent(event_type="sell", session_id="s1", payload={}))
        store.emit(TelemetryEvent(event_type="buy", session_id="s2", payload={}))
        time.sleep(0.1)

        events = store.query(filters={"event_type": "buy"})
        assert len(events) == 2
        assert all(e.event_type == "buy" for e in events)

    def test_query_with_session_filter(self, store):
        """Query should filter by session ID."""
        store.emit(
            TelemetryEvent(event_type="trade", session_id="session_a", payload={})
        )
        store.emit(
            TelemetryEvent(event_type="trade", session_id="session_b", payload={})
        )
        time.sleep(0.1)

        events = store.query(filters={"session_id": "session_a"})
        assert len(events) == 1
        assert events[0].session_id == "session_a"

    def test_query_with_since_filter(self, store):
        """Query should filter by timestamp."""
        store.emit(TelemetryEvent(event_type="early", session_id="s1", payload={}))
        time.sleep(0.05)
        since = time.time()
        time.sleep(0.05)
        store.emit(TelemetryEvent(event_type="late", session_id="s1", payload={}))
        time.sleep(0.1)

        events = store.query(filters={"since": since})
        assert len(events) == 1
        assert events[0].event_type == "late"

    def test_query_limit(self, store):
        """Query should respect limit parameter."""
        for i in range(10):
            store.emit(TelemetryEvent(event_type="test", session_id="s", payload={}))
        time.sleep(0.1)

        events = store.query(limit=5)
        assert len(events) == 5

    def test_count_events_since(self, store):
        """count_events_since should return correct count."""
        store.emit(TelemetryEvent(event_type="test", session_id="s", payload={}))
        store.emit(TelemetryEvent(event_type="test", session_id="s", payload={}))
        time.sleep(0.1)

        since = time.time() - 10
        count = store.count_events_since(since)
        assert count == 2

    def test_cleanup_old_events(self, store, temp_db_path):
        """cleanup_old_events should delete old records."""
        event = TelemetryEvent(event_type="old", session_id="s", payload={})
        store.emit(event)
        time.sleep(0.1)

        cutoff_ts = event.timestamp - 1
        deleted = store.cleanup_old_events(retention_days=0)
        assert deleted >= 1

        events = store.query()
        assert len(events) == 0

    def test_emit_when_disabled(self, store, temp_db_path):
        """Emit should not store events when disabled."""
        store.emit(TelemetryEvent(event_type="test", session_id="s", payload={}))
        time.sleep(0.1)

        with sqlite3.connect(temp_db_path) as conn:
            rows = conn.execute("SELECT * FROM events").fetchall()
            assert len(rows) == 1


class TestEmitEventConvenience:
    """Test the emit_event convenience function."""

    def test_emit_event_uses_current_session(self, tmp_path):
        """emit_event should use current session ID."""
        reset_session_id()
        set_session_id("my_session_xyz")

        test_db_path = tmp_path / "test_telemetry.db"
        from polycli.telemetry.store import TelemetryStore
        import polycli.telemetry as telemetry

        original_store_class = telemetry.TelemetryStore
        telemetry.TelemetryStore = lambda: TelemetryStore(db_path=test_db_path)

        try:
            emit_event("test_event", {"key": "val"})
            time.sleep(0.1)

            store = TelemetryStore(db_path=test_db_path)
            events = store.query()
            assert len(events) == 1
            assert events[0].session_id == "my_session_xyz"
        finally:
            telemetry.TelemetryStore = original_store_class
            reset_session_id()

    def test_emit_event_with_custom_session(self, tmp_path):
        """emit_event should use provided session ID."""
        test_db_path = tmp_path / "test_telemetry2.db"
        from polycli.telemetry.store import TelemetryStore
        import polycli.telemetry as telemetry

        original_store_class = telemetry.TelemetryStore
        telemetry.TelemetryStore = lambda: TelemetryStore(db_path=test_db_path)

        try:
            emit_event("test", {"key": "val"}, session_id="custom_session")
            time.sleep(0.1)

            store = TelemetryStore(db_path=test_db_path)
            events = store.query()
            assert len(events) == 1
            assert events[0].session_id == "custom_session"
        finally:
            telemetry.TelemetryStore = original_store_class
            reset_session_id()

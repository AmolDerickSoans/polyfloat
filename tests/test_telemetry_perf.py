"""Performance tests for telemetry system."""
import threading
import time

import pytest

from polycli.telemetry import TelemetryEvent, TelemetryStore, get_session_id


class TestTelemetryPerformance:
    """Performance tests for TelemetryStore."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return tmp_path / "telemetry_perf.db"

    @pytest.fixture
    def store(self, temp_db_path):
        return TelemetryStore(db_path=temp_db_path)

    def test_emit_performance(self, store, temp_db_path):
        """Test that emit stays under 5ms average."""
        event = TelemetryEvent(
            event_type="perf_test",
            timestamp=time.time(),
            session_id=get_session_id(),
            payload={"test": "data"},
        )

        for _ in range(5):
            store.emit(event)
        time.sleep(0.1)

        times = []
        for _ in range(10):
            start = time.perf_counter()
            store.emit(event)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            time.sleep(0.01)

        avg_time = sum(times) / len(times)
        assert (
            avg_time < 0.005
        ), f"Average emit time {avg_time*1000:.2f}ms exceeds 5ms target"

    def test_query_performance(self, store, temp_db_path):
        """Test that queries complete in <100ms for 1000 events."""
        session_id = get_session_id()
        base_time = time.time()

        for i in range(1000):
            store.emit(
                TelemetryEvent(
                    event_type="query_perf_test",
                    timestamp=base_time - (i * 0.001),
                    session_id=session_id,
                    payload={"index": i},
                )
            )
        time.sleep(0.2)

        start = time.perf_counter()
        events = store.query(
            filters={"event_type": "query_perf_test", "session_id": session_id},
            limit=100,
        )
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"Query took {elapsed*1000:.2f}ms, expected <100ms"
        assert len(events) == 100

    def test_concurrent_emit(self, store, temp_db_path):
        """Test that concurrent emits don't cause errors."""
        session_id = get_session_id()

        def emit_events():
            for i in range(10):
                store.emit(
                    TelemetryEvent(
                        event_type="concurrent_test",
                        timestamp=time.time(),
                        session_id=session_id,
                        payload={"thread_index": i},
                    )
                )

        threads = [threading.Thread(target=emit_events) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.3)
        events = store.query(
            filters={"event_type": "concurrent_test", "session_id": session_id},
            limit=200,
        )
        assert len(events) == 100, f"Expected 100 events, got {len(events)}"

    def test_cleanup_old_events(self, store, temp_db_path):
        """Test that old events are cleaned up correctly."""
        old_session = "old_session_test"
        recent_session = "recent_session_test"

        old_event = TelemetryEvent(
            event_type="old_event",
            timestamp=time.time() - (31 * 86400),
            session_id=old_session,
            payload={},
        )
        store.emit(old_event)

        recent_event = TelemetryEvent(
            event_type="recent_event",
            timestamp=time.time(),
            session_id=recent_session,
            payload={},
        )
        store.emit(recent_event)
        time.sleep(0.1)

        deleted = store.cleanup_old_events(retention_days=30)

        assert deleted >= 1, f"Expected at least 1 deletion, got {deleted}"

        remaining = store.query(limit=100)
        assert len(remaining) == 1, f"Expected 1 event, got {len(remaining)}"
        assert remaining[0].event_type == "recent_event"

    def test_get_event_count(self, store, temp_db_path):
        """Test get_event_count returns correct values."""
        session_id = get_session_id()

        for i in range(5):
            store.emit(
                TelemetryEvent(
                    event_type="count_test",
                    timestamp=time.time(),
                    session_id=session_id,
                    payload={},
                )
            )
        time.sleep(0.1)

        total = store.get_event_count()
        assert total >= 5, f"Expected at least 5 events, got {total}"

        since = time.time() - 10
        recent_count = store.get_event_count(since=since)
        assert (
            recent_count >= 5
        ), f"Expected at least 5 recent events, got {recent_count}"

        old_count = store.get_event_count(since=time.time() - 86400)
        assert (
            old_count >= 5
        ), f"Expected at least 5 events from last day, got {old_count}"

    def test_get_db_size(self, store, temp_db_path):
        """Test get_db_size returns reasonable size."""
        session_id = get_session_id()

        for i in range(100):
            store.emit(
                TelemetryEvent(
                    event_type="size_test",
                    timestamp=time.time(),
                    session_id=session_id,
                    payload={"data": "x" * 100},
                )
            )
        time.sleep(0.2)

        size = store.get_db_size()
        assert size > 0, "Database size should be positive"
        assert size < 1024 * 1024, f"Database size {size} seems unreasonably large"

    def test_periodic_cleanup(self, store, temp_db_path):
        """Test periodic_cleanup wrapper method."""
        old_session = "periodic_old"
        recent_session = "periodic_recent"

        store.emit(
            TelemetryEvent(
                event_type="old_for_periodic",
                timestamp=time.time() - (60 * 86400),
                session_id=old_session,
                payload={},
            )
        )
        store.emit(
            TelemetryEvent(
                event_type="recent_for_periodic",
                timestamp=time.time(),
                session_id=recent_session,
                payload={},
            )
        )
        time.sleep(0.1)

        result = store.periodic_cleanup(retention_days=30)

        assert result is not None, "periodic_cleanup should return count"
        assert result >= 1, f"Expected at least 1 deletion, got {result}"

        remaining = store.query(limit=100)
        assert len(remaining) == 1

    def test_emit_non_blocking(self, store, temp_db_path):
        """Test that emit doesn't block main thread."""
        event = TelemetryEvent(
            event_type="nonblock_test",
            timestamp=time.time(),
            session_id=get_session_id(),
            payload={},
        )

        start = time.time()
        store.emit(event)
        elapsed = time.time() - start

        assert (
            elapsed < 0.05
        ), f"emit() took {elapsed*1000:.2f}ms, should be non-blocking"
        time.sleep(0.1)

    def test_high_volume_emit(self, store, temp_db_path):
        """Test system handles high volume emits without crashing."""
        session_id = get_session_id()

        for i in range(500):
            store.emit(
                TelemetryEvent(
                    event_type="high_volume",
                    timestamp=time.time(),
                    session_id=session_id,
                    payload={"index": i},
                )
            )

        time.sleep(0.5)

        count = store.get_event_count()
        assert count >= 400, f"Expected at least 400 events, got {count}"

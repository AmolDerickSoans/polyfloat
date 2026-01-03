"""SQLite storage for risk audit logs."""
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite3

from .models import TradeAuditLog


class RiskAuditStore:
    """Persistent storage for risk audit data."""

    DEFAULT_DB_PATH = Path.home() / ".polycli" / "risk_audit.db"

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trade_audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    token_id TEXT,
                    market_id TEXT,
                    side TEXT,
                    amount TEXT,
                    price TEXT,
                    provider TEXT,
                    approved INTEGER,
                    violations TEXT,
                    warnings TEXT,
                    risk_score REAL,
                    agent_id TEXT,
                    agent_reasoning TEXT,
                    executed INTEGER,
                    execution_result TEXT,
                    metrics_snapshot TEXT
                );
                
                CREATE TABLE IF NOT EXISTS circuit_breaker_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT,
                    cooldown_until TIMESTAMP,
                    provider TEXT
                );
                
                CREATE TABLE IF NOT EXISTS daily_pnl_tracking (
                    date DATE PRIMARY KEY,
                    starting_balance TEXT,
                    ending_balance TEXT,
                    realized_pnl TEXT,
                    peak_balance TEXT,
                    provider TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON trade_audit_logs(timestamp);
                CREATE INDEX IF NOT EXISTS idx_audit_approved ON trade_audit_logs(approved);
                CREATE INDEX IF NOT EXISTS idx_audit_agent ON trade_audit_logs(agent_id);

                CREATE TABLE IF NOT EXISTS execution_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id TEXT REFERENCES trade_audit_logs(id),
                    execution_status TEXT NOT NULL,
                    order_id TEXT,
                    filled_amount REAL,
                    latency_ms REAL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_outcome_attempt ON execution_outcomes(attempt_id);
                CREATE INDEX IF NOT EXISTS idx_outcome_status ON execution_outcomes(execution_status);
            """
            )

    def log_trade_attempt(self, log: TradeAuditLog) -> None:
        """Log a trade attempt (approved or rejected)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trade_audit_logs
                (id, timestamp, token_id, market_id, side, amount, price, provider,
                 approved, violations, warnings, risk_score, agent_id, agent_reasoning,
                 executed, execution_result, metrics_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log.id,
                    log.timestamp,
                    log.token_id,
                    log.market_id,
                    log.side,
                    str(log.amount),
                    str(log.price) if log.price else None,
                    log.provider,
                    1 if log.approved else 0,
                    log.violations,
                    log.warnings,
                    log.risk_score,
                    log.agent_id,
                    log.agent_reasoning,
                    1 if log.executed else 0,
                    log.execution_result,
                    log.metrics_snapshot,
                ),
            )

    def get_trades_since(
        self, since: datetime, provider: Optional[str] = None
    ) -> List[TradeAuditLog]:
        """Get trade attempts since a given time."""
        with sqlite3.connect(self.db_path) as conn:
            if provider:
                rows = conn.execute(
                    "SELECT * FROM trade_audit_logs WHERE timestamp >= ? AND provider = ? ORDER BY timestamp DESC",
                    (since, provider),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_audit_logs WHERE timestamp >= ? ORDER BY timestamp DESC",
                    (since,),
                ).fetchall()

            return [self._row_to_log(row) for row in rows]

    def get_rejected_trades(self, limit: int = 100) -> List[TradeAuditLog]:
        """Get recently rejected trades."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM trade_audit_logs WHERE approved = 0 ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_log(row) for row in rows]

    def trigger_circuit_breaker(
        self, reason: str, cooldown_minutes: int, provider: str = "all"
    ) -> None:
        """Record circuit breaker trigger."""
        cooldown_until = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO circuit_breaker_events (reason, cooldown_until, provider) VALUES (?, ?, ?)",
                (reason, cooldown_until, provider),
            )

    def is_circuit_breaker_active(self, provider: str = "all") -> bool:
        """Check if circuit breaker is currently active."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT cooldown_until FROM circuit_breaker_events "
                "WHERE (provider = ? OR provider = 'all') "
                "ORDER BY triggered_at DESC LIMIT 1",
                (provider,),
            ).fetchone()

            if row and row[0]:
                cooldown_until = datetime.fromisoformat(row[0])
                return datetime.utcnow() < cooldown_until
            return False

    def get_trades_count_since(
        self, since: datetime, provider: Optional[str] = None
    ) -> int:
        """Count trades since a given time."""
        with sqlite3.connect(self.db_path) as conn:
            if provider:
                row = conn.execute(
                    "SELECT COUNT(*) FROM trade_audit_logs WHERE timestamp >= ? AND provider = ? AND approved = 1",
                    (since, provider),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM trade_audit_logs WHERE timestamp >= ? AND approved = 1",
                    (since,),
                ).fetchone()
            return row[0] if row else 0

    def log_execution_outcome(
        self,
        attempt_id: str,
        execution_status: str,
        order_id: Optional[str] = None,
        filled_amount: Optional[float] = None,
        latency_ms: Optional[float] = None,
    ) -> int:
        """Log an execution outcome after trade execution."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO execution_outcomes
                (attempt_id, execution_status, order_id, filled_amount, latency_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (attempt_id, execution_status, order_id, filled_amount, latency_ms),
            )
            return cursor.lastrowid or 0

    def get_execution_outcome(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        """Get execution outcome for a given attempt_id."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM execution_outcomes WHERE attempt_id = ? ORDER BY id DESC LIMIT 1",
                (attempt_id,),
            ).fetchone()
            if row:
                return {
                    "id": row[0],
                    "attempt_id": row[1],
                    "execution_status": row[2],
                    "order_id": row[3],
                    "filled_amount": row[4],
                    "latency_ms": row[5],
                    "executed_at": row[6],
                }
            return None

    def get_orphaned_approvals(self, limit: int = 100) -> List[TradeAuditLog]:
        """Get approved trades that have no execution outcome recorded."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM trade_audit_logs
                WHERE approved = 1 AND id NOT IN (
                    SELECT attempt_id FROM execution_outcomes
                )
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
            return [self._row_to_log(row) for row in rows]

    def get_execution_stats(self, since: Optional[datetime] = None) -> Dict[str, Any]:
        """Get execution statistics (success/fail rates)."""
        with sqlite3.connect(self.db_path) as conn:
            if since:
                total = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE executed_at >= ?",
                    (since,),
                ).fetchone()[0]
                success = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE execution_status = 'SUCCESS' AND executed_at >= ?",
                    (since,),
                ).fetchone()[0]
                failed = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE execution_status = 'FAILED' AND executed_at >= ?",
                    (since,),
                ).fetchone()[0]
                timeout = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE execution_status = 'TIMEOUT' AND executed_at >= ?",
                    (since,),
                ).fetchone()[0]
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes"
                ).fetchone()[0]
                success = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE execution_status = 'SUCCESS'"
                ).fetchone()[0]
                failed = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE execution_status = 'FAILED'"
                ).fetchone()[0]
                timeout = conn.execute(
                    "SELECT COUNT(*) FROM execution_outcomes WHERE execution_status = 'TIMEOUT'"
                ).fetchone()[0]

            avg_latency = (
                conn.execute(
                    "SELECT AVG(latency_ms) FROM execution_outcomes WHERE latency_ms IS NOT NULL"
                ).fetchone()[0]
                or 0.0
            )

            return {
                "total_executions": total,
                "success_count": success,
                "failed_count": failed,
                "timeout_count": timeout,
                "success_rate": (success / total * 100) if total > 0 else 0.0,
                "avg_latency_ms": avg_latency,
            }

    def _row_to_log(self, row) -> TradeAuditLog:
        return TradeAuditLog(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]) if row[1] else datetime.utcnow(),
            token_id=row[2],
            market_id=row[3],
            side=row[4],
            amount=Decimal(row[5]) if row[5] else Decimal("0"),
            price=Decimal(row[6]) if row[6] else None,
            provider=row[7],
            approved=bool(row[8]),
            violations=row[9] or "",
            warnings=row[10] or "",
            risk_score=row[11] or 0.0,
            agent_id=row[12],
            agent_reasoning=row[13],
            executed=bool(row[14]),
            execution_result=row[15] or "",
            metrics_snapshot=row[16] or "",
        )

"""SQLite storage for risk audit logs."""
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import sqlite3

from .models import TradeAuditLog, RiskMetrics


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
            conn.executescript("""
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
            """)
    
    def log_trade_attempt(self, log: TradeAuditLog) -> None:
        """Log a trade attempt (approved or rejected)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trade_audit_logs
                (id, timestamp, token_id, market_id, side, amount, price, provider,
                 approved, violations, warnings, risk_score, agent_id, agent_reasoning,
                 executed, execution_result, metrics_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.id, log.timestamp, log.token_id, log.market_id, log.side,
                str(log.amount), str(log.price) if log.price else None, log.provider,
                1 if log.approved else 0, log.violations, log.warnings, log.risk_score,
                log.agent_id, log.agent_reasoning,
                1 if log.executed else 0, log.execution_result, log.metrics_snapshot
            ))
    
    def get_trades_since(self, since: datetime, provider: Optional[str] = None) -> List[TradeAuditLog]:
        """Get trade attempts since a given time."""
        with sqlite3.connect(self.db_path) as conn:
            if provider:
                rows = conn.execute(
                    "SELECT * FROM trade_audit_logs WHERE timestamp >= ? AND provider = ? ORDER BY timestamp DESC",
                    (since, provider)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_audit_logs WHERE timestamp >= ? ORDER BY timestamp DESC",
                    (since,)
                ).fetchall()
            
            return [self._row_to_log(row) for row in rows]
    
    def get_rejected_trades(self, limit: int = 100) -> List[TradeAuditLog]:
        """Get recently rejected trades."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM trade_audit_logs WHERE approved = 0 ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [self._row_to_log(row) for row in rows]
    
    def trigger_circuit_breaker(self, reason: str, cooldown_minutes: int, provider: str = "all") -> None:
        """Record circuit breaker trigger."""
        cooldown_until = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO circuit_breaker_events (reason, cooldown_until, provider) VALUES (?, ?, ?)",
                (reason, cooldown_until, provider)
            )
    
    def is_circuit_breaker_active(self, provider: str = "all") -> bool:
        """Check if circuit breaker is currently active."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT cooldown_until FROM circuit_breaker_events "
                "WHERE (provider = ? OR provider = 'all') "
                "ORDER BY triggered_at DESC LIMIT 1",
                (provider,)
            ).fetchone()
            
            if row and row[0]:
                cooldown_until = datetime.fromisoformat(row[0])
                return datetime.utcnow() < cooldown_until
            return False
    
    def get_trades_count_since(self, since: datetime, provider: Optional[str] = None) -> int:
        """Count trades since a given time."""
        with sqlite3.connect(self.db_path) as conn:
            if provider:
                row = conn.execute(
                    "SELECT COUNT(*) FROM trade_audit_logs WHERE timestamp >= ? AND provider = ? AND approved = 1",
                    (since, provider)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM trade_audit_logs WHERE timestamp >= ? AND approved = 1",
                    (since,)
                ).fetchone()
            return row[0] if row else 0
    
    def _row_to_log(self, row) -> TradeAuditLog:
        """Convert database row to TradeAuditLog."""
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
            metrics_snapshot=row[16] or ""
        )

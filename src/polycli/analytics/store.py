"""SQLite storage for analytics data."""
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict
import sqlite3

from .models import TradeRecord, DailyPnL


class AnalyticsStore:
    """Persistent storage for analytics data."""
    
    DEFAULT_DB_PATH = Path.home() / ".polycli" / "analytics.db"
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    market_id TEXT NOT NULL,
                    market_name TEXT,
                    token_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    outcome TEXT,
                    price TEXT NOT NULL,
                    size TEXT NOT NULL,
                    total TEXT NOT NULL,
                    fee TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    pnl TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS daily_snapshots (
                    date DATE PRIMARY KEY,
                    starting_balance TEXT NOT NULL,
                    ending_balance TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    unrealized_pnl TEXT NOT NULL,
                    trades_count INTEGER NOT NULL,
                    winning_trades INTEGER NOT NULL,
                    losing_trades INTEGER NOT NULL,
                    positions_snapshot TEXT,
                    provider TEXT
                );
                
                CREATE TABLE IF NOT EXISTS balance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    balance TEXT NOT NULL,
                    provider TEXT NOT NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
                CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
                CREATE INDEX IF NOT EXISTS idx_trades_provider ON trades(provider);
            """)
    
    def record_trade(self, trade: TradeRecord) -> None:
        """Record a trade for analytics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades
                (id, timestamp, market_id, market_name, token_id, side, outcome,
                 price, size, total, fee, provider, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.timestamp, trade.market_id, trade.market_name,
                trade.token_id, trade.side, trade.outcome,
                str(trade.price), str(trade.size), str(trade.total),
                str(trade.fee), trade.provider, str(trade.pnl) if trade.pnl else None
            ))
    
    def get_trades(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        provider: Optional[str] = None,
        market_id: Optional[str] = None,
        limit: int = 1000
    ) -> List[TradeRecord]:
        """Get trades with optional filters."""
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_trade(row) for row in rows]
    
    def record_daily_snapshot(self, snapshot: DailyPnL) -> None:
        """Record end-of-day snapshot."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO daily_snapshots
                (date, starting_balance, ending_balance, realized_pnl, unrealized_pnl,
                 trades_count, winning_trades, losing_trades)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.date, str(snapshot.starting_balance), str(snapshot.ending_balance),
                str(snapshot.realized_pnl), str(snapshot.unrealized_pnl),
                snapshot.trades_count, snapshot.winning_trades, snapshot.losing_trades
            ))
    
    def get_daily_snapshots(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 365
    ) -> List[DailyPnL]:
        """Get daily P&L snapshots."""
        query = "SELECT * FROM daily_snapshots WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_daily_pnl(row) for row in rows]
    
    def record_balance(self, balance: Decimal, provider: str) -> None:
        """Record current balance for history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO balance_history (balance, provider) VALUES (?, ?)",
                (str(balance), provider)
            )
    
    def get_peak_balance(self, provider: Optional[str] = None) -> Decimal:
        """Get peak balance for drawdown calculation."""
        with sqlite3.connect(self.db_path) as conn:
            if provider:
                row = conn.execute(
                    "SELECT MAX(CAST(balance AS REAL)) FROM balance_history WHERE provider = ?",
                    (provider,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT MAX(CAST(balance AS REAL)) FROM balance_history"
                ).fetchone()
            return Decimal(str(row[0])) if row and row[0] else Decimal("0")
    
    def _row_to_trade(self, row) -> TradeRecord:
        return TradeRecord(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            market_id=row[2],
            market_name=row[3] or "",
            token_id=row[4],
            side=row[5],
            outcome=row[6] or "",
            price=Decimal(row[7]),
            size=Decimal(row[8]),
            total=Decimal(row[9]),
            fee=Decimal(row[10]),
            provider=row[11],
            pnl=Decimal(row[12]) if row[12] else None
        )
    
    def _row_to_daily_pnl(self, row) -> DailyPnL:
        return DailyPnL(
            date=date.fromisoformat(row[0]),
            starting_balance=Decimal(row[1]),
            ending_balance=Decimal(row[2]),
            realized_pnl=Decimal(row[3]),
            unrealized_pnl=Decimal(row[4]),
            total_pnl=Decimal(row[3]) + Decimal(row[4]),
            trades_count=row[5],
            winning_trades=row[6],
            losing_trades=row[7]
        )

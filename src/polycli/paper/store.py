"""SQLite-based storage for paper trading state."""
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import sqlite3

from .models import (
    PaperOrder, PaperPosition, PaperTrade, PaperWallet,
    PaperOrderStatus, PaperOrderSide
)


class PaperTradingStore:
    """Persistent storage for paper trading data using SQLite."""
    
    DEFAULT_DB_PATH = Path.home() / ".polycli" / "paper_trading.db"
    DEFAULT_INITIAL_BALANCE = Decimal("1000.00")
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS paper_wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL UNIQUE,
                    balance TEXT NOT NULL,
                    initial_balance TEXT NOT NULL,
                    total_deposited TEXT NOT NULL,
                    total_withdrawn TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    price TEXT,
                    status TEXT NOT NULL,
                    filled_amount TEXT NOT NULL,
                    avg_fill_price TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS paper_positions (
                    id TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    size TEXT NOT NULL,
                    avg_price TEXT NOT NULL,
                    cost_basis TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(token_id, provider)
                );
                
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    token_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price TEXT NOT NULL,
                    size TEXT NOT NULL,
                    total TEXT NOT NULL,
                    fee TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES paper_orders(id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_orders_provider ON paper_orders(provider);
                CREATE INDEX IF NOT EXISTS idx_positions_provider ON paper_positions(provider);
                CREATE INDEX IF NOT EXISTS idx_trades_provider ON paper_trades(provider);
            """)
    
    def get_wallet(self, provider: str = "polymarket") -> PaperWallet:
        """Get or create wallet for provider."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT balance, initial_balance, total_deposited, total_withdrawn, realized_pnl "
                "FROM paper_wallets WHERE provider = ?",
                (provider,)
            ).fetchone()
            
            if row:
                return PaperWallet(
                    balance=Decimal(row[0]),
                    initial_balance=Decimal(row[1]),
                    total_deposited=Decimal(row[2]),
                    total_withdrawn=Decimal(row[3]),
                    realized_pnl=Decimal(row[4]),
                    provider=provider
                )
            
            # Create new wallet with default balance
            wallet = PaperWallet(provider=provider)
            conn.execute(
                "INSERT INTO paper_wallets (provider, balance, initial_balance, total_deposited, total_withdrawn, realized_pnl) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (provider, str(wallet.balance), str(wallet.initial_balance), 
                 str(wallet.total_deposited), str(wallet.total_withdrawn), str(wallet.realized_pnl))
            )
            return wallet
    
    def update_wallet_balance(self, provider: str, new_balance: Decimal, realized_pnl: Optional[Decimal] = None) -> None:
        """Update wallet balance and optionally realized PnL."""
        with sqlite3.connect(self.db_path) as conn:
            if realized_pnl is not None:
                conn.execute(
                    "UPDATE paper_wallets SET balance = ?, realized_pnl = ?, updated_at = ? WHERE provider = ?",
                    (str(new_balance), str(realized_pnl), datetime.utcnow(), provider)
                )
            else:
                conn.execute(
                    "UPDATE paper_wallets SET balance = ?, updated_at = ? WHERE provider = ?",
                    (str(new_balance), datetime.utcnow(), provider)
                )
    
    def save_order(self, order: PaperOrder) -> None:
        """Save or update an order."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO paper_orders 
                (id, token_id, market_id, side, amount, price, status, filled_amount, avg_fill_price, provider, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.id, order.token_id, order.market_id, order.side.value,
                str(order.amount), str(order.price) if order.price else None,
                order.status.value, str(order.filled_amount), str(order.avg_fill_price),
                order.provider, order.created_at, order.updated_at
            ))
    
    def save_position(self, position: PaperPosition) -> None:
        """Save or update a position."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO paper_positions
                (id, token_id, market_id, outcome, size, avg_price, cost_basis, realized_pnl, provider, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.id, position.token_id, position.market_id, position.outcome,
                str(position.size), str(position.avg_price), str(position.cost_basis),
                str(position.realized_pnl), position.provider, position.created_at, position.updated_at
            ))
    
    def save_trade(self, trade: PaperTrade) -> None:
        """Save a trade record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO paper_trades
                (id, order_id, token_id, market_id, side, price, size, total, fee, provider, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.order_id, trade.token_id, trade.market_id,
                trade.side.value, str(trade.price), str(trade.size), str(trade.total),
                str(trade.fee), trade.provider, trade.executed_at
            ))
    
    def get_positions(self, provider: str = "polymarket") -> List[PaperPosition]:
        """Get all positions for a provider."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, token_id, market_id, outcome, size, avg_price, cost_basis, realized_pnl, created_at, updated_at "
                "FROM paper_positions WHERE provider = ? AND CAST(size AS REAL) > 0",
                (provider,)
            ).fetchall()
            
            return [
                PaperPosition(
                    id=row[0], token_id=row[1], market_id=row[2], outcome=row[3],
                    size=Decimal(row[4]), avg_price=Decimal(row[5]), cost_basis=Decimal(row[6]),
                    realized_pnl=Decimal(row[7]), provider=provider
                )
                for row in rows
            ]
    
    def get_position(self, token_id: str, provider: str = "polymarket") -> Optional[PaperPosition]:
        """Get a specific position."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, token_id, market_id, outcome, size, avg_price, cost_basis, realized_pnl "
                "FROM paper_positions WHERE token_id = ? AND provider = ?",
                (token_id, provider)
            ).fetchone()
            
            if row:
                return PaperPosition(
                    id=row[0], token_id=row[1], market_id=row[2], outcome=row[3],
                    size=Decimal(row[4]), avg_price=Decimal(row[5]), cost_basis=Decimal(row[6]),
                    realized_pnl=Decimal(row[7]), provider=provider
                )
            return None
    
    def get_trades(self, provider: str = "polymarket", limit: int = 100) -> List[PaperTrade]:
        """Get trade history."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, order_id, token_id, market_id, side, price, size, total, fee, executed_at "
                "FROM paper_trades WHERE provider = ? ORDER BY executed_at DESC LIMIT ?",
                (provider, limit)
            ).fetchall()
            
            return [
                PaperTrade(
                    id=row[0], order_id=row[1], token_id=row[2], market_id=row[3],
                    side=PaperOrderSide(row[4]), price=Decimal(row[5]), size=Decimal(row[6]),
                    total=Decimal(row[7]), fee=Decimal(row[8]), provider=provider
                )
                for row in rows
            ]

    def get_orders(self, provider: str = "polymarket", limit: int = 100) -> List[PaperOrder]:
        """Get order history."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, token_id, market_id, side, amount, price, status, filled_amount, avg_fill_price, created_at, updated_at "
                "FROM paper_orders WHERE provider = ? ORDER BY created_at DESC LIMIT ?",
                (provider, limit)
            ).fetchall()
            
            return [
                PaperOrder(
                    id=row[0], token_id=row[1], market_id=row[2], side=PaperOrderSide(row[3]),
                    amount=Decimal(row[4]), price=Decimal(row[5]) if row[5] else None,
                    status=PaperOrderStatus(row[6]), filled_amount=Decimal(row[7]),
                    avg_fill_price=Decimal(row[8]), provider=provider,
                    created_at=datetime.fromisoformat(row[9]) if isinstance(row[9], str) else row[9],
                    updated_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10]
                )
                for row in rows
            ]
    
    def reset(self, provider: str = "polymarket", initial_balance: Decimal = DEFAULT_INITIAL_BALANCE) -> None:
        """Reset paper trading state for a provider."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM paper_trades WHERE provider = ?", (provider,))
            conn.execute("DELETE FROM paper_positions WHERE provider = ?", (provider,))
            conn.execute("DELETE FROM paper_orders WHERE provider = ?", (provider,))
            conn.execute("DELETE FROM paper_wallets WHERE provider = ?", (provider,))
            
            # Create fresh wallet
            conn.execute(
                "INSERT INTO paper_wallets (provider, balance, initial_balance, total_deposited, total_withdrawn, realized_pnl) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (provider, str(initial_balance), str(initial_balance), str(initial_balance), "0", "0")
            )

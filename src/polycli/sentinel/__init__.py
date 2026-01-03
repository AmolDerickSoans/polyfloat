"""
Sentinel Agent - Watchful, conservative market monitoring.

The Sentinel continuously watches user-defined markets and detects when
pre-agreed conditions are met, producing risk-aware trade proposals.

It does NOT:
- Execute trades
- Autonomously size positions
- Optimize for PnL

Every proposal is surfaced for human approval.
"""

from polycli.sentinel.models import (
    TriggerType,
    TriggerCondition,
    WatchedMarket,
    SentinelConfig,
    MarketSnapshot,
    SentinelProposal,
    ProposalStatus,
    SentinelRiskSnapshot,
)
from polycli.sentinel.triggers import TriggerEvaluator
from polycli.sentinel.agent import SentinelAgent

__all__ = [
    # Models
    "TriggerType",
    "TriggerCondition",
    "WatchedMarket",
    "SentinelConfig",
    "MarketSnapshot",
    "SentinelProposal",
    "ProposalStatus",
    "SentinelRiskSnapshot",
    # Components
    "TriggerEvaluator",
    "SentinelAgent",
]

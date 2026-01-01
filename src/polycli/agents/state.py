from typing import TypedDict, Annotated, List, Dict, Any, Optional
from datetime import datetime
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentMetadata(TypedDict):
    """Metadata for agent execution tracking"""
    agent_id: str
    session_id: str
    version: str
    model: str
    start_time: float
    end_time: Optional[float]
    latency_ms: float
    confidence: float
    reasoning_trace: List[str]
    tool_calls: List[Dict[str, Any]]
    state_transitions: List[Dict[str, Any]]


class Task(TypedDict):
    """A task for an agent to execute"""
    task_id: str
    task_type: str
    description: str
    priority: str
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    status: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]]
    error_message: Optional[str]
    agent_id: Optional[str]
    latency_ms: Optional[float]


class AgentExecutionState(TypedDict):
    """State for agent execution"""
    current_task: Optional[Task]
    task_queue: List[Task]
    decision: Optional[Dict[str, Any]]
    reasoning_trace: List[str]
    intermediate_states: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]


class MarketState(TypedDict):
    """State for market data"""
    markets: Dict[str, Dict[str, Any]]
    orderbooks: Dict[str, Dict[str, Any]]
    tickers: Dict[str, Dict[str, Any]]
    watchlist: List[str]
    subscriptions: List[str]


class TradingState(TypedDict):
    """State for trading operations"""
    positions: List[Dict[str, Any]]
    orders: List[Dict[str, Any]]
    fills: List[Dict[str, Any]]
    pnl: Dict[str, float]
    exposure: Dict[str, float]


class RiskState(TypedDict):
    """State for risk management"""
    position_limits: Dict[str, float]
    exposure_limits: Dict[str, float]
    daily_loss_limit: float
    max_drawdown: float
    current_exposure: float
    daily_loss: float
    current_drawdown: float
    circuit_breaker_triggered: bool


class CoreState(TypedDict):
    """Core state shared across all agents"""
    messages: Annotated[List[BaseMessage], add_messages]
    timestamp: float
    session_id: str
    agent_id: str
    graph_id: str
    metadata: AgentMetadata


class RealtimeState(TypedDict):
    """State for real-time processing graph"""
    core: CoreState
    market: MarketState
    agent: AgentExecutionState


class ArbState(TypedDict):
    """State for arbitrage detection graph"""
    core: CoreState
    market: MarketState
    opportunities: List[Dict[str, Any]]
    matched_markets: List[Dict[str, Any]]


class DecisionState(TypedDict):
    """State for decision making graph"""
    core: CoreState
    market: MarketState
    trading: TradingState
    risk: RiskState
    agent: AgentExecutionState
    decisions: List[Dict[str, Any]]
    trade_plans: List[Dict[str, Any]]


class SupervisorState(TypedDict):
    """State for supervisor agent"""
    core: CoreState
    active_agents: List[str]
    agent_health: Dict[str, Dict[str, Any]]
    task_assignments: Dict[str, List[str]]
    pending_tasks: List[Task]


class AgentAlert(TypedDict):
    """Alert data structure"""
    alert_id: str
    timestamp: float
    severity: str
    category: str
    message: str
    source: str
    data: Optional[Dict[str, Any]]
    acknowledged: bool
    resolved: bool


class AlertState(TypedDict):
    """State for alert management"""
    alerts: List[AgentAlert]
    alert_rules: Dict[str, Dict[str, Any]]
    notification_channels: List[str]


# Legacy TradingState for backward compatibility
class LegacyTradingState(TypedDict):
    """Legacy state managed by LangGraph agents (deprecated)"""
    messages: Annotated[List[Any], add_messages]
    market_data: Dict[str, Any]
    positions: List[Dict[str, Any]]
    strategy: str
    risk_score: float
    last_action: str
    next_step: str
    arb_opportunities: List[Dict[str, Any]]

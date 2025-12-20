from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages

class TradingState(TypedDict):
    """State managed by the LangGraph agents"""
    messages: Annotated[List[Any], add_messages]
    market_data: Dict[str, Any]
    positions: List[Dict[str, Any]]
    strategy: str
    risk_score: float
    last_action: str
    next_step: str

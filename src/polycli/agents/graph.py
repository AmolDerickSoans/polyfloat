from langgraph.graph import StateGraph, END
from polycli.agents.state import TradingState
from polycli.agents.nodes import trader_node, risk_node

def create_trading_graph():
    """Create the agentic trading workflow"""
    workflow = StateGraph(TradingState)
    
    # Add nodes
    workflow.add_node("trader", trader_node)
    workflow.add_node("risk", risk_node)
    
    # Define edges
    workflow.set_entry_point("trader")
    workflow.add_edge("trader", "risk")
    workflow.add_edge("risk", END)
    
    return workflow.compile()

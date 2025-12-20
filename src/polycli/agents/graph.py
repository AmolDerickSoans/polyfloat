from langgraph.graph import StateGraph, END
from polycli.agents.state import TradingState
from polycli.agents.nodes import trader_node, risk_node, arb_observer_node, arb_planner_node

def create_trading_graph(mode: str = "default"):
    """Create the agentic trading workflow"""
    workflow = StateGraph(TradingState)
    
    if mode == "arb":
        workflow.add_node("arb_observer", arb_observer_node)
        workflow.add_node("arb_planner", arb_planner_node)
        
        workflow.set_entry_point("arb_observer")
        workflow.add_edge("arb_observer", "arb_planner")
        workflow.add_edge("arb_planner", END)
    else:
        # Add nodes
        workflow.add_node("trader", trader_node)
        workflow.add_node("risk", risk_node)
        
        # Define edges
        workflow.set_entry_point("trader")
        workflow.add_edge("trader", "risk")
        workflow.add_edge("risk", END)
    
    return workflow.compile()

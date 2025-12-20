from polycli.agents.state import TradingState
import random

async def trader_node(state: TradingState) -> TradingState:
    """Decide on trading actions based on market data"""
    price = state["market_data"].get("price", 0.5)
    
    # Simple logic for MVP demonstration
    if price < 0.6:
        action = "BUY"
    elif price > 0.7:
        action = "SELL"
    else:
        action = "HOLD"
        
    return {
        **state,
        "last_action": action,
        "messages": [f"Trader decided to {action} at price {price}"]
    }

async def risk_node(state: TradingState) -> TradingState:
    """Validate the decision against risk parameters"""
    risk_score = random.random()
    
    # If risk is too high, override action
    if risk_score > 0.9:
        return {
            **state,
            "risk_score": risk_score,
            "last_action": "HOLD",
            "messages": ["Risk too high! Overriding to HOLD."]
        }
        
    return {**state, "risk_score": risk_score}

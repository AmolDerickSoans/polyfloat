from polycli.agents.state import TradingState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import os

from polycli.providers.polymarket import PolyProvider
from polycli.providers.kalshi import KalshiProvider
from polycli.utils.matcher import match_markets
from polycli.utils.arbitrage import find_opportunities

async def arb_observer_node(state: TradingState) -> TradingState:
    """Scan for arbitrage opportunities and add to state"""
    poly = PolyProvider()
    kalshi = KalshiProvider()
    
    p_markets = await poly.get_markets(limit=30)
    k_markets = await kalshi.get_markets(limit=30)
    
    matches = match_markets(p_markets, k_markets)
    opps = find_opportunities(matches, min_edge=0.01)
    
    # Convert Pydantic models to dicts for state
    opp_dicts = [o.model_dump() for o in opps]
    
    return {
        **state,
        "arb_opportunities": opp_dicts,
        "messages": [f"ArbObserver found {len(opp_dicts)} opportunities."]
    }

async def arb_planner_node(state: TradingState) -> TradingState:
    """Evaluate arbs using Gemini and plan execution"""
    if not state.get("arb_opportunities"):
        return {**state, "last_action": "IDLE"}
        
    opps = state["arb_opportunities"]
    llm = ChatGoogleGenerativeAI(model="gemini-pro")
    
    prompt = f"""
    You are an Arb Planner. Evaluate these arbitrage opportunities:
    {opps}
    
    Pick the BEST one based on edge and provide a summary.
    If no opportunity is good (edge < 2%), respond with NO_ACTION.
    Otherwise respond with EXECUTE: [Market Name] | [Direction] | [Edge]
    """
    
    response = await llm.ainvoke([
        SystemMessage(content="You are a trading strategist."),
        HumanMessage(content=prompt)
    ])
    
    plan = response.content.strip()
    action = "PLAN_READY" if "EXECUTE" in plan else "IDLE"
    
    return {
        **state,
        "last_action": action,
        "messages": [f"ArbPlanner: {plan}"]
    }

async def trader_node(state: TradingState) -> TradingState:
    """Decide on trading actions based on market data using Gemini"""
    
    # Check for API key
    if not os.getenv("GOOGLE_API_KEY"):
        return {
            **state,
            "last_action": "ERROR",
            "messages": ["GOOGLE_API_KEY not found. Please set it in your environment."]
        }

    # Initialize Gemini
    llm = ChatGoogleGenerativeAI(model="gemini-pro")
    
    market_data = state["market_data"]
    strategy = state["strategy"]
    
    prompt = f"""
    You are an autonomous trading agent for prediction markets.
    
    Market Context:
    - Token: {market_data.get('token_id', 'UNKNOWN')}
    - Price: ${market_data.get('price', 0.0)}
    - Strategy: {strategy}
    
    Your goal is to decide whether to BUY, SELL, or HOLD based on the current price and strategy.
    
    If strategy is 'simple':
    - BUY if price < 0.60
    - SELL if price > 0.70
    - HOLD otherwise
    
    If strategy is 'aggressive':
    - BUY if price < 0.80
    - SELL if price > 0.90
    
    Respond with a SINGLE word: BUY, SELL, or HOLD.
    """
    
    try:
        response = await llm.ainvoke([
            SystemMessage(content="You are a strict trading engine. Output only the decision."),
            HumanMessage(content=prompt)
        ])
        action = response.content.strip().upper()
        
        # Fallback for unexpected LLM output
        if action not in ["BUY", "SELL", "HOLD"]:
            action = "HOLD"
            
    except Exception as e:
        return {
            **state,
            "last_action": "ERROR",
            "messages": [f"LLM Error: {str(e)}"]
        }

    return {
        **state,
        "last_action": action,
        "messages": [f"Gemini Trader decided to {action} based on price {market_data.get('price')}"]
    }

async def risk_node(state: TradingState) -> TradingState:
    """Validate the decision against risk parameters"""
    # Simple risk check (simulated)
    import random
    risk_score = random.random()
    
    if state["last_action"] == "ERROR":
         return {**state, "risk_score": 1.0}

    # If risk is too high, override action
    if risk_score > 0.9:
        return {
            **state,
            "risk_score": risk_score,
            "last_action": "HOLD",
            "messages": ["Risk too high! Overriding to HOLD."]
        }
        
    return {**state, "risk_score": risk_score}
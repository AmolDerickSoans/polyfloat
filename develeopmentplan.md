# PolyCLI Terminal: Master Agentic Development Plan

**Version:** 2.0 (December 20, 2025)  
**Objective:** Build a production-ready, agentic CLI/TUI terminal for prediction markets (Polymarket + Kalshi) with autonomous trading agents, real-time analytics, and portfolio management.

**Target Completion:** 8 weeks (MVP by February 14, 2026)

---

## Executive Summary

PolyCLI is a **power-user CLI/TUI terminal** that bridges the gap between web-based trading interfaces and professional trading infrastructure. Unlike competitors (Betmoar, Polymtrade), PolyCLI focuses on:

1. **Scriptability & Automation**: Full CLI with programmatic access
2. **Agentic Trading**: LangGraph-powered autonomous bots (market making, arbitrage, risk management)
3. **Cross-Platform Execution**: Unified Polymarket + Kalshi interface with intelligent order routing
4. **Advanced Analytics**: Backtesting, risk modeling, correlation analysis
5. **Local-First**: Terminal-based workflow, sub-200ms execution, no browser overhead

**Key Differentiation**: Only terminal with production-grade agentic harness for hands-off trading strategies.

---

## I. Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      PolyCLI Terminal                        │
├─────────────────┬─────────────────┬─────────────────────────┤
│  CLI Layer      │  TUI Layer      │  Agentic Harness        │
│  (Typer)        │  (Textual)      │  (LangGraph)            │
│                 │                 │                          │
│  - Commands     │  - Dashboard    │  - Observer Agent       │
│  - Scripts      │  - Orderbooks   │  - Trader Agent         │
│  - Automation   │  - Charts       │  - Risk Agent           │
│                 │  - Positions    │  - MM Agent             │
└─────────────────┴─────────────────┴─────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼───────┐  ┌────────▼──────────┐
│ Provider Layer │  │ Data Layer   │  │ State Management  │
│                │  │              │  │                    │
│ - PolyProvider │  │ - Redis      │  │ - LangGraph State │
│ - KalshiProvider│ │ - SQLite     │  │ - Checkpointer    │
│ - UnifiedAPI   │  │ - Pandas     │  │ - Session Store   │
└────────────────┘  └──────────────┘  └───────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼───────┐  ┌────────▼──────────┐
│ Polymarket API │  │ Kalshi API   │  │ External APIs     │
│ - CLOB         │  │ - Trading v2 │  │ - News/Sentiment  │
│ - Gamma        │  │ - WebSocket  │  │ - OpenAI/Anthropic│
│ - WebSocket*   │  │ - Orders     │  │ - Blockchain RPC  │
└────────────────┘  └──────────────┘  └───────────────────┘

*Note: py-clob-client lacks WebSocket support as of Jan 2025 (Issue #116)
      We'll implement custom WebSocket client using websockets==12.0
```

### Core Design Principles

1. **OpenBB-Inspired Architecture**: Modular provider system, extensible routers
2. **Async-First**: All I/O operations use asyncio for concurrent execution
3. **Type Safety**: Pydantic models for all data structures
4. **Stateful Agents**: LangGraph checkpointing for resumable workflows
5. **Fast Execution**: Redis caching, connection pooling, sub-200ms order placement

---

## II. Critical Repository Analysis

### A. OpenBB Platform (Foundation Architecture)

**Repo**: `github.com/OpenBB-finance/OpenBB`

**Key Files & Patterns**:

```
openbb_platform/
├── core/
│   ├── platform/
│   │   ├── providers/
│   │   │   └── fetcher.py          # TET Pattern (Transform-Extract-Transform)
│   │   ├── router.py               # FastAPI routing, command registration
│   │   └── obbject.py              # Standardized response wrapper
│   └── extensions.py               # Dynamic provider discovery
├── extensions/
│   ├── openbb_equity/
│   │   └── equity_router.py        # Nested routers (equity/price/historical)
│   └── openbb_provider_fmp/
│       └── models/equity.py        # Provider-specific data models
└── cli/
    ├── argparse_translator.py      # CLI generation from Pydantic models
    └── controllers/controller_factory.py  # Dynamic controller generation
```

**Adoption Strategy**:
- **Provider Abstraction**: Implement `BaseProvider` → `PolyProvider`, `KalshiProvider`
- **Fetcher Pattern**: Use TET (Transform query → Extract data → Transform to standard model)
- **CLI Auto-Generation**: Leverage Pydantic models to generate Typer commands
- **Extension System**: Plugin architecture for community providers (e.g., Manifold, PredictIt)

**Implementation**:
```python
# polycli/providers/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Dict

class MarketData(BaseModel):
    """Standardized market data model"""
    token_id: str
    title: str
    price: float
    volume_24h: float
    liquidity: float
    
class BaseProvider(ABC):
    """OpenBB-style provider interface"""
    
    @abstractmethod
    async def get_markets(self, **kwargs) -> List[MarketData]:
        """Fetch markets with standardized output"""
        pass
    
    @abstractmethod
    async def place_order(self, order: OrderArgs) -> OrderResponse:
        pass
```

---

### B. py-clob-client (Polymarket Integration)

**Repo**: `github.com/Polymarket/py-clob-client`

**Critical Insights**:

1. **Authentication Flow**:
```python
# py_clob_client/client.py:45-60
from py_clob_client.client import ClobClient
from eth_account import Account

# Two signature types:
# signature_type=0: EOA (MetaMask, hardware wallets)
# signature_type=1: Proxy wallets (Magic, email wallets)

client = ClobClient(
    host="https://clob.polymarket.com",
    key=private_key,                    # Signing key
    chain_id=137,                        # Polygon mainnet
    signature_type=1,                    # Proxy wallet
    funder=proxy_wallet_address          # Actual fund holder
)

# Derive API credentials (L2-specific)
client.set_api_creds(client.create_or_derive_api_creds())
```

2. **Order Placement**:
```python
# py_clob_client/order_builder/order_builder.py:100-150
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

mo = MarketOrderArgs(
    token_id="<token_id>",
    amount=25.0,                        # USDC amount
    side=BUY,                            # BUY or SELL
    order_type=OrderType.FOK             # FOK, GTC, GTD
)

signed_order = client.create_market_order(mo)
response = client.post_order(signed_order, OrderType.FOK)
```

3. **Missing WebSocket Support**:
   - **Issue #116** (Jan 28, 2025): No WebSocket implementation
   - **Workaround**: Implement custom WebSocket client using `websockets==12.0`
   - **CLOB WebSocket Endpoint**: `wss://ws-subscriptions-clob.polymarket.com/ws/` (undocumented, reverse-engineered)

**Implementation Plan**:
```python
# polycli/providers/polymarket/websocket.py
import asyncio
import websockets
import json
from typing import Callable

class PolymarketWebSocket:
    """Custom WebSocket client for Polymarket orderbook streams"""
    
    def __init__(self, url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/"):
        self.url = url
        self.subscriptions = {}
        
    async def subscribe_orderbook(self, token_id: str, callback: Callable):
        """Subscribe to orderbook updates"""
        async with websockets.connect(self.url) as ws:
            subscribe_msg = {
                "type": "subscribe",
                "channel": f"orderbook:{token_id}"
            }
            await ws.send(json.dumps(subscribe_msg))
            
            async for message in ws:
                data = json.loads(message)
                await callback(data)
```

---

### C. Textual TUI Framework

**Repo**: `github.com/Textualize/textual`

**Key Files & Patterns**:

```
textual/
├── app.py                  # App base class, event loop
├── widgets/
│   ├── data_table.py       # Table widget (for orderbooks)
│   ├── chart.py            # Plotting widget
│   ├── input.py            # Input fields
│   └── footer.py           # Status bar
├── reactive.py             # Reactive attributes (@reactive decorator)
├── work.py                 # @work decorator for async tasks
└── css/
    └── parse.py            # CSS parser for styling
```

**Critical Patterns**:

1. **Reactive Updates**:
```python
# textual/reactive.py:50-100
from textual.reactive import reactive
from textual.widget import Widget

class PriceWidget(Widget):
    price = reactive(0.0)           # Auto-updates UI on change
    
    def watch_price(self, old: float, new: float):
        """Called automatically when price changes"""
        self.query_one(Label).update(f"${new:.2f}")
```

2. **Async Workers** (for WebSocket integration):
```python
# textual/work.py:120-150
from textual import work
from textual.app import App

class DashboardApp(App):
    @work(exclusive=True)           # Only one instance at a time
    async def stream_orderbook(self, token_id: str):
        """Background task for WebSocket streaming"""
        async for update in polymarket_ws.subscribe(token_id):
            self.price = update['price']  # Triggers reactive update
```

3. **DataTable for Orderbooks**:
```python
# examples/data_table.py:1-50
from textual.widgets import DataTable

class OrderbookWidget(Widget):
    def compose(self):
        yield DataTable()
        
    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("Price", "Size", "Total")
        table.add_rows([
            ("0.65", "100", "65.00"),
            ("0.64", "250", "160.00"),
        ])
        
    @work(interval=1.0)             # Update every second
    async def update_orderbook(self):
        data = await polymarket.get_orderbook(self.token_id)
        self.query_one(DataTable).clear()
        self.query_one(DataTable).add_rows(data)
```

**PolyCLI TUI Layout**:
```
┌────────────────────────────────────────────────────────────┐
│ PolyCLI Terminal                    [Q]uit [H]elp [S]ettings│
├─────────────────┬──────────────────────────────────────────┤
│ Markets         │ TRUMP24 - Will Trump Win 2024?           │
│ ├─ Politics     │ ┌──────────────────────────────────────┐ │
│ │  ├─ TRUMP24   │ │ Price: $0.65 ▲ 2.3%                  │ │
│ │  └─ SENATE-R  │ │ Volume: $1.2M | Liquidity: $450K     │ │
│ ├─ Sports       │ └──────────────────────────────────────┘ │
│ └─ Crypto       │ ┌─ Orderbook ──────┬─ Positions ───────┐│
│                 │ │ BID    SIZE TOTAL │ Token    P&L     ││
│ Positions (3)   │ │ 0.65   100  65   │ TRUMP24  +$45.00 ││
│ ├─ TRUMP24 +$45 │ │ 0.64   250  160  │ BIDEN24  -$12.50 ││
│ ├─ BIDEN24 -$12 │ │                  │                  ││
│ └─ BTC100K +$8  │ │ ASK    SIZE TOTAL │ Total:   +$40.50 ││
│                 │ │ 0.66   150  99   │                  ││
│ Agents (2)      │ │ 0.67   200  134  │                  ││
│ ├─ MM Bot ●     │ └──────────────────┴──────────────────┘│
│ └─ Arb Bot ●    │                                          │
├─────────────────┴──────────────────────────────────────────┤
│ > poly buy TRUMP24 100 @0.65                                │
└────────────────────────────────────────────────────────────┘
```

---

### D. LangGraph (Agentic Orchestration)

**Repo**: `github.com/langchain-ai/langgraph`

**Key Concepts**:

1. **State Management**:
```python
# State is a TypedDict that flows through graph nodes
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class TradingState(TypedDict):
    messages: Annotated[list, add_messages]      # Chat history with LLM
    market_data: dict                             # Current orderbook
    positions: list                               # Open positions
    strategy: str                                 # Active strategy
    risk_score: float                             # Risk assessment
    last_action: str                              # Last executed action
```

2. **Graph Architecture**:
```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

# Define nodes (agents)
workflow = StateGraph(TradingState)

workflow.add_node("observe", observe_markets)       # Pull market data
workflow.add_node("analyze", llm_analyze)            # LLM strategizing
workflow.add_node("execute", place_orders)           # Order placement
workflow.add_node("risk_check", assess_risk)         # Risk validation

# Define edges (transitions)
workflow.add_edge("observe", "analyze")
workflow.add_conditional_edges(
    "analyze",
    route_decision,
    {
        "trade": "execute",
        "hold": "observe",
        "exit": END
    }
)
workflow.add_edge("execute", "risk_check")
workflow.add_edge("risk_check", "observe")          # Loop back

# Enable checkpointing for persistence
checkpointer = SqliteSaver.from_conn_string("trading_state.db")
app = workflow.compile(checkpointer=checkpointer)
```

3. **Agent Implementation**:
```python
# polycli/agents/trader_agent.py
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

async def llm_analyze(state: TradingState) -> TradingState:
    """Trader agent: Analyzes market and decides action"""
    llm = ChatAnthropic(model="claude-sonnet-4-20250514")
    
    prompt = f"""
    Current market data:
    - Token: {state['market_data']['token_id']}
    - Price: ${state['market_data']['price']}
    - Volume: ${state['market_data']['volume_24h']}
    - Your position: {state['positions']}
    
    Strategy: {state['strategy']}
    Risk tolerance: {state['risk_score']}
    
    Decide: Should we BUY, SELL, or HOLD? Explain reasoning.
    Respond in JSON: {{"action": "BUY|SELL|HOLD", "amount": 100, "reason": "..."}}
    """
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    decision = json.loads(response.content)
    
    return {
        **state,
        "last_action": decision["action"],
        "messages": state["messages"] + [response]
    }
```

4. **Multi-Agent Coordination**:
```python
# polycli/agents/multi_agent_system.py

class AgentRouter:
    """Routes tasks to specialized agents"""
    
    agents = {
        "trader": TraderAgent(),      # Executes trades
        "risk": RiskAgent(),           # Validates risk
        "mm": MarketMakerAgent(),      # Quotes markets
        "arb": ArbitrageAgent()        # Finds arbitrage
    }
    
    async def route(self, state: TradingState) -> str:
        """Decide which agent to invoke next"""
        if state["risk_score"] > 0.8:
            return "risk"                # Risk too high, pause
        elif state["strategy"] == "market_making":
            return "mm"
        elif state["strategy"] == "arbitrage":
            return "arb"
        else:
            return "trader"

workflow.add_conditional_edges(
    "analyze",
    AgentRouter().route,
    {
        "trader": "execute_trade",
        "risk": "pause_trading",
        "mm": "update_quotes",
        "arb": "execute_arbitrage"
    }
)
```

---

## III. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Objective**: Core architecture, provider abstraction, basic CLI

**Tasks**:
1. **Project Setup**
   - Initialize monorepo: `polycli/` (src), `tests/`, `docs/`
   - Dependencies: `pyproject.toml` with Poetry
   - Pre-commit hooks: black, mypy, pytest
   
2. **Provider Layer**
   - Implement `BaseProvider` interface (OpenBB-style)
   - `PolyProvider`: Wrap py-clob-client
   - `KalshiProvider`: Integrate kalshi-python
   - Unit tests: 80% coverage

3. **CLI Foundation**
   - Typer-based CLI: `poly markets list`, `poly markets search <query>`
   - Configuration: `~/.polycli/config.yaml`
   - Logging: structlog with console output

**Deliverables**:
- ✅ `poly --version` works
- ✅ `poly markets list --provider polymarket` fetches 10 markets
- ✅ Unit tests pass
- ✅ Git tag: `v0.1-foundation`

**Success Criteria**:
- [ ] 100% provider interface coverage
- [ ] <500ms API response time
- [ ] CLI documentation generated

---

### Phase 2: TUI & Real-Time Data (Weeks 3-4)

**Objective**: Textual dashboard with live orderbook updates

**Tasks**:
1. **WebSocket Implementation**
   - Custom Polymarket WebSocket client (Issue #116 workaround)
   - Kalshi WebSocket integration
   - Redis pub/sub for cross-component streaming

2. **TUI Development**
   - Dashboard layout (see ASCII mockup above)
   - OrderbookWidget with auto-refresh (@work decorator)
   - PositionsWidget with P&L calculations
   - Market search/filter

3. **Arbitrage Scanner**
   - Logic: Detect price deltas >3% between Polymarket/Kalshi
   - CLI: `poly arb scan --min-edge 3 --notify`
   - TUI: Live arbitrage opportunities panel

**Deliverables**:
- ✅ TUI renders live orderbook data (<200ms latency)
- ✅ `poly dashboard` launches Textual app
- ✅ Arbitrage scanner finds real opportunities
- ✅ Git tag: `v0.2-tui`

**Success Criteria**:
- [ ] <200ms WebSocket latency
- [ ] TUI handles 10+ concurrent market subscriptions
- [ ] Arb scanner detects >5 opportunities/day (testnet)

---

### Phase 3: Agentic Harness (Weeks 5-6)

**Objective**: LangGraph-powered autonomous trading bots

**Tasks**:
1. **Agent Graph Architecture**
   - `TradingState` model with checkpointing
   - Observer node: WebSocket → state updates
   - Trader node: LLM planning + execution
   - Risk node: Kelly Criterion, drawdown limits

2. **Bot Deployment**
   - Config: YAML-based strategies (`strategies/market_maker.yaml`)
   - CLI: `poly bot deploy <strategy.yaml>`
   - Monitoring: `poly bot status`, `poly bot logs <bot_id>`

3. **Backtesting Engine**
   - Historical data replay (Pandas)
   - Slippage simulation
   - Sharpe ratio, max drawdown metrics

**Deliverables**:
- ✅ Bot executes paper trade autonomously
- ✅ Risk agent prevents >10% drawdown
- ✅ Backtesting: `poly backtest my_strategy.py --period 30d`
- ✅ Git tag: `v0.3-agents`

**Success Criteria**:
- [ ] Agent survives 24h live paper trading
- [ ] Risk check halts on threshold breach
- [ ] Backtest completes <5min for 30d data

---

### Phase 4: Production Polish (Weeks 7-8)

**Objective**: Pro features, documentation, community launch

**Tasks**:
1. **Pro Tier Features**
   - API key gating: Unlimited calls for Pro users
   - Sentiment integration: Twitter/Reddit feeds
   - Advanced analytics: Correlation matrix, VaR

2. **Documentation**
   - MkDocs site: `docs.polycli.dev`
   - Video tutorials: Basic usage, bot deployment
   - API reference: Auto-generated from docstrings

3. **Community Launch**
   - GitHub: MIT license, CONTRIBUTING.md
   - Discord: Support server
   - PyPI: `pip install polycli`

**Deliverables**:
- ✅ 50 beta users onboarded
- ✅ Documentation site live
- ✅ PyPI package published
- ✅ Git tag: `v1.0-mvp`

**Success Criteria**:
- [ ] 20% beta user retention (week 2)
- [ ] >100 GitHub stars (30 days)
- [ ] Avg session time >15min

---

## IV. Technical Specifications

### A. Configuration System

**File**: `~/.polycli/config.yaml`

```yaml
# PolyCLI Configuration
version: "1.0"

# Authentication
auth:
  polymarket:
    private_key: "${POLY_PRIVATE_KEY}"
    funder_address: "0x..."
    signature_type: 1
  kalshi:
    api_key: "${KALSHI_API_KEY}"
    api_secret: "${KALSHI_SECRET}"

# Providers
providers:
  default: "polymarket"
  priority: ["polymarket", "kalshi"]

# Agents
agents:
  max_concurrent: 5
  checkpoint_interval: 300  # seconds

# Risk Management
risk:
  max_position_size: 1000  # USDC
  max_drawdown: 0.10       # 10%
  max_leverage: 1.0

# TUI Settings
tui:
  refresh_rate: 1.0        # seconds
  theme: "dark"
  show_orderbook_depth: 10
```

---

### B. Database Schema

**SQLite**: `~/.polycli/data.db`

```sql
-- Markets cache
CREATE TABLE markets (
    token_id TEXT PRIMARY KEY,
    title TEXT,
    provider TEXT,
    price REAL,
    volume_24h REAL,
    liquidity REAL,
    updated_at TIMESTAMP
);

-- Positions
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT,
    side TEXT,  -- 'BUY' or 'SELL'
    size REAL,
    entry_price REAL,
    current_price REAL,
    pnl REAL,
    opened_at TIMESTAMP,
    closed_at TIMESTAMP
);

-- Agent checkpoints (LangGraph)
CREATE TABLE agent_state (
    checkpoint_id TEXT PRIMARY KEY,
    agent_id TEXT,
    state_json TEXT,  -- JSON blob of TradingState
    created_at TIMESTAMP
);

-- Backtesting results
CREATE TABLE backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT,
    start_date DATE,
    end_date DATE,
    sharpe_ratio REAL,
    max_drawdown REAL,
    total_return REAL,
    trades INTEGER,
    results_json TEXT,  -- Detailed trade log
    created_at TIMESTAMP
);
```

---

### C. Provider Interface Specification

```python
# polycli/providers/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    FOK = "FOK"  # Fill or Kill
    GTC = "GTC"  # Good Till Cancel

class MarketData(BaseModel):
    token_id: str
    title: str
    description: Optional[str]
    price: float
    volume_24h: float
    liquidity: float
    end_date: Optional[str]
    provider: str

class OrderArgs(BaseModel):
    token_id: str
    side: OrderSide
    amount: float
    price: Optional[float] = None
    order_type: OrderType = OrderType.MARKET

class OrderResponse(BaseModel):
    order_id: str
    status: str
    filled_amount: float
    avg_price: float

class BaseProvider(ABC):
    """Standard interface for prediction market providers"""
    
    @abstractmethod
    async def get_markets(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[MarketData]:
        """Fetch available markets"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, token_id: str) -> dict:
        """Get orderbook for specific market"""
        pass
    
    @abstractmethod
    async def place_order(self, order: OrderArgs) -> OrderResponse:
        """Place an order"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[dict]:
        """Get user's open positions"""
        pass
```

---

## V. Documentation Structure

### A. File Organization

```
docs/
├── index.md                    # Landing page
├── getting-started/
│   ├── installation.md
│   ├── configuration.md
│   └── first-trade.md
├── user-guide/
│   ├── cli-commands.md
│   ├── tui-navigation.md
│   ├── risk-management.md
│   └── backtesting.md
├── agents/
│   ├── overview.md
│   ├── creating-strategies.md
│   ├── deploying-bots.md
│   └── monitoring.md
├── api-reference/
│   ├── providers.md
│   ├── state-models.md
│   └── utilities.md
└── contributing/
    ├── development-setup.md
    ├── architecture.md
    └── testing.md
```

---

## VI. Testing Strategy

### A. Unit Tests (80% Coverage)

```python
# tests/test_providers.py
import pytest
from polycli.providers.polymarket import PolyProvider

@pytest.mark.asyncio
async def test_poly_provider_get_markets():
    provider = PolyProvider(api_key="test")
    markets = await provider.get_markets(limit=10)
    assert len(markets) == 10
    assert all(m.provider == "polymarket" for m in markets)

@pytest.mark.asyncio
async def test_order_placement():
    provider = PolyProvider(api_key="test")
    order = OrderArgs(
        token_id="test_token",
        side=OrderSide.BUY,
        amount=10.0
    )
    response = await provider.place_order(order)
    assert response.status == "filled"
```

### B. Integration Tests

```python
# tests/test_integration.py
@pytest.mark.integration
async def test_cross_provider_arbitrage():
    poly = PolyProvider()
    kalshi = KalshiProvider()
    
    # Find same market on both platforms
    poly_market = await poly.get_markets(search="TRUMP24")
    kalshi_market = await kalshi.get_markets(search="TRUMP24")
    
    # Calculate arbitrage opportunity
    edge = abs(poly_market[0].price - kalshi_market[0].price)
    assert edge < 0.10  # Arbitrage rare in efficient markets
```

### C. E2E Tests (TUI)

```python
# tests/test_tui.py
from textual.testing import App

async def test_dashboard_renders():
    app = DashboardApp()
    async with app.run_test() as pilot:
        await pilot.press("m")  # Open markets menu
        assert app.query_one(MarketsPanel).is_visible
        
        await pilot.press("p")  # Open positions
        assert app.query_one(PositionsPanel).is_visible
```

---

## VII. Deployment & Operations

### A. PyPI Package Structure

```
polycli/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── polycli/
│       ├── __init__.py
│       ├── cli.py              # Typer entry point
│       ├── tui.py              # Textual app
│       ├── providers/
│       ├── agents/
│       └── utils/
└── tests/
```

**pyproject.toml**:

```toml
[tool.poetry]
name = "polycli"
version = "1.0.0"
description = "Agentic CLI/TUI terminal for Polymarket and Kalshi prediction markets"
authors = ["PolyCLI Team"]
license = "MIT"
readme = "README.md"
homepage = "https://docs.polycli.dev"
repository = "https://github.com/polycli/polycli"
keywords = ["polymarket", "kalshi", "prediction-markets", "trading", "cli", "langgraph"]

[tool.poetry.dependencies]
python = "^3.11"
# CLI/TUI
typer = "^0.12.0"
rich = "^13.7.0"
textual = "^0.50.1"
# APIs
py-clob-client = "^0.24.0"
kalshi-python = "^1.0.0"
httpx = "^0.27.0"
websockets = "^12.0"
# Agents
langgraph = "^0.2.28"
langchain-anthropic = "^0.3.0"
langchain-core = "^0.3.0"
# Data
pydantic = "^2.10.0"
pandas = "^2.2.0"
numpy = "^2.0.0"
scipy = "^1.14.0"
# Storage
redis = {extras = ["hiredis"], version = "^5.1.0"}
sqlalchemy = "^2.0.0"
# Utils
python-dotenv = "^1.0.0"
structlog = "^24.4.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3.0"
pytest-asyncio = "^0.24.0"
pytest-cov = "^6.0.0"
pytest-mock = "^3.14.0"
black = "^24.10.0"
mypy = "^1.13.0"
ruff = "^0.8.0"
pre-commit = "^4.0.0"

[tool.poetry.scripts]
poly = "polycli.cli:app"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]
```

### B. CI/CD Pipeline

**GitHub Actions** (`.github/workflows/test.yml`):

```yaml
name: Test & Deploy

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install Poetry
        run: |
          curl -sSL https://install.python-poetry.org | python3 -
          echo "$HOME/.local/bin" >> $GITHUB_PATH
      
      - name: Install dependencies
        run: poetry install
      
      - name: Run tests
        run: |
          poetry run pytest --cov=polycli --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
  
  deploy-docs:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    needs: test
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install MkDocs
        run: pip install mkdocs mkdocs-material
      
      - name: Deploy docs
        run: mkdocs gh-deploy --force
  
  publish-pypi:
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    needs: test
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install Poetry
        run: curl -sSL https://install.python-poetry.org | python3 -
      
      - name: Build package
        run: poetry build
      
      - name: Publish to PyPI
        env:
          POETRY_PYPI_TOKEN_PYPI: ${{ secrets.PYPI_TOKEN }}
        run: poetry publish
```

---

## VIII. Open Source Strategy

### A. Repository Structure

```
polycli/
├── .github/
│   ├── workflows/
│   │   ├── test.yml
│   │   └── release.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── src/polycli/
├── tests/
├── docs/
├── examples/
│   ├── strategies/
│   │   ├── market_maker.yaml
│   │   ├── simple_momentum.py
│   │   └── arbitrage.yaml
│   └── notebooks/
│       └── backtesting_tutorial.ipynb
├── LICENSE (MIT)
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── CHANGELOG.md
└── pyproject.toml
```

### B. Community Guidelines

**CONTRIBUTING.md**:

```markdown
# Contributing to PolyCLI

## Development Setup
1. Fork the repository
2. Clone: `git clone https://github.com/yourusername/polycli`
3. Install: `poetry install`
4. Create branch: `git checkout -b feature/your-feature`

## Code Standards
- Run `pre-commit install`
- Tests required for all features
- Follow Google Python Style Guide
- Type hints mandatory

## Pull Request Process
1. Update docs if needed
2. Add tests (maintain 80%+ coverage)
3. Run `poetry run pytest`
4. Update CHANGELOG.md

## Community
- Discord: https://discord.gg/polycli
- Twitter: @polycli_dev
```

---

## IX. Pricing & Business Model

### Free Tier (Open Source)
- ✅ Full CLI access
- ✅ Basic TUI dashboard
- ✅ Paper trading unlimited
- ✅ 100 API calls/day
- ✅ Community support (Discord)

### Pro Tier ($29/month)
- ✅ Unlimited API calls
- ✅ Advanced agents (MM, Arbitrage)
- ✅ Backtesting engine
- ✅ Real-time alerts (Discord/Slack webhooks)
- ✅ Priority support

### Enterprise ($199/month)
- ✅ Multi-account management
- ✅ Custom strategies (consulting)
- ✅ White-label option
- ✅ SLA guarantees
- ✅ Dedicated support channel

**Revenue Goal**: 100 Pro users × $29 = $2,900/month (covers API costs + hosting)

---

## X. Risk Mitigation Summary

| Risk | Likelihood | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| WebSocket gap | High | High | Custom implementation | Core Dev |
| LLM hallucinations | Medium | High | Confidence thresholds, paper trading | AI Engineer |
| API rate limits | High | Medium | Redis caching, batching | Backend Dev |
| Key security | Low | Critical | Encrypted storage, hardware wallet support | Security Lead |
| Beta churn | High | Medium | Rapid iteration, feedback loops | Growth Lead |
| Competitor moats | Medium | Medium | Speed to market, open source | Product Manager |

---

## XI. Success Criteria

### MVP Launch (v1.0)
- [ ] 50 beta users onboarded
- [ ] 20% retention at Week 2
- [ ] >100 GitHub stars (30 days)
- [ ] Avg session time >15 minutes
- [ ] <5 P0 bugs in production
- [ ] 80%+ unit test coverage

### 6-Month Goals (v2.0)
- [ ] 500 active users (50 Pro tier)
- [ ] 5+ community-contributed strategies
- [ ] Featured on Polymarket blog
- [ ] Integration with 3+ markets (Poly, Kalshi, Manifold)
- [ ] <200ms P95 latency
- [ ] 1000+ GitHub stars

---

## XII. Post-MVP Roadmap

### Q2 2026
- Voice trading integration (NOYA-style)
- Mobile companion app (React Native)
- Strategy marketplace (buy/sell strategies)
- Advanced charting (TradingView integration)

### Q3 2026
- Multi-account management for funds
- Fiat on-ramp (Stripe integration)
- Hardware wallet support (Ledger)
- More providers: Manifold, PredictIt, Azuro

### Q4 2026
- White-label enterprise option
- API for third-party developers
- AI-powered market analysis (auto-generation of LLM prompts)

---

## XIII. Team Allocation

| Role | Weeks 1-2 | Weeks 3-4 | Weeks 5-6 | Weeks 7-8 |
|------|-----------|-----------|-----------|-----------|
| Core Dev | Foundation | CLI polish | Bot mgmt | PyPI publish |
| AI Engineer | - | - | Agents | LLM tuning |
| Quant Dev | - | Arb scanner | MM/Risk | Analytics |
| Frontend Dev | - | TUI | - | - |
| Backend Dev | - | WebSocket | Deployment | Infra |
| Data Engineer | - | - | Backtesting | Sentiment |
| Tech Writer | - | - | - | Docs |
| Dev Bot (AI) | Templates | Layout gen | Graph init | Doc gen |

**Total**: ~315 person-hours over 8 weeks

---

## Conclusion

This master plan provides a **comprehensive, executable roadmap** for building PolyCLI from zero to production in 8 weeks. Key success factors:

1. ✅ **Modular Architecture**: OpenBB-inspired design for extensibility
2. ✅ **Agentic Core**: LangGraph-powered autonomous trading
3. ✅ **Clear Milestones**: 4 phases with testable checkpoints
4. ✅ **Risk Management**: Comprehensive risk register with mitigation
5. ✅ **Community-First**: Open source with Pro tier upgrades

**Next Action**: Begin Day 1 setup (Project initialization) → See Quick-Start Guide

---

**Document Maintenance**: Update weekly during Friday standups  
**Feedback**: Submit issues to GitHub or Discord #dev-planning
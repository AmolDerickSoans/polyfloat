# Plan: Core Trading & Real-time Monitoring Foundation

## Phase 1: Unified Market Models & Base Providers [checkpoint: 74209a5]
Establish the data structures and base communication layers.

- [x] Task: Define standardized models for `Market`, `OrderBook`, `Trade`, and `Position` in `models.py` 51e3b34
    - [x] Task: Write tests for model validation and serialization
    - [x] Task: Implement models using Pydantic
- [x] Task: Enhance Base Provider interface with unified methods for trading and data ce0f5ca
    - [x] Task: Write tests for the base provider interface
    - [x] Task: Refactor `base.py` to include abstract methods for all core operations
- [x] Task: Conductor - User Manual Verification 'Phase 1: Unified Market Models & Base Providers' (Protocol in workflow.md)

## Phase 2: Polymarket Integration Refinement [checkpoint: c2866db]
Complete the trading and real-time data implementation for Polymarket.

- [x] Task: Implement comprehensive trading methods in `PolymarketProvider` 500f971
    - [x] Task: Write tests for Polymarket order placement and cancellation (using mocks)
    - [x] Task: Implement `create_order`, `cancel_order`, and `get_orders` in `polymarket.py`
- [x] Task: Robust Polymarket WebSocket implementation 41b1105
    - [x] Task: Write tests for WebSocket message parsing and reconnection logic
    - [x] Task: Refine `polymarket_ws.py` for real-time orderbook and trade updates
- [x] Task: Conductor - User Manual Verification 'Phase 2: Polymarket Integration Refinement' (Protocol in workflow.md)

## Phase 3: Kalshi Integration Refinement [checkpoint: b9ef329]
Complete the trading and real-time data implementation for Kalshi.

- [~] Task: Implement comprehensive trading methods in `KalshiProvider`
    - [ ] Task: Write tests for Kalshi order placement and cancellation (using mocks)
    - [ ] Task: Implement `create_order`, `cancel_order`, and `get_orders` in `kalshi.py`
- [x] Task: Robust Kalshi WebSocket implementation dc0db22
    - [x] Task: Write tests for Kalshi WebSocket message parsing and reconnection logic
    - [x] Task: Refine `kalshi_ws.py` for real-time orderbook and trade updates
- [x] Task: Conductor - User Manual Verification 'Phase 3: Kalshi Integration Refinement' (Protocol in workflow.md)

## Phase 4: Integration & History
Finalize history retrieval and cross-market consistency.

- [ ] Task: Implement unified trade and fill history retrieval
    - [ ] Task: Write tests for history aggregation across providers
    - [ ] Task: Implement `get_history` in providers and unified entry point
- [ ] Task: Final verification of real-time data consistency
    - [ ] Task: Write integration tests verifying data flow from WS to unified models
    - [ ] Task: Implement monitoring hooks for data latency and health
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Integration & History' (Protocol in workflow.md)

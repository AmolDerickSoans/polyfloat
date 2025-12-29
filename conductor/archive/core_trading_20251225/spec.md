# Spec: Core Trading & Real-time Monitoring Foundation

## Overview
This track focuses on establishing the core data ingestion and execution engine for PolyCLI. It aims to provide a stable, unified interface for real-time market data (order books, tickertapes) and order management (placing, canceling, history) across both Polymarket and Kalshi.

## Goals
- **Unified Market Interface:** Abstract the differences between Polymarket and Kalshi APIs into a consistent internal model.
- **Reliable WebSocket Streams:** Implement resilient WebSocket clients for real-time data with auto-reconnect and health monitoring.
- **Atomic Order Operations:** Ensure order placement and cancellation are robust and provide clear feedback.
- **Comprehensive Data Retrieval:** Implement full history retrieval for trades and positions.

## Core Components
1. **Provider Layer (`src/polycli/providers/`):**
    - Enhanced `PolymarketProvider` and `KalshiProvider`.
    - WebSocket managers for each platform.
2. **Models (`src/polycli/models.py`):**
    - Standardized `Order`, `Trade`, `Book`, and `Position` models.
3. **Internal CLI/TUI Bridge:**
    - Unified methods for fetching data that the TUI and future agents will consume.

## Acceptance Criteria
- [ ] Successful real-time streaming of order books for any given market on both platforms.
- [ ] Tickertape implementation showing live trades for selected markets.
- [ ] Ability to place Limit and Market orders (where supported) via the provider interface.
- [ ] Reliable retrieval of open orders and historical fills.
- [ ] Unit test coverage > 80% for all new/modified provider logic.

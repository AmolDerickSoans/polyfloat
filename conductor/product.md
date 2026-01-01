# Initial Concept
Agentic CLI/TUI terminal for prediction markets (Polymarket + Kalshi).

## Target Users
- **Professional Arbitrageurs:** Traders seeking cross-platform price discrepancies between Polymarket and Kalshi.
- **Retail Terminal Users:** Participants who prefer a fast, keyboard-centric terminal interface over web UIs.
- **Agent Developers:** Engineers building and deploying autonomous trading agents using LLMs and LangGraph.

## Core Goals
- **Full Trading Execution:** Enable users to place orders, manage positions, and view trade history for both Polymarket and Kalshi.
- **Live Market Monitoring:** Provide real-time data visualization including order books, tickertapes, and sentiment analysis via a TUI dashboard.
- **Agent Framework:** Build a robust, scalable infrastructure for deploying and monitoring autonomous trading agents.

## Key Features
- **Unified Market Interface:** A single CLI/TUI to interact with multiple prediction markets simultaneously.
- **Flexible Configuration:** Support for both interactive setup and CLI flags for credential management, enabling easy automation and ephemeral usage.
- **Advanced Agent Capabilities:**
    - **Low-Latency Streams:** High-frequency WebSocket integration for rapid agent response.
    - **Safety & Risk Management:** Integrated "Safety Rails" to enforce trade limits and exposure caps.
    - **Multi-Agent Orchestration:** Support for complex LangGraph workflows (e.g., separate researcher and trader agents).
- **Extensible Architecture:** Modular provider system to easily add new markets or data sources.

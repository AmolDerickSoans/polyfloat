# PolyCLI: Technology Stack

## Core Language & Runtime
- **Python 3.11+:** The primary language for all application logic, agents, and data processing.

## UI/UX Frameworks
- **Textual:** Used for building the rich, multi-pane TUI dashboard.
- **Typer & Click:** Used for the command-line interface and command parsing.
- **Rich:** For high-quality terminal formatting, tables, and color-coding.

## Market Connectivity
- **Polymarket:** Integrated via `py-clob-client` and direct WebSocket connections for order books.
- **Kalshi:** Integrated via `kalshi-python` SDK and direct WebSocket integrations.
- **httpx & websockets:** For custom API interactions and high-frequency data ingestion.

## Agent Orchestration
- **LangGraph:** To define complex agent workflows and state management.
- **LangChain:** For LLM interaction patterns and tool-calling.
- **Google Gemini:** The primary LLM provider for agent reasoning and market analysis.

## Data Management & Utilities
- **Pydantic:** For robust data validation and configuration management.
- **Pandas & NumPy:** For market data analysis and signal processing.
- **Redis:** Used as a high-speed cache for real-time market data and inter-process communication.
- **SQLAlchemy:** For persistent storage of trade history and agent logs.

## Quality Assurance & Tooling
- **Pytest:** The primary testing framework.
- **Ruff:** For extremely fast linting and code formatting.
- **Mypy:** For static type checking to ensure codebase reliability.
- **Poetry:** For dependency management and packaging.

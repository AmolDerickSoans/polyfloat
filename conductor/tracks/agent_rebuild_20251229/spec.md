# Specification: Agent Architecture Rebuild (Reference Implementation)

## Overview
Rebuild the existing agent system to emulate the official Polymarket Agent framework (Creator, Trader, Executor) as documented in `docs/polymarketagent/`. The goal is to replace the current simplistic `SupervisorAgent` with the sophisticated, autonomous reasoning system defined in the reference codebase.

## Source Material
- **Reference Codebase:** `docs/polymarketagent/poly-market-agent-codebase.md`
- **Architecture Understanding:** `docs/polymarketagent/poly-market-agent-understanding.md`

## Functional Requirements

### 1. Core Agent Trio (Ported from Reference)
We will port the logic from the official agent into our codebase structure:
- **Executor Agent (`src/polycli/agents/executor.py`):**
    - Port logic from official `agents/application/executor.py`.
    - Capabilities: Central orchestrator, LLM interaction management, data chunking (`divide_list`, `retain_keys`), and RAG retrieval orchestration.
- **Trader Agent (`src/polycli/agents/trader.py`):**
    - Port logic from official `agents/application/trade.py`.
    - Capabilities: `one_best_trade` loop, market filtering, and superforecasting.
    - **Constraint:** Must use our new `BaseProvider` to support both Kalshi and Polymarket, replacing the hardcoded `polymarket-py` calls in the reference.
- **Creator Agent (`src/polycli/agents/creator.py`):**
    - Port logic from official `agents/application/creator.py`.
    - Capabilities: Identification of market creation opportunities.
    - **Constraint:** This logic will strictly disable itself if the active provider is not Polymarket.

### 2. Provider Adapter Layer
The official agent code relies on specific Polymarket API clients. We must abstract this:
- Define `BaseProvider` interface in `src/polycli/providers/base.py`.
- Refactor `PolyProvider` and `KalshiProvider` to implement this interface.
- Ensure the new Agents interact *only* with `BaseProvider`.

### 3. External Data & RAG Stack (Reference Implementation)
We will implement the exact data stack used in the reference:
- **Vector Database:** Port `agents/connectors/chroma.py` to `src/polycli/agents/tools/chroma.py`.
- **News Intelligence:** Port `agents/connectors/news.py` to `src/polycli/agents/tools/news.py` (NewsAPI).
- **Web Search:** Port `agents/connectors/search.py` to `src/polycli/agents/tools/search.py` (Tavily).

### 4. TUI Integration
- **Internal Monologue:** The TUI's Chat Panel must display the `Executor`'s step-by-step reasoning (e.g., "Fetching news...", "Ranking markets...").
- **Trade Proposals:** When `TraderAgent` identifies a trade, it must not execute immediately (unless in Full Auto). It must emit a structured event that the TUI renders as a "Trade Proposal Card" with an [Approve] button.
- **Mode Toggle:** TUI controls to switch between:
    - **Manual:** No auto-trading.
    - **Auto-Approval:** Agents propose; user clicks to execute.
    - **Full-Auto:** Agents execute silently within limits.

## Non-Functional Requirements
- **Safety Rails:** Strictly enforce existing trade limits and exposure caps.
- **Latency:** Asynchronous processing to ensure the TUI remains responsive during deep reasoning tasks.
- **Modularity:** High separation between agent logic and market connectivity.

## Acceptance Criteria
- [ ] `ExecutorAgent` logic matches the reference `executor.py` flow.
- [ ] Agents successfully retrieve news and perform RAG queries via ChromaDB.
- [ ] Trader agent can generate a "Superforecast" probability for a given event using the reference prompts.
- [ ] System identifies the correct provider and disables "Creator" logic for Kalshi.
- [ ] "Auto with Approval" mode correctly pauses for user input before execution.

## Out of Scope
- Integration of markets other than Polymarket and Kalshi.
- Automated wallet funding or withdrawal.
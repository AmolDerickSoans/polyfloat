# Implementation Plan: Agent Architecture Rebuild

This plan follows a TDD approach to rebuild the agent system, explicitly porting logic from the official Polymarket reference code (`docs/polymarketagent/`) while adapting it for the TUI and multi-provider support.

## Phase 1: Provider Abstraction & Base Refactoring [checkpoint: 87c47bd]
- [x] Task: Define `BaseProvider` abstract interface in `src/polycli/providers/base.py` (Methods: `get_markets`, `get_news`, `place_order`) 376c205
- [x] Task: Refactor `PolyProvider` to implement `BaseProvider` 9200013
- [x] Task: Refactor `KalshiProvider` to implement `BaseProvider` fc3baab
- [x] Task: Update `BaseAgent` in `src/polycli/agents/base.py` to use `BaseProvider` instead of direct provider calls 2e03fb6
- [x] Task: Conductor - User Manual Verification 'Phase 1: Provider Abstraction' (Protocol in workflow.md) 87c47bd

## Phase 2: External Data Stack (Porting Reference Connectors) [checkpoint: a19d14e]
- [x] Task: Port `agents/connectors/chroma.py` from reference to `src/polycli/agents/tools/chroma.py` (ChromaDB Integration) 7776fcd
- [x] Task: Port `agents/connectors/news.py` from reference to `src/polycli/agents/tools/news.py` (NewsAPI Integration) 644b7b8
- [x] Task: Port `agents/connectors/search.py` from reference to `src/polycli/agents/tools/search.py` (Tavily Integration) c6f62a5
- [x] Task: Conductor - User Manual Verification 'Phase 2: External Data Stack' (Protocol in workflow.md) a19d14e

## Phase 3: The Executor Agent (Porting Logic & RAG) [checkpoint: 78fe875]
- [x] Task: Implement `ExecutorAgent` in `src/polycli/agents/executor.py`, porting logic from reference `agents/application/executor.py` (Chunking, RAG orchestration) 5076369
- [x] Task: Port Prompts from reference `agents/application/prompts.py` to `src/polycli/agents/prompts.py` 5076369
- [x] Task: Integrate `ExecutorAgent` with `ChromaConnector` and `SearchConnector` 5076369
- [x] Task: Conductor - User Manual Verification 'Phase 3: Executor Agent' (Protocol in workflow.md) 78fe875

## Phase 4: Specialist Agents (Porting Trader & Creator) [checkpoint: 2a0f002]
- [x] Task: Implement `TraderAgent` in `src/polycli/agents/trader.py`, porting `one_best_trade` logic from reference `agents/application/trade.py` 7f65eeb
- [x] Task: Implement `CreatorAgent` in `src/polycli/agents/creator.py`, porting logic from reference `agents/application/creator.py` (with Kalshi disable check) 7f65eeb
- [x] Task: Refactor `SupervisorAgent` to become the specialized Orchestrator that manages this new Trio 7f65eeb
- [x] Task: Conductor - User Manual Verification 'Phase 4: Specialist Agents' (Protocol in workflow.md) 2a0f002

## Phase 5: TUI Integration & Autonomous Modes [checkpoint: 1c400d5]

- [x] Task: Update `AgentChatInterface` to render "Trade Proposal" events as UI cards e4d2913

- [x] Task: Implement the background autonomous loop in `DashboardApp` that ticks the `TraderAgent` e4d2913

- [x] Task: Add UI controls for switching between Manual, Auto-Approval, and Full-Auto modes e4d2913

- [x] Task: Conductor - User Manual Verification 'Phase 5: TUI Integration' (Protocol in workflow.md) 1c400d5





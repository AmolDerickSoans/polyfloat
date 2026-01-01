# Spec: Flatten Agents Directory Structure

## Overview
The current directory structure for agents in `polycli` contains a redundant nested directory: `src/polycli/agents/agents/`. This track aims to flatten this structure by moving all files from the nested `agents/` directory up one level into `src/polycli/agents/` and updating all import references throughout the codebase to ensure consistency and maintainability.

## Functional Requirements
- Move `alert_manager.py`, `market_observer.py`, and `supervisor.py` from `src/polycli/agents/agents/` to `src/polycli/agents/`.
- Remove the now-empty `src/polycli/agents/agents/` directory.
- Update all internal Python imports that reference `polycli.agents.agents` to `polycli.agents`.
- Ensure all agent-related logic (initialization, tool registration, etc.) remains fully functional after the move.

## Non-Functional Requirements
- **Thoroughness:** Every file in the repository must be checked for imports that need updating.
- **Maintainability:** The resulting structure should be idiomatic and easier to navigate.
- **Backward Compatibility:** As this is an internal refactor, external compatibility is not required, but all internal tests must pass.

## Acceptance Criteria
- [x] No `src/polycli/agents/agents/` directory exists.
- [x] Files `alert_manager.py`, `market_observer.py`, and `supervisor.py` exist in `src/polycli/agents/`.
- [x] A project-wide search for `polycli.agents.agents` returns zero results.
- [x] All existing tests in `tests/` pass successfully.
- [x] The TUI and CLI commands that utilize agents function as expected.

## Out of Scope
- Adding new agent features or fixing unrelated bugs.
- Moving TUI-specific files (e.g., `tui_agent_chat.py`) unless strictly necessary for the refactor.

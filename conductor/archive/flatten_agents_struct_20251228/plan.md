# Plan: Flatten Agents Directory Structure

This plan outlines the steps to flatten the redundant nested directory structure `src/polycli/agents/agents/` into `src/polycli/agents/` and update all imports.

## Phase 1: Red Phase & Prep
Confirm the current state and establish failing tests for the new structure.

- [x] Task: Run existing tests `pytest tests/test_agents.py` and confirm they pass.
- [x] Task: Create a "canary" test command `export PYTHONPATH=$PYTHONPATH:$(pwd)/src && python3 -c "from polycli.agents import SupervisorAgent"` and confirm it FAILS.
- [x] Task: Conductor - User Manual Verification 'Red Phase & Prep' (Protocol in workflow.md)

## Phase 2: Refactoring
Perform the actual movement of files and update import references.

- [x] Task: Move `alert_manager.py`, `market_observer.py`, and `supervisor.py` from `src/polycli/agents/agents/` to `src/polycli/agents/`.
- [x] Task: Update all import references in `src/polycli/` (e.g., `tui.py`, `agents/__init__.py`).
- [x] Task: Update all import references in `tests/test_agents.py`.
- [x] Task: Update documentation references in `PHASE1_SUMMARY.md`.
- [x] Task: Remove the empty `src/polycli/agents/agents/` directory.
- [x] Task: Conductor - User Manual Verification 'Refactoring' (Protocol in workflow.md)

## Phase 3: Green Phase & Verification
Ensure the new structure works and all tests pass.

- [x] Task: Run the "canary" test command `export PYTHONPATH=$PYTHONPATH:$(pwd)/src && python3 -c "from polycli.agents import SupervisorAgent"` and confirm it SUCCEEDS.
- [x] Task: Run all tests `pytest tests/test_agents.py` and confirm they PASS.
- [x] Task: Run full test suite `pytest` to ensure zero regressions.
- [x] Task: Conductor - User Manual Verification 'Green Phase & Verification' (Protocol in workflow.md)

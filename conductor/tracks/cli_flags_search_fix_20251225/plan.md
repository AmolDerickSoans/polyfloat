# Plan: Fix TUI Search & Add CLI Credential Flags

## Phase 1: CLI Credential Flags
- [x] Task: Implement Ephemeral CLI Flags b8659e5
    - [ ] Update `src/polycli/cli.py` (or entry point) to accept new flags: `--poly-key`, `--gemini-key`, `--kalshi-key`, `--kalshi-key-id`, `--kalshi-pem`.
    - [ ] Modify `src/polycli/utils/config.py` to accept runtime overrides.
    - [ ] Verify flags inject credentials into the running session without saving to disk.
- [ ] Task: Implement Persistent Flag Logic (`--save`)
    - [ ] Add `--save` boolean flag.
    - [ ] Implement logic to write provided flag values to `.env` or `setup_state.json` when `--save` is present.
- [ ] Task: Verify CLI Flag Precedence & Security
    - [ ] Test: Flags override env vars.
    - [ ] Test: Flags + `--save` persists changes.
    - [ ] Test: No flags = fallback to interactive mode/env vars.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: CLI Credential Flags' (Protocol in workflow.md)

## Phase 2: Diagnostics & RCA
- [ ] Task: Create reproduction script for TUI search failure
    - [ ] Create `repro_search_fail.py` to simulate `tui.py` search logic without the UI loop.
    - [ ] Verify `Action: Focus Search` -> `Action: Input Text` -> `Update Market List` flow.
- [ ] Task: Analyze API Provider Search Implementations
    - [ ] Audit `src/polycli/providers/kalshi.py` `search_markets` method.
    - [ ] Audit `src/polycli/providers/polymarket.py` `search_markets` method.
    - [ ] Write unit tests to verify raw API search results are correctly mapped to `Market` models.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Diagnostics & RCA' (Protocol in workflow.md)

## Phase 3: TUI Search Fix
- [ ] Task: Implement TUI Search Logic Fix
    - [ ] Refactor `DashboardApp.update_markets` to handle search queries correctly.
    - [ ] Ensure proper threading/async handling to prevent UI freezing during remote search.
    - [ ] Update `tui.py` to display "No results found" or "Searching..." states.
- [ ] Task: Verify Fix with Reproduction Script & Tests
    - [ ] Run `repro_search_fail.py` to confirm fix.
    - [ ] Add regression test in `tests/test_tui_integration.py`.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: TUI Search Fix' (Protocol in workflow.md)

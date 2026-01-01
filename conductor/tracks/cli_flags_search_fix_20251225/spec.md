# Specification: Fix TUI Search & Add CLI Credential Flags

## 1. Overview
This track addresses two distinct needs:
1.  **Critical Bug Fix:** The market search functionality in the TUI (`tui.py`) is broken, consistently returning zero results for known markets. This requires a full Root Cause Analysis (RCA) spanning from the API providers to the UI rendering.
2.  **Feature Enhancement:** Enable users to pass API credentials (Polymarket, Gemini, Kalshi) directly via CLI flags, supporting both ephemeral usage (single session) and persistent configuration (skipping the interactive questionnaire).

## 2. Functional Requirements

### 2.1 TUI Search Repair
*   **Root Cause Analysis (RCA):**
    *   Investigate the data flow in `src/polycli/tui.py`, specifically the `action_focus_search` and any filtering logic applied to `markets_cache` or `update_markets`.
    *   Verify the `search_markets` implementations in `src/polycli/providers/kalshi.py` and `src/polycli/providers/polymarket.py` to ensure they correctly query the APIs and return standardized `Market` objects.
    *   Identify if the issue is a data normalization problem (e.g., mismatched field names) or a logic error in the TUI's filter predicate.
*   **Resolution:**
    *   Ensure typing in the search box correctly filters the displayed market list.
    *   If remote search is required (vs. local filtering of cached items), ensure it triggers the appropriate async provider calls without blocking the UI.
    *   Search results must populate the `#market_list` DataTable.

### 2.2 CLI Credential Flags
*   **New Flags:** Add the following optional flags to the main CLI entry point (likely `cli.py` or the `config` command):
    *   `--poly-key <key>`: Polymarket Private Key.
    *   `--gemini-key <key>`: Gemini API Key.
    *   `--kalshi-key <key>`: Kalshi API Key.
    *   `--kalshi-key-id <id>`: Kalshi Key ID (if distinct from API key in current auth flow).
    *   `--kalshi-pem <path>`: Path to Kalshi private key file.
*   **Ephemeral Mode (Default):**
    *   If flags are provided *without* the `--save` flag, values are used for the current execution context only and do not modify the persistent configuration file (`.env` or `setup_state.json`).
*   **Persistent Mode:**
    *   If the `--save` flag is provided alongside credential flags, the application must write these values to the persistent configuration, effectively automating the setup questionnaire.
*   **Backward Compatibility:**
    *   Retain the existing interactive questionnaire behavior if no flags are provided.

## 3. Non-Functional Requirements
*   **Security:** Ensure that credentials passed via flags are handled securely in memory and not inadvertently logged to debug logs or console output.
*   **Usability:** The search function should provide immediate visual feedback (e.g., "Searching..." or "No results found") rather than failing silently.

## 4. Acceptance Criteria
*   [ ] **Search Verification:** A user can search for a known market string (e.g., "Trump", "Fed") in the TUI and see relevant results in the market list.
*   [ ] **Ephemeral Flag Verification:** Running `poly tui --kalshi-key ...` works for that session without altering the `.env` file.
*   [ ] **Persistent Flag Verification:** Running `poly config --kalshi-key ... --save` updates the persistent configuration.
*   [ ] **Regression Check:** Existing interactive setup still works when no flags are used.

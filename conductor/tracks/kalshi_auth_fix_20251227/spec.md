# Specification: Fix Kalshi Authentication & Hang

## 1. Overview
The Kalshi integration currently hangs during the verification step because the RSA signing logic is stubbed out ("In a real implementation..."). This causes unsigned requests to be sent to the API, which likely results in a connection hang or silent failure. This track implements the actual signing logic and adds safeguards against indefinite hangs.

## 2. Technical Requirements

### 2.1 RSA Signing Implementation
*   **Location:** `src/polycli/providers/kalshi.py` -> `_authenticate` -> `signed_call_api`.
*   **Logic:**
    *   Intercept calls to `api_client.call_api`.
    *   Extract `method` (GET/POST), `path` (resource_path), and `body`.
    *   Call `self.signer.get_headers(method, path, body)` (assuming `signer` is available in scope).
    *   Inject the returned headers (specifically `WAL-Auth`) into the request's `header_params`.
    *   Proceed with the original call.

### 2.2 Timeout Safeguard
*   **Location:** `src/polycli/providers/kalshi.py` -> `check_connection` (and potentially `get_markets`).
*   **Logic:**
    *   Wrap the `loop.run_in_executor` call in `asyncio.wait_for` with a reasonable timeout (e.g., 10 seconds).
    *   Catch `TimeoutError` and log/return failure instead of hanging indefinitely.

## 3. Acceptance Criteria
*   [ ] **Signing:** Requests made by `KalshiProvider` must include the `WAL-Auth` header when `KalshiAuth` is active.
*   [ ] **No Hang:** The `check_connection` method must return `False` (or `True`) within 10 seconds, even if the network is down or keys are invalid.
*   [ ] **Verification:** The CLI `ensure_credentials` flow proceeds past "Verifying Kalshi credentials..." without getting stuck.

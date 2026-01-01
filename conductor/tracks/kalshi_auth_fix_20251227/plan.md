# Plan: Fix Kalshi Authentication & Hang

## Phase 1: Authentication Logic Fix
- [x] Task: Implement RSA Signing in Provider
    - [x] Update `src/polycli/providers/kalshi.py`: Implement `signed_call_api` to use `signer.get_headers`.
    - [x] Ensure `resource_path`, `method`, and `body` are correctly extracted from arguments.
    - [x] Ensure headers are correctly merged into `header_params`.
- [x] Task: Add Connection Timeout
    - [x] Update `check_connection` to use `asyncio.wait_for` or configured timeout to prevent infinite hangs.
    - [x] Handle timeout exceptions gracefully in `cli.py`.

## Phase 2: Verification
- [x] Task: Verify Authentication with Mock
    - [x] Create `tests/test_kalshi_auth_flow.py` to mock `original_call_api` and verify `signed_call_api` injects headers.
    - [x] Verify `WAL-Auth` header format.
- [~] Task: Conductor - User Manual Verification (Protocol in workflow.md)

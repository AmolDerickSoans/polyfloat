
import asyncio
import os
from polycli.providers.kalshi import KalshiProvider
import time

async def verify_no_hang():
    print("--- Verifying Kalshi Connection Safeguards ---")
    
    # Test 1: Invalid Credentials (should fail fast, not hang)
    print("\n1. Testing with INVALID credentials...")
    os.environ['KALSHI_KEY_ID'] = 'invalid'
    os.environ['KALSHI_PRIVATE_KEY_PATH'] = 'nonexistent.pem'
    
    start = time.time()
    provider = KalshiProvider()
    is_connected = await provider.check_connection()
    duration = time.time() - start
    
    print(f"Connection result: {is_connected}")
    print(f"Duration: {duration:.2f}s")
    if duration < 5:
        print("PASS: Failed fast as expected.")
    else:
        print("FAIL: Took too long.")

    # Test 2: (Optional) If real credentials provided, verify success
    # This assumes .env is loaded if present
    from dotenv import load_dotenv
    load_dotenv()
    
    key_id = os.getenv("KALSHI_KEY_ID")
    if key_id and key_id != 'invalid':
        print(f"\n2. Testing with REAL credentials (ID: {key_id})...")
        provider = KalshiProvider()
        start = time.time()
        is_connected = await provider.check_connection()
        duration = time.time() - start
        print(f"Connection result: {is_connected}")
        print(f"Duration: {duration:.2f}s")
        if is_connected:
            print("PASS: Authenticated successfully.")
        else:
            print("FAIL: Could not authenticate with provided keys.")

if __name__ == "__main__":
    asyncio.run(verify_no_hang())

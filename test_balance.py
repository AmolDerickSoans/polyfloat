
import asyncio
import os
from polycli.providers.kalshi import KalshiProvider

async def main():
    # Set Credentials Explicitly
    os.environ["KALSHI_KEY_ID"] = "0248916e-2f36-4245-830b-a0931d6fd387"
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = "/Users/amoldericksoans/Documents/polyfloat/private.pem"
    os.environ["KALSHI_API_HOST"] = "https://api.elections.kalshi.com/trade-api/v2"

    provider = KalshiProvider()
    if provider.config: 
        provider.config.host = "https://api.elections.kalshi.com/trade-api/v2"
    
    print("--- Testing get_balance (check_connection) ---")
    try:
        bal = await provider.get_balance()
        print(f"Balance: {bal}")
        print("get_balance SUCCESS")
    except Exception as e:
        print(f"get_balance FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(main())

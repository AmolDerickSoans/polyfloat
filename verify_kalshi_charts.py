
import asyncio
import os
from dotenv import load_dotenv

load_dotenv(".env", override=True)
from polycli.providers.kalshi import KalshiProvider

async def main():
    print("--- Verifying Kalshi Charts (get_candlesticks) ---")
    provider = KalshiProvider()
    
    markets = await provider.search("Mars")
    if not markets:
        print("No markets found to test.")
        return
        
    target = markets[0]
    print(f"Testing with Market: {target.token_id}")
    
    print("Fetching candlesticks...")
    try:
        # Check hour
        candles = await provider.get_candlesticks(target.token_id, period="hour")
        
        print(f"Candles Returned: {len(candles)}")
        if candles:
            print(f"Sample: {candles[0]}")
        else:
            print("No candles found.")
            
    except Exception as e:
        print(f"Chart Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

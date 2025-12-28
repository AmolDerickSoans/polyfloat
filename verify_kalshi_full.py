
import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv(".env", override=True)
from polycli.providers.kalshi import KalshiProvider
from polycli.providers.kalshi_ws import KalshiWebSocket

async def test_rest(provider, ticker):
    print(f"\n--- Testing REST for {ticker} ---")
    
    print("Fetching Candlesticks...")
    candles = await provider.get_candlesticks(ticker)
    print(f"Candles: {len(candles)}")
    if candles: print(f"Sample Candle: {candles[0]}")
    
    print("\nFetching Orderbook Snapshot...")
    ob = await provider.get_orderbook(ticker)
    print(f"Bids: {len(ob['bids'])} | Asks: {len(ob['asks'])}")
    if ob['bids']: print(f"Top Bid: {ob['bids'][0]}")
    if ob['asks']: print(f"Top Ask: {ob['asks'][0]}")

async def test_ws(ticker):
    print(f"\n--- Testing WebSockets for {ticker} ---")
    ws = KalshiWebSocket()
    
    def on_ob(data):
        print(f"\n[WS] Received OB Update for {ticker}")
        print(f"Bids: {len(data['bids'])} | Asks: {len(data['asks'])}")
        if data['bids']: print(f"Top Bid: {data['bids'][0]}")
        if data['asks']: print(f"Top Ask: {data['asks'][0]}")

    def on_trade(data):
        print(f"\n[WS] Received Trade for {ticker}: {data}")

    ws.add_callback("orderbook", on_ob)
    ws.add_callback("trade", on_trade)
    
    print("Connecting...")
    await ws.connect()
    
    await asyncio.sleep(2) # Wait for connection
    
    print(f"Subscribing to {ticker}...")
    await ws.subscribe(ticker)
    
    print("Waiting 10 seconds for live updates (market must be active)...")
    await asyncio.sleep(10)
    
    await ws.disconnect()
    print("WS Test Complete.")

async def main():
    provider = KalshiProvider()
    
    # Let's find a real active market first
    print("Searching for active markets...")
    markets = await provider.search("Government")
    if not markets:
        print("No markets found to test.")
        return
        
    target = markets[0]
    ticker = target.token_id
    print(f"Target Ticker: {ticker}")
    
    await test_rest(provider, ticker)
    await test_ws(ticker)

if __name__ == "__main__":
    asyncio.run(main())

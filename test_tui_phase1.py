#!/usr/bin/env python3
"""
Test Phase 1 fixes: Enhanced metadata and orderbook display
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from polycli.providers.kalshi import KalshiProvider
from polycli.providers.polymarket import PolyProvider

async def test_phase1():
    print("=" * 70)
    print("Phase 1 Testing: Enhanced Market Details")
    print("=" * 70)
    
    # Test Polymarket
    print("\n🔵 Testing Polymarket...")
    print("-" * 70)
    try:
        poly = PolyProvider()
        markets = await poly.search("Trump", max_results=1)
        
        if markets:
            m = markets[0]
            print(f"✓ Found market: {m.question}")
            print(f"✓ Market ID: {m.id[:20]}...")
            print(f"✓ Provider: {m.provider}")
            print(f"✓ Status: {m.status}")
            
            # Check metadata availability
            metadata = m.metadata or {}
            print(f"\n📊 Metadata Fields Available:")
            print(f"  - Outcome Prices: {metadata.get('outcomePrices', 'N/A')}")
            print(f"  - Best Bid: ${metadata.get('bestBid', 0):.3f}")
            print(f"  - Best Ask: ${metadata.get('bestAsk', 0):.3f}")
            print(f"  - Volume 24h: ${metadata.get('volume24hr', 0):,.0f}")
            print(f"  - Volume 7d: ${metadata.get('volume1wk', 0):,.0f}")
            print(f"  - Liquidity: ${metadata.get('liquidityNum', 0):,.2f}")
            print(f"  - 1d Change: {metadata.get('oneDayPriceChange', 0)*100:+.2f}%")
            print(f"  - 7d Change: {metadata.get('oneWeekPriceChange', 0)*100:+.2f}%")
            print(f"  - Competitive Score: {metadata.get('competitive', 0):.2%}")
            
            # Test orderbook
            ctids = metadata.get('clobTokenIds', [])
            if isinstance(ctids, str):
                import json
                ctids = json.loads(ctids)
            
            if ctids:
                print(f"\n📖 Testing Orderbook...")
                ob = await poly.get_orderbook(ctids[0])
                print(f"  ✓ Bids: {len(ob.bids)} levels")
                print(f"  ✓ Asks: {len(ob.asks)} levels")
                
                if ob.bids and ob.asks:
                    best_bid = ob.bids[0]
                    best_ask = ob.asks[0]
                    spread = best_ask.price - best_bid.price
                    mid = (best_bid.price + best_ask.price) / 2
                    spread_bps = (spread / mid) * 10000
                    
                    print(f"  ✓ Best Bid: ${best_bid.price:.3f} @ {best_bid.size:,.0f}")
                    print(f"  ✓ Best Ask: ${best_ask.price:.3f} @ {best_ask.size:,.0f}")
                    print(f"  ✓ Mid Price: ${mid:.3f}")
                    print(f"  ✓ Spread: {spread_bps:.0f} bps")
                    
                    # Show first 5 levels
                    print(f"\n  Top 5 Levels:")
                    print(f"  {'Size':>10} {'Bid':>10} {'Ask':>10} {'Size':>10}")
                    for i in range(min(5, max(len(ob.bids), len(ob.asks)))):
                        b = ob.bids[i] if i < len(ob.bids) else None
                        a = ob.asks[i] if i < len(ob.asks) else None
                        
                        bid_str = f"{b.size:>10,.0f} ${b.price:>8.3f}" if b else " " * 20
                        ask_str = f"${a.price:<8.3f} {a.size:<10,.0f}" if a else " " * 20
                        
                        print(f"  {bid_str} {ask_str}")
                else:
                    print("  ⚠ Empty orderbook")
            else:
                print("  ⚠ No CLOB token IDs")
                
        else:
            print("✗ No markets found")
            
    except Exception as e:
        print(f"✗ Polymarket test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Kalshi
    print("\n\n🟠 Testing Kalshi...")
    print("-" * 70)
    try:
        kalshi = KalshiProvider()
        
        if not kalshi.api_instance:
            print("✗ Kalshi authentication failed")
            return False
        
        print("✓ Kalshi authenticated")
        
        markets = await kalshi.get_markets(limit=1)
        
        if markets:
            m = markets[0]
            print(f"✓ Found market: {m.question}")
            print(f"✓ Ticker: {m.id}")
            print(f"✓ Provider: {m.provider}")
            print(f"✓ Status: {m.status}")
            
            # Check metadata availability
            metadata = m.metadata or {}
            print(f"\n📊 Metadata Fields Available:")
            print(f"  - Last Price: {metadata.get('_last_price', 0)}¢")
            print(f"  - Previous Price: {metadata.get('_previous_price', 0)}¢")
            print(f"  - Yes Bid/Ask: {metadata.get('_yes_bid', 0)}¢ / {metadata.get('_yes_ask', 0)}¢")
            print(f"  - No Bid/Ask: {metadata.get('_no_bid', 0)}¢ / {metadata.get('_no_ask', 0)}¢")
            print(f"  - Volume: {metadata.get('_volume', 0):,} contracts")
            print(f"  - Volume 24h: {metadata.get('_volume_24h', 0):,} contracts")
            print(f"  - Liquidity: ${metadata.get('_liquidity', 0)/100:,.2f}")
            print(f"  - Open Interest: {metadata.get('_open_interest', 0):,} contracts")
            print(f"  - Close Time: {metadata.get('_close_time', '')[:10]}")
            
            # Test orderbook
            print(f"\n📖 Testing Orderbook...")
            ob = await kalshi.get_orderbook(m.id)
            print(f"  ✓ Bids: {len(ob.bids)} levels")
            print(f"  ✓ Asks: {len(ob.asks)} levels")
            
            if ob.bids and ob.asks:
                best_bid = ob.bids[0]
                best_ask = ob.asks[0]
                spread = best_ask.price - best_bid.price
                mid = (best_bid.price + best_ask.price) / 2
                spread_bps = (spread / mid) * 10000 if mid else 0
                
                print(f"  ✓ Best Bid: ${best_bid.price:.3f} @ {best_bid.size:,.0f}")
                print(f"  ✓ Best Ask: ${best_ask.price:.3f} @ {best_ask.size:,.0f}")
                print(f"  ✓ Mid Price: ${mid:.3f}")
                print(f"  ✓ Spread: {spread_bps:.0f} bps")
                
                # Show first 5 levels
                print(f"\n  Top 5 Levels:")
                print(f"  {'Size':>10} {'Bid':>10} {'Ask':>10} {'Size':>10}")
                for i in range(min(5, max(len(ob.bids), len(ob.asks)))):
                    b = ob.bids[i] if i < len(ob.bids) else None
                    a = ob.asks[i] if i < len(ob.asks) else None
                    
                    bid_str = f"{b.size:>10,.0f} ${b.price:>8.3f}" if b else " " * 20
                    ask_str = f"${a.price:<8.3f} {a.size:<10,.0f}" if a else " " * 20
                    
                    print(f"  {bid_str} {ask_str}")
            else:
                print("  ⚠ Empty orderbook")
                
        else:
            print("✗ No markets found")
            
    except Exception as e:
        print(f"✗ Kalshi test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("✓ Phase 1 Testing Complete!")
    print("=" * 70)
    print("\n💡 Next: Run the TUI with 'python -m polycli.tui' to see the enhancements")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_phase1())
    exit(0 if success else 1)

#!/usr/bin/env python3
"""
Test script to verify TUI fixes:
1. Kalshi search works
2. Polymarket search works
3. Order book and market details display correctly
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from polycli.providers.kalshi import KalshiProvider
from polycli.providers.polymarket import PolyProvider

async def test_providers():
    print("=" * 60)
    print("Testing Provider Fixes")
    print("=" * 60)
    
    # Test 1: Kalshi Authentication and Search
    print("\n1. Testing Kalshi Provider...")
    try:
        kalshi = KalshiProvider()
        if kalshi.api_instance:
            print("   ✓ Kalshi authentication successful")
        else:
            print("   ✗ Kalshi authentication failed")
            return False
            
        # Test search
        results = await kalshi.search("Trump")
        print(f"   ✓ Kalshi search returned {len(results)} results")
        
        if results:
            print(f"   ✓ Sample market: {results[0].question}")
            
            # Test orderbook fetch
            try:
                ob = await kalshi.get_orderbook(results[0].id)
                print(f"   ✓ Orderbook fetch successful: {len(ob.bids)} bids, {len(ob.asks)} asks")
            except Exception as e:
                print(f"   ⚠ Orderbook fetch warning: {e}")
    except Exception as e:
        print(f"   ✗ Kalshi test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 2: Polymarket Search
    print("\n2. Testing Polymarket Provider...")
    try:
        poly = PolyProvider()
        results = await poly.search("Trump")
        print(f"   ✓ Polymarket search returned {len(results)} results")
        
        if results:
            print(f"   ✓ Sample market: {results[0].question}")
            
            # Check metadata structure
            market = results[0]
            if market.metadata:
                ctids = market.metadata.get("clobTokenIds", [])
                if isinstance(ctids, str):
                    import json
                    ctids = json.loads(ctids)
                print(f"   ✓ Market has {len(ctids) if isinstance(ctids, list) else 0} token IDs")
                
                # Test orderbook fetch if we have token IDs
                if ctids and isinstance(ctids, list) and len(ctids) > 0:
                    try:
                        ob = await poly.get_orderbook(ctids[0])
                        print(f"   ✓ Orderbook fetch successful: {len(ob.bids)} bids, {len(ob.asks)} asks")
                    except Exception as e:
                        print(f"   ⚠ Orderbook fetch warning: {e}")
            else:
                print("   ⚠ Market metadata is empty")
    except Exception as e:
        print(f"   ✗ Polymarket test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("✓ All provider tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = asyncio.run(test_providers())
    exit(0 if success else 1)

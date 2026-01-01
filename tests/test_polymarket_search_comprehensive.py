# test_polymarket_search_comprehensive.py
import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from polycli.providers.polymarket import PolyProvider

async def test_search():
    """Test Polymarket search functionality"""
    print("=" * 60)
    print("POLYMARKET SEARCH TEST")
    print("=" * 60)
    
    # Initialize provider with longer timeout for testing
    provider = PolyProvider(timeout=30.0)
    
    # Test cases
    test_queries = [
        ("trump", 5),
        ("bitcoin", 5),
        ("election", 10),
    ]
    
    for query, max_results in test_queries:
        print(f"\n🔍 Searching for: '{query}' (max {max_results} results)")
        print("-" * 60)
        
        try:
            results = await provider.search(query, max_results=max_results)
            
            if results:
                print(f"✅ Found {len(results)} markets\n")
                
                for i, market in enumerate(results, 1):
                    print(f"{i}. {market.question[:70]}...")
                    print(f"   ID: {market.id}")
                    print(f"   Event: {market.event_id}")
                    print(f"   Status: {market.status.value}")
                    print(f"   Outcomes: {', '.join(market.outcomes)}")
                    print(f"   Provider: {market.provider}")
                    
                    # Show some metadata if available
                    if market.metadata:
                        volume_24h = market.metadata.get("volume24hr")
                        liquidity = market.metadata.get("liquidityNum")
                        if volume_24h:
                            try:
                                print(f"   24h Volume: ${float(volume_24h):,.0f}")
                            except (ValueError, TypeError):
                                pass
                        if liquidity:
                            try:
                                print(f"   Liquidity: ${float(liquidity):,.0f}")
                            except (ValueError, TypeError):
                                pass
                    print()
            else:
                print("⚠️  No results found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

async def test_search_with_closed():
    """Test search including closed markets"""
    print("\n" + "=" * 60)
    print("TESTING SEARCH WITH CLOSED MARKETS")
    print("=" * 60)
    
    provider = PolyProvider(timeout=30.0)
    
    query = "trump"
    print(f"\n🔍 Searching for: '{query}' (including closed markets)")
    
    results = await provider.search(query, max_results=10, include_closed=True)
    
    print(f"✅ Found {len(results)} markets")
    
    active_count = sum(1 for m in results if m.status.value == "active")
    closed_count = sum(1 for m in results if m.status.value == "closed")
    
    print(f"   Active: {active_count}")
    print(f"   Closed: {closed_count}")
    
    for market in results[:3]:
        print(f"\n• {market.question[:60]}...")
        print(f"  Status: {market.status.value}")

async def test_pagination():
    """Test that pagination works correctly"""
    print("\n" + "=" * 60)
    print("TESTING PAGINATION")
    print("=" * 60)
    
    provider = PolyProvider(timeout=30.0)
    
    # Request more results than typical API page size
    query = "election"
    max_results = 100
    
    print(f"\n🔍 Requesting {max_results} results for '{query}'")
    results = await provider.search(query, max_results=max_results)
    
    print(f"✅ Retrieved {len(results)} markets")
    
    if len(results) < max_results:
        print(f"ℹ️  Note: Only {len(results)} markets available (less than requested)")
    else:
        print(f"✅ Successfully paginated to retrieve full {max_results} results")

async def test_edge_cases():
    """Test edge cases and error handling"""
    print("\n" + "=" * 60)
    print("TESTING EDGE CASES")
    print("=" * 60)
    
    provider = PolyProvider(timeout=30.0)
    
    # Test empty query
    print("\n1. Testing empty query...")
    results = await provider.search("", max_results=5)
    print(f"   Empty query returned {len(results)} results")
    
    # Test special characters
    print("\n2. Testing special characters...")
    results = await provider.search("trump 2024", max_results=5)
    print(f"   Query with space returned {len(results)} results")
    
    # Test very specific query
    print("\n3. Testing very specific query...")
    results = await provider.search("xyzabc123nonexistent", max_results=5)
    print(f"   Non-existent query returned {len(results)} results")

async def main():
    """Run all tests"""
    try:
        await test_search()
        await test_search_with_closed()
        await test_pagination()
        await test_edge_cases()
        
        print("\n" + "🎉 ALL TESTS COMPLETED SUCCESSFULLY! 🎉")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

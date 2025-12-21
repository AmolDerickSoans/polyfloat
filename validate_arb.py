import sys
import os
import asyncio

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

async def test():
    print("Testing imports...")
    try:
        from polycli.arbitrage.models import MarketPair
        from polycli.arbitrage.discovery import DiscoveryClient
        from polycli.arbitrage.detector import ArbDetector
        from polycli.tui import DashboardApp
        print("Imports successful.")
        
        print("Instantiating clients (mocking env if needed)...")
        dc = DiscoveryClient()
        ad = ArbDetector()
        print("Clients instantiated.")
        
    except ImportError as e:
        print(f"ImportError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test())

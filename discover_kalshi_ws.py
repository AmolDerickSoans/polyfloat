
import asyncio
import os
import websockets
from dotenv import load_dotenv
load_dotenv(".env", override=True)
from polycli.providers.kalshi_auth import KalshiAuth

async def test_endpoint(host, path):
    url = f"wss://{host}{path}"
    print(f"Testing {url} ...")
    
    key_id = os.getenv("KALSHI_KEY_ID")
    key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    
    auth = KalshiAuth(key_id, key_path)
    # Most Kalshi v2 paths for signing start with /trade-api/v2
    # But if the path is actually just /websocket, maybe it's signed as that.
    
    # Try multiple signing paths for each URL path
    sign_paths = [path]
    if not path.startswith("/trade-api/v2") and path != "/":
        sign_paths.append("/trade-api/v2" + path)
    
    for s_path in sign_paths:
        headers = auth.get_headers("GET", s_path)
        try:
            async with websockets.connect(url, additional_headers=headers, open_timeout=2) as ws:
                print(f"  [SUCCESS] Connected to {url} with sign path {s_path}")
                return True
        except Exception as e:
            # print(f"  [FAILED] {s_path}: {e}")
            pass
    return False

async def main():
    hosts = ["api.elections.kalshi.com", "api.kalshi.com"]
    paths = ["/", "/ws", "/websocket", "/trade-api/v2/websocket"]
    
    for h in hosts:
        for p in paths:
            if await test_endpoint(h, p):
                print(f"\nFOUND WORKING ENDPOINT: wss://{h}{p}")
                return

if __name__ == "__main__":
    asyncio.run(main())

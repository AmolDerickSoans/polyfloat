
import asyncio
import os
import kalshi_python
from dotenv import load_dotenv
load_dotenv(".env", override=True)

def main():
    config = kalshi_python.Configuration()
    config.host = os.getenv("KALSHI_API_HOST", "https://api.elections.kalshi.com/trade-api/v2")
    api_instance = kalshi_python.ApiInstance(configuration=config)
    
    print("Methods in api_instance:")
    for m in sorted(dir(api_instance)):
        if not m.startswith("_"):
            print(f"  {m}")

if __name__ == "__main__":
    main()

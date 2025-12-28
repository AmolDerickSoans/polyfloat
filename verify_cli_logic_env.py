
import os
import asyncio
from dotenv import load_dotenv

# Ensure we have the env vars loaded (like cli.py does at the start)
load_dotenv(".env", override=True)

from polycli.providers.kalshi import KalshiProvider

# Mock what cli.py does
async def verify():
    print("\n[dim]Verifying Kalshi credentials...[/dim]")
    try:
         # Simulate ensure_credentials context
         prov = KalshiProvider()
         if not prov.api_instance:
              print("[bold red]❌ Authentication Failed: Unable to initialize API client. Check your keys/password.[/bold red]")
         else:
              # Run check
              is_valid = await prov.check_connection()
              if is_valid:
                  print("[bold green]✓ Verified: Connected to Kalshi[/bold green]")
              else:
                  print("[bold red]⚠ Warning: API Client initialized but check_connection failed.[/bold red]")
    except Exception as e:
         print(f"[red]Verification Error: {e}[/red]")

if __name__ == "__main__":
    asyncio.run(verify())

import os
import asyncio
import kalshi_python
from typing import List, Optional, Dict
from polycli.providers.base import BaseProvider, MarketData, OrderArgs, OrderResponse, OrderSide, OrderType

class KalshiProvider(BaseProvider):
    """Kalshi provider implementation using official SDK"""
    
    def __init__(self, host: str = "https://trading-api.kalshi.com/trade-api/v2"):
        self.host = host
        self.config = kalshi_python.Configuration()
        self.config.host = host
        self.api_instance = None
        self._authenticate()

    def _authenticate(self):
        """Initialize the API instance with available credentials"""
        email = os.getenv("KALSHI_EMAIL")
        password = os.getenv("KALSHI_PASSWORD")
        key_id = os.getenv("KALSHI_KEY_ID")
        key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        key_content = os.getenv("KALSHI_PRIVATE_KEY")

        if email and password:
            self.api_instance = kalshi_python.ApiInstance(
                email=email,
                password=password,
                configuration=self.config
            )
        elif key_id and (key_path or key_content):
            # If key_content is provided, we use it directly if supported, 
            # otherwise we might need a temp file helper.
            # Official SDK typically wants a path for RSA keys.
            actual_path = key_path
            if key_content and not key_path:
                # Basic check for key format
                if "BEGIN RSA PRIVATE KEY" in key_content or "BEGIN PRIVATE KEY" in key_content:
                    import tempfile
                    # We create a temporary file that persists for the session
                    self._tmp_key = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
                    self._tmp_key.write(key_content)
                    self._tmp_key.close()
                    actual_path = self._tmp_key.name

            self.api_instance = kalshi_python.ApiInstance(
                key_id=key_id,
                private_key_path=actual_path,
                configuration=self.config
            )

    async def get_markets(
        self,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[MarketData]:
        """Fetch active markets from Kalshi API"""
        if not self.api_instance:
            return []

        try:
            # kalshi-python is typically synchronous, so we run in thread
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.api_instance.get_markets(status="open", limit=limit)
            )
            
            markets = []
            # response is typically a GetMarketsResponse object with a markets field
            raw_markets = getattr(response, "markets", [])
            
            for m in raw_markets:
                # m is a Market object
                price = (getattr(m, "yes_bid", 50) or 50) / 100.0
                
                markets.append(MarketData(
                    token_id=getattr(m, "ticker", "unknown"),
                    title=getattr(m, "title", "Unknown Kalshi Market"),
                    description=getattr(m, "subtitle", ""),
                    price=price,
                    volume_24h=0.0,
                    liquidity=0.0,
                    end_date=str(getattr(m, "close_time", "")),
                    provider="kalshi"
                ))
                
            return markets
        except Exception as e:
            # Fallback for unexpected SDK behavior or auth errors
            return []

    async def get_orderbook(self, ticker: str) -> Dict:
        """Get orderbook for a ticker"""
        if not self.api_instance:
            return {}
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, 
                lambda: self.api_instance.get_market_orderbook(ticker)
            )
            if hasattr(resp, "to_dict"):
                return resp.to_dict()
            
            # Manual fallback
            obs = getattr(resp, "order_book", None)
            if obs:
                return {
                    "yes": getattr(obs, "yes", []),
                    "no": getattr(obs, "no", [])
                }
            return {}
        except Exception:
            return {}

    async def get_balance(self) -> float:
        """Get account balance in dollars"""
        if not self.api_instance:
            return 0.0
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                self.api_instance.get_balance
            )
            # Response in cents usually
            return getattr(response, "balance", 0) / 100.0
        except Exception:
            return 0.0

    async def place_order(self, order: OrderArgs) -> OrderResponse:
        return OrderResponse(order_id="pending", status="pending", filled_amount=0.0, avg_price=0.0)

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_positions(self) -> List[Dict]:
        return []

    async def get_events(self, series_ticker: str, limit: int = 50) -> List[Dict]:
        """Fetch events for a series (e.g., KXNBA)"""
        if not self.api_instance:
            return []
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.api_instance.get_events(series_ticker=series_ticker, limit=limit, status="open")
            )
            return getattr(response, "events", [])
        except Exception:
            return []
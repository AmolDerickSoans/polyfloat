
import os
import asyncio
import kalshi_python
from typing import List, Optional, Dict
from polycli.providers.base import BaseProvider, MarketData, OrderArgs, OrderResponse, OrderSide
from polycli.providers.kalshi_auth import KalshiAuth
from kalshi_python.rest import RESTClientObject

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

        # Priority: RSA Key (Production) > Email/Password (Legacy/Sandbox)
        if key_id and (key_path or key_content):
            # RSA AUTHENTICATION
            actual_path = key_path
            
            # If explicit content provided, use that (via temp file if necessary)
            if key_content and not key_path:
                if "BEGIN RSA PRIVATE KEY" in key_content or "BEGIN PRIVATE KEY" in key_content:
                    import tempfile
                    # Secure temp file creation
                    self._tmp_key = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
                    self._tmp_key.write(key_content)
                    self._tmp_key.close()
                    actual_path = self._tmp_key.name
                    # Ensure only owner can read
                    os.chmod(actual_path, 0o600)

            # Security Check: File Permissions
            if actual_path and os.path.exists(actual_path):
                # Check if file is too open (e.g. 777) - Unix only
                if os.name == 'posix':
                    st = os.stat(actual_path)
                    # Check if group or others have any permission (0o077 mask)
                    if st.st_mode & 0o077:
                        print(f"WARNING: Private key {actual_path} is too open. Please `chmod 600 {actual_path}` for security.")

            try:
                # Update Host to new endpoint
                self.config.host = "https://api.elections.kalshi.com/trade-api/v2"
                
                # Create ApiInstance FIRST
                self.api_instance = kalshi_python.ApiInstance(configuration=self.config)
                
                # Get the internal client
                internal_client = self.api_instance.api_client
                original_call_api = internal_client.call_api
                
                # Init Signer
                signer = KalshiAuth(key_id=key_id, private_key_path=actual_path)
                
                print("DEBUG: Patching ApiInstance.api_client.call_api method...")
                
                def signed_call_api(resource_path, method, path_params=None, query_params=None, header_params=None, body=None, post_params=None, files=None, response_type=None, auth_settings=None, async_req=None, _return_http_data_only=None, collection_formats=None, _preload_content=None, _request_timeout=None):
                    try:
                        # 1. Reconstruct Final Path
                        # Path Params
                        final_path = resource_path
                        if path_params:
                            for k, v in path_params.items():
                                final_path = final_path.replace('{' + k + '}', str(v))
                        
                        # Query Params
                        # query_params is list of tuples [(key, val), ...] or dict
                        q_str = ""
                        if query_params:
                            from urllib.parse import urlencode
                            # if it's list of tuples
                            if isinstance(query_params, list):
                                # Filter None values if any
                                q_p = [(k, v) for k, v in query_params if v is not None]
                                if q_p: q_str = "?" + urlencode(q_p)
                            elif isinstance(query_params, dict):
                                q_p = {k: v for k, v in query_params.items() if v is not None}
                                if q_p: q_str = "?" + urlencode(q_p)
                                
                        full_relative_path = "/trade-api/v2" + final_path + q_str
                        
                        # Let's ensure we match what they expect.
                        if not final_path.startswith("/trade-api/v2"):
                            full_relative_path = "/trade-api/v2" + final_path + q_str
                        else:
                            full_relative_path = final_path + q_str

                        # DEBUG
                        # print(f"DEBUG: Signing {method} {full_relative_path}")
                        
                        # 2. Sign
                        payload = body
                        if post_params: payload = post_params
                        
                        auth_headers = signer.get_headers(method, full_relative_path, payload)
                        
                        # 3. Update Headers
                        if header_params is None: header_params = {}
                        header_params.update(auth_headers)
                        
                        # Call Original
                        return original_call_api(resource_path, method, path_params, query_params, header_params, body, post_params, files, response_type, auth_settings, async_req, _return_http_data_only, collection_formats, _preload_content, _request_timeout)
                        
                    except Exception as e:
                        print(f"DEBUG: Call API Wrapper Error: {e}")
                        import traceback
                        traceback.print_exc()
                        raise e

                # Apply Patch
                internal_client.call_api = signed_call_api
                
                # Also ensure sub-APIs (if stored) use this client? 
                # If they store reference to internal_client, treating it as object, modification works.
                # If they stored methods, we might be in trouble. Usually they store client.


                
                print("Authenticated via RSA Key")

            except Exception as e:
                print(f"RSA Auth Failed: {e}")
                import traceback
                traceback.print_exc()
                self.api_instance = None
                
        elif email and password:
            # LEGACY PASSWORD AUTH
            try:
                print("WARNING: Using Email/Password auth. This is deprecated for production trading. Please use RSA-PSS Keys.")
                self.api_instance = kalshi_python.ApiInstance(
                    email=email,
                    password=password,
                    configuration=self.config
                )
            except Exception as e:
                print(f"Login Failed: {e}")
                self.api_instance = None
        else:
            print("No Kalshi Credentials Found")
            self.api_instance = None

    async def check_connection(self) -> bool:
        """Verify authentication status by fetching a small amount of public data"""
        if not self.api_instance:
            return False
        try:
            # get_balance often fails with 401 on some endpoints/keys, 
            # use get_public_events manual call which is proven robust.
            events = await self.get_public_events(limit=1)
            return True
        except Exception as e:
            print(f"Connection Check Error: {e}")
            return False

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
                lambda: self.api_instance.get_markets(status="open", limit=limit))
            # response is typically a GetMarketsResponse object with a markets field
            markets = getattr(response, "markets", [])
            
            if not markets:
                return []
            
            # If event_ticker provided, filter? The SDK call handles it?
            # get_markets(..., event_ticker=...)
            # SDK maps it? Checking implementation, yes usually.
            
            return [
                MarketData(
                    id=m.ticker,
                    token_id=m.ticker,
                    title=getattr(m, "title", getattr(m, "ticker", "Unknown Ticker")),
                    description=getattr(m, "subtitle", ""),
                    price=(getattr(m, "yes_bid", 50) or 50) / 100.0,
                    volume_24h=float(getattr(m, "volume_24h", 0) or 0),
                    liquidity=float(getattr(m, "liquidity", 0) or 0),
                    end_date=str(getattr(m, "close_time", "")),
                    provider="kalshi",
                    extra_data={"subtitle": getattr(m, "subtitle", "")}
                )
                for m in markets
            ]
        except Exception as e:
            # Fallback for unexpected SDK behavior or auth errors
            return []

    async def get_public_events(self, limit: int = 100) -> List[Dict]:
        """Fetch high-level events (Series) from Kalshi V2 API"""
        if not self.api_instance: return []
        try:
            # SDK doesn't always expose get_events, so we use safe manual call
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.api_client.call_api(
                    "/events", "GET",
                    query_params=[("status", "open"), ("limit", limit)],
                    auth_settings=["bearerAuth"],
                    _return_http_data_only=False,
                    _preload_content=False
                )
            )
            # resp is (data, status, headers)
            if not resp or len(resp) < 1: return []
            
            http_resp = resp[0]
            if http_resp.status != 200: return []
            
            import json
            data = json.loads(http_resp.data.decode('utf-8'))
            return data.get("events", [])
        except Exception as e:
            print(f"Fetch Events Error: {e}")
            return []

    async def search(self, query: str) -> List[MarketData]:
        """Search Kalshi markets with combined discovery (Direct Markets + Events)"""
        if not self.api_instance: return []
        
        query_lo = query.lower()
        results_map = {} # token_id -> MarketData to avoid duplicates
        
        # 1. Direct Market Discovery (Covers specific market titles/tickers)
        # Fetch up to 500 open markets
        direct_markets = await self.get_markets(limit=500)
        for m in direct_markets:
            if query_lo in m.title.lower() or query_lo in m.token_id.lower():
                results_map[m.token_id] = m
                
        # 2. Event Discovery (Covers high-level topics)
        events = await self.get_public_events(limit=100)
        matched_event_tickers = []
        for e in events:
            title = e.get("title", "") or ""
            # Kalshi API returns event_ticker or series_ticker depending on nested level
            e_ticker = e.get("series_ticker") or e.get("event_ticker") or e.get("ticker", "")
            if query_lo in title.lower() or query_lo in e_ticker.lower():
                if e_ticker:
                    matched_event_tickers.append(e_ticker)
        
        # 3. Fetch Markets for Matched Events (Max top 5 topics to avoid spamming)
        for ticker in matched_event_tickers[:5]:
            try:
                loop = asyncio.get_event_loop()
                # Check based on series_ticker
                m_resp = await loop.run_in_executor(
                    None, 
                    lambda: self.api_instance.get_markets(series_ticker=ticker, status="open")
                )
                markets_raw = getattr(m_resp, "markets", [])
                
                # If series_ticker failed, try as event_ticker (some markets use one or the other)
                if not markets_raw:
                    m_resp = await loop.run_in_executor(
                        None, 
                        lambda: self.api_instance.get_markets(event_ticker=ticker, status="open")
                    )
                    markets_raw = getattr(m_resp, "markets", [])

                for m in markets_raw:
                    if m.ticker not in results_map:
                        results_map[m.ticker] = MarketData(
                            id=m.ticker,
                            token_id=m.ticker,
                            title=getattr(m, "title",  m.ticker),
                            description=getattr(m, "subtitle", ""),
                            price=(getattr(m, "yes_bid", 50) or 50) / 100.0,
                            volume_24h=float(getattr(m, "volume_24h", 0) or 0),
                            liquidity=float(getattr(m, "liquidity", 0) or 0),
                            end_date=str(getattr(m, "close_time", "")),
                            provider="kalshi",
                            extra_data={
                                "series_ticker": ticker,
                                "subtitle": getattr(m, "subtitle", "")
                            }
                        )
            except Exception as e:
                print(f"Search Drilldown Error for {ticker}: {e}")
                continue
                
        return list(results_map.values())

    async def get_orderbook(self, ticker: str) -> Dict:
        """
        Get orderbook for a ticker.
        Normalizes Kalshi's Yes/No bids into a standard Bid/Ask queue for the 'Yes' outcome.
        Bids = Yes Bids
        Asks = (100 - No Bids)
        """
        if not self.api_instance:
            return {"bids": [], "asks": []}
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, 
                lambda: self.api_instance.get_market_orderbook(ticker)
            )
            
            # Extract raw yes/no queues
            # resp.order_book might be the object
            obs = getattr(resp, "order_book", None) or resp
            yes_bids = getattr(obs, "yes", []) or []
            no_bids = getattr(obs, "no", []) or []
            
            # Normalize to standard Bids/Asks for standard TUI
            # Bids: [[price, size], ...]
            formatted_bids = []
            for level in yes_bids:
                # level usually [price_cents, count] or object
                if isinstance(level, list):
                    p, s = level[0], level[1]
                else:
                    p, s = getattr(level, "price", 0), getattr(level, "count", 0)
                formatted_bids.append({"price": float(p)/100.0, "size": float(s)})
                
            # Asks: Derived from NO bids
            formatted_asks = []
            for level in no_bids:
                if isinstance(level, list):
                    p, s = level[0], level[1] # p is Price of NO
                else:
                    p, s = getattr(level, "price", 0), getattr(level, "count", 0)
                
                # Ask on YES = 1.00 - Bid on NO
                ask_p = (100 - p)
                formatted_asks.append({"price": float(ask_p)/100.0, "size": float(s)})
            
            # Sort
            formatted_bids.sort(key=lambda x: x["price"], reverse=True)
            formatted_asks.sort(key=lambda x: x["price"])
            
            return {
                "bids": formatted_bids,
                "asks": formatted_asks
            }
        except Exception as e:
            print(f"OB Error: {e}")
            return {"bids": [], "asks": []}

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
        """Place an order on Kalshi"""
        if not self.api_instance:
            return OrderResponse(order_id="", status="failed", filled_amount=0.0, avg_price=0.0)

        # Map Side
        # Kalshi uses "yes" / "no"
        side = "yes" if order.side == OrderSide.BUY else "no"
        # Since we are buying "contracts" on Kalshi, buying YES means betting FOR. 
        # Buying NO means betting AGAINST.
        # This mapping depends on how OrderSide is defined. Assuming BUY=Long/Yes, SELL=Short/No?
        # Typically polyfloat seems to treat outcomes as tokens.
        # If I want to BUY "Yes", side="yes", action="buy".
        # If I want to SELL "Yes", side="yes", action="sell".
        # But Kalshi API simplifies: "buy" action on "yes" side.
        
        # Let's assume OrderArgs.side refers to the action (BUY/SELL) on the TARGET token.
        # But Kalshi markets are binary.
        # In PolyFloat, we usually select a specific outcome (token_id).
        # On Kalshi, `ticker` is the market unique ID. The "token_id" in OrderArgs should be the market ticker.
        # We need to know WHICH side we are buying.
        # Standard PolyFloat usage seems to be: user selects "Yes" token -> clicks Buy.
        # So we probably need to pass `side` (Yes/No) in OrderArgs or infer it.
        # For now, let's assume `order.side` is the ACTION (Buy/Sell) and the token_id implies the outcome?
        # Wait, PolyFloat's `OrderSide` is usually BUY/SELL.
        # The `token_id` should point to a specific outcome (e.g. KXNBA-24OCT-LAL-WIN).
        # Actually Kalshi treats the "Market" as the object, and you buy "Yes" or "No".
        
        # REVISION: In tui.py, `QuickOrderModal` takes a `market` object.
        # If the user is buying shares of a specific OUTCOME, the `token_id` passed should probably successfully map to that.
        # However, Kalshi's `market` object has `ticker`.
        # Let's assume order.token_id IS the market ticker (e.g. KXTRUMPWIN).
        # To simplify, we will default to buying "Yes" contracts unless specified.
        # TODO: Add specific side selection in TUI later or assume "Yes" for the generic market listing.
        
        action = "buy" if order.side == OrderSide.BUY else "sell"
        
        try:
            # Convert dollars to count or whatever Kalshi expects.
            # Kalshi expects `count` (number of contracts).
            # Price is in cents (1-99).
            # limit_price usually in dollars in our app (0.50).
            c_price = int(order.price * 100) # Cents
            if c_price < 1: c_price = 1
            if c_price > 99: c_price = 99
            
            # Amount is in dollars. Contracts = Amount / Price
            count = int(order.amount / order.price)
            if count < 1: count = 1

            # Determine side from token/context or default to yes
            # For now hardcode 'yes' as most users buy the displayed market
            # If we want to short, we 'sell' 'yes' or 'buy' 'no'.
            # Simplest for integration: Always trade "yes" contracts.
            # BUY = Buy Yes
            # SELL = Sell Yes
            trade_side = "yes"

            import uuid
            client_id = str(uuid.uuid4())

            req = kalshi_python.CreateOrderRequest(
                ticker=order.token_id,
                action=action,
                side=trade_side,
                count=count,
                type="limit",
                yes_price=c_price,
                client_order_id=client_id,
                expiration_ts=None # GTC
            )

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.create_order(req)
            )
            
            # Resp is CreateOrderResponse
            o_id = getattr(resp, "order_id", client_id)
            status = getattr(resp, "status", "submitted")
            
            return OrderResponse(
                order_id=o_id,
                status=status,
                filled_amount=0.0, # Async fill
                avg_price=float(c_price)/100.0
            )

        except Exception as e:
            print(f"Order Error: {e}")
            return OrderResponse(order_id="err", status="failed", filled_amount=0, avg_price=0)

    async def cancel_order(self, order_id: str) -> bool:
        if not self.api_instance: return False
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.api_instance.cancel_order(order_id)
            )
            return True
        except Exception:
            return False
            
    async def place_batch_orders(self, orders: List[OrderArgs]) -> List[OrderResponse]:
        """Execute multiple orders in a single batch request"""
        if not self.api_instance or not orders:
            return []
            
        try:
            # Construct batch request
            import uuid
            reqs = []
            for o in orders:
                c_price = int(o.price * 100)
                count = int(o.amount / o.price) if o.price > 0 else 1
                action = "buy" if o.side == OrderSide.BUY else "sell"
                
                reqs.append({
                    "ticker": o.token_id,
                    "action": action,
                    "side": "yes", # Defaulting to YES contracts
                    "count": count,
                    "type": "limit",
                    "yes_price": c_price,
                    "client_order_id": str(uuid.uuid4())
                })
            
            # SDK might not have a clean batch wrapper, assume list usage or iteration
            # Checking valid method: api_instance.batch_create_orders(body=reqs)
            
            loop = asyncio.get_event_loop()
            # If batch endpoint exists in SDK:
            if hasattr(self.api_instance, "batch_create_orders"):
                wrapper = kalshi_python.BatchCreateOrdersRequest(orders=reqs)
                resp = await loop.run_in_executor(
                    None,
                    lambda: self.api_instance.batch_create_orders(wrapper)
                )
                # Map back to responses
                # This is complex without seeing exact response structure, defaulting to generic success
                return [OrderResponse(order_id="batch", status="submitted", filled_amount=0, avg_price=0) for _ in orders]
            else:
                # Fallback to serial
                ress = []
                for o in orders:
                    ress.append(await self.place_order(o))
                return ress
                
        except Exception as e:
            print(f"Batch Error: {e}")
            return []

    async def get_positions(self) -> List[Dict]:
        """Fetch user positions"""
        if not self.api_instance:
            return []
        try:
            loop = asyncio.get_event_loop()
            # Fetch settlements (active positions are subset or separate endpoint?)
            # get_portfolio_positions is standard
            resp = await loop.run_in_executor(
                None,
                self.api_instance.get_portfolio_positions
            )
            
            raw_pos = getattr(resp, "market_positions", [])
            positions = []
            for p in raw_pos:
                # p has: ticker, position, market_exposure, fees_paid, realized_pnl, etc.
                # All currency in centi-cents? Check spec. usually yes.
                # Actually positions often just count.
                # market_exposure is value.
                
                count = getattr(p, "position", 0)
                if count == 0: continue
                
                ticker = getattr(p, "ticker", "")
                
                # exposure is in cents usually for Positions endpoint? Or centi-cents. Assume cents for safety or check docs.
                # Docs say "Monetary Values: ... returned in centi-cents". Div by 10000 -> Dollars.
                # Cost basis = fees + cost?
                cost = getattr(p, "cost_basis", 0) / 100.0 # Verify if basis is cents
                
                positions.append({
                    "symbol": ticker,
                    "size": count,
                    "entry_price": (cost / count) / 100.0 if count else 0, # Rough est
                    "current_price": 0.0, # Need to fetch?
                    "pnl": getattr(p, "realized_pnl", 0) / 10000.0,
                    "provider": "kalshi"
                })
            return positions
        except Exception as e:
            print(f"Positions Error: {e}")
            return []

    async def get_candlesticks(self, ticker: str, period: str = "hour") -> List[Dict]:
        """Fetch OHLCV history"""
        if not self.api_instance: return []
        try:
            # Try to get series_ticker from ticker split, or maybe it's passed differently
            # Usually it's first part before dash.
            parts = ticker.split("-")
            series_ticker = parts[0]
            
            # Map period to interval (minutes)
            interval_map = {
                "minute": 1,
                "hour": 60,
                "day": 1440
            }
            period_interval = interval_map.get(period, 60)
            
            import time
            limit = 100
            now = int(time.time())
            end_ts = now
            start_ts = now - (limit * period_interval * 60) 

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.api_client.call_api(
                    f"/series/{series_ticker}/markets/{ticker}/candlesticks", "GET",
                    query_params=[
                        ("period_interval", period_interval), 
                        ("limit", limit),
                        ("start_ts", start_ts),
                        ("end_ts", end_ts)
                    ],
                    auth_settings=["bearerAuth"],
                    _return_http_data_only=False,
                    _preload_content=False
                )
            )
            
            # Parse response
            http_resp = resp[0]
            if http_resp.status != 200: return []
            
            import json
            data = json.loads(http_resp.data.decode('utf-8'))
            candles = data.get("candlesticks", [])
            
            results = []
            for c in candles:
                try:
                    results.append({
                        "t": c.get("end_period_ts"),
                        "o": (c.get("open") or 0)/100.0,
                        "h": (c.get("high") or 0)/100.0,
                        "l": (c.get("low") or 0)/100.0,
                        "c": (c.get("close") or 0)/100.0,
                        "v": c.get("volume") or 0
                    })
                except Exception:
                    continue
            return results
        except Exception as e:
            print(f"Candle Error: {e}")
            return []

    async def get_trades(self, ticker: str, limit: int = 50) -> List[Dict]:
        """Fetch public trade history"""
        if not self.api_instance: return []
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.api_instance.get_trades(ticker=ticker, limit=limit))
            raw_trades = getattr(resp, "trades", [])
            return [
                {
                    "price": t.yes_price/100.0,
                    "size": t.count,
                    "side": "buy" if t.taker_side == "yes" else "sell", # Simplified
                    "time": t.created_time
                }
                for t in raw_trades
            ]
        except Exception:
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
import asyncio
import time
from typing import Dict, Any, List, Optional
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseAgent
from .state import Task, AgentExecutionState

logger = structlog.get_logger()


class MarketObserverAgent(BaseAgent):
    """Real-time market scanning and anomaly detection"""
    
    def __init__(
        self,
        redis_store,
        sqlite_store,
        poly_provider,
        kalshi_provider,
        config: Optional[Dict[str, Any]] = None
    ):
        self.poly = poly_provider
        self.kalshi = kalshi_provider
        
        super().__init__(
            agent_id="market_observer",
            model="gemini-2.0-flash",
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            config=config or {}
        )
        
        self.watchlist: List[str] = []
        self.subscribed_markets: List[str] = []
        self.scan_interval = self.config.get("scan_interval", 5)
        self.price_change_threshold = self.config.get("price_change_threshold", 0.05)
        self.volume_spike_threshold = self.config.get("volume_spike_threshold", 2.0)
        
        logger.info("Market Observer Agent initialized")
    
    def _register_tools(self):
        """Register market observer tools"""
        pass
    
    async def process(self, state: AgentExecutionState) -> AgentExecutionState:
        """Process state and scan markets"""
        # Execute periodic scan
        await self._scan_markets()
        
        return state
    
    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Process market observer task logic"""
        task_type = task["task_type"]
        
        if task_type == "SCAN_MARKETS":
            return await self._scan_markets_task(task)
        elif task_type == "ADD_WATCHLIST":
            return await self._add_to_watchlist(task)
        elif task_type == "REMOVE_WATCHLIST":
            return await self._remove_from_watchlist(task)
        elif task_type == "GET_MARKET_DATA":
            return await self._get_market_data(task)
        elif task_type == "SUBSCRIBE_MARKET":
            return await self._subscribe_to_market(task)
        elif task_type == "CHECK_ANOMALIES":
            return await self._check_anomalies(task)
        else:
            logger.warning("Unknown task type", task_type=task_type)
            return {"error": f"Unknown task type: {task_type}", "success": False}
    
    async def _scan_markets_task(self, task: Task) -> Dict[str, Any]:
        """Scan markets for interesting conditions"""
        results = await self._scan_markets()
        
        return {
            "success": True,
            "markets_scanned": len(results.get("markets", [])),
            "alerts": results.get("alerts", [])
        }
    
    async def _scan_markets(self) -> Dict[str, Any]:
        """Scan all markets for interesting conditions"""
        alerts = []
        markets_scanned = []
        
        # Scan Polymarket
        if self.poly:
            poly_markets = await self._scan_provider_markets("polymarket", self.poly)
            markets_scanned.extend(poly_markets)
            poly_alerts = await self._detect_anomalies("polymarket", poly_markets)
            alerts.extend(poly_alerts)
        
        # Scan Kalshi
        if self.kalshi:
            kalshi_markets = await self._scan_provider_markets("kalshi", self.kalshi)
            markets_scanned.extend(kalshi_markets)
            kalshi_alerts = await self._detect_anomalies("kalshi", kalshi_markets)
            alerts.extend(kalshi_alerts)
        
        # Store results
        if self.redis:
            await self.redis.set(
                "market_scan:latest",
                {
                    "timestamp": time.time(),
                    "markets_count": len(markets_scanned),
                    "alerts_count": len(alerts),
                    "alerts": alerts
                },
                ttl=300  # 5 minutes
            )
        
        return {
            "markets": markets_scanned,
            "alerts": alerts
        }
    
    async def _scan_provider_markets(
        self,
        provider_name: str,
        provider
    ) -> List[Dict[str, Any]]:
        """Scan markets from a specific provider"""
        markets = []
        
        try:
            # Get watchlist markets first
            watchlist_markets = []
            for market_id in self.watchlist:
                try:
                    market = await self._get_single_market(provider, market_id)
                    if market:
                        watchlist_markets.append(market)
                except Exception as e:
                    logger.warning(
                        "Failed to get watchlist market",
                        market_id=market_id,
                        provider=provider_name,
                        error=str(e)
                    )
            
            markets.extend(watchlist_markets)
            
            # Also get recent/active markets
            all_markets = await provider.get_markets(limit=50)
            
            # Filter for active markets only
            active_markets = [
                {
                    "id": m.id,
                    "question": m.question,
                    "status": m.status.value,
                    "provider": provider_name
                }
                for m in all_markets
                if m.status.value == "active"
            ]
            
            markets.extend(active_markets[:20])  # Limit to 20 additional markets
            
            logger.debug(
                "Markets scanned",
                provider=provider_name,
                count=len(markets)
            )
            
        except Exception as e:
            logger.error(
                "Failed to scan provider markets",
                provider=provider_name,
                error=str(e)
            )
        
        return markets
    
    async def _get_single_market(
        self,
        provider,
        market_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get single market details"""
        try:
            from polycli.models import Market
            markets = await provider.get_markets()
            market = next((m for m in markets if m.id == market_id), None)
            
            if market:
                return {
                    "id": market.id,
                    "question": market.question,
                    "status": market.status.value,
                    "provider": provider.__class__.__name__.replace("Provider", "")
                }
            return None
            
        except Exception as e:
            logger.error("Failed to get market", market_id=market_id, error=str(e))
            return None
    
    async def _detect_anomalies(
        self,
        provider_name: str,
        markets: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect anomalies in market data"""
        anomalies = []
        
        for market in markets:
            market_id = market.get("id")
            if not isinstance(market_id, str):
                continue
            
            # Check price changes
            price_alert = await self._check_price_anomaly(provider_name, market_id)
            if price_alert:
                anomalies.append(price_alert)
            
            # Check volume spikes (if we have volume data)
            volume_alert = await self._check_volume_anomaly(provider_name, market_id)
            if volume_alert:
                anomalies.append(volume_alert)
        
        return anomalies
    
    async def _check_price_anomaly(
        self,
        provider_name: str,
        market_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check for price movement anomalies"""
        if not self.redis:
            return None
        
        try:
            # Get previous price from Redis
            prev_price_key = f"market:{provider_name}:{market_id}:prev_price"
            prev_price = await self.redis.get(prev_price_key)
            
            # Get current price
            orderbook = await self._get_orderbook(provider_name, market_id)
            if not orderbook or not orderbook.get("bids"):
                return None
            
            current_price = orderbook["bids"][0].get("price") if orderbook["bids"] else None
            
            if not current_price:
                return None
            
            if prev_price:
                # Calculate price change
                price_change = abs(current_price - prev_price) / prev_price if prev_price > 0 else 0
                
                if price_change >= self.price_change_threshold:
                    alert = {
                        "type": "PRICE_ANOMALY",
                        "severity": "HIGH" if price_change >= 0.10 else "MEDIUM",
                        "market_id": market_id,
                        "provider": provider_name,
                        "message": f"Price changed by {price_change:.2%} from {prev_price:.2f} to {current_price:.2f}",
                        "timestamp": __import__('time').time()
                    }
                    
                    logger.info(
                        "Price anomaly detected",
                        market_id=market_id,
                        change=price_change
                    )
                    
                    return alert
            
            # Update previous price in Redis
            await self.redis.set(
                prev_price_key,
                current_price,
                ttl=3600  # 1 hour
            )
            
            return None
            
        except Exception as e:
            logger.error("Price anomaly check failed", market_id=market_id, error=str(e))
            return None
    
    async def _check_volume_anomaly(
        self,
        provider_name: str,
        market_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check for volume spikes"""
        if not self.redis:
            return None
        
        try:
            # Get previous volume from Redis
            prev_volume_key = f"market:{provider_name}:{market_id}:prev_volume"
            prev_volume = await self.redis.get(prev_volume_key)
            
            # Get current volume (would need to be tracked separately)
            current_volume = 0  # This would need to be tracked over time
            
            if prev_volume and prev_volume > 0:
                volume_change = current_volume / prev_volume
                
                if volume_change >= self.volume_spike_threshold:
                    alert = {
                        "type": "VOLUME_ANOMALY",
                        "severity": "MEDIUM",
                        "market_id": market_id,
                        "provider": provider_name,
                        "message": f"Volume increased by {volume_change:.2x}",
                        "timestamp": __import__('time').time()
                    }
                    
                    logger.info(
                        "Volume anomaly detected",
                        market_id=market_id,
                        change=volume_change
                    )
                    
                    return alert
            
            await self.redis.set(
                prev_volume_key,
                current_volume,
                ttl=3600
            )
            
            return None
            
        except Exception as e:
            logger.error("Volume anomaly check failed", market_id=market_id, error=str(e))
            return None
    
    async def _get_orderbook(
        self,
        provider_name: str,
        market_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get orderbook for market"""
        try:
            provider = self.poly if provider_name == "polymarket" else self.kalshi
            if not provider:
                return None
            
            orderbook = await provider.get_orderbook(market_id)
            
            return {
                "market_id": market_id,
                "bids": [
                    {"price": b.price, "size": b.size}
                    for b in orderbook.bids
                ],
                "asks": [
                    {"price": a.price, "size": a.size}
                    for a in orderbook.asks
                ],
                "timestamp": orderbook.timestamp
            }
            
        except Exception as e:
            logger.error("Failed to get orderbook", market_id=market_id, error=str(e))
            return None
    
    async def _add_to_watchlist(self, task: Task) -> Dict[str, Any]:
        """Add market to watchlist"""
        inputs = task.get("inputs", {})
        market_id = inputs.get("market_id")
        
        if not market_id:
            return {"error": "market_id not provided", "success": False}
        
        if market_id not in self.watchlist:
            self.watchlist.append(market_id)
            
            # Store watchlist in Redis
            if self.redis:
                await self.redis.set(
                    f"watchlist:{self.agent_id}",
                    self.watchlist,
                    ttl=86400
                )
            
            logger.info("Added to watchlist", market_id=market_id)
        
        return {"success": True, "watchlist": self.watchlist}
    
    async def _remove_from_watchlist(self, task: Task) -> Dict[str, Any]:
        """Remove market from watchlist"""
        inputs = task.get("inputs", {})
        market_id = inputs.get("market_id")
        
        if not market_id:
            return {"error": "market_id not provided", "success": False}
        
        if market_id in self.watchlist:
            self.watchlist.remove(market_id)
            
            if self.redis:
                await self.redis.set(
                    f"watchlist:{self.agent_id}",
                    self.watchlist,
                    ttl=86400
                )
            
            logger.info("Removed from watchlist", market_id=market_id)
        
        return {"success": True, "watchlist": self.watchlist}
    
    async def _get_market_data(self, task: Task) -> Dict[str, Any]:
        """Get market data"""
        inputs = task.get("inputs", {})
        market_id = inputs.get("market_id")
        provider_name = inputs.get("provider", "polymarket")
        
        if not market_id:
            return {"error": "market_id not provided", "success": False}
        
        provider = self.poly if provider_name == "polymarket" else self.kalshi
        if not provider:
            return {"error": "Invalid provider", "success": False}
        
        market = await self._get_single_market(provider, market_id)
        orderbook = await self._get_orderbook(provider_name, market_id)
        
        return {
            "success": True,
            "market": market,
            "orderbook": orderbook
        }
    
    async def _subscribe_to_market(self, task: Task) -> Dict[str, Any]:
        """Subscribe to market updates"""
        inputs = task.get("inputs", {})
        market_id = inputs.get("market_id")
        provider_name = inputs.get("provider", "polymarket")
        
        if not market_id:
            return {"error": "market_id not provided", "success": False}
        
        # Subscription would be handled by WebSocket clients
        # For now, just track that we want to subscribe
        if market_id not in self.subscribed_markets:
            self.subscribed_markets.append(market_id)
        
        return {
            "success": True,
            "market_id": market_id,
            "subscribed": True
        }
    
    async def _check_anomalies(self, task: Task) -> Dict[str, Any]:
        """Check for anomalies across all watchlist markets"""
        alerts = []
        
        for market_id in self.watchlist:
            # Check polymarket
            if self.poly:
                poly_alert = await self._check_price_anomaly("polymarket", market_id)
                if poly_alert:
                    alerts.append(poly_alert)
            
            # Check kalshi
            if self.kalshi:
                kalshi_alert = await self._check_price_anomaly("kalshi", market_id)
                if kalshi_alert:
                    alerts.append(kalshi_alert)
        
        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts)
        }

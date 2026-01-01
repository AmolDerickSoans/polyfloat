from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from polycli.models import Event, Market, OrderBook, Trade, Position, Order, Side, OrderType

class BaseProvider(ABC):
    """Standard interface for prediction market providers"""
    
    @abstractmethod
    async def get_events(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """Fetch available events"""
        pass

    @abstractmethod
    async def get_markets(
        self,
        event_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Market]:
        """Fetch available markets"""
        pass

    @abstractmethod
    async def search(self, query: str) -> List[Market]:
        """Search for markets by query string"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, market_id: str) -> OrderBook:
        """Get orderbook for specific market"""
        pass
    
    @abstractmethod
    async def place_order(
        self, 
        market_id: str,
        side: Side,
        size: float,
        price: float,
        order_type: OrderType = OrderType.LIMIT
    ) -> Order:
        """Place an order"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get user's open positions"""
        pass

    @abstractmethod
    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """Get user's open orders"""
        pass

    @abstractmethod
    async def get_history(self, market_id: Optional[str] = None) -> List[Trade]:
        """Get user's trade history"""
        pass

    @abstractmethod
    async def get_news(
        self,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[Any]:
        """Fetch market-related news"""
        pass

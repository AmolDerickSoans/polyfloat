from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Optional, Dict
from enum import Enum

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    FOK = "FOK"  # Fill or Kill
    GTC = "GTC"  # Good Till Cancel

class MarketData(BaseModel):
    token_id: str
    title: str
    description: Optional[str] = None
    price: float
    volume_24h: float
    liquidity: float
    end_date: Optional[str] = None
    provider: str
    extra_data: Optional[Dict] = None

class OrderArgs(BaseModel):
    token_id: str
    side: OrderSide
    amount: float
    price: Optional[float] = None
    order_type: OrderType = OrderType.MARKET

class OrderResponse(BaseModel):
    order_id: str
    status: str
    filled_amount: float
    avg_price: float

class BaseProvider(ABC):
    """Standard interface for prediction market providers"""
    
    @abstractmethod
    async def get_markets(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[MarketData]:
        """Fetch available markets"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, token_id: str) -> Dict:
        """Get orderbook for specific market"""
        pass
    
    @abstractmethod
    async def place_order(self, order: OrderArgs) -> OrderResponse:
        """Place an order"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Dict]:
        """Get user's open positions"""
        pass

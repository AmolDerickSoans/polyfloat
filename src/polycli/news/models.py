from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class SourceType(str, Enum):
    NITTER = "nitter"
    RSS = "rss"


class CategoryType(str, Enum):
    POLITICS = "politics"
    CRYPTO = "crypto"
    ECONOMICS = "economics"
    SPORTS = "sports"
    OTHER = "other"


class NewsItem(BaseModel):
    id: str
    source: SourceType
    source_account: Optional[str] = None
    title: Optional[str] = None
    content: str
    url: str
    published_at: float

    impact_score: float = Field(default=0.0, ge=0.0, le=100.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=100.0)

    tickers: List[str] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)
    category: Optional[CategoryType] = None
    tags: List[str] = Field(default_factory=list)


class UserSubscription(BaseModel):
    user_id: str
    categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    impact_threshold: int = 70


class SystemStats(BaseModel):
    total_news_items: int = 0
    items_last_24h: int = 0
    average_impact: float = 0.0
    active_connections: int = 0

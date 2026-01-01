"""
News Alerts System - Real-time notifications for high-impact news
Supports impact thresholds, position-based alerts, and keyword triggers.
"""

from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import structlog
import time

logger = structlog.get_logger()


class AlertPriority(Enum):
    """Alert priority levels"""
    BREAKING = "breaking"  # Impact >= 80
    HIGH = "high"          # Impact >= 60
    MEDIUM = "medium"      # Impact >= 40
    LOW = "low"            # Impact < 40


@dataclass
class AlertConfig:
    """User alert configuration"""
    user_id: str
    impact_threshold: int = 70  # Minimum impact to trigger alert
    categories: List[str] = field(default_factory=list)  # Empty = all categories
    keywords: List[str] = field(default_factory=list)  # Custom keyword triggers
    tickers: List[str] = field(default_factory=list)  # Ticker symbols to track
    people: List[str] = field(default_factory=list)  # People to track
    enabled: bool = True
    auto_trigger_agent: bool = False  # Future: trigger agent analysis on breaking news


@dataclass
class NewsAlert:
    """A triggered news alert"""
    alert_id: str
    news_item: Dict[str, Any]
    priority: AlertPriority
    trigger_reason: str
    timestamp: float
    acknowledged: bool = False


class NewsAlertManager:
    """
    Manages news alerts and subscriptions.
    Connects to WebSocket client and triggers callbacks on matching news.
    """
    
    def __init__(self, ws_client=None, api_client=None):
        self.ws_client = ws_client
        self.api_client = api_client
        self.configs: Dict[str, AlertConfig] = {}
        self.pending_alerts: Dict[str, List[NewsAlert]] = {}  # user_id -> alerts
        self.alert_callbacks: List[Callable] = []
        self._alert_counter = 0
        self._seen_news_ids: Set[str] = set()
        
        # Connect to WebSocket if available
        if ws_client:
            ws_client.add_callback("news_item", self._on_news_item)
            logger.info("NewsAlertManager connected to WebSocket")
    
    def add_config(self, config: AlertConfig) -> None:
        """Add or update user alert configuration"""
        self.configs[config.user_id] = config
        self.pending_alerts.setdefault(config.user_id, [])
        logger.debug("Alert config added", user_id=config.user_id)
    
    def remove_config(self, user_id: str) -> None:
        """Remove user alert configuration"""
        self.configs.pop(user_id, None)
        self.pending_alerts.pop(user_id, None)
    
    def add_callback(self, callback: Callable) -> None:
        """Add callback for alert notifications"""
        self.alert_callbacks.append(callback)
    
    def get_pending_alerts(self, user_id: str) -> List[NewsAlert]:
        """Get unacknowledged alerts for a user"""
        return [a for a in self.pending_alerts.get(user_id, []) if not a.acknowledged]
    
    def acknowledge_alert(self, user_id: str, alert_id: str) -> bool:
        """Mark an alert as acknowledged"""
        alerts = self.pending_alerts.get(user_id, [])
        for alert in alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def acknowledge_all(self, user_id: str) -> int:
        """Acknowledge all pending alerts for a user"""
        count = 0
        for alert in self.pending_alerts.get(user_id, []):
            if not alert.acknowledged:
                alert.acknowledged = True
                count += 1
        return count
    
    def clear_old_alerts(self, max_age_hours: int = 24) -> int:
        """Remove alerts older than max_age_hours"""
        cutoff = time.time() - (max_age_hours * 3600)
        removed = 0
        
        for user_id in self.pending_alerts:
            original_count = len(self.pending_alerts[user_id])
            self.pending_alerts[user_id] = [
                a for a in self.pending_alerts[user_id] 
                if a.timestamp > cutoff
            ]
            removed += original_count - len(self.pending_alerts[user_id])
        
        return removed
    
    async def _on_news_item(self, news_data: Dict[str, Any]) -> None:
        """Handle incoming news from WebSocket"""
        news_id = news_data.get("id")
        
        # Deduplicate
        if news_id in self._seen_news_ids:
            return
        self._seen_news_ids.add(news_id)
        
        # Keep seen set manageable
        if len(self._seen_news_ids) > 1000:
            self._seen_news_ids = set(list(self._seen_news_ids)[-500:])
        
        # Check against all user configs
        for user_id, config in self.configs.items():
            if not config.enabled:
                continue
            
            match_result = self._matches_config(news_data, config)
            if match_result:
                alert = self._create_alert(news_data, match_result)
                self.pending_alerts[user_id].append(alert)
                
                # Trigger callbacks
                for callback in self.alert_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(user_id, alert)
                        else:
                            callback(user_id, alert)
                    except Exception as e:
                        logger.error("Alert callback failed", error=str(e))
                
                logger.info(
                    "Alert triggered",
                    user_id=user_id,
                    priority=alert.priority.value,
                    reason=alert.trigger_reason
                )
    
    def _matches_config(self, news_data: Dict[str, Any], config: AlertConfig) -> Optional[str]:
        """Check if news matches user config. Returns match reason or None."""
        impact = news_data.get("impact_score", 0)
        
        # Check impact threshold
        if impact < config.impact_threshold:
            return None
        
        category = news_data.get("category", "")
        title = (news_data.get("title") or "").lower()
        content = (news_data.get("content") or "").lower()
        news_tickers = [t.upper() for t in news_data.get("tickers", [])]
        news_people = [p.lower() for p in news_data.get("people", [])]
        
        # Check category filter (empty = all)
        if config.categories and category not in config.categories:
            return None
        
        # Check ticker match
        for ticker in config.tickers:
            if ticker.upper() in news_tickers:
                return f"Ticker match: ${ticker}"
        
        # Check people match
        for person in config.people:
            if person.lower() in news_people:
                return f"Person match: {person}"
        
        # Check keyword match
        for keyword in config.keywords:
            kw_lower = keyword.lower()
            if kw_lower in title or kw_lower in content:
                return f"Keyword match: {keyword}"
        
        # If no specific filters, just the impact threshold
        if not config.tickers and not config.people and not config.keywords:
            return f"Impact: {impact}"
        
        return None
    
    def _create_alert(self, news_data: Dict[str, Any], trigger_reason: str) -> NewsAlert:
        """Create an alert from news data"""
        self._alert_counter += 1
        impact = news_data.get("impact_score", 0)
        
        if impact >= 80:
            priority = AlertPriority.BREAKING
        elif impact >= 60:
            priority = AlertPriority.HIGH
        elif impact >= 40:
            priority = AlertPriority.MEDIUM
        else:
            priority = AlertPriority.LOW
        
        return NewsAlert(
            alert_id=f"alert_{self._alert_counter}_{int(time.time())}",
            news_item=news_data,
            priority=priority,
            trigger_reason=trigger_reason,
            timestamp=time.time()
        )
    
    def get_priority_color(self, priority: AlertPriority) -> str:
        """Get terminal color for priority level"""
        colors = {
            AlertPriority.BREAKING: "red",
            AlertPriority.HIGH: "yellow",
            AlertPriority.MEDIUM: "cyan",
            AlertPriority.LOW: "white"
        }
        return colors.get(priority, "white")
    
    def format_alert(self, alert: NewsAlert) -> str:
        """Format alert for terminal display"""
        priority_icons = {
            AlertPriority.BREAKING: "🔴 BREAKING",
            AlertPriority.HIGH: "🟡 HIGH",
            AlertPriority.MEDIUM: "🔵 MEDIUM",
            AlertPriority.LOW: "⚪ LOW"
        }
        
        icon = priority_icons.get(alert.priority, "⚪")
        title = alert.news_item.get("title") or alert.news_item.get("content", "")[:60]
        
        return f"{icon}: {title[:50]}... ({alert.trigger_reason})"


class PositionAlertManager:
    """
    Specialized alert manager for position-based news.
    Tracks user's market positions and alerts on related news.
    """
    
    def __init__(self, alert_manager: NewsAlertManager):
        self.alert_manager = alert_manager
        self.position_entities: Dict[str, Dict[str, Any]] = {}  # user_id -> entities
    
    def update_positions(self, user_id: str, positions: List[Dict[str, Any]]) -> None:
        """Update tracked entities based on user positions"""
        entities = {"tickers": set(), "people": set(), "keywords": set()}
        
        for position in positions:
            question = position.get("question", "")
            
            # Extract entities from market questions
            for ticker in ["BTC", "ETH", "SOL", "ADA", "DOGE", "XRP"]:
                if ticker.upper() in question.upper():
                    entities["tickers"].add(ticker)
            
            for person in ["Trump", "Biden", "Harris", "Musk", "Powell"]:
                if person.lower() in question.lower():
                    entities["people"].add(person)
        
        self.position_entities[user_id] = {
            "tickers": list(entities["tickers"]),
            "people": list(entities["people"]),
            "keywords": list(entities["keywords"])
        }
        
        # Update user's alert config with position entities
        if user_id in self.alert_manager.configs:
            config = self.alert_manager.configs[user_id]
            config.tickers = list(entities["tickers"])
            config.people = list(entities["people"])
            logger.debug("Position entities updated", user_id=user_id, entities=entities)


# Default terminal user config
DEFAULT_TERMINAL_CONFIG = AlertConfig(
    user_id="terminal_user",
    impact_threshold=70,
    categories=[],  # All categories
    keywords=["breaking", "urgent", "alert"],
    enabled=True,
    auto_trigger_agent=False
)

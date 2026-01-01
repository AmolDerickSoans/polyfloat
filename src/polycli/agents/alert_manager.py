import time
from typing import Dict, Any, List, Optional
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseAgent
from .state import Task, AgentExecutionState, AgentAlert

logger = structlog.get_logger()


class AlertManagerAgent(BaseAgent):
    """Alert monitoring, threshold checking, and notification dispatch"""
    
    def __init__(
        self,
        redis_store,
        sqlite_store,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            agent_id="alert_manager",
            model="gemini-2.0-flash",
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            config=config
        )
        
        self.alerts: List[AgentAlert] = []
        self.alert_rules: Dict[str, Dict[str, Any]] = self._init_default_rules()
        self.notification_channels: List[str] = ["tui"]
        self.alert_aggregation_window = self.config.get("aggregation_window", 60)  # seconds
        self.alert_aggregation: Dict[str, List[AgentAlert]] = {}
        
        logger.info("Alert Manager Agent initialized")
    
    def _init_default_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize default alert rules"""
        return {
            "price_change": {
                "enabled": True,
                "threshold": 0.10,
                "severity": "MEDIUM",
                "description": "Price change threshold"
            },
            "volume_spike": {
                "enabled": True,
                "threshold": 2.0,
                "severity": "MEDIUM",
                "description": "Volume spike multiplier"
            },
            "arb_opportunity": {
                "enabled": True,
                "threshold": 0.02,
                "severity": "HIGH",
                "description": "Arbitrage opportunity edge"
            },
            "risk_limit": {
                "enabled": True,
                "threshold": 0.90,
                "severity": "HIGH",
                "description": "Risk limit utilization"
            },
            "circuit_breaker": {
                "enabled": True,
                "severity": "CRITICAL",
                "description": "Circuit breaker triggered"
            }
        }
    
    def _register_tools(self):
        """Register alert manager tools"""
        pass
    
    async def process(self, state: AgentExecutionState) -> AgentExecutionState:
        """Process alerts and dispatch notifications"""
        # Check for stale alerts
        await self._cleanup_stale_alerts()
        
        # Aggregate alerts
        await self._aggregate_alerts()
        
        return state
    
    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Process alert manager task logic"""
        task_type = task["task_type"]
        
        if task_type == "CREATE_ALERT":
            return await self._create_alert(task)
        elif task_type == "CHECK_THRESHOLDS":
            return await self._check_thresholds(task)
        elif task_type == "SEND_NOTIFICATION":
            return await self._send_notification(task)
        elif task_type == "ACKNOWLEDGE_ALERT":
            return await self._acknowledge_alert(task)
        elif task_type == "RESOLVE_ALERT":
            return await self._resolve_alert(task)
        elif task_type == "UPDATE_RULE":
            return await self._update_alert_rule(task)
        elif task_type == "GET_ALERTS":
            return await self._get_alerts(task)
        elif task_type == "ADD_CHANNEL":
            return await self._add_notification_channel(task)
        elif task_type == "REMOVE_CHANNEL":
            return await self._remove_notification_channel(task)
        else:
            logger.warning("Unknown task type", task_type=task_type)
            return {"error": f"Unknown task type: {task_type}", "success": False}
    
    async def _create_alert(self, task: Task) -> Dict[str, Any]:
        """Create a new alert"""
        inputs = task.get("inputs", {})
        
        alert_id = str(task.get("task_id"))
        severity = inputs.get("severity", "INFO")
        category = inputs.get("category", "general")
        message = inputs.get("message", "")
        source = inputs.get("source", "system")
        data = inputs.get("data")
        
        alert = AgentAlert(
            alert_id=alert_id,
            timestamp=time.time(),
            severity=severity,
            category=category,
            message=message,
            source=source,
            data=data,
            acknowledged=False,
            resolved=False
        )
        
        self.alerts.append(alert)
        
        # Store in Redis
        if self.redis:
            await self.redis.hset(
                f"alert:{alert_id}",
                "data",
                alert
            )
            await self.redis.lpush("alerts:recent", alert_id)
        
        # Store in SQLite
        if self.sqlite:
            await self.sqlite.set(
                f"alert:{alert_id}",
                alert
            )
        
        # Send notification
        await self._dispatch_alert(alert)
        
        logger.info(
            "Alert created",
            alert_id=alert_id,
            severity=severity,
            category=category,
            message=message
        )
        
        return {"success": True, "alert_id": alert_id, "alert": alert}
    
    async def _check_thresholds(self, task: Task) -> Dict[str, Any]:
        """Check all configured thresholds"""
        inputs = task.get("inputs", {})
        metrics = inputs.get("metrics", {})
        
        triggered_alerts = []
        
        # Check price change threshold
        if self.alert_rules["price_change"]["enabled"]:
            price_change = metrics.get("price_change", 0)
            threshold = self.alert_rules["price_change"]["threshold"]
            
            if abs(price_change) >= threshold:
                alert = await self._create_threshold_alert(
                    "price_change",
                    f"Price change: {price_change:.2%}",
                    {"price_change": price_change, "threshold": threshold}
                )
                triggered_alerts.append(alert)
        
        # Check volume spike threshold
        if self.alert_rules["volume_spike"]["enabled"]:
            volume_change = metrics.get("volume_change", 0)
            threshold = self.alert_rules["volume_spike"]["threshold"]
            
            if volume_change >= threshold:
                alert = await self._create_threshold_alert(
                    "volume_spike",
                    f"Volume spike: {volume_change:.2x}",
                    {"volume_change": volume_change, "threshold": threshold}
                )
                triggered_alerts.append(alert)
        
        # Check arbitrage opportunity
        if self.alert_rules["arb_opportunity"]["enabled"]:
            arb_edge = metrics.get("arb_edge", 0)
            threshold = self.alert_rules["arb_opportunity"]["threshold"]
            
            if arb_edge >= threshold:
                alert = await self._create_threshold_alert(
                    "arb_opportunity",
                    f"Arbitrage edge: {arb_edge:.2%}",
                    {"arb_edge": arb_edge, "threshold": threshold}
                )
                triggered_alerts.append(alert)
        
        # Check risk limits
        if self.alert_rules["risk_limit"]["enabled"]:
            risk_used = metrics.get("risk_used", 0)
            threshold = self.alert_rules["risk_limit"]["threshold"]
            
            if risk_used >= threshold:
                alert = await self._create_threshold_alert(
                    "risk_limit",
                    f"Risk limit: {risk_used:.1%} used",
                    {"risk_used": risk_used, "threshold": threshold}
                )
                triggered_alerts.append(alert)
        
        return {
            "success": True,
            "triggered_alerts": triggered_alerts,
            "count": len(triggered_alerts)
        }
    
    async def _create_threshold_alert(
        self,
        rule_name: str,
        message: str,
        data: Dict[str, Any]
    ) -> AgentAlert:
        """Create a threshold-triggered alert"""
        rule_config = self.alert_rules.get(rule_name, {})
        
        alert_id = f"threshold:{rule_name}:{int(time.time())}"
        
        alert = AgentAlert(
            alert_id=alert_id,
            timestamp=time.time(),
            severity=rule_config.get("severity", "INFO"),
            category="threshold",
            message=message,
            source="alert_manager",
            data=data,
            acknowledged=False,
            resolved=False
        )
        
        self.alerts.append(alert)
        
        # Store
        if self.redis:
            await self.redis.hset(
                f"alert:{alert_id}",
                "data",
                alert
            )
        
        # Dispatch
        await self._dispatch_alert(alert)
        
        return alert
    
    async def _send_notification(self, task: Task) -> Dict[str, Any]:
        """Send notification via configured channels"""
        inputs = task.get("inputs", {})
        alert_id = inputs.get("alert_id")
        channels = inputs.get("channels", self.notification_channels)
        
        # Get alert data
        alert_data = None
        if self.redis and alert_id:
            alert_data = await self.redis.hget(f"alert:{alert_id}", "data")
        
        if not alert_data and alert_id:
            # Try to find in local alerts
            alert_data = next(
                (a for a in self.alerts if a["alert_id"] == alert_id),
                None
            )
        
        if not alert_data:
            return {"error": "Alert not found", "success": False}
        
        # Send via each channel
        results = []
        for channel in channels:
            try:
                result = await self._dispatch_to_channel(channel, alert_data)
                results.append({"channel": channel, "success": True})
            except Exception as e:
                logger.error(
                    "Failed to send notification",
                    channel=channel,
                    error=str(e)
                )
                results.append({
                    "channel": channel,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "channels": channels,
            "results": results
        }
    
    async def _dispatch_to_channel(
        self,
        channel: str,
        alert: AgentAlert
    ) -> bool:
        """Dispatch alert to specific channel"""
        if channel == "tui":
            # Publish to TUI via Redis pub/sub
            if self.redis:
                await self.redis.publish("tui:alerts", alert)
            return True
        elif channel == "email":
            # Email notification would be implemented here
            logger.warning("Email notifications not implemented")
            return False
        elif channel == "slack":
            # Slack notifications would be implemented here
            logger.warning("Slack notifications not implemented")
            return False
        else:
            logger.warning("Unknown notification channel", channel=channel)
            return False
    
    async def _dispatch_alert(self, alert: AgentAlert):
        """Dispatch alert to all configured channels"""
        for channel in self.notification_channels:
            try:
                await self._dispatch_to_channel(channel, alert)
            except Exception as e:
                logger.error(
                    "Failed to dispatch alert",
                    channel=channel,
                    alert_id=alert["alert_id"],
                    error=str(e)
                )
    
    async def _acknowledge_alert(self, task: Task) -> Dict[str, Any]:
        """Acknowledge an alert"""
        inputs = task.get("inputs", {})
        alert_id = inputs.get("alert_id")
        
        if not alert_id:
            return {"error": "alert_id not provided", "success": False}
        
        # Find and update alert
        updated = False
        for alert in self.alerts:
            if alert["alert_id"] == alert_id:
                alert["acknowledged"] = True
                updated = True
                break
        
        if updated and self.redis:
            await self.redis.hset(
                f"alert:{alert_id}",
                "acknowledged",
                True
            )
        
        logger.info("Alert acknowledged", alert_id=alert_id)
        
        return {"success": True, "alert_id": alert_id}
    
    async def _resolve_alert(self, task: Task) -> Dict[str, Any]:
        """Mark an alert as resolved"""
        inputs = task.get("inputs", {})
        alert_id = inputs.get("alert_id")
        
        if not alert_id:
            return {"error": "alert_id not provided", "success": False}
        
        # Find and update alert
        updated = False
        for alert in self.alerts:
            if alert["alert_id"] == alert_id:
                alert["resolved"] = True
                alert["acknowledged"] = True
                updated = True
                break
        
        if updated and self.redis:
            await self.redis.hset(
                f"alert:{alert_id}",
                "resolved",
                True
            )
            await self.redis.hset(
                f"alert:{alert_id}",
                "acknowledged",
                True
            )
        
        logger.info("Alert resolved", alert_id=alert_id)
        
        return {"success": True, "alert_id": alert_id}
    
    async def _update_alert_rule(self, task: Task) -> Dict[str, Any]:
        """Update an alert rule"""
        inputs = task.get("inputs", {})
        rule_name = inputs.get("rule_name")
        
        if not rule_name:
            return {"error": "rule_name not provided", "success": False}
        
        if rule_name not in self.alert_rules:
            return {"error": "Rule not found", "success": False}
        
        # Update rule
        updates = {
            k: v for k, v in inputs.items()
            if k not in ["rule_name", "task_id", "task_type", "inputs"]
        }
        
        self.alert_rules[rule_name].update(updates)
        
        # Store in Redis
        if self.redis:
            await self.redis.hset(
                f"alert:rules",
                rule_name,
                self.alert_rules[rule_name]
            )
        
        logger.info("Alert rule updated", rule_name=rule_name, updates=updates)
        
        return {"success": True, "rule_name": rule_name, "rule": self.alert_rules[rule_name]}
    
    async def _get_alerts(self, task: Task) -> Dict[str, Any]:
        """Get alerts with optional filters"""
        inputs = task.get("inputs", {})
        severity = inputs.get("severity")
        category = inputs.get("category")
        acknowledged = inputs.get("acknowledged")
        resolved = inputs.get("resolved")
        limit = inputs.get("limit", 100)
        
        # Filter alerts
        filtered_alerts = self.alerts.copy()
        
        if severity:
            filtered_alerts = [a for a in filtered_alerts if a["severity"] == severity]
        
        if category:
            filtered_alerts = [a for a in filtered_alerts if a["category"] == category]
        
        if acknowledged is not None:
            filtered_alerts = [a for a in filtered_alerts if a["acknowledged"] == acknowledged]
        
        if resolved is not None:
            filtered_alerts = [a for a in filtered_alerts if a["resolved"] == resolved]
        
        # Sort by timestamp descending and limit
        filtered_alerts.sort(key=lambda x: x["timestamp"], reverse=True)
        filtered_alerts = filtered_alerts[:limit]
        
        return {
            "success": True,
            "alerts": filtered_alerts,
            "count": len(filtered_alerts)
        }
    
    async def _add_notification_channel(self, task: Task) -> Dict[str, Any]:
        """Add a notification channel"""
        inputs = task.get("inputs", {})
        channel = inputs.get("channel")
        
        if not channel:
            return {"error": "channel not provided", "success": False}
        
        if channel not in self.notification_channels:
            self.notification_channels.append(channel)
            
            # Store in Redis
            if self.redis:
                await self.redis.set(
                    f"alert:channels",
                    self.notification_channels,
                    ttl=86400
                )
            
            logger.info("Notification channel added", channel=channel)
        
        return {"success": True, "channels": self.notification_channels}
    
    async def _remove_notification_channel(self, task: Task) -> Dict[str, Any]:
        """Remove a notification channel"""
        inputs = task.get("inputs", {})
        channel = inputs.get("channel")
        
        if not channel:
            return {"error": "channel not provided", "success": False}
        
        if channel in self.notification_channels:
            self.notification_channels.remove(channel)
            
            # Store in Redis
            if self.redis:
                await self.redis.set(
                    f"alert:channels",
                    self.notification_channels,
                    ttl=86400
                )
            
            logger.info("Notification channel removed", channel=channel)
        
        return {"success": True, "channels": self.notification_channels}
    
    async def _aggregate_alerts(self):
        """Aggregate similar alerts to reduce noise"""
        current_time = time.time()
        
        # Clean up old aggregations
        for alert_id in list(self.alert_aggregation.keys()):
            aggregated = self.alert_aggregation[alert_id]
            if aggregated and current_time - aggregated[0].get("timestamp", 0) > self.alert_aggregation_window:
                del self.alert_aggregation[alert_id]
        
        # Aggregate by category and message similarity
        # For simplicity, just count alerts per category in window
        category_counts: Dict[str, int] = {}
        
        for alert in self.alerts:
            if current_time - alert["timestamp"] <= self.alert_aggregation_window:
                category = alert["category"]
                category_counts[category] = category_counts.get(category, 0) + 1
        
        # Create summary alerts for high-frequency categories
        for category, count in category_counts.items():
            if count > 5:  # More than 5 alerts in window
                logger.info(
                    "High alert frequency detected",
                    category=category,
                    count=count
                )
    
    async def _cleanup_stale_alerts(self):
        """Clean up old alerts from memory"""
        max_alert_age = self.config.get("max_alert_age", 86400)  # 24 hours
        current_time = time.time()
        
        old_alerts = [
            a for a in self.alerts
            if current_time - a["timestamp"] > max_alert_age
        ]
        
        # Remove old alerts
        for old_alert in old_alerts:
            self.alerts.remove(old_alert)
            logger.debug(
                "Cleaned up stale alert",
                alert_id=old_alert["alert_id"]
            )
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get alert manager summary"""
        unresolved_count = len([a for a in self.alerts if not a["resolved"]])
        unacknowledged_count = len([a for a in self.alerts if not a["acknowledged"]])
        
        recent_alerts = [
            a for a in self.alerts
            if time.time() - a["timestamp"] <= 3600
        ]
        
        return {
            "agent_id": self.agent_id,
            "status": "RUNNING",
            "total_alerts": len(self.alerts),
            "unresolved_count": unresolved_count,
            "unacknowledged_count": unacknowledged_count,
            "recent_alerts_count": len(recent_alerts),
            "notification_channels": self.notification_channels,
            "alert_rules": self.alert_rules
        }

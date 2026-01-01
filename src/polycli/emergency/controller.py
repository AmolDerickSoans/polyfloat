"""Emergency stop controller."""
import asyncio
import json
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import structlog

from .models import EmergencyStopEvent, StopReason, StopState

logger = structlog.get_logger()


class EmergencyStopController:
    
    STOP_FILE = Path.home() / ".polycli" / ".emergency_stop"
    STOP_CHANNEL = "polycli:emergency_stop"
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        cancel_orders_fn: Optional[Callable] = None,
        close_websockets_fn: Optional[Callable] = None
    ):
        self.redis = redis_client
        self._cancel_orders = cancel_orders_fn
        self._close_websockets = close_websockets_fn
        self._is_stopped = False
        self._current_event: Optional[EmergencyStopEvent] = None
        self._stop_callbacks: List[Callable] = []
        self._resume_callbacks: List[Callable] = []
        
        self._load_stop_state()
    
    def _load_stop_state(self) -> None:
        if self.STOP_FILE.exists():
            try:
                with open(self.STOP_FILE) as f:
                    data = json.load(f)
                self._is_stopped = True
                self._current_event = EmergencyStopEvent(
                    id=data.get("id", ""),
                    timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                    reason=StopReason(data.get("reason", "user_initiated")),
                    description=data.get("description", "")
                )
                logger.warning("Loaded existing emergency stop state", event_id=self._current_event.id)
            except Exception as e:
                logger.error("Failed to load stop state", error=str(e))
    
    def _save_stop_state(self, event: EmergencyStopEvent) -> None:
        self.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.STOP_FILE, "w") as f:
            json.dump(event.to_dict(), f, indent=2)
    
    def _clear_stop_state(self) -> None:
        if self.STOP_FILE.exists():
            self.STOP_FILE.unlink()
    
    @property
    def is_stopped(self) -> bool:
        if self.STOP_FILE.exists():
            return True
        return self._is_stopped
    
    @property
    def current_event(self) -> Optional[EmergencyStopEvent]:
        if self.is_stopped:
            return self._current_event
        return None
    
    def register_stop_callback(self, callback: Callable) -> None:
        self._stop_callbacks.append(callback)
    
    def register_resume_callback(self, callback: Callable) -> None:
        self._resume_callbacks.append(callback)
    
    async def trigger_stop(
        self,
        reason: StopReason = StopReason.USER_INITIATED,
        description: str = "",
        cancel_orders: bool = True,
        close_websockets: bool = True
    ) -> EmergencyStopEvent:
        if self._is_stopped:
            logger.warning("Emergency stop already active")
            return self._current_event
        
        event = EmergencyStopEvent(
            reason=reason,
            description=description or f"Emergency stop: {reason.value}"
        )
        
        logger.critical(
            "EMERGENCY STOP TRIGGERED",
            reason=reason.value,
            description=description,
            event_id=event.id
        )
        
        self._is_stopped = True
        self._current_event = event
        self._save_stop_state(event)
        
        if self.redis:
            try:
                await self.redis.publish(
                    self.STOP_CHANNEL,
                    json.dumps({"action": "stop", "event": event.to_dict()})
                )
                logger.info("Published stop event to Redis")
            except Exception as e:
                logger.error("Failed to publish to Redis", error=str(e))
        
        if cancel_orders and self._cancel_orders:
            try:
                cancelled = await self._cancel_orders()
                event.orders_cancelled = cancelled
                logger.info("Cancelled pending orders", count=cancelled)
            except Exception as e:
                logger.error("Failed to cancel orders", error=str(e))
        
        if close_websockets and self._close_websockets:
            try:
                closed = await self._close_websockets()
                event.websockets_closed = closed
                logger.info("Closed WebSocket connections", count=closed)
            except Exception as e:
                logger.error("Failed to close websockets", error=str(e))
        
        for callback in self._stop_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error("Stop callback failed", error=str(e))
        
        self._save_stop_state(event)
        
        return event
    
    async def resume(self, resumed_by: str = "user") -> bool:
        if not self._is_stopped:
            logger.info("System is not stopped, nothing to resume")
            return True
        
        logger.info("Resuming from emergency stop", resumed_by=resumed_by)
        
        if self._current_event:
            self._current_event.resumed_at = datetime.utcnow()
            self._current_event.resumed_by = resumed_by
        
        self._is_stopped = False
        self._clear_stop_state()
        
        if self.redis:
            try:
                await self.redis.publish(
                    self.STOP_CHANNEL,
                    json.dumps({"action": "resume", "resumed_by": resumed_by})
                )
            except Exception as e:
                logger.error("Failed to publish resume to Redis", error=str(e))
        
        for callback in self._resume_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error("Resume callback failed", error=str(e))
        
        logger.info("System resumed", resumed_by=resumed_by)
        return True
    
    def check_and_raise(self) -> None:
        if self.is_stopped:
            raise EmergencyStopError(
                f"Emergency stop active: {self._current_event.description if self._current_event else 'Unknown'}"
            )
    
    async def start_listener(self) -> None:
        if not self.redis:
            logger.warning("No Redis client, cannot start stop listener")
            return
        
        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(self.STOP_CHANNEL)
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    if data.get("action") == "stop":
                        self._is_stopped = True
                        event_data = data.get("event", {})
                        self._current_event = EmergencyStopEvent(
                            id=event_data.get("id", ""),
                            reason=StopReason(event_data.get("reason", "user_initiated")),
                            description=event_data.get("description", "")
                        )
                        logger.warning("Received remote emergency stop signal")
                        
                        for callback in self._stop_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(self._current_event)
                                else:
                                    callback(self._current_event)
                            except Exception as e:
                                logger.error("Stop callback failed", error=str(e))
                    
                    elif data.get("action") == "resume":
                        self._is_stopped = False
                        self._clear_stop_state()
                        logger.info("Received remote resume signal")
                        
                        for callback in self._resume_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback()
                                else:
                                    callback()
                            except Exception as e:
                                logger.error("Resume callback failed", error=str(e))
        
        except Exception as e:
            logger.error("Stop listener error", error=str(e))


class EmergencyStopError(Exception):
    """Raised when an operation is attempted during emergency stop."""
    pass

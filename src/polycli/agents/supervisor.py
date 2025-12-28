import time
from typing import Dict, Any, List, Optional
import json
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from polycli.agents.base import BaseAgent
from polycli.agents.state import SupervisorState, Task, AgentMetadata

logger = structlog.get_logger()


class SupervisorAgent(BaseAgent):
    """Central coordinator for managing specialist agents and routing tasks"""

    def __init__(
        self,
        redis_store=None,
        sqlite_store=None,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            agent_id="supervisor",
            model="gemini-2.0-flash",
            redis_store=redis_store,
            sqlite_store=sqlite_store,
            config=config
        )
        
        self.active_agents: List[str] = []
        self.agent_health: Dict[str, Dict[str, Any]] = {}
        self.task_assignments: Dict[str, List[str]] = {}
        self.pending_tasks: List[Task] = []
        
        logger.info("Supervisor Agent initialized")

    def _register_tools(self):
        """Register supervisor-specific tools"""
        pass
    
    async def process(self, state: SupervisorState) -> SupervisorState:
        """Process supervisor state and route tasks to agents"""
        
        # Update health monitoring
        await self._update_agent_health()
        
        # Route pending tasks
        if self.pending_tasks:
            await self._route_tasks()
        
        # Update state
        state["pending_tasks"] = self.pending_tasks
        state["active_agents"] = self.active_agents
        state["agent_health"] = self.agent_health
        state["task_assignments"] = self.task_assignments
        
        return state
    
    async def _process_task_logic(self, task: Task) -> Dict[str, Any]:
        """Process supervisor task logic"""
        task_type = task["task_type"]
        
        if task_type == "ROUTE_TASK":
            return await self._route_single_task(task)
        elif task_type == "CHECK_HEALTH":
            return await self._check_agent_health(task)
        elif task_type == "RESTART_AGENT":
            return await self._restart_agent(task)
        elif task_type == "REGISTER_AGENT":
            return await self._register_agent(task)
        elif task_type == "UNREGISTER_AGENT":
            return await self._unregister_agent(task)
        else:
            logger.warning("Unknown task type", task_type=task_type)
            return {"error": f"Unknown task type: {task_type}", "success": False}
    
    async def _update_agent_health(self):
        """Update health status for all registered agents"""
        import asyncio
        health_checks = []
        
        for agent_id in self.active_agents:
            health_key = f"agent:health:{agent_id}"
            health_data = await self.redis.hgetall(health_key) if self.redis else {}
            
            if health_data:
                last_update = health_data.get("last_update", 0)
                age = time.time() - last_update
                
                # Mark agent as unhealthy if no update in 60 seconds
                if age > 60:
                    health_data["status"] = "UNHEALTHY"
                    health_data["last_error"] = "No heartbeat for 60s"
                else:
                    health_data["status"] = "RUNNING"
                    health_data["last_error"] = None
                
                self.agent_health[agent_id] = health_data
            else:
                # Agent not responding
                self.agent_health[agent_id] = {
                    "status": "UNRESPONSIVE",
                    "last_update": time.time(),
                    "last_error": "No health data"
                }
        
        logger.debug("Agent health updated", agents_count=len(self.agent_health))
    
    async def _route_tasks(self):
        """Route all pending tasks to appropriate agents"""
        while self.pending_tasks:
            task = self.pending_tasks[0]
            agent_id = await self._determine_target_agent(task)
            
            if agent_id:
                # Assign task to agent
                self.pending_tasks.pop(0)
                
                if agent_id not in self.task_assignments:
                    self.task_assignments[agent_id] = []
                
                self.task_assignments[agent_id].append(task["task_id"])
                
                # Send task to agent via Redis
                if self.redis:
                    await self.redis.lpush(f"agent:queue:{agent_id}", task)
                
                logger.info(
                    "Task routed",
                    task_id=task["task_id"],
                    to_agent=agent_id
                )
            else:
                # No suitable agent found, move to end of queue
                self.pending_tasks.append(self.pending_tasks.pop(0))
                logger.warning("No suitable agent for task", task_id=task["task_id"])
                break
    
    async def _route_single_task(self, task: Task) -> Dict[str, Any]:
        """Route a single task to appropriate agent"""
        inputs = task.get("inputs", {})
        task_type = inputs.get("task_type", "UNKNOWN")
        
        agent_id = await self._determine_target_agent(task)
        
        if agent_id:
            # Add to agent's queue
            if self.redis:
                await self.redis.lpush(f"agent:queue:{agent_id}", task)
            
            return {"success": True, "routed_to": agent_id}
        else:
            return {
                "success": False,
                "error": "No suitable agent found for task"
            }
    
    async def _determine_target_agent(self, task: Task) -> Optional[str]:
        """Determine which agent should handle the task"""
        task_type = task.get("task_type", task.get("inputs", {}).get("task_type", ""))
        
        # Simple routing rules
        routing_rules = {
            "SCAN_MARKETS": "market_observer",
            "ADD_WATCHLIST": "market_observer",
            "REMOVE_WATCHLIST": "market_observer",
            "GET_MARKET_DATA": "market_observer",
            "SUBSCRIBE_MARKET": "market_observer",
            "CHECK_ANOMALIES": "market_observer",
            "CREATE_ALERT": "alert_manager",
            "CHECK_ALERTS": "alert_manager",
            "CHECK_THRESHOLDS": "alert_manager",
            "SEND_NOTIFICATION": "alert_manager",
            "ACKNOWLEDGE_ALERT": "alert_manager",
            "RESOLVE_ALERT": "alert_manager",
            "UPDATE_RULE": "alert_manager",
            "GET_ALERTS": "alert_manager",
            "ADD_CHANNEL": "alert_manager",
            "REMOVE_CHANNEL": "alert_manager",
            "CHECK_LIMITS": "risk_manager",
            "UPDATE_POSITIONS": "risk_manager",
            "CHECK_RISK": "risk_manager",
            "CALCULATE_VAR": "risk_manager",
            "PLACE_ORDER": "execution_agent",
            "CANCEL_ORDER": "execution_agent",
            "RECONCILE_FILLS": "execution_agent",
            "GET_POSITIONS": "execution_agent",
            "GET_BALANCES": "execution_agent",
            "GET_TASK_HISTORY": "supervisor",
            "DETECT_ARB": "arb_scout",
            "SCAN_ARB": "arb_scout",
        }
        
        return routing_rules.get(task_type)
    
    async def _check_agent_health(self, task: Task) -> Dict[str, Any]:
        """Check health of specific agent"""
        agent_id = task.get("inputs", {}).get("agent_id")
        
        if agent_id in self.agent_health:
            health = self.agent_health[agent_id]
            status = health.get("status", "UNKNOWN")
            
            return {
                "success": True,
                "agent_id": agent_id,
                "status": status,
                "last_error": health.get("last_error")
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "status": "NOT_REGISTERED",
                "error": f"Agent {agent_id} not registered"
            }
    
    async def _register_agent(self, task: Task) -> Dict[str, Any]:
        """Register a new specialist agent"""
        agent_id = task.get("inputs", {}).get("agent_id")
        agent_type = task.get("inputs", {}).get("agent_type", "")
        
        if agent_id and agent_id not in self.active_agents:
            self.active_agents.append(agent_id)
            self.agent_health[agent_id] = {
                "status": "RUNNING",
                "last_update": time.time()
            }
            
            logger.info("Agent registered", agent_id=agent_id, agent_type=agent_type)
            
            return {"success": True, "agent_id": agent_id, "agent_type": agent_type}
        else:
            return {"success": False, "error": "Agent already registered"}
    
    async def _unregister_agent(self, task: Task) -> Dict[str, Any]:
        """Unregister a specialist agent"""
        agent_id = task.get("inputs", {}).get("agent_id")
        
        if agent_id in self.active_agents:
            self.active_agents.remove(agent_id)
            if agent_id in self.agent_health:
                del self.agent_health[agent_id]
            
            logger.info("Agent unregistered", agent_id=agent_id)
            
            return {"success": True, "agent_id": agent_id}
        else:
            return {"success": False, "error": "Agent not registered"}
    
    async def _restart_agent(self, task: Task) -> Dict[str, Any]:
        """Restart an agent"""
        agent_id = task.get("inputs", {}).get("agent_id")
        
        logger.info("Agent restart requested", agent_id=agent_id)
        
        # Unregister and re-register to restart
        await self._unregister_agent(task)
        result = await self._register_agent(task)
        
        return result
    
    async def send_heartbeat(self):
        """Send heartbeat for supervisor"""
        health_data = {
            "status": "RUNNING",
            "last_update": time.time(),
            "active_agents": len(self.active_agents),
            "pending_tasks": len(self.pending_tasks)
        }
        
        if self.redis:
            await self.redis.hset("agent:health:supervisor", "status", "RUNNING")
            await self.redis.hset("agent:health:supervisor", "last_update", health_data["last_update"])
            await self.redis.hset("agent:health:supervisor", "active_agents", health_data["active_agents"])
            await self.redis.hset("agent:health:supervisor", "pending_tasks", health_data["pending_tasks"])

    async def get_summary(self) -> Dict[str, Any]:
        """Get supervisor summary"""
        return {
            "agent_id": self.agent_id,
            "status": "RUNNING",
            "active_agents": self.active_agents,
            "agent_health": self.agent_health,
            "pending_tasks": len(self.pending_tasks),
            "task_assignments": self.task_assignments
        }
    
    async def route_command(self, command: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Route natural language or structured commands to agents"""
        logger.info("Routing command", command=command, args=args)
        
        # Simple routing for now - process as CHAT task
        result = f"Command received: {command}"
        if args:
            result += f" with args: {args}"
        
        # Publish result for TUI
        if self.redis:
            await self.redis.publish("command:results", json.dumps({
                "command": command,
                "result": result
            }))
        
        return {
            "success": True,
            "result": result
        }

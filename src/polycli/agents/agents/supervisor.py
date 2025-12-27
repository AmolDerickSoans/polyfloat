import time
from typing import Dict, Any, List, Optional
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..base import BaseAgent
from ..state import SupervisorState, Task, AgentMetadata

logger = structlog.get_logger()


class SupervisorAgent(BaseAgent):
    """Central coordinator for managing specialist agents and routing tasks"""
    
    def __init__(
        self,
        redis_store,
        sqlite_store,
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
                
                self.agent_health[agent_id] = health_data
        
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
        
        # Task routing rules
        routing_map = {
            "SCAN_MARKETS": "market_observer",
            "MONITOR_MARKET": "market_observer",
            "DETECT_ARB": "arb_scout",
            "ANALYZE_SENTIMENT": "researcher",
            "PLAN_TRADE": "strategy_planner",
            "EXECUTE_TRADE": "execution_agent",
            "CHECK_RISK": "risk_manager",
            "TRACK_POSITION": "position_tracker",
            "MONITOR_SENTIMENT": "sentiment_analyzer",
            "CHECK_ALERTS": "alert_manager"
        }
        
        target_agent = routing_map.get(task_type)
        
        # Check if agent is healthy and active
        if target_agent and target_agent in self.active_agents:
            health = self.agent_health.get(target_agent, {})
            if health.get("status") == "RUNNING":
                return target_agent
        
        logger.warning(
            "No suitable agent for task",
            task_type=task_type,
            target_agent=target_agent,
            active_agents=self.active_agents
        )
        return None
    
    async def _check_agent_health(self, task: Task) -> Dict[str, Any]:
        """Check health of a specific agent"""
        inputs = task.get("inputs", {})
        agent_id = inputs.get("agent_id")
        
        if not agent_id:
            return {"error": "agent_id not provided", "success": False}
        
        health_data = self.agent_health.get(agent_id)
        
        if health_data:
            return {"success": True, "health": health_data}
        else:
            return {
                "success": False,
                "error": f"Agent {agent_id} not registered"
            }
    
    async def _restart_agent(self, task: Task) -> Dict[str, Any]:
        """Restart a failed agent"""
        inputs = task.get("inputs", {})
        agent_id = inputs.get("agent_id")
        
        if not agent_id:
            return {"error": "agent_id not provided", "success": False}
        
        # Signal agent to restart via Redis
        if self.redis:
            await self.redis.set(f"agent:restart:{agent_id}", "restart")
        
        logger.info("Agent restart requested", agent_id=agent_id)
        
        return {"success": True, "agent_id": agent_id}
    
    async def _register_agent(self, task: Task) -> Dict[str, Any]:
        """Register a new agent"""
        inputs = task.get("inputs", {})
        agent_id = inputs.get("agent_id")
        agent_type = inputs.get("agent_type")
        
        if not agent_id:
            return {"error": "agent_id not provided", "success": False}
        
        if agent_id not in self.active_agents:
            self.active_agents.append(agent_id)
            
            # Initialize health tracking
            self.agent_health[agent_id] = {
                "status": "RUNNING",
                "registered_at": time.time(),
                "last_update": time.time(),
                "tasks_completed": 0,
                "errors": 0
            }
            
            # Store registration
            if self.redis:
                await self.redis.hset(
                    f"agent:health:{agent_id}",
                    "status",
                    "RUNNING"
                )
                await self.redis.hset(
                    f"agent:health:{agent_id}",
                    "registered_at",
                    time.time()
                )
            
            logger.info("Agent registered", agent_id=agent_id, agent_type=agent_type)
            
            return {"success": True, "agent_id": agent_id}
        else:
            return {"error": "Agent already registered", "success": False}
    
    async def _unregister_agent(self, task: Task) -> Dict[str, Any]:
        """Unregister an agent"""
        inputs = task.get("inputs", {})
        agent_id = inputs.get("agent_id")
        
        if not agent_id:
            return {"error": "agent_id not provided", "success": False}
        
        if agent_id in self.active_agents:
            self.active_agents.remove(agent_id)
            
            if agent_id in self.agent_health:
                del self.agent_health[agent_id]
            
            if agent_id in self.task_assignments:
                del self.task_assignments[agent_id]
            
            # Remove from Redis
            if self.redis:
                await self.redis.delete(f"agent:health:{agent_id}")
            
            logger.info("Agent unregistered", agent_id=agent_id)
            
            return {"success": True, "agent_id": agent_id}
        else:
            return {"error": "Agent not registered", "success": False}
    
    async def send_heartbeat(self):
        """Send heartbeat for supervisor"""
        health_data = {
            "status": "RUNNING",
            "last_update": time.time(),
            "active_agents": len(self.active_agents),
            "pending_tasks": len(self.pending_tasks)
        }
        
        if self.redis:
            await self.redis.hset(
                f"agent:health:{self.agent_id}",
                "status",
                "RUNNING"
            )
            await self.redis.hset(
                f"agent:health:{self.agent_id}",
                "last_update",
                time.time()
            )
            await self.redis.hset(
                f"agent:health:{self.agent_id}",
                "active_agents",
                len(self.active_agents)
            )
            await self.redis.hset(
                f"agent:health:{self.agent_id}",
                "pending_tasks",
                len(self.pending_tasks)
            )
    
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

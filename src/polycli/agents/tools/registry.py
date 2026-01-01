import asyncio
from typing import Callable, Any, Dict, List, Optional, Type
from functools import wraps
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class ToolInput(BaseModel):
    """Base model for tool input schema"""
    pass


class ToolMetadata(BaseModel):
    """Metadata for a registered tool"""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable
    async_function: bool = True


class ToolRegistry:
    """Registry for managing agent tools"""
    
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._categories: Dict[str, List[str]] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        category: str = "general"
    ):
        """Decorator to register a function as a tool"""
        def decorator(func: Callable) -> Callable:
            metadata = ToolMetadata(
                name=name,
                description=description,
                parameters=parameters or {},
                function=func,
                async_function=asyncio.iscoroutinefunction(func)
            )
            self._tools[name] = metadata
            
            if category not in self._categories:
                self._categories[category] = []
            self._categories[category].append(name)
            
            logger.info(
                "Registered tool",
                tool=name,
                category=category,
                description=description
            )
            return func
        return decorator
    
    def get(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name"""
        return self._tools.get(name)
    
    def get_all(self) -> Dict[str, ToolMetadata]:
        """Get all registered tools"""
        return self._tools.copy()
    
    def get_by_category(self, category: str) -> List[ToolMetadata]:
        """Get all tools in a category"""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    def exists(self, name: str) -> bool:
        """Check if tool is registered"""
        return name in self._tools
    
    async def execute(self, name: str, **kwargs) -> Any:
        """Execute a tool by name with provided arguments"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")
        
        try:
            if tool.async_function:
                result = await tool.function(**kwargs)
            else:
                result = tool.function(**kwargs)
            
            logger.info(
                "Tool executed",
                tool=name,
                kwargs=kwargs,
                success=True
            )
            return result
        except Exception as e:
            logger.error(
                "Tool execution failed",
                tool=name,
                kwargs=kwargs,
                error=str(e)
            )
            raise
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all tools with metadata"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "async": tool.async_function
            }
            for tool in self._tools.values()
        ]
    
    def list_categories(self) -> List[str]:
        """List all tool categories"""
        return list(self._categories.keys())


def tool(
    name: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    category: str = "general"
):
    """Decorator to register a function as a tool"""
    def decorator(func: Callable) -> Callable:
        setattr(func, '_tool_metadata', {
            "name": name,
            "description": description,
            "parameters": parameters or {},
            "category": category
        })
        return func
    return decorator


class ToolExecutor:
    """Helper class for executing tools with error handling and logging"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
    
    async def execute(self, tool_name: str, **kwargs) -> Any:
        """Execute tool with validation and error handling"""
        tool = self.registry.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found in registry")
        
        self._validate_parameters(tool, kwargs)
        
        return await self.registry.execute(tool_name, **kwargs)
    
    def _validate_parameters(self, tool: ToolMetadata, kwargs: Dict[str, Any]):
        """Validate that required parameters are provided"""
        for param_name, param_info in tool.parameters.items():
            if param_info.get("required", False) and param_name not in kwargs:
                raise ValueError(f"Missing required parameter '{param_name}' for tool '{tool.name}'")

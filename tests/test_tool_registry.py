"""Tests for Phase 1: Tool Registry"""
import pytest
from polycli.agents.tools.registry import ToolRegistry, ToolExecutor, ToolMetadata


@pytest.fixture
def tool_registry():
    """Create a tool registry instance"""
    return ToolRegistry()


class TestToolRegistry:
    """Test tool registration and execution"""
    
    def test_register_tool(self, tool_registry):
        """Test tool registration"""
        @tool_registry.register(
            name="test_tool",
            description="A test tool",
            parameters={"param1": {"type": "string", "required": True}},
            category="test"
        )
        async def test_function(param1: str):
            return f"Received: {param1}"
        
        # Verify tool is registered
        assert tool_registry.exists("test_tool")
        metadata = tool_registry.get("test_tool")
        assert metadata.name == "test_tool"
        assert metadata.description == "A test tool"
        assert metadata.async_function == True
    
    def test_get_tool(self, tool_registry):
        """Test retrieving tool metadata"""
        @tool_registry.register(name="get_test", description="Test getting tool")
        async def func():
            return "test"
        
        tool = tool_registry.get("get_test")
        assert tool is not None
        assert tool.name == "get_test"
        assert tool.description == "Test getting tool"
    
    def test_get_all_tools(self, tool_registry):
        """Test getting all tools"""
        @tool_registry.register(name="tool1", description="First tool")
        async def func1():
            return "1"
        
        @tool_registry.register(name="tool2", description="Second tool")
        async def func2():
            return "2"
        
        all_tools = tool_registry.get_all()
        assert len(all_tools) == 2
        assert "tool1" in all_tools
        assert "tool2" in all_tools
    
    def test_get_by_category(self, tool_registry):
        """Test getting tools by category"""
        @tool_registry.register(name="cat1_tool", description="Tool 1", category="category1")
        async def func1():
            return "1"
        
        @tool_registry.register(name="cat2_tool", description="Tool 2", category="category2")
        async def func2():
            return "2"
        
        cat1_tools = tool_registry.get_by_category("category1")
        assert len(cat1_tools) == 1
        assert cat1_tools[0].name == "cat1_tool"
        
        cat2_tools = tool_registry.get_by_category("category2")
        assert len(cat2_tools) == 1
        assert cat2_tools[0].name == "cat2_tool"
    
    def test_list_tools(self, tool_registry):
        """Test listing tools with metadata"""
        @tool_registry.register(
            name="list_tool",
            description="List test tool",
            parameters={"arg": {"type": "string"}}
        )
        async def func(arg: str):
            return arg
        
        tools = tool_registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "list_tool"
        assert tools[0]["description"] == "List test tool"
        assert tools[0]["async"] == True
        assert "arg" in tools[0]["parameters"]
    
    def test_list_categories(self, tool_registry):
        """Test listing categories"""
        @tool_registry.register(name="cat_a", description="Tool A", category="alpha")
        async def func_a():
            return "a"
        
        @tool_registry.register(name="cat_b", description="Tool B", category="beta")
        async def func_b():
            return "b"
        
        @tool_registry.register(name="cat_a2", description="Tool A2", category="alpha")
        async def func_a2():
            return "a2"
        
        categories = tool_registry.list_categories()
        assert set(categories) == {"alpha", "beta"}
    
    @pytest.mark.asyncio
    async def test_execute_tool(self, tool_registry):
        """Test executing a registered tool"""
        @tool_registry.register(name="exec_test", description="Execution test")
        async def test_exec(value: str):
            return f"Executed with: {value}"
        
        result = await tool_registry.execute("exec_test", value="test123")
        assert result == "Executed with: test123"
    
    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self, tool_registry):
        """Test executing a tool that doesn't exist"""
        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            await tool_registry.execute("nonexistent")
    
    @pytest.mark.asyncio
    async def test_execute_sync_tool(self, tool_registry):
        """Test executing a synchronous tool"""
        @tool_registry.register(name="sync_test", description="Sync test")
        def sync_func(value: int):
            return value * 2
        
        result = await tool_registry.execute("sync_test", value=5)
        assert result == 10


class TestToolExecutor:
    """Test tool executor with validation"""
    
    @pytest.mark.asyncio
    async def test_validate_parameters_success(self, tool_registry):
        """Test parameter validation success"""
        executor = ToolExecutor(tool_registry)
        
        @tool_registry.register(
            name="validated_tool",
            description="Validated tool",
            parameters={
                "required_param": {"type": "string", "required": True},
                "optional_param": {"type": "int", "required": False}
            }
        )
        async def validated_tool(required_param: str, optional_param: int = 10):
            return {"required": required_param, "optional": optional_param}
        
        result = await executor.execute(
            "validated_tool",
            required_param="test"
        )
        assert result == {"required": "test", "optional": 10}
    
    @pytest.mark.asyncio
    async def test_validate_parameters_missing_required(self, tool_registry):
        """Test parameter validation failure for missing required param"""
        executor = ToolExecutor(tool_registry)
        
        @tool_registry.register(
            name="requires_param",
            description="Requires param",
            parameters={
                "required_param": {"type": "string", "required": True}
            }
        )
        async def requires_param(required_param: str):
            return required_param
        
        with pytest.raises(ValueError, match="Missing required parameter"):
            await executor.execute("requires_param")


class TestToolDecorator:
    """Test the @tool decorator"""
    
    def test_tool_decorator(self):
        """Test that the @tool decorator sets metadata"""
        from polycli.agents.tools.registry import tool
        
        @tool(
            name="decorator_test",
            description="Decorator test tool",
            parameters={"test": {"type": "string"}},
            category="test_cat"
        )
        def test_function(test: str):
            return test
        
        metadata = getattr(test_function, '_tool_metadata', {})
        assert metadata["name"] == "decorator_test"
        assert metadata["description"] == "Decorator test tool"
        assert metadata["category"] == "test_cat"
        assert "test" in metadata["parameters"]

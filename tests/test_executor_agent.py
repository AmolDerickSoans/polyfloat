import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from polycli.agents.executor import ExecutorAgent

@pytest.fixture
def executor():
    with patch("polycli.agents.tools.chroma.GoogleGenerativeAIEmbeddings"), \
         patch("polycli.agents.executor.ExecutorAgent._init_llm"):
        agent = ExecutorAgent()
        agent.llm = MagicMock()
        return agent

@pytest.mark.asyncio
async def test_executor_get_superforecast(executor):
    # Mock LLM response
    executor.llm.ainvoke = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "I believe test has a likelihood 0.65"
    executor.llm.ainvoke.return_value = mock_response
    
    result = await executor.get_superforecast("Event", "Question", ["Yes", "No"])
    assert "0.65" in result
    executor.llm.ainvoke.assert_called_once()

def test_executor_divide_list(executor):
    data = [1, 2, 3, 4, 5]
    divided = executor.divide_list(data, 2)
    assert len(divided) == 2
    assert len(divided[0]) == 3
    assert len(divided[1]) == 2

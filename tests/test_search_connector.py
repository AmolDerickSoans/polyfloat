import pytest
from unittest.mock import MagicMock, patch
from polycli.agents.tools.search import SearchConnector

def test_search_connector_init():
    with patch("polycli.agents.tools.search.TavilyClient") as mock_tavily:
        connector = SearchConnector(api_key="test_key")
        mock_tavily.assert_called_once_with(api_key="test_key")

def test_search_connector_get_context():
    with patch("polycli.agents.tools.search.TavilyClient") as mock_tavily:
        mock_instance = mock_tavily.return_value
        mock_instance.get_search_context.return_value = "Search results context"
        
        connector = SearchConnector(api_key="test_key")
        context = connector.get_search_context("test query")
        
        assert context == "Search results context"
        mock_instance.get_search_context.assert_called_with(query="test query")

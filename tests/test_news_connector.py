import pytest
from unittest.mock import MagicMock, patch
from polycli.agents.tools.news import NewsConnector

def test_news_connector_init():
    with patch("polycli.agents.tools.news.NewsApiClient") as mock_api:
        connector = NewsConnector(api_key="test_key")
        mock_api.assert_called_once_with(api_key="test_key")

def test_news_connector_get_category():
    connector = NewsConnector(api_key="test_key")
    assert connector.get_category("Business") == "business"
    assert connector.get_category("Unknown") == "general"

@pytest.mark.asyncio
async def test_news_connector_get_top_articles():
    with patch("polycli.agents.tools.news.NewsApiClient") as mock_api:
        mock_instance = mock_api.return_value
        mock_instance.get_top_headlines.return_value = {
            "articles": [{"title": "Test News", "url": "http://test.com"}]
        }
        
        connector = NewsConnector(api_key="test_key")
        articles = connector.get_top_articles_for_market("Test question")
        
        assert len(articles) == 1
        assert articles[0].title == "Test News"

import os
from typing import Optional
from tavily import TavilyClient

# Ported from reference agents/connectors/search.py
# Adapted for polycli project structure

class SearchConnector:
    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            self.client = None
        else:
            self.client = TavilyClient(api_key=key)

    def get_search_context(self, query: str) -> str:
        """
        Execute a context search query.
        Returns a context string that can be fed into RAG.
        """
        if not self.client:
            return ""
        
        try:
            # Tavily context search
            return self.client.get_search_context(query=query)
        except Exception as e:
            # Graceful failure
            return f"Search failed: {str(e)}"

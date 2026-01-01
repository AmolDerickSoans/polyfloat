from datetime import datetime
import os
from typing import List, Dict, Optional, Any
from newsapi import NewsApiClient
from polycli.models import Article

# Ported from reference agents/connectors/news.py
# Adapted for polycli project structure

class NewsConnector:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.configs = {
            "language": "en",
            "country": "us",
            "top_headlines": "https://newsapi.org/v2/top-headlines?country=us&apiKey=",
            "base_url": "https://newsapi.org/v2/",
        }

        self.categories = {
            "business",
            "entertainment",
            "general",
            "health",
            "science",
            "sports",
            "technology",
        }
        
        key = api_key or os.getenv("NEWSAPI_API_KEY")
        if not key:
            # For testing/graceful degradation
            self.API = None
        else:
            self.API = NewsApiClient(api_key=key)

    def get_articles_for_cli_keywords(self, keywords: str) -> List[Article]:
        if not self.API:
            return []
        query_words = keywords.split(",")
        all_articles = self.get_articles_for_options(query_words)
        article_objects: List[Article] = []
        for _, articles in all_articles.items():
            for article in articles:
                # Handle possible missing fields gracefully
                article_objects.append(Article(**article))
        return article_objects

    def get_top_articles_for_market(self, market_question: str) -> List[Article]:
        if not self.API:
            return []
        # Official implementation used market_object["description"]
        # We use question as it's more descriptive in our models
        response_dict = self.API.get_top_headlines(
            language="en", q=market_question
        )
        articles = response_dict.get("articles", [])
        return [Article(**a) for a in articles]

    def get_articles_for_options(
        self,
        market_options: List[str],
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
    ) -> Dict[str, List[Any]]:
        if not self.API:
            return {opt: [] for opt in market_options}

        all_articles = {}
        # Default to top articles if no start and end dates are given for search
        if not date_start and not date_end:
            for option in market_options:
                response_dict = self.API.get_top_headlines(
                    q=option.strip(),
                    language=self.configs["language"],
                    country=self.configs["country"],
                )
                articles = response_dict.get("articles", [])
                all_articles[option] = articles
        else:
            for option in market_options:
                response_dict = self.API.get_everything(
                    q=option.strip(),
                    language=self.configs["language"],
                    country=self.configs["country"],
                    from_param=date_start.strftime("%Y-%m-%dT%H:%M:%S") if date_start else None,
                    to=date_end.strftime("%Y-%m-%dT%H:%M:%S") if date_end else None,
                )
                articles = response_dict.get("articles", [])
                all_articles[option] = articles

        return all_articles

    def get_category(self, market_category: str) -> str:
        news_category = "general"
        if market_category.lower() in self.categories:
            news_category = market_category.lower()
        return news_category

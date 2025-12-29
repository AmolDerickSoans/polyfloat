import json
import os
import time
from typing import List, Tuple, Optional, Any, Dict

from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import JSONLoader
from langchain_community.vectorstores import Chroma

# Ported from reference agents/connectors/chroma.py
# Adapted to use polycli models and provider logic

class ChromaConnector:
    def __init__(self, local_db_directory: str = "./local_db", embedding_function: Optional[Any] = None) -> None:
        self.local_db_directory = local_db_directory
        # Use OpenAI embeddings as per reference
        self.embedding_function = embedding_function or OpenAIEmbeddings(model="text-embedding-3-small")

    def load_json_from_local(
        self, json_file_path: str, vector_db_directory: str = "./local_db"
    ) -> None:
        loader = JSONLoader(
            file_path=json_file_path, jq_schema=".[].description", text_content=False
        )
        loaded_docs = loader.load()

        Chroma.from_documents(
            loaded_docs, self.embedding_function, persist_directory=vector_db_directory
        )

    def create_local_markets_rag(self, markets_data: List[Dict[str, Any]], local_directory: str = "./local_db") -> None:
        if not os.path.isdir(local_directory):
            os.makedirs(local_directory, exist_ok=True)

        local_file_path = f"{local_directory}/all-current-markets_{time.time()}.json"

        with open(local_file_path, "w+") as output_file:
            json.dump(markets_data, output_file)

        self.load_json_from_local(
            json_file_path=local_file_path, vector_db_directory=local_directory
        )

    def query_local_markets_rag(
        self, query: str, local_directory: Optional[str] = None
    ) -> List[Tuple[Any, float]]:
        persist_dir = local_directory or self.local_db_directory
        local_db = Chroma(
            persist_directory=persist_dir, embedding_function=self.embedding_function
        )
        response_docs = local_db.similarity_search_with_score(query=query)
        return response_docs

    def events(self, events: List[Any], prompt: str) -> List[Tuple[Any, float]]:
        """Process a list of Event models for RAG"""
        local_events_directory = "./local_db_events"
        if not os.path.isdir(local_events_directory):
            os.makedirs(local_events_directory, exist_ok=True)
            
        local_file_path = f"{local_events_directory}/events.json"
        
        # Convert Pydantic models to dict if necessary
        dict_events = []
        for e in events:
            if hasattr(e, "dict"):
                dict_events.append(e.dict())
            elif hasattr(e, "model_dump"):
                dict_events.append(e.model_dump())
            else:
                dict_events.append(e)
                
        with open(local_file_path, "w+") as output_file:
            json.dump(dict_events, output_file)

        def metadata_func(record: dict, metadata: dict) -> dict:
            metadata["id"] = record.get("id")
            metadata["markets"] = record.get("markets")
            return metadata

        loader = JSONLoader(
            file_path=local_file_path,
            jq_schema=".[]",
            content_key="description",
            text_content=False,
            metadata_func=metadata_func,
        )
        loaded_docs = loader.load()
        vector_db_directory = f"{local_events_directory}/chroma"
        
        local_db = Chroma.from_documents(
            loaded_docs, self.embedding_function, persist_directory=vector_db_directory
        )

        return local_db.similarity_search_with_score(query=prompt)

    def markets(self, markets: List[Any], prompt: str) -> List[Tuple[Any, float]]:
        """Process a list of Market models for RAG"""
        local_markets_directory = "./local_db_markets"
        if not os.path.isdir(local_markets_directory):
            os.makedirs(local_markets_directory, exist_ok=True)
            
        local_file_path = f"{local_markets_directory}/markets.json"
        
        dict_markets = []
        for m in markets:
            if hasattr(m, "dict"):
                dict_markets.append(m.dict())
            elif hasattr(m, "model_dump"):
                dict_markets.append(m.model_dump())
            else:
                dict_markets.append(m)
                
        with open(local_file_path, "w+") as output_file:
            json.dump(dict_markets, output_file)

        def metadata_func(record: dict, metadata: dict) -> dict:
            metadata["id"] = record.get("id")
            metadata["outcomes"] = record.get("outcomes")
            # Handle possible nested metadata or direct fields
            meta = record.get("metadata", {})
            metadata["outcome_prices"] = meta.get("outcomePrices") or record.get("outcome_prices")
            metadata["question"] = record.get("question")
            metadata["clob_token_ids"] = meta.get("clobTokenIds") or record.get("clob_token_ids")
            return metadata

        loader = JSONLoader(
            file_path=local_file_path,
            jq_schema=".[]",
            content_key="question", # Using question if description is missing
            text_content=False,
            metadata_func=metadata_func,
        )
        loaded_docs = loader.load()
        vector_db_directory = f"{local_markets_directory}/chroma"
        
        local_db = Chroma.from_documents(
            loaded_docs, self.embedding_function, persist_directory=vector_db_directory
        )

        return local_db.similarity_search_with_score(query=prompt)

import pytest
from unittest.mock import MagicMock, patch
from polycli.agents.tools.chroma import ChromaConnector

def test_chroma_connector_init():
    with patch("polycli.agents.tools.chroma.OpenAIEmbeddings") as mock_embeddings:
        connector = ChromaConnector()
        assert connector.local_db_directory == "./local_db"
        mock_embeddings.assert_called_once_with(model="text-embedding-3-small")

@pytest.mark.asyncio
async def test_chroma_connector_events_path_creation():
    with patch("polycli.agents.tools.chroma.OpenAIEmbeddings"), \
         patch("os.path.isdir", return_value=False), \
         patch("os.makedirs") as mock_makedirs, \
         patch("builtins.open", MagicMock()), \
         patch("json.dump"), \
         patch("polycli.agents.tools.chroma.JSONLoader"), \
         patch("polycli.agents.tools.chroma.Chroma") as mock_chroma:
        
        connector = ChromaConnector()
        # Mock Chroma instance
        mock_db = MagicMock()
        mock_chroma.from_documents.return_value = mock_db
        mock_db.similarity_search_with_score.return_value = []
        
        events = [MagicMock(id="e1", markets=[], description="test")]
        for e in events:
            e.dict = MagicMock(return_value={"id": "e1", "markets": [], "description": "test"})
            
        connector.events(events, "test query")
        mock_makedirs.assert_called()

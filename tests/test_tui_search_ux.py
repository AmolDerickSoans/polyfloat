import pytest
from unittest.mock import MagicMock, AsyncMock
from polycli.tui import DashboardApp
from textual.widgets import DataTable

@pytest.mark.asyncio
async def test_search_no_results_feedback():
    app = DashboardApp()
    app.poly = AsyncMock()
    app.kalshi = AsyncMock()
    
    # Mock providers returning empty lists
    app.poly.search.return_value = []
    app.kalshi.search.return_value = []
    
    # Mock query_one
    mock_input = MagicMock()
    mock_input.value = "NonExistentMarket"
    
    # We mock DataTable to inspect calls
    mock_table = MagicMock(spec=DataTable)
    # mock_table.row_count is property, usually mocked like this:
    type(mock_table).row_count = MagicMock(return_value=0)
    
    def side_effect(selector, *args):
        if selector == "#search_box": return mock_input
        if selector == "#market_list": return mock_table
        return MagicMock()
    
    app.query_one = MagicMock(side_effect=side_effect)
    app.selected_provider = "all"
    
    # Execute update_markets
    worker = app.update_markets()
    await worker.wait()
    
    # Assertions
    # We expect the table to have been cleared
    mock_table.clear.assert_called()
    
    # We expect a row added indicating no results. 
    # Current implementation DOES NOT do this, so this assertion should fail.
    # We will look for a call to add_row with a specific message.
    
    # We need to capture the calls to add_row.
    added_rows = [str(args[0]) for args, _ in mock_table.add_row.call_args_list]
    print(f"Added rows: {added_rows}")
    
    # We expect one of the rows to contain "No results"
    assert any("No results" in row for row in added_rows), "Expected 'No results' message in table"

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from polycli.tui import MarketDetail, OrderbookDepth
from polycli.models import OrderBook, PriceLevel, Market, MarketStatus

@pytest.mark.asyncio
async def test_market_detail_on_k_ob():
    # We avoid setting .app directly as it's a property
    detail = MarketDetail()
    
    # Mock query_one to simulate the child widget
    mock_depth_wall = MagicMock()
    detail.query_one = MagicMock(return_value=mock_depth_wall)
    
    # Standardized Kalshi OB update
    data = {
        "market_ticker": "M1",
        "bids": [{"price": 0.45, "size": 10}],
        "asks": [{"price": 0.46, "size": 20}]
    }
    
    await detail.on_k_ob(data)
    
    # Verify that query_one was called to find depth_wall
    detail.query_one.assert_called_with("#depth_wall", OrderbookDepth)
    # Verify snapshot was updated on the mock depth wall
    assert mock_depth_wall.snapshot is not None
    assert mock_depth_wall.snapshot.market_id == "M1"

@pytest.mark.asyncio
async def test_search_triggers_provider_search():
    from polycli.tui import DashboardApp
    app = DashboardApp()
    app.poly = AsyncMock()
    app.kalshi = AsyncMock()
    
    # Mock query_one to return "Trump" for search_box
    mock_input = MagicMock()
    mock_input.value = "Trump"
    mock_table = MagicMock()
    
    def side_effect(selector, *args):
        if selector == "#search_box": return mock_input
        if selector == "#market_list": return mock_table
        return MagicMock()
    
    app.query_one = MagicMock(side_effect=side_effect)
    app.selected_provider = "all"
    
    # Execute update_markets
    try:
        worker = app.update_markets()
        await worker.wait()
        
        # We expect search() to be called.
        app.poly.search.assert_called_with("Trump")
        app.kalshi.search.assert_called_with("Trump")
        
    except Exception as e:
         # If update_markets crashes or assertion fails
         pytest.fail(f"Search logic failed: {e}")

@pytest.mark.asyncio
async def test_search_no_results_feedback():
    from polycli.tui import DashboardApp
    from textual.widgets import DataTable
    
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
    # mock_table.row_count is property
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
    added_rows = [str(args[0]) for args, _ in mock_table.add_row.call_args_list]
    
    # We expect one of the rows to contain "No results"
    assert any("No results" in row for row in added_rows), "Expected 'No results' message in table"

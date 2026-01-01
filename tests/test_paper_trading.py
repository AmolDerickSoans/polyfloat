"""Comprehensive unit tests for paper trading module."""
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

from polycli.paper.store import PaperTradingStore
from polycli.paper.provider import PaperTradingProvider
from polycli.paper.models import (
    PaperOrder, PaperPosition, PaperTrade, PaperWallet,
    PaperOrderStatus, PaperOrderSide
)


@pytest.fixture
def paper_store(tmp_path):
    """Create temporary paper trading store."""
    db_path = tmp_path / "test_paper.db"
    return PaperTradingStore(db_path)


@pytest.fixture
def mock_poly_provider():
    """Mock PolyProvider for testing."""
    mock_provider = Mock()
    mock_provider.client = Mock()
    
    # Mock price methods
    mock_provider.client.get_midpoint = Mock(return_value=0.50)
    mock_provider.client.get_price = Mock(return_value=0.50)
    
    # Mock async methods
    mock_provider.get_markets = AsyncMock(return_value=[])
    
    return mock_provider


@pytest.fixture
async def paper_provider(mock_poly_provider, paper_store):
    """Creates PaperTradingProvider with mocks."""
    provider = PaperTradingProvider(mock_poly_provider, paper_store)
    await provider.initialize()
    return provider


class TestPaperTradingStore:
    """Test suite for PaperTradingStore."""
    
    def test_wallet_creation(self, paper_store):
        """Verify wallet created with 1000.00 balance."""
        wallet = paper_store.get_wallet("polymarket")
        assert wallet.balance == Decimal("1000.00")
        assert wallet.provider == "polymarket"
        assert wallet.initial_balance == Decimal("1000.00")
        assert wallet.total_deposited == Decimal("1000.00")
    
    def test_wallet_creation_custom_provider(self, paper_store):
        """Verify wallet created for custom provider."""
        wallet = paper_store.get_wallet("kalshi")
        assert wallet.balance == Decimal("1000.00")
        assert wallet.provider == "kalshi"
    
    def test_reset_clears_data(self, paper_store):
        """Verify reset functionality."""
        # Create some data first
        paper_store.save_order(PaperOrder(
            token_id="test",
            market_id="market1",
            side=PaperOrderSide.BUY,
            amount=Decimal("100.00"),
            provider="polymarket"
        ))
        paper_store.save_position(PaperPosition(
            token_id="test",
            market_id="market1",
            outcome="YES",
            size=Decimal("10"),
            avg_price=Decimal("0.50"),
            cost_basis=Decimal("5.00"),
            provider="polymarket"
        ))
        
        # Reset
        paper_store.reset("polymarket", Decimal("500.00"))
        wallet = paper_store.get_wallet("polymarket")
        
        assert wallet.balance == Decimal("500.00")
        assert wallet.initial_balance == Decimal("500.00")
    
    def test_save_and_get_order(self, paper_store):
        """Test order persistence."""
        order = PaperOrder(
            token_id="token123",
            market_id="market456",
            side=PaperOrderSide.BUY,
            amount=Decimal("100.00"),
            price=Decimal("0.50"),
            status=PaperOrderStatus.FILLED,
            filled_amount=Decimal("200"),
            avg_fill_price=Decimal("0.50"),
            provider="polymarket"
        )
        
        paper_store.save_order(order)
        # Order is saved to DB - verify through paper_store.get_orders
        orders = paper_store.get_orders("polymarket")
        assert len(orders) == 1
        assert orders[0].token_id == "token123"
    
    def test_save_and_get_position(self, paper_store):
        """Test position persistence."""
        position = PaperPosition(
            token_id="token123",
            market_id="market456",
            outcome="YES",
            size=Decimal("100"),
            avg_price=Decimal("0.60"),
            cost_basis=Decimal("60.00"),
            realized_pnl=Decimal("10.00"),
            provider="polymarket"
        )
        
        paper_store.save_position(position)
        positions = paper_store.get_positions("polymarket")
        
        assert len(positions) == 1
        assert positions[0].token_id == "token123"
        assert positions[0].size == Decimal("100")
        assert positions[0].avg_price == Decimal("0.60")
        assert positions[0].cost_basis == Decimal("60.00")
        assert positions[0].realized_pnl == Decimal("10.00")
    
    def test_save_and_get_trade(self, paper_store):
        """Test trade persistence."""
        trade = PaperTrade(
            order_id="order123",
            token_id="token456",
            market_id="market789",
            side=PaperOrderSide.BUY,
            price=Decimal("0.55"),
            size=Decimal("50"),
            total=Decimal("27.50"),
            fee=Decimal("0.275"),
            provider="polymarket"
        )
        
        paper_store.save_trade(trade)
        trades = paper_store.get_trades("polymarket")
        
        assert len(trades) == 1
        assert trades[0].token_id == "token456"
        assert trades[0].price == Decimal("0.55")
        assert trades[0].size == Decimal("50")
        assert trades[0].total == Decimal("27.50")
        assert trades[0].fee == Decimal("0.275")
    
    def test_get_positions_excludes_zero_size(self, paper_store):
        """Ensure closed positions filtered."""
        # Create active position
        paper_store.save_position(PaperPosition(
            token_id="active_token",
            market_id="market1",
            outcome="YES",
            size=Decimal("10"),
            avg_price=Decimal("0.50"),
            cost_basis=Decimal("5.00"),
            provider="polymarket"
        ))
        
        # Create closed position
        paper_store.save_position(PaperPosition(
            token_id="closed_token",
            market_id="market2",
            outcome="YES",
            size=Decimal("0"),
            avg_price=Decimal("0.50"),
            cost_basis=Decimal("0"),
            provider="polymarket"
        ))
        
        positions = paper_store.get_positions("polymarket")
        
        assert len(positions) == 1
        assert positions[0].token_id == "active_token"
    
    def test_update_wallet_balance(self, paper_store):
        """Test wallet balance update."""
        # Ensure wallet exists first
        paper_store.get_wallet("polymarket")
        
        paper_store.update_wallet_balance("polymarket", Decimal("750.00"))
        wallet = paper_store.get_wallet("polymarket")
        
        assert wallet.balance == Decimal("750.00")
    
    def test_get_position_by_token(self, paper_store):
        """Test retrieving specific position by token ID."""
        paper_store.save_position(PaperPosition(
            token_id="target_token",
            market_id="market1",
            outcome="YES",
            size=Decimal("20"),
            avg_price=Decimal("0.75"),
            cost_basis=Decimal("15.00"),
            provider="polymarket"
        ))
        
        position = paper_store.get_position("target_token", "polymarket")
        
        assert position is not None
        assert position.token_id == "target_token"
        assert position.size == Decimal("20")
        
        # Test non-existent token
        non_existent = paper_store.get_position("non_existent", "polymarket")
        assert non_existent is None


class TestPaperTradingProvider:
    """Test suite for PaperTradingProvider."""
    
    @pytest.mark.asyncio
    async def test_buy_order_reduces_balance(self, paper_provider, mock_poly_provider):
        """Simulate buy, verify balance decreases."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        assert result["success"] is True
        balance = await paper_provider.get_balance()
        assert balance["balance"] < 1000.0
        # 1000 - 101 = 899. 899 >= 899.
        assert balance["balance"] >= 899.0 
    
    @pytest.mark.asyncio
    async def test_buy_order_creates_position(self, paper_provider, mock_poly_provider):
        """Verify position created on buy."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        assert result["success"] is True
        
        positions = await paper_provider.get_positions()
        assert len(positions) == 1
        assert positions[0]["token_id"] == "test_token"
        assert positions[0]["size"] > 0
    
    @pytest.mark.asyncio
    async def test_sell_order_increases_balance(self, paper_provider, mock_poly_provider):
        """Simulate sell, verify balance increases."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # First buy to create position
        await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        initial_balance = (await paper_provider.get_balance())["balance"]
        
        # Now sell
        mock_poly_provider.client.get_price.return_value = 0.55  # Price increased
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=100.0
        )
        
        assert result["success"] is True
        final_balance = (await paper_provider.get_balance())["balance"]
        assert final_balance > initial_balance
    
    @pytest.mark.asyncio
    async def test_sell_order_closes_position(self, paper_provider, mock_poly_provider):
        """Verify position size decreases on sell."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # Buy 200 shares
        buy_result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        shares_bought = buy_result["size"]
        
        # Sell half
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=shares_bought / 2
        )
        
        assert result["success"] is True
        
        positions = await paper_provider.get_positions()
        assert len(positions) == 1
        assert positions[0]["size"] > 0
        assert positions[0]["size"] < shares_bought
    
    @pytest.mark.asyncio
    async def test_insufficient_balance_rejects_buy(self, paper_provider, mock_poly_provider):
        """Verify balance checks work."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # Try to buy more than balance allows
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=2000.0  # More than 1000 balance
        )
        
        assert result["success"] is False
        assert "Insufficient balance" in result["error"]
    
    @pytest.mark.asyncio
    async def test_insufficient_shares_rejects_sell(self, paper_provider, mock_poly_provider):
        """Verify share checks work."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # Try to sell without position
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=100.0
        )
        
        assert result["success"] is False
        assert "Insufficient shares" in result["error"]
    
    @pytest.mark.asyncio
    async def test_fees_calculated_correctly(self, paper_provider, mock_poly_provider):
        """Verify 1% taker fee applied."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        assert result["success"] is True
        
        # Fee should be 1% of $100 = $1.00
        expected_fee = 100.0 * 0.01
        assert abs(result["fee"] - expected_fee) < 0.01
    
    @pytest.mark.asyncio
    async def test_sell_fee_calculated_correctly(self, paper_provider, mock_poly_provider):
        """Verify 1% taker fee applied to sell."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # Buy first
        await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        # Sell
        mock_poly_provider.client.get_price.return_value = 0.55
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=100.0
        )
        
        assert result["success"] is True
        
        # Fee should be 1% of proceeds (100 * 0.55 = 55, fee = 0.55)
        expected_proceeds = 100.0 * 0.55
        expected_fee = expected_proceeds * 0.01
        assert abs(result["fee"] - expected_fee) < 0.01
    
    @pytest.mark.asyncio
    async def test_pnl_calculations(self, paper_provider, mock_poly_provider):
        """Test realized/unrealized P&L."""
        mock_poly_provider.client.get_price.return_value = 0.50
        mock_poly_provider.client.get_midpoint.return_value = 0.50
        
        # Buy at 0.50
        await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        balance = await paper_provider.get_balance()
        positions = await paper_provider.get_positions()
        
        # Unrealized P&L should be 0 at purchase price
        assert positions[0]["unrealized_pnl"] == pytest.approx(0.0, abs=0.01)
        
        # Price goes up
        mock_poly_provider.client.get_price.return_value = 0.60
        mock_poly_provider.client.get_midpoint.return_value = 0.60
        
        balance = await paper_provider.get_balance()
        positions = await paper_provider.get_positions()
        
        # Unrealized P&L should be positive
        assert positions[0]["unrealized_pnl"] > 0
        
        # Sell at 0.60
        initial_balance = balance["balance"]
        sell_result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=100.0
        )
        
        # Realized P&L should be in wallet
        final_balance = await paper_provider.get_balance()
        assert final_balance["realized_pnl"] > 0
    
    @pytest.mark.asyncio
    async def test_reset_clears_all_data(self, paper_provider):
        """Test reset functionality."""
        # Create some positions and trades
        paper_provider.store.save_position(PaperPosition(
            token_id="test",
            market_id="market1",
            outcome="YES",
            size=Decimal("10"),
            avg_price=Decimal("0.50"),
            cost_basis=Decimal("5.00"),
            provider=paper_provider.provider_name
        ))
        
        # Reset
        result = await paper_provider.reset(initial_balance=500.0)
        
        assert result["success"] is True
        
        # Check all data cleared
        positions = await paper_provider.get_positions()
        assert len(positions) == 0
        
        balance = await paper_provider.get_balance()
        assert balance["balance"] == 500.0
        assert balance["initial_balance"] == 500.0
    
    @pytest.mark.asyncio
    async def test_get_balance_includes_paper_mode_flag(self, paper_provider):
        """Verify balance returns paper_mode flag."""
        balance = await paper_provider.get_balance()
        
        assert "paper_mode" in balance
        assert balance["paper_mode"] is True
    
    @pytest.mark.asyncio
    async def test_get_trades_history(self, paper_provider, mock_poly_provider):
        """Test trade history retrieval."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # Execute multiple trades
        await paper_provider.place_market_order(
            token_id="token1",
            side="BUY",
            amount=50.0
        )
        await paper_provider.place_market_order(
            token_id="token2",
            side="BUY",
            amount=75.0
        )
        
        trades = await paper_provider.get_trades()
        
        assert len(trades) == 2
        assert all("paper_mode" in t for t in trades)
        assert all(t["paper_mode"] for t in trades)
    
    @pytest.mark.asyncio
    async def test_average_into_existing_position(self, paper_provider, mock_poly_provider):
        """Test averaging into existing position."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # First buy
        result1 = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        # Second buy at different price
        mock_poly_provider.client.get_price.return_value = 0.60
        result2 = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        positions = await paper_provider.get_positions()
        assert len(positions) == 1
        
        # Average price should be between 0.50 and 0.60
        avg_price = positions[0]["avg_price"]
        assert 0.50 < avg_price < 0.60
    
    @pytest.mark.asyncio
    async def test_get_current_price_error_handling(self, paper_provider, mock_poly_provider):
        """Test handling of price fetch errors."""
        mock_poly_provider.client.get_midpoint.side_effect = Exception("API Error")
        
        # Create a position first
        mock_poly_provider.client.get_price.return_value = 0.50
        await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        # Get balance should handle price errors gracefully
        balance = await paper_provider.get_balance()
        assert balance is not None


class TestIntegration:
    """Integration tests for paper trading workflow."""
    
    @pytest.mark.asyncio
    async def test_full_trading_workflow(self, paper_provider, mock_poly_provider):
        """Complete buy/sell cycle."""
        # Buy at 0.50
        mock_poly_provider.client.get_price.return_value = 0.50
        buy_result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        assert buy_result["success"] is True
        initial_balance = (await paper_provider.get_balance())["balance"]
        
        # Verify position created
        positions = await paper_provider.get_positions()
        assert len(positions) == 1
        
        # Sell at 0.60 (profit)
        mock_poly_provider.client.get_price.return_value = 0.60
        sell_result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=buy_result["size"]
        )
        
        assert sell_result["success"] is True
        final_balance = (await paper_provider.get_balance())["balance"]
        
        # Should have profit (minus fees)
        assert final_balance > initial_balance
        
        # Verify position closed
        positions = await paper_provider.get_positions()
        assert len(positions) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_positions(self, paper_provider, mock_poly_provider):
        """Track multiple positions."""
        mock_poly_provider.client.get_price.return_value = 0.50
        
        # Buy multiple tokens
        await paper_provider.place_market_order(
            token_id="token1",
            side="BUY",
            amount=50.0
        )
        await paper_provider.place_market_order(
            token_id="token2",
            side="BUY",
            amount=50.0
        )
        await paper_provider.place_market_order(
            token_id="token3",
            side="BUY",
            amount=50.0
        )
        
        positions = await paper_provider.get_positions()
        assert len(positions) == 3
        
        token_ids = {p["token_id"] for p in positions}
        assert "token1" in token_ids
        assert "token2" in token_ids
        assert "token3" in token_ids
    
    @pytest.mark.asyncio
    async def test_real_price_fetching(self, paper_provider, mock_poly_provider):
        """Mock price fetching verification."""
        mock_poly_provider.client.get_price.return_value = 0.75
        mock_poly_provider.client.get_midpoint.return_value = 0.75
        
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        assert result["success"] is True
        assert result["price"] == 0.75
        
        # Verify price methods were called
        mock_poly_provider.client.get_price.assert_called()
    
    @pytest.mark.asyncio
    async def test_price_fetching_for_sides(self, paper_provider, mock_poly_provider):
        """Test different price fetching for buy vs sell."""
        # Buy with bid price
        mock_poly_provider.client.get_price.return_value = 0.50
        buy_result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        mock_poly_provider.client.get_price.assert_called_with("test_token", "BUY")
        assert buy_result["price"] == 0.50
        
        # Sell with ask price
        mock_poly_provider.client.get_price.return_value = 0.55
        sell_result = await paper_provider.place_market_order(
            token_id="test_token",
            side="SELL",
            amount=buy_result["size"]
        )
        
        mock_poly_provider.client.get_price.assert_called_with("test_token", "SELL")
        assert sell_result["price"] == 0.55
    
    @pytest.mark.asyncio
    async def test_error_handling_on_price_fetch(self, paper_provider, mock_poly_provider):
        """Test error handling when price fetch fails."""
        mock_poly_provider.client.get_price.side_effect = Exception("Network error")
        
        result = await paper_provider.place_market_order(
            token_id="test_token",
            side="BUY",
            amount=100.0
        )
        
        assert result["success"] is False
        assert "Failed to get market price" in result["error"]
    
    @pytest.mark.asyncio
    async def test_trading_workflow_with_multiple_providers(self, paper_store, mock_poly_provider):
        """Test trading with multiple providers."""
        # Create providers for different exchanges
        poly_provider = PaperTradingProvider(mock_poly_provider, paper_store, "polymarket")
        await poly_provider.initialize()
        
        kalshi_provider = PaperTradingProvider(mock_poly_provider, paper_store, "kalshi")
        await kalshi_provider.initialize()
        
        # Buy on polymarket
        mock_poly_provider.client.get_price.return_value = 0.50
        poly_result = await poly_provider.place_market_order(
            token_id="poly_token",
            side="BUY",
            amount=100.0
        )
        
        assert poly_result["success"] is True
        
        # Buy on kalshi
        kalshi_result = await kalshi_provider.place_market_order(
            token_id="kalshi_token",
            side="BUY",
            amount=100.0
        )
        
        assert kalshi_result["success"] is True
        
        # Verify both balances
        poly_balance = await poly_provider.get_balance()
        kalshi_balance = await kalshi_provider.get_balance()
        
        assert poly_balance["balance"] < 1000.0
        assert kalshi_balance["balance"] < 1000.0
        assert poly_balance["balance"] > 890.0
        assert kalshi_balance["balance"] > 890.0


@pytest.mark.asyncio
async def test_provider_initialization(mock_poly_provider, paper_store):
    """Test provider initialization."""
    provider = PaperTradingProvider(mock_poly_provider, paper_store)
    
    assert not provider._initialized
    
    await provider.initialize()
    
    assert provider._initialized
    
    # Wallet should be created
    wallet = paper_store.get_wallet("polymarket")
    assert wallet.balance == Decimal("1000.00")


@pytest.mark.asyncio
async def test_provider_with_custom_provider_name(mock_poly_provider, paper_store):
    """Test provider with custom provider name."""
    provider = PaperTradingProvider(mock_poly_provider, paper_store, "custom_exchange")
    await provider.initialize()
    
    balance = await provider.get_balance()
    
    assert balance["paper_mode"] is True
    assert provider.provider_name == "custom_exchange"
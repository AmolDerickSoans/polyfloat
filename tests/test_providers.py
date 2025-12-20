import pytest
from polycli.providers.polymarket import PolyProvider

@pytest.mark.asyncio
async def test_poly_provider_init():
    provider = PolyProvider(api_key="test")
    assert provider is not None

@pytest.mark.asyncio
async def test_poly_provider_get_markets():
    provider = PolyProvider(api_key="test")
    markets = await provider.get_markets(limit=10)
    assert isinstance(markets, list)

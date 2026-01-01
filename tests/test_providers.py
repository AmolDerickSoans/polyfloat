import pytest
from polycli.providers.polymarket import PolyProvider

@pytest.mark.asyncio
async def test_poly_provider_init():
    provider = PolyProvider(private_key="0x" + "1" * 64)
    assert provider is not None
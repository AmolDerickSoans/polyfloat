import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# Mock kalshi_python before importing provider
mock_kalshi = MagicMock()
sys.modules["kalshi_python"] = mock_kalshi

from polycli.providers.kalshi import KalshiProvider

@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {
        "KALSHI_KEY_ID": "test_key_id",
        "KALSHI_PRIVATE_KEY_PATH": "test_key.pem"
    }):
        yield

@pytest.fixture
def mock_signer():
    with patch("polycli.providers.kalshi.KalshiAuth") as MockAuth:
        instance = MockAuth.return_value
        # Mock get_headers to return a predictable signature
        instance.get_headers.return_value = {"WAL-Auth": "signed_header_value"}
        yield instance

def test_rsa_signing_injection(mock_env, mock_signer):
    # Setup mock API client
    mock_api_instance = MagicMock()
    mock_client = MagicMock()
    mock_api_instance.api_client = mock_client
    
    # Original call_api mock
    original_mock = MagicMock(return_value=["response"])
    mock_client.call_api = original_mock
    
    mock_kalshi.ApiInstance.return_value = mock_api_instance
    mock_kalshi.Configuration.return_value = MagicMock()
    
    # Initialize provider
    provider = KalshiProvider()
    
    # Verify signer was initialized
    mock_signer.get_headers.assert_not_called() # Should only be called when API is called
    
    # Manually trigger the patched call_api
    # We simulate what generated code does: calling api_client.call_api
    # The provider monkey-patches this method on init.
    
    # Arguments mimicking call_api(resource_path, method, ..., header_params=..., body=...)
    # index 0: path, 1: method
    # header_params is usually passed as kwarg or arg index 4.
    
    # Let's call it via the instance's client (which is now the wrapper)
    provider.api_instance.api_client.call_api(
        "/events", "GET", 
        header_params={"Existing": "Header"},
        body=None
    )
    
    # Now check if get_headers was called
    mock_signer.get_headers.assert_called_with("GET", "/events", None)
    
    # And check if the original call_api (the mock we set up) was called with updated headers
    args, kwargs = original_mock.call_args
    
    # Note: Because of the monkey patch, 'mock_client.call_api' inside the wrapper refers to the ORIGINAL mock.
    # The wrapper is what we just called.
    # Wait, if we called `provider.api_instance.api_client.call_api`, we called the WRAPPER.
    # The wrapper calls `original_call_api`.
    # `original_call_api` is the `mock_client.call_api` BEFORE patching.
    # But `mock_client` is a MagicMock. When we access `mock_client.call_api` inside the wrapper,
    # does it refer to the same object?
    # Yes, `internal_client = self.api_instance.api_client`.
    # `original_call_api = internal_client.call_api`.
    # `internal_client.call_api = signed_call_api`.
    # So `original_call_api` holds the reference to the mock method.
    
    # Verification:
    # 1. get_headers called correctly?
    mock_signer.get_headers.assert_called_once()
    
    # 2. original_call_api called with merged headers?
    # args[0] is path, args[1] is method.
    # header_params might be in kwargs or args.
    # In our test call, we passed header_params as kwarg.
    
    called_kwargs = kwargs
    headers = called_kwargs.get("header_params", {})
    assert "WAL-Auth" in headers, "WAL-Auth header missing from downstream call"
    assert headers["WAL-Auth"] == "signed_header_value"
    assert headers["Existing"] == "Header"

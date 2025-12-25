import os
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from polycli.cli import app

runner = CliRunner()

@pytest.fixture(autouse=True)
def clean_env():
    """Clean up env vars after tests"""
    old_environ = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(old_environ)

def test_ephemeral_flags_injection():
    """
    Test that providing flags injects them into os.environ for the command execution duration.
    """
    with patch("polycli.cli.ensure_credentials") as mock_ensure:
        # We invoke 'version' command which is harmless.
        # The flags are on the main callback, so they must be before the command.
        result = runner.invoke(app, [
            "--poly-key", "0xEPHEMERAL",
            "--gemini-key", "GEMINI_EPHEMERAL",
            "--kalshi-email", "test@kalshi.com",
            "--kalshi-pass", "secret123",
            "--kalshi-key-id", "kid-123",
            "--kalshi-pem", "/path/to/key.pem",
            "version"
        ])
        
        assert result.exit_code == 0
        
        # Verify all flags were mapped to env vars
        assert os.environ.get("POLY_PRIVATE_KEY") == "0xEPHEMERAL"
        assert os.environ.get("GOOGLE_API_KEY") == "GEMINI_EPHEMERAL"
        assert os.environ.get("KALSHI_EMAIL") == "test@kalshi.com"
        assert os.environ.get("KALSHI_PASSWORD") == "secret123"
        assert os.environ.get("KALSHI_KEY_ID") == "kid-123"
        assert os.environ.get("KALSHI_PRIVATE_KEY_PATH") == "/path/to/key.pem"

def test_no_flags_leaves_env_untouched():
    """Test that running without flags doesn't clear existing env vars or set new ones."""
    os.environ["POLY_PRIVATE_KEY"] = "0xEXISTING"
    
    with patch("polycli.cli.ensure_credentials") as mock_ensure:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        
        assert os.environ.get("POLY_PRIVATE_KEY") == "0xEXISTING"
        assert "KALSHI_EMAIL" not in os.environ # Should not be set if not provided

def test_persistent_flags_save_to_env():
    """Test that using --save writes the values to the .env file."""
    
    with patch("polycli.cli.set_key") as mock_set_key, \
         patch("polycli.cli.ensure_credentials"):
         
        result = runner.invoke(app, [
            "--poly-key", "0xPERSIST",
            "--save",
            "version"
        ])
        
        # Current status: Green
        if result.exit_code != 0:
            pytest.fail(f"CLI failed to accept --save: {result.stdout}")
            
        # Verify set_key was called
        mock_set_key.assert_any_call(".env", "POLY_PRIVATE_KEY", "0xPERSIST")
        mock_set_key.assert_any_call(".env", "SKIP_POLY", "false")

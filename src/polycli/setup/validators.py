"""Validation functions for setup wizard."""
import asyncio
import re
from typing import Tuple
import httpx
import structlog

logger = structlog.get_logger()


class PolymarketValidator:
    """Validate Polymarket credentials."""
    
    @staticmethod
    def validate_private_key(key: str) -> Tuple[bool, str]:
        """Validate private key format."""
        if not key:
            return False, "Private key is required"
        
        # Should be hex, optionally with 0x prefix
        key = key.strip()
        if key.startswith("0x"):
            key = key[2:]
        
        if len(key) != 64:
            return False, "Private key must be 64 hex characters (32 bytes)"
        
        if not all(c in "0123456789abcdefABCDEF" for c in key):
            return False, "Private key must contain only hexadecimal characters"
        
        return True, "Valid format"
    
    @staticmethod
    def validate_address(address: str) -> Tuple[bool, str]:
        """Validate Ethereum address format."""
        if not address:
            return False, "Address is required"
        
        address = address.strip()
        if not address.startswith("0x"):
            return False, "Address must start with 0x"
        
        if len(address) != 42:
            return False, "Address must be 42 characters (0x + 40 hex)"
        
        if not all(c in "0123456789abcdefABCDEFx" for c in address):
            return False, "Invalid address format"
        
        return True, "Valid format"
    
    @staticmethod
    async def test_connection(private_key: str, funder: str, signature_type: int = 0) -> Tuple[bool, str]:
        """Test Polymarket connection with credentials."""
        try:
            from py_clob_client.client import ClobClient
            
            # Ensure proper format
            if not private_key.startswith("0x"):
                private_key = f"0x{private_key}"
            
            client = ClobClient(
                "https://clob.polymarket.com",
                key=private_key,
                chain_id=137,
                signature_type=signature_type,
                funder=funder
            )
            
            # Try to create API credentials
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
            
            # Test with a simple read operation
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            balance = client.get_balance_allowance(params)
            
            return True, f"Connected! Balance: ${float(balance.get('balance', 0)):.2f} USDC"
        
        except Exception as e:
            logger.error("Polymarket connection test failed", error=str(e))
            return False, f"Connection failed: {str(e)}"


class KalshiValidator:
    """Validate Kalshi credentials."""
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """Validate email format."""
        if not email:
            return False, "Email is required"
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "Invalid email format"
        
        return True, "Valid format"
    
    @staticmethod
    async def test_connection(api_key: str) -> Tuple[bool, str]:
        """Test Kalshi API connection."""
        try:
            # Kalshi uses API key in Authorization header
            # GET /portfolio/balance to test
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://trading-api.kalshi.com/trade-api/v2/portfolio/balance",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    balance = data.get("balance", 0) / 100  # Kalshi uses cents
                    return True, f"Connected! Balance: ${balance:.2f}"
                elif response.status_code == 401:
                    return False, "Invalid API key"
                else:
                    return False, f"API error: {response.status_code}"
        
        except Exception as e:
            logger.error("Kalshi connection test failed", error=str(e))
            return False, f"Connection failed: {str(e)}"


class NewsApiValidator:
    """Validate News API credentials."""
    
    @staticmethod
    async def test_newsapi(api_key: str) -> Tuple[bool, str]:
        """Test NewsAPI connection."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={
                        "apiKey": api_key,
                        "country": "us",
                        "pageSize": 1
                    }
                )
                
                if response.status_code == 200:
                    return True, "NewsAPI connected successfully"
                elif response.status_code == 401:
                    return False, "Invalid API key"
                else:
                    return False, f"API error: {response.status_code}"
        
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    @staticmethod
    async def test_tavily(api_key: str) -> Tuple[bool, str]:
        """Test Tavily API connection."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": "test",
                        "max_results": 1
                    }
                )
                
                if response.status_code == 200:
                    return True, "Tavily connected successfully"
                elif response.status_code == 401:
                    return False, "Invalid API key"
                else:
                    return False, f"API error: {response.status_code}"
        
        except Exception as e:
            return False, f"Connection failed: {str(e)}"


class GoogleValidator:
    """Validate Google API credentials."""
    
    @staticmethod
    async def test_gemini(api_key: str) -> Tuple[bool, str]:
        """Test Google Gemini API connection."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                    json={
                        "contents": [{"parts": [{"text": "Hello"}]}]
                    }
                )
                
                if response.status_code == 200:
                    return True, "Gemini API connected successfully"
                elif response.status_code == 401 or response.status_code == 403:
                    return False, "Invalid API key"
                else:
                    return False, f"API error: {response.status_code}"
        
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

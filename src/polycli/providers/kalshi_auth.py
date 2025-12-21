
import base64
import time
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import serialization
from typing import Dict, Any

class KalshiAuth:
    def __init__(self, key_id: str, private_key_path: str):
        self.key_id = key_id
        
        with open(private_key_path, "rb") as key_file:
            self.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None
            )

    def get_headers(self, method: str, path: str, body: Any = None) -> Dict[str, str]:
        # Timestamp in string milliseconds
        timestamp = str(int(time.time() * 1000))
        
        # Prepare content to sign
        # Signature = Sign(timestamp + method + path + body_str)
        # Note: path should include query params if Kalshi requires it? 
        # Usually standard REST signing is path only or full path+query.
        # Kalshi V2 docs say: "path" is the relative path e.g. /trade-api/v2/markets
        # It does NOT explicitly say query params in some versions, but usually it's safer to include if part of URI.
        # However, generated SDK splits URL and query params.
        # We will assume 'path' passed here is the full relative URI provided by REST client.
        
        body_str = ""
        if body:
             # Canonicalize JSON? 
             # Usually standard json.dumps with no spaces or as supplied.
             # Since we intercept before sending, we might receive dict or str.
             if isinstance(body, (dict, list)):
                 body_str = json.dumps(body, separators=(',', ':'))
             else:
                 body_str = str(body)
        
        msg = timestamp + method.upper() + path + body_str
        message_bytes = msg.encode('utf-8')
        
        # RSA-PSS Signing
        signature = self.private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        b64_sig = base64.b64encode(signature).decode('utf-8')
        
        return {
            "WAL-Auth": f"{self.key_id} {timestamp} {b64_sig}",
            "Content-Type": "application/json"
        }

    def get_ws_headers(self, method: str, path: str) -> Dict[str, str]:
        """Generate headers for WS Handshake with Kalshi specific format"""
        timestamp = str(int(time.time() * 1000))
        msg = timestamp + method.upper() + path
        message_bytes = msg.encode('utf-8')
        
        signature = self.private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        b64_sig = base64.b64encode(signature).decode('utf-8')

        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": b64_sig,
            "KALSHI-ACCESS-TIMESTAMP": timestamp
        }

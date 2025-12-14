# tripay.py
import os
import time
import hmac
import hashlib
import requests
from typing import Dict, Any, List

def _base_url() -> str:
    mode = os.getenv("TRIPAY_MODE", "production").lower()
    return "https://tripay.co.id/api-sandbox" if mode == "sandbox" else "https://tripay.co.id/api"

def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['TRIPAY_API_KEY']}"}

def signature_closed_payment(merchant_code: str, merchant_ref: str, amount: int, private_key: str) -> str:
    sign_str = f"{merchant_code}{merchant_ref}{amount}"
    return hmac.new(private_key.encode("latin-1"), sign_str.encode("latin-1"), hashlib.sha256).hexdigest()

def callback_signature(raw_body: bytes, private_key: str) -> str:
    return hmac.new(private_key.encode("latin-1"), raw_body, hashlib.sha256).hexdigest()

def list_payment_channels() -> List[Dict[str, Any]]:
    # GET /merchant/payment-channel :contentReference[oaicite:4]{index=4}
    r = requests.get(f"{_base_url()}/merchant/payment-channel", headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(data.get("message") or "Failed to fetch channels")
    return data["data"]

def create_transaction(payload: Dict[str, Any]) -> Dict[str, Any]:
    # POST /transaction/create :contentReference[oaicite:5]{index=5}
    r = requests.post(f"{_base_url()}/transaction/create", data=payload, headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(data.get("message") or "Create transaction failed")
    return data["data"]

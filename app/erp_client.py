import os, requests
from typing import List, Dict

ERP_BASE = os.getenv("ERP_BASE_URL", "http://localhost:8000")

def post_vendor_bill(vendor_id: str, invoice_number: str, invoice_date: str, currency: str, lines: List[Dict]) -> str:
    payload = {
        "vendor_id": vendor_id or "UNKNOWN",
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "currency": currency or "USD",
        "lines": [{"description": ln.get("description","Item"), "qty": ln.get("qty",0.0), "unit_price": ln.get("unit_price",0.0), "gl_account": ln.get("gl_account","6401")} for ln in lines]
    }
    r = requests.post(f"{ERP_BASE}/vendor-bills", json=payload, timeout=15)
    r.raise_for_status()
    return r.json().get("id")

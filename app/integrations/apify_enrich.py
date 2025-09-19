import os
from typing import Dict, Optional

HEURISTICS = {
    "ACME": {"website": "https://acme.example", "category": "office", "gl_suggestion": "6100 - Office Supplies"},
}

def enrich_vendor(vendor_id: str) -> Optional[Dict]:
    """Return {'website','category','gl_suggestion'} or None."""
    if not vendor_id:
        return None

    # quick local fallback heuristics
    for k, v in HEURISTICS.items():
        if k.lower() in vendor_id.lower():
            return v

    token = os.getenv("APIFY_TOKEN")
    if not token:
        # No token? Provide a sensible default
        return {"website": None, "category": None, "gl_suggestion": "6200 - COGS"}

    try:
        from apify_client import ApifyClient
        actor = os.getenv("APIFY_ACTOR_ID") or "apify/website-info-scraper"
        client = ApifyClient(token)
        run = client.actor(actor).call(run_input={"query": vendor_id, "maxResults": 1})
        items = run.get("items") or []
        first = items[0] if items else {}
        website = first.get("url") or first.get("domain")
        text = f"{first}"
        category = first.get("category") or first.get("tags") or None
        # naive GL suggestion based on detected words
        gl = "6100 - Office Supplies" if "office" in (text or "").lower() else "6200 - COGS"
        return {"website": website, "category": category, "gl_suggestion": gl}
    except Exception:
        return {"website": None, "category": None, "gl_suggestion": "6200 - COGS"}


def _normalize_url(url: str) -> str:
    """Best-effort URL normalizer to ensure consistent 'website' field."""
    if not url:
        return url
    u = str(url).strip()
    # Add scheme if missing
    if not u.startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    # Remove trailing slash for consistency
    if u.endswith("/"):
        u = u[:-1]
    return u
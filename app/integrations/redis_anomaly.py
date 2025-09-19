"""
Anomaly scoring for invoices using Redis.

Features
--------
- Loads environment variables robustly:
  1) Respect existing environment (e.g., GitHub Actions/Codespaces secrets).
  2) Attempt to load a .env file from:
     - DOTENV_PATH env var (if provided),
     - <repo_root>/.env (repo root is inferred),
     - CWD/.env
- Prefers Redis VL (vector KNN) if available; falls back to rolling z-score.

Public API
----------
anomaly_score(vendor_id: str, amount: float, line_count: int, invoice_key: str | None) -> float
get_history(vendor_id: str, limit: int = 50) -> list[float]
reset_vendor_history(vendor_id: str) -> None

Env
---
REDIS_URL = redis://user:pass@host:port/db

Install
-------
pip install redis
# optional for Redis VL prize track:
pip install redisvl
"""

from __future__ import annotations

import os
import math
import statistics
from typing import List, Optional

import redis  # required

# --- Robust .env loading (safe everywhere, optional) -------------------------
def _safe_load_dotenv():
    """
    Try to load a .env without relying on python-dotenv's find_dotenv(),
    which can fail in stdin/heredoc contexts. This is a no-op if:
    - REDIS_URL is already set in the environment, or
    - python-dotenv isn't installed, or
    - no .env is found.
    Load precedence:
      1) Existing os.environ (e.g., GitHub/Codespaces secrets)
      2) DOTENV_PATH if set
      3) <repo_root>/.env  (two levels up from this file: app/integrations/.. -> repo root)
      4) CWD/.env
    """
    if os.getenv("REDIS_URL"):
        return  # already provided by environment/secrets

    try:
        from dotenv import load_dotenv
    except Exception:
        return  # dotenv not installed: skip silently

    # 1) explicit path via env var
    explicit = os.getenv("DOTENV_PATH")
    if explicit and os.path.isfile(explicit):
        load_dotenv(dotenv_path=explicit, override=False)
        if os.getenv("REDIS_URL"):
            return

    # 2) try repo root (two levels up from this file)
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))  # <repo>/
    candidate = os.path.join(repo_root, ".env")
    if os.path.isfile(candidate):
        load_dotenv(dotenv_path=candidate, override=False)
        if os.getenv("REDIS_URL"):
            return

    # 3) try CWD
    cwd_candidate = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(cwd_candidate):
        load_dotenv(dotenv_path=cwd_candidate, override=False)

_safe_load_dotenv()
# -----------------------------------------------------------------------------


# Try to enable Redis VL mode (optional)
try:
    from redisvl.index import SearchIndex
    from redisvl.client import RedisClient
    from redisvl.query import VectorQuery

    _HAS_VL = True
except Exception:
    _HAS_VL = False


# -----------------------------
# Connection helpers
# -----------------------------
def _get_redis_client() -> redis.Redis:
    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError(
            "REDIS_URL not set. Provide it via environment (preferred for GitHub/Codespaces) "
            "or a local .env file at the repo root."
        )
    return redis.Redis.from_url(url)


# -----------------------------
# Fallback: Rolling z-score
# -----------------------------
_HISTORY_KEY = "vendor:{vendor_id}:amounts"
_MAX_HISTORY = 50  # keep last N amounts per vendor

def _zscore_push_and_score(r: redis.Redis, vendor_id: str, amount: float) -> float:
    """
    Push the amount to a rolling Redis List and compute a z-score.
    Returns 0.0 if not enough history or zero stdev.
    """
    key = _HISTORY_KEY.format(vendor_id=vendor_id or "UNKNOWN")

    r.lpush(key, amount)
    r.ltrim(key, 0, _MAX_HISTORY - 1)

    raw = r.lrange(key, 0, _MAX_HISTORY - 1)
    vals: List[float] = []
    for b in raw:
        try:
            vals.append(float(b))
        except Exception:
            pass

    if len(vals) < 5:
        return 0.0

    mean = statistics.fmean(vals)
    try:
        stdev = statistics.pstdev(vals)
    except statistics.StatisticsError:
        stdev = 0.0

    if stdev == 0.0:
        return 0.0

    z = (float(amount) - mean) / stdev
    return round(float(z), 2)


# -----------------------------
# Preferred: Redis VL (vector KNN)
# -----------------------------
_INDEX_NAME = "invoice_vl"
_SCHEMA = {
    "index": {"name": _INDEX_NAME, "prefix": ["inv:"]},
    "fields": [
        {"name": "vendor", "type": "tag"},
        {"name": "amount", "type": "numeric"},
        {"name": "line_count", "type": "numeric"},
        {"name": "vec", "type": "vector", "attrs": {"dims": 3, "distance_metric": "L2", "algorithm": "flat"}},
    ],
}

def _vendor_bucket(vendor_id: str) -> float:
    # hash-bucket vendor to [0,1)
    return float(abs(hash(vendor_id or "UNKNOWN")) % 1000) / 1000.0

def _ensure_vl_index(rc: "RedisClient") -> SearchIndex:
    idx = SearchIndex.from_dict(_SCHEMA, client=rc)
    if not idx.exists():
        idx.create()
    return idx

def _vl_record_and_knn_score(vendor_id: str, amount: float, line_count: int, invoice_key: str) -> float:
    """
    Store a 3D vector and compute average KNN distance as an anomaly score.
    Larger score => more unusual.
    """
    vec = [_vendor_bucket(vendor_id), float(amount or 0.0), float(line_count or 0)]
    rc = RedisClient.from_url(os.getenv("REDIS_URL"))
    idx = _ensure_vl_index(rc)

    key = f"inv:{vendor_id or 'UNKNOWN'}:{invoice_key or 'UNK'}"
    rc.hset(key, mapping={
        "vendor": vendor_id or "UNKNOWN",
        "amount": float(amount or 0.0),
        "line_count": int(line_count or 0),
        "vec": rc.store_vector(vec),
    })

    q = VectorQuery("vec", vec, return_fields=["vendor", "amount"], num_results=10)
    resp = idx.query(q)
    dists = [res["__distance"] for res in resp.results]

    if not dists:
        return 0.0

    score = sum(dists) / len(dists)
    return round(float(score), 3)


# -----------------------------
# Public API
# -----------------------------
def anomaly_score(
    vendor_id: str,
    amount: float,
    line_count: int,
    invoice_key: Optional[str] = None,
) -> float:
    """
    Compute an anomaly score for an invoice.
    - If redisvl is installed: average KNN distance (vector search).
    - Else: z-score over last N amounts for this vendor.
    """
    vendor_id = vendor_id or "UNKNOWN"

    try:
        r = _get_redis_client()
    except Exception:
        # If Redis isn't available, be neutral
        return 0.0

    if _HAS_VL:
        try:
            return _vl_record_and_knn_score(vendor_id, amount, line_count, invoice_key or "UNK")
        except Exception:
            # fall back to z-score if VL path fails
            pass

    try:
        return _zscore_push_and_score(r, vendor_id, float(amount or 0.0))
    except Exception:
        return 0.0


# -----------------------------
# Utilities
# -----------------------------
def get_history(vendor_id: str, limit: int = 50) -> List[float]:
    """Return up to `limit` historical amounts for a vendor (newest first)."""
    r = _get_redis_client()
    raw = r.lrange(_HISTORY_KEY.format(vendor_id=vendor_id or "UNKNOWN"), 0, max(0, limit - 1))
    out: List[float] = []
    for b in raw:
        try:
            out.append(float(b))
        except Exception:
            pass
    return out

def reset_vendor_history(vendor_id: str) -> None:
    """Delete rolling history for a vendor (z-score mode)."""
    r = _get_redis_client()
    r.delete(_HISTORY_KEY.format(vendor_id=vendor_id or "UNKNOWN"))

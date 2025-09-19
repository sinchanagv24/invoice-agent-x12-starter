import sys, os, json, datetime, time
from dotenv import load_dotenv
from app.x12.parse_810 import parse_810_text
from app.validate import validate_invoice
from app.integrations.redis_anomaly import anomaly_score
from app.integrations.apify_enrich import enrich_vendor
from app.integrations.ai_explain import explain_errors
from app.erp_client import post_vendor_bill
from app import state

# --- optional: HoneyHive logging (safe if not configured) --------------------
def _hh(event: str, data: dict):
    try:
        from app.integrations.honeyhive_log import log_run
        log_run(event, data)
    except Exception:
        pass

# --- robust .env load: prefer env vars; otherwise try repo-root .env ----------
def _load_env():
    if os.getenv("REDIS_URL"):
        return
    explicit = os.getenv("DOTENV_PATH")
    if explicit and os.path.isfile(explicit):
        load_dotenv(dotenv_path=explicit, override=False)
        return
    here = os.path.abspath(os.path.dirname(__file__))          # .../app
    repo_root = os.path.abspath(os.path.join(here, ".."))      # repo root
    candidate = os.path.join(repo_root, ".env")
    if os.path.isfile(candidate):
        load_dotenv(dotenv_path=candidate, override=False)
        return
    cwd_candidate = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(cwd_candidate):
        load_dotenv(dotenv_path=cwd_candidate, override=False)

def read_text(p: str) -> str:
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _today_iso() -> str:
    return datetime.date.today().isoformat()

def _maybe_upload_s3(local_path: str):
    """If S3_BUCKET is configured, upload artifact for demo credibility."""
    bucket = os.getenv("S3_BUCKET")
    if not bucket or not os.path.exists(local_path):
        return
    try:
        import boto3
        key = f"artifacts/{os.path.basename(local_path)}"
        boto3.client("s3").upload_file(local_path, bucket, key)
    except Exception:
        pass

def main(path: str):
    _load_env()

    raw = read_text(path)
    _hh("ingest:start", {"file": path})

    # Parse X12 810 -> dict
    doc = parse_810_text(raw)
    inv = doc.get("invoice", {}) or {}

    # Identify core fields
    vendor_id = (inv.get("parties", {}) or {}).get("remit_to_id") or "ACME"
    inv_no = inv.get("invoice_number") or "UNKNOWN"
    tds = inv.get("totals", {}).get("invoice_total", 0.0)
    inv_date = inv.get("invoice_date") or _today_iso()
    currency = inv.get("currency", "USD")
    line_items = inv.get("lines", []) or []

    _hh("parse:done", {"invoice_number": inv_no, "vendor_id": vendor_id, "tds": tds, "line_count": len(line_items)})

    # Enrichment (Apify heuristics/API).
    enrich = enrich_vendor(vendor_id) or {}
    inv.setdefault("enrichment", enrich)

    # Set GL suggestion per line (fallback to '6401' if enrichment missing)
    gl_default = enrich.get("gl_suggestion", "6401")
    for ln in line_items:
        ln["gl_account"] = ln.get("gl_account") or gl_default

    # Validate business rules
    errs = validate_invoice(doc)
    _hh("validate:done", {"invoice_number": inv_no, "errors": errs})

    # Anomaly score via Redis (VL → KNN distance; fallback → z-score)
    anomaly = anomaly_score(vendor_id, tds, len(line_items), inv_no)

    status = "READY"
    erp_id = None
    out_dir_ok = "data/processed"
    out_dir_bad = "data/rejects"
    os.makedirs(out_dir_ok, exist_ok=True)
    os.makedirs(out_dir_bad, exist_ok=True)

    if errs:
        status = "REJECTED"
        explanation = explain_errors(errs)
        doc["explanation"] = explanation
        doc["enrichment"] = enrich
        doc["anomaly"] = anomaly

        out_path = os.path.join(out_dir_bad, os.path.basename(path) + ".json")
        with open(out_path, "w") as f:
            json.dump(doc, f, indent=2)

        _maybe_upload_s3(out_path)
        # Ensure a consistent errors shape: list of (code, msg) pairs
        errs_to_store = []
        for e in errs:
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                errs_to_store.append((e[0], e[1]))
            elif isinstance(e, dict):
                errs_to_store.append((e.get("code", "VALIDATION"), e.get("message", json.dumps(e))))
            else:
                errs_to_store.append(("VALIDATION", str(e)))

        state.record_invoice(path, vendor_id, inv_no, status, tds, anomaly, errs_to_store, erp_id)
        _hh("result", {"invoice_number": inv_no, "status": status, "anomaly": anomaly, "errors": errs_to_store})
        print(f"[REJECTED] {inv_no}: {errs_to_store}\nExplanation:\n{explain_errors(errs)}")
        return

    # ----- ERP post (with DRY RUN support) -----
    errs_to_store = []
    if os.getenv("ERP_DRY_RUN", "0") == "1":
        erp_id = f"DEMO-{int(time.time())}"
        status = "POSTED"
    else:
        try:
            erp_id = post_vendor_bill(vendor_id, inv_date, inv_no, currency, line_items)
            status = "POSTED"
        except Exception as e:
            status = "REJECTED"  # normalize for UI
            errs_to_store = [("ERP_POST", str(e))]

    # Save output artifact
    doc["enrichment"] = enrich
    doc["anomaly"] = anomaly
    out_dir = out_dir_ok if status == "POSTED" else out_dir_bad
    out_path = os.path.join(out_dir, os.path.basename(path) + ".json")
    with open(out_path, "w") as f:
        json.dump(doc, f, indent=2)

    _maybe_upload_s3(out_path)
    state.record_invoice(path, vendor_id, inv_no, status, tds, anomaly, errs_to_store, erp_id)

    _hh("result", {"invoice_number": inv_no, "status": status, "erp_id": erp_id, "anomaly": anomaly})
    if status == "POSTED":
        print(f"[POSTED] {inv_no} | ERP_ID={erp_id} | anomaly={anomaly}")
    else:
        print(f"[REJECTED] {inv_no} | ERP_ID=None | anomaly={anomaly} | errors={errs_to_store}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.ingest <path-to-.edi>")
        sys.exit(1)
    main(sys.argv[1])

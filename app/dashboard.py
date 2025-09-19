import streamlit as st
import sqlite3, os, json, sys
import pandas as pd

# --- ensure project root is importable & load .env early ----------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    # Prefer repo-root .env; fallback to CWD
    load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=False)
    if not os.getenv("GLADIA_API_KEY"):
        load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)
except Exception:
    pass
# -----------------------------------------------------------------------------

STATE_DB = os.path.join(os.path.dirname(__file__), "state.db")

st.set_page_config(page_title="Invoice Agent Dashboard", layout="wide")
st.title("🧾 Invoice Agent — X12 → ERP")

# Helpful banner if Gladia key is missing
if not os.getenv("GLADIA_API_KEY"):
    st.warning("GLADIA_API_KEY is not set. Voice actions will fail until you add it to your .env.")

# ---------- Data access ----------
def load_data() -> pd.DataFrame:
    con = sqlite3.connect(STATE_DB)
    cur = con.cursor()
    cur.execute(
        """
        create table if not exists invoices(
            id integer primary key autoincrement,
            file_path text,
            vendor_id text,
            invoice_number text,
            status text,
            amount real,
            anomaly real,
            errors text,
            erp_id text,
            created_at real
        )
        """
    )
    df = pd.read_sql_query("select * from invoices order by id desc", con)
    return df

df = load_data()

# ---------- KPIs ----------
col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("Total Processed", int(len(df)))
with col_b:
    st.metric("Posted", int((df["status"] == "POSTED").sum()) if len(df) else 0)
with col_c:
    st.metric("Rejected", int((df["status"] == "REJECTED").sum()) if len(df) else 0)

# ---------- Table: Recent Invoices ----------
st.subheader("Recent Invoices")
if len(df):
    st.dataframe(
        df[["id", "invoice_number", "vendor_id", "status", "amount", "anomaly", "erp_id", "file_path"]],
        use_container_width=True,
        height=320,
    )
else:
    st.info("No invoices yet. Ingest one from your terminal and come back!")
    st.stop()

# ---------- Selector for detailed view ----------
st.subheader("Invoice Detail")

# Safer labels for selection (id — inv_no (status))
options = df.apply(
    lambda r: f"{int(r['id'])} — {r['invoice_number'] or 'UNKNOWN'} ({r['status']})",
    axis=1,
)
pick = st.selectbox("Select an invoice", options=list(options))
selected_id = int(pick.split(" — ", 1)[0])

row = df[df["id"] == selected_id]
if row.empty:
    st.warning("Selected invoice not found.")
    st.stop()

# Extract fields from row
inv_id = int(row["id"].iloc[0])
inv_no = row["invoice_number"].iloc[0] or "UNKNOWN"
status = row["status"].iloc[0] or "UNKNOWN"
vendor = row["vendor_id"].iloc[0] or "—"
amount = row["amount"].iloc[0]
anomaly = row["anomaly"].iloc[0]
erp_id = row["erp_id"].iloc[0]
path = row["file_path"].iloc[0] or ""

st.markdown(f"### Invoice {inv_id}: **{inv_no}** • Vendor: `{vendor}`")

# ---------- Resolve artifact JSON path & load once ----------
artifact_path = None
if path:
    ok_json = f"data/processed/{os.path.basename(path)}.json"
    bad_json = f"data/rejects/{os.path.basename(path)}.json"
    artifact_path = ok_json if os.path.exists(ok_json) else (bad_json if os.path.exists(bad_json) else None)

artifact_doc = None
if artifact_path and os.path.exists(artifact_path):
    try:
        with open(artifact_path, "r", encoding="utf-8") as f:
            artifact_doc = json.load(f)
    except Exception:
        artifact_doc = None

# ---------- Emphasized status panel ----------
if status == "REJECTED":
    # Parse readable reasons
    try:
        errs_list = json.loads(row["errors"].iloc[0] or "[]")
    except Exception:
        errs_list = []
    reasons = "\n".join([f"- **{code}**: {msg}" for code, msg in errs_list]) or "_No errors captured._"

    st.error(
        f"**Status:** REJECTED  \n"
        f"**Amount:** ${amount:,.2f} • **Anomaly:** {anomaly if anomaly is not None else '—'}\n\n"
        f"**Reason(s):**\n{reasons}"
    )

    # Optional: show explainer text from artifact (if present)
    if artifact_doc:
        exp = artifact_doc.get("explanation")
        if exp:
            st.info(exp)

elif status == "POSTED":
    st.success(
        f"**Status:** POSTED  \n"
        f"**ERP ID:** `{erp_id}`  \n"
        f"**Amount:** ${amount:,.2f} • **Anomaly:** {anomaly if anomaly is not None else '—'}"
    )
else:
    st.warning(f"**Status:** {status}")

# ---------- Enrichment panel ----------
def _get_enrichment(doc: dict):
    if not isinstance(doc, dict):
        return {}
    # prefer top-level "enrichment", fallback to invoice.enrichment
    e = doc.get("enrichment") or (doc.get("invoice", {}) or {}).get("enrichment")
    return e or {}

enrichment = _get_enrichment(artifact_doc)
with st.container():
    st.markdown("#### 🔎 Enrichment")
    if enrichment:
        website = enrichment.get("website")
        category = enrichment.get("category")
        gl = enrichment.get("gl_suggestion")
        lines = []
        if website:
            lines.append(f"- **Website:** [{website}]({website})")
        if category:
            lines.append(f"- **Category:** {category}")
        if gl:
            lines.append(f"- **GL Suggestion:** `{gl}`")
        if not lines:
            lines.append("_No enrichment fields available._")
        st.markdown("\n".join(lines))
    else:
        st.write("—")

# ---------- Voice action (Gladia) ----------
with st.expander("🎙 Voice action (Gladia)"):
    up = st.file_uploader("Upload an audio note (mp3/wav/m4a)", type=["mp3", "wav", "m4a"])
    if st.button("Transcribe & execute", disabled=up is None):
        import tempfile, re, subprocess
        try:
            from app.integrations.gladia_stt import transcribe_audio
        except Exception as e:
            st.error(f"Failed to import Gladia STT helper: {e}")
            st.stop()

        if not os.getenv("GLADIA_API_KEY"):
            st.error("GLADIA_API_KEY is not set. Add it to your .env and restart.")
            st.stop()

        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{up.name}")
            tmp.write(up.read())
            tmp.flush()
            text = transcribe_audio(tmp.name)
            st.write("Transcript:", text)

            invno = (row["invoice_number"].iloc[0] or "UNKNOWN")
            # Very simple intent parser for demo
            if re.search(r"\bapprove\b", text, re.I):
                # Re-run ingest to (re)post this invoice; use current interpreter for venv safety
                subprocess.run([sys.executable, "-m", "app.ingest", path], check=False)
                st.success(f"Approved intent detected → re-ingested {invno}")
            elif re.search(r"\breject\b", text, re.I):
                st.error(f"Reject intent detected for {invno} (demo: logged only)")
            else:
                st.info("No approve/reject intent detected.")
        finally:
            try:
                if tmp:
                    os.unlink(tmp.name)
            except Exception:
                pass

# ---------- Line Items table (with GL & amounts) ----------
def _get_lines(doc: dict):
    if not isinstance(doc, dict):
        return []
    inv = doc.get("invoice") or {}
    return inv.get("lines") or []

lines = _get_lines(artifact_doc)
st.markdown("#### 📦 Line Items")
if lines:
    # Normalize into DataFrame
    rows = []
    for ln in lines:
        rows.append({
            "line_no": ln.get("line_no"),
            "item": ln.get("item"),
            "description": ln.get("description"),
            "qty": ln.get("qty"),
            "uom": ln.get("uom"),
            "unit_price": ln.get("unit_price"),
            "ext_price": ln.get("ext_price"),
            "gl_account": ln.get("gl_account"),
        })
    ldf = pd.DataFrame(rows, columns=["line_no", "item", "description", "qty", "uom", "unit_price", "ext_price", "gl_account"])
    st.dataframe(ldf, use_container_width=True, height=220)
else:
    st.write("—")

# ---------- Side-by-side detail panels ----------
col1, col2 = st.columns(2)

with col1:
    st.markdown("**Errors (raw list)**")
    try:
        errs = json.loads(row["errors"].iloc[0] or "[]")
    except Exception:
        errs = []
    if errs:
        for code, msg in errs:
            st.write(f"- `{code}`: {msg}")
    else:
        st.write("—")

with col2:
    st.markdown("**Canonical JSON**")
    if artifact_doc:
        st.code(json.dumps(artifact_doc, indent=2), language="json")
    elif artifact_path:
        try:
            st.code(open(artifact_path).read(), language="json")
        except Exception:
            st.write("No JSON artifact found.")
    else:
        st.write("No JSON artifact found.")

st.caption("Tip: run `python -m app.ingest data/inbound/ACME_GOOD.edi` in a terminal while this dashboard is open.")

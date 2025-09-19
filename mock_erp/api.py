from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import sqlite3, hashlib, os

DB_PATH = os.path.join(os.path.dirname(__file__), "db.sqlite")

app = FastAPI(title="Mock ERP API", version="1.0")

def _db():
    con = sqlite3.connect(DB_PATH)
    con.execute("create table if not exists bills (id text primary key, vendor_id text, inv_no text, inv_date text, currency text)")
    con.execute("create table if not exists bill_lines (id text, ln integer, descr text, qty real, price real, gl text)")
    return con

class BillLine(BaseModel):
    description: str
    qty: float
    unit_price: float
    gl_account: str = "6401"

class Bill(BaseModel):
    vendor_id: str
    invoice_number: str
    invoice_date: str
    currency: str = "USD"
    lines: List[BillLine]

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/vendor-bills")
def create_bill(b: Bill):
    ext_id = hashlib.sha1(f"{b.vendor_id}|{b.invoice_number}".encode()).hexdigest()
    con = _db()
    with con:
        con.execute("insert or ignore into bills values(?,?,?,?,?)",
                    (ext_id, b.vendor_id, b.invoice_number, b.invoice_date, b.currency))
        for i, ln in enumerate(b.lines, 1):
            con.execute("insert into bill_lines values(?,?,?,?,?,?)",
                        (ext_id, i, ln.description, ln.qty, ln.unit_price, ln.gl_account))
    return {"id": ext_id}

import os, sqlite3, json, time

DB_PATH = os.path.join(os.path.dirname(__file__), "state.db")

def _db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""create table if not exists invoices(
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
    )""")
    return con

def record_invoice(file_path, vendor_id, invoice_number, status, amount, anomaly, errors, erp_id):
    con = _db()
    with con:
        con.execute("insert into invoices(file_path,vendor_id,invoice_number,status,amount,anomaly,errors,erp_id,created_at) values(?,?,?,?,?,?,?,?,?)",
                    (file_path, vendor_id, invoice_number, status, float(amount or 0), None if anomaly is None else float(anomaly), json.dumps(errors or []), erp_id, time.time()))

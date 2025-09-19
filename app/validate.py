from typing import List, Tuple

def validate_invoice(doc: dict):
    errs = []
    inv = doc.get("invoice", {})

    if not inv.get("invoice_number"):
        errs.append(("BIG02", "Missing invoice number (BIG02)."))
    if not inv.get("invoice_date"):
        errs.append(("BIG01", "Missing invoice date (BIG01)."))

    lines = inv.get("lines", [])
    if not lines:
        errs.append(("IT1", "No line items (IT1)."))

    # ✅ Totals math now includes SAC charges/allowances
    calc_lines = sum(l.get("ext_price", 0.0) for l in lines)
    tax_sum = sum(t.get("amount", 0.0) for t in inv.get("tax", []))
    charge_sum = sum(c.get("amount", 0.0) for c in inv.get("charges", []))
    tds = inv.get("totals", {}).get("invoice_total", None)

    if tds is None:
        errs.append(("TDS", "Missing invoice total (TDS)."))
    else:
        computed = calc_lines + tax_sum + charge_sum
        if abs(computed - tds) > 0.01:
            errs.append(("TDS", f"Totals mismatch: lines+tax+charges={computed:.2f} vs TDS={tds:.2f}."))

    ctt = inv.get("totals", {}).get("line_count", None)
    if ctt is not None and ctt != len(lines):
        errs.append(("CTT", f"Line count mismatch: CTT={ctt} vs actual={len(lines)}."))

    return errs

from datetime import datetime

import re

def _split_segments(text: str):
    """Split EDI into segments; handle '~' or newline terminators; regex fallback."""
    if not text:
        return []
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Primary: '~' or newline
    if "~" in t:
        segs = [s.strip() for s in t.split("~") if s.strip()]
    else:
        segs = [s.strip() for s in t.split("\n") if s.strip()]

    # Fallback: if we still have too few segments, extract by SEG*... pattern
    if len(segs) <= 2:
        segs = [m.group(0).strip() for m in re.finditer(r"[A-Z0-9]{2,3}\*[^~\n\r]*", t)]

    return segs

def _split_elems(seg: str, elem_sep='*'):
    """Split one segment into elements, trimming each piece."""
    parts = [p.strip() for p in seg.split(elem_sep)]
    return parts[0], parts[1:]



def parse_810_text(text: str) -> dict:
    out = {"meta":{}, "invoice": {"lines":[], "charges":[], "tax":[], "totals":{}}}
    segs = _split_segments(text)

    for seg in segs:
        tag, el = _split_elems(seg)
        if tag == 'ISA':
            out["meta"]["interchange_control"] = el[12] if len(el) > 12 else None
            out["meta"]["sender_id"] = (el[5] if len(el) > 5 else "").strip()
            out["meta"]["receiver_id"] = (el[7] if len(el) > 7 else "").strip()
        elif tag == 'GS':
            out["meta"]["group_control"] = el[5] if len(el) > 5 else None
        elif tag == 'ST':
            out["meta"]["transaction_control"] = el[1] if len(el) > 1 else None
        elif tag == 'BIG':
            if len(el) > 0 and el[0]:
                out["invoice"]["invoice_date"] = datetime.strptime(el[0], "%Y%m%d").date().isoformat()
            out["invoice"]["invoice_number"] = el[1] if len(el) > 1 else None
            if len(el) > 2 and el[2]:
                out["invoice"]["po_number"] = el[2]
        elif tag == 'N1':
            if len(el) >= 4 and el[0] == 'RE':
                out["invoice"].setdefault("parties", {})["bill_to_id"] = el[3]
            if len(el) >= 4 and el[0] == 'RI':
                out["invoice"].setdefault("parties", {})["remit_to_id"] = el[3]
        elif tag == 'ITD':
            # Terms: try to read day due (element 6 or 7); default 30
            days = None
            if len(el) > 6 and el[6]:
                days = el[6]
            elif len(el) > 7 and el[7]:
                days = el[7]
            out["invoice"]["terms"] = "NET" + (str(days) if days else "30")
        elif tag == 'IT1':
            line = {
                "line_no": int(el[0]) if len(el) > 0 and el[0].isdigit() else len(out["invoice"]["lines"])+1,
                "qty": float(el[1]) if len(el) > 1 and el[1] else 0.0,
                "uom": el[2] if len(el) > 2 else "EA",
                "unit_price": float(el[3]) if len(el) > 3 and el[3] else 0.0,
                "item": el[6] if len(el) > 6 else None
            }
            line["ext_price"] = round(line["qty"] * line["unit_price"], 2)
            line["description"] = f"Item {line['item'] or line['line_no']}"
            out["invoice"]["lines"].append(line)
        elif tag == 'TXI':
            # TXI amount is commonly N2 (implied cents). If it's an integer-like string with no decimal,
            # treat it as cents and divide by 100. Otherwise parse as float.
            try:
                raw_amt = el[1] if len(el) > 1 else None
                if raw_amt is None:
                    pass
                else:
                    raw = raw_amt.strip()
                    if raw and raw.isdigit():
                        amt = float(raw) / 100.0
                    else:
                        amt = float(raw)
                out["invoice"]["tax"].append({"type": el[0], "amount": round(amt, 2)})
            except Exception:
                pass
        elif tag == 'SAC':
            # SAC: Allowance/Charge. Commonly:
            # SAC01 = 'A' (allowance / subtract) or 'C' (charge / add)
            # SAC05 = amount (often plain dollars)
            try:
                kind = (el[0] if len(el) > 0 else '').upper()   # 'A' or 'C'
                amt_raw = el[4] if len(el) > 4 else None        # SAC05
                if amt_raw:
                    amt = float(amt_raw)
                    signed_amt = amt if kind != 'A' else -amt   # Allowance reduces total
                    out["invoice"]["charges"].append({
                        "type": kind or "C",
                        "amount": round(signed_amt, 2)
                    })
            except Exception:
                pass

        elif tag == 'TDS':
            try:
                # TDS often uses N2: implied cents
                tds_raw = float(el[0])
                inv_total = tds_raw/100.0 if tds_raw.is_integer() or tds_raw > 100 else tds_raw
                out["invoice"]["totals"]["invoice_total"] = round(inv_total, 2)
            except Exception:
                pass
        elif tag == 'CTT':
            try:
                out["invoice"]["totals"]["line_count"] = int(el[0])
            except Exception:
                pass
    return out

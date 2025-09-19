import os
from typing import List, Tuple

def explain_errors(errors: List[Tuple[str,str]], context_snippet: str = "") -> str:
    """If LLM keys present, you could wire LlamaIndex here.

    For hackathon speed, we do a simple template that cites likely X12 segments.
    """
    # Placeholder: human-friendly explanation
    parts = []
    for code, msg in errors:
        if code == "TDS":
            parts.append("- **TDS totals mismatch**: In X12 810, `TDS` is the invoice total (often N2 implied cents). Sum of line extended amounts plus taxes/charges must equal TDS. " + msg)
        elif code == "IT1":
            parts.append("- **IT1 missing**: At least one line item is required.")
        elif code == "BIG02":
            parts.append("- **BIG02 missing**: Invoice number not found in BIG segment.")
        elif code == "BIG01":
            parts.append("- **BIG01 missing**: Invoice date not found in BIG segment.")
        elif code == "CTT":
            parts.append("- **CTT mismatch**: CTT01 should equal count of IT1 lines.")
        else:
            parts.append(f"- {code}: {msg}")
    if not parts:
        return "No errors to explain."
    return "\n".join(parts)

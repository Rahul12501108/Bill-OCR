import os
import tempfile

from dec import decrypt_text, decrypt_file
from date import extract_date_from_text
from total import extract_total
from invoice import extract_invoice
from ven1 import get_vendor

# -------------------------------------------------------------
# MAIN FUNCTION
# ------------------------------------------------------------- 
def process_invoice_request(enc_date, enc_total, enc_invoice, enc_vendor, enc_file):

    # STEP 1 — decrypt all data
    dec_expected_date = decrypt_text(enc_date)
    dec_expected_total = decrypt_text(enc_total)
    dec_expected_invoice = decrypt_text(enc_invoice)
    dec_expected_vendor = decrypt_text(enc_vendor)

    # decrypt actual file bytes
    file_bytes = decrypt_file(enc_file)

    # save file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_bytes)
        temp_path = tmp.name

    # ---------------------------------------------------------
    # STEP 2 — run extractors
    # ---------------------------------------------------------
    text = ""  # you already have extract_text_full inside total.py
    from total import extract_text_full
    text = extract_text_full(temp_path)

    found_date = extract_date_from_text(text)
    found_total = extract_total(text)
    found_invoice = extract_invoice(text)
    found_vendor = get_vendor(temp_path)

    # ---------------------------------------------------------
    # STEP 3 — compare extracted vs decrypted expected
    # ---------------------------------------------------------
    result = {
        "date": found_date,
        "date_match": (found_date == dec_expected_date),

        "total": found_total,
        "total_match": (str(found_total).replace(" ", "") == dec_expected_total.replace(" ", "")),

        "invoice": found_invoice,
        "invoice_match": (found_invoice.lower() == dec_expected_invoice.lower()),

        "vendor": found_vendor,
        "vendor_match": (found_vendor.lower() == dec_expected_vendor.lower()),
    }

    # delete the temp file
    os.remove(temp_path)

    return result


# -------------------------------------------------------------
# TEST
# -------------------------------------------------------------
if __name__ == "__main__":
    # these 5 values will come encrypted from outside API
    print("Main ready — waiting for encrypted inputs")

import os
import base64
import uuid
import pandas as pd
from flask import Flask, request, jsonify
from dateutil import parser

# external extractors
from total import extract_total, extract_text_full
from invoice import extract_invoice
from date import extract_date_from_text

# ================= DATE NORMALIZER =================
def normalize_date(date_str):
    if not date_str:
        return None
    try:
        return parser.parse(str(date_str), dayfirst=True).date()
    except:
        return None

# ================= BASE64 DECODER =================
def decode_base64_file(base64_string):
    if "base64," in base64_string:
        base64_string = base64_string.split("base64,")[1]

    file_bytes = base64.b64decode(base64_string.strip())

    os.makedirs("temp_files", exist_ok=True)

    # detect file type
    if file_bytes.startswith(b"%PDF"):
        ext = ".pdf"
    elif file_bytes[:2] == b"PK":   # Excel xlsx
        ext = ".xlsx"
    else:
        ext = ".jpg"

    path = os.path.join("temp_files", f"{uuid.uuid4()}{ext}")

    with open(path, "wb") as f:
        f.write(file_bytes)

    return path

# ================= DUPLICATE CHECK =================
def check_duplicate(df, emp, inv, date, amt):
    if df.empty:
        return False

    dup = df[
        (df["Employee_Code"] == emp) &
        (df["Invoice_No"] == inv) &
        (df["Date"] == date) &
        (abs(df["Total_Amount"] - amt) <= 5)
    ]
    return not dup.empty

# ================= EXCEL SAVE =================
def insert_into_excel(records):
    DB = "claim.xlsx"

    if os.path.exists(DB):
        df = pd.read_excel(DB)
    else:
        df = pd.DataFrame(columns=[
            "Employee_Code",
            "Invoice_No",
            "Date",
            "Total_Amount",
            "Claim_Type"
        ])

    df = pd.concat([df, pd.DataFrame(records)], ignore_index=True)
    df.to_excel(DB, index=False)

# ================= PROCESS EXCEL ATTACHMENT =================
def process_excel_attachment(path, emp, ctype, voucher_amount, db_df):
    df = pd.read_excel(path)

    required_cols = ["Invoice_No", "Date", "Total_Amount"]
    for col in required_cols:
        if col not in df.columns:
            return {"error": f"{col} column missing in Excel"}

    excel_total = df["Total_Amount"].sum()

    # ✅ check voucher limit
    if excel_total > voucher_amount + 5:
        return {
            "error": "EXCEL_AMOUNT_EXCEEDS_VOUCHER",
            "excel_total": float(excel_total),
            "voucher_amount": voucher_amount
        }

    records = []

    for _, row in df.iterrows():
        inv = str(row["Invoice_No"])
        date_obj = normalize_date(row["Date"])
        amt = float(row["Total_Amount"])

        if check_duplicate(db_df, emp, inv, str(date_obj), amt):
            return {
                "error": "DUPLICATE_CLAIM",
                "invoice_number": inv,
                "invoice_date": str(date_obj),
                "total_amount": amt
            }

        records.append({
            "Employee_Code": emp,
            "Invoice_No": inv,
            "Date": str(date_obj),
            "Total_Amount": amt,
            "Claim_Type": ctype
        })

    return {"records": records, "total": excel_total}

# ================= CLAIM PROCESSOR =================
def process_claim(data):

    claim = data.get("Claim", {})
    emp = claim.get("Employee_Code")
    ctype = claim.get("Claim_Type")
    total_expected = float(claim.get("Total_Bill_Amount", 0))

    vouchers = claim.get("Vouchers", [])

    db_df = pd.read_excel("claim.xlsx") if os.path.exists("claim.xlsx") else pd.DataFrame()

    grand_total = 0
    all_records = []

    for v in vouchers:

        expected = float(v.get("Bill_Amount", 0))
        voucher_total = 0
        voucher_records = []

        from_date = normalize_date(v.get("From_Date"))
        to_date = normalize_date(v.get("To_Date"))

        attachments = v.get("Attachments", [])

        for att in attachments:

            file_data = att.get("base64File")
            if not file_data:
                continue

            path = decode_base64_file(file_data)

            # ========= EXCEL FILE =========
            if path.endswith(".xlsx"):
                result = process_excel_attachment(
                    path, emp, ctype, expected, db_df
                )

                if "error" in result:
                    return result

                voucher_records.extend(result["records"])
                voucher_total += result["total"]
                continue

            # ========= PDF / IMAGE =========
            text = extract_text_full(path)

            inv = extract_invoice(text)
            date_text = extract_date_from_text(text)
            invoice_date = normalize_date(date_text)

            # ✅ date validation
            if invoice_date and from_date and to_date:
                if not (from_date <= invoice_date <= to_date):
                    return {
                        "status": "INCORRECT_DATE",
                        "invoice_date": str(invoice_date),
                        "from_date": str(from_date),
                        "to_date": str(to_date),
                        "message": "Date is not between from and to date"
                    }

            total = float(extract_total(text) or 0)

            if check_duplicate(db_df, emp, inv, str(invoice_date), total):
                return {
                    "status": "DUPLICATE_CLAIM",
                    "invoice_number": inv,
                    "invoice_date": str(invoice_date),
                    "total_amount": total
                }

            voucher_total += total

            voucher_records.append({
                "Employee_Code": emp,
                "Invoice_No": inv,
                "Date": str(invoice_date),
                "Total_Amount": round(total, 2),
                "Claim_Type": ctype
            })

        # ✅ voucher validation
        if voucher_total > expected + 5:
            return {
                "status": "AMOUNT_MISMATCH",
                "expected_bill_amount": expected,
                "extracted_attachment_total": voucher_total
            }

        all_records.extend(voucher_records)
        grand_total += voucher_total

    # ✅ final claim validation
    if grand_total > total_expected + 5:
        return {
            "status": "CLAIM_TOTAL_MISMATCH",
            "total_attachments_amount": grand_total
        }

    # ✅ save only after all validations pass
    insert_into_excel(all_records)

    return {
        "status": "NEW_CLAIM",
        "records_saved": len(all_records),
        "total_attachments_amount": grand_total
    }

# ================= FLASK API =================
app = Flask(__name__)

@app.route("/process-claim", methods=["POST"])
def api():
    try:
        return jsonify(process_claim(request.get_json()))
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)})

if __name__ == "__main__":
    app.run(debug=True)

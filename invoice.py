import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import re
import os
 
# -----------------------------------------------------------
# TESSERACT PATH (add your path here)
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\VikasTiwari\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
 
# -----------------------------------------------------------
# POPPLER PATH FOR SCANNED PDF → IMAGE CONVERSION
POPLER_PATH = r"C:\poppler-25.07.0\Library\bin"
# -----------------------------------------------------------
 
 
# ------------------------- INVOICE EXTRACTION LOGIC (UNCHANGED) -------------------------
def extract_invoice(text):
 
    text_clean = (
        text.replace(",", " ")
            .replace(":", " ")
            .replace("#", " # ")
            .replace("-", " ")
    ).lower()
 
    address_words = [
        "india","karnataka","maharashtra","thane","bengaluru","mumbai",
        "road","village","taluka","district","dist","pin","pincode",
        "state","west","east","south","north"
    ]
 
    def is_not_address(line):
        return not any(w in line.lower() for w in address_words)
 
    invoice_keywords = [
        "invoice number", "invoice no", "invoice id", "invoice #",
        "tax invoice", "bill number", "bill no", "inv no", "invoice", "Patient Id"
    ]
 
    invoice_patterns = [
        r"(?:invoice\s*number|invoice\s*no|invoice\s*#|invoice\s*id|bill\s*no|bill\s*number|Patient\s*Id|inv\s*no)[\s:#]*([A-Za-z0-9\-\/]+)",
        r"invoice\s*#\s*([A-Za-z0-9]+)",
        r"invoice\s*no\s*([A-Za-z0-9]+)",
        r"invoice\s*id\s*([A-Za-z0-9]+)",
        r"\b([A-Z]{2,4}\d{6,12})\b",
 
    ]
 
    lines = text.split("\n")
 
    # First pass: keyword based
    for line in lines:
        if not is_not_address(line):
            continue
 
        low = line.lower()
 
        if any(k in low for k in invoice_keywords):
            for pat in invoice_patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
 
    # Second pass
    for pat in invoice_patterns:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            return m.group(1).strip()
 
    # Order ID fallback
    order_match = re.search(r"\bOD[0-9]{10,}\b", text_clean)
    if order_match:
        return "Invoice Missing - Using OrderID: " + order_match.group(0)
 
    return "Invoice Not Found"
 
 
# -------------------------- STRICT MATCHING LOGIC (UNCHANGED) --------------------------
def normalize_invoice(value):
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", value).lower()
 
 
def check_known_invoice_in_text(text, known_invoice):
    if not known_invoice:
        return False
 
    norm_known = normalize_invoice(known_invoice)
    candidates = re.findall(r"[A-Za-z0-9\-\/]+", text)
 
    for c in candidates:
        norm_c = normalize_invoice(c)
        if len(norm_c) == len(norm_known) and norm_c == norm_known:
            return True
 
    return False
 
 
# ------------------------ UNIVERSAL PDF/IMAGE TEXT EXTRACTOR -------------------------
def extract_text_full(filepath):
 
    ext = filepath.lower().split(".")[-1]
 
    # -------------------------------- PDF --------------------------------
    if ext == "pdf":
        text_out = ""
 
        try:
            pdf = pdfplumber.open(filepath)
 
            for pg in pdf.pages:
                txt = pg.extract_text()
                if txt and txt.strip():
                    text_out += "\n" + txt
                else:
                    # Page might be scanned → OCR
                    images = convert_from_path(
                        filepath,
                        first_page=pg.page_number,
                        last_page=pg.page_number,
                        poppler_path=POPLER_PATH
                    )
 
                    for img in images:
                        img = img.rotate(-90, expand=True)
                        ocr_text = pytesseract.image_to_string(img)
                        text_out += "\n" + ocr_text
 
            pdf.close()
            return text_out
 
        except Exception as e:
            # If pdfplumber fails → fallback OCR for whole PDF
            images = convert_from_path(filepath, poppler_path=POPLER_PATH)
            full_text = ""
            for img in images:
                img = img.rotate(-90, expand=True)
                full_text += pytesseract.image_to_string(img) + "\n"
            return full_text
 
    # -------------------------------- IMAGE --------------------------------
    else:
        img = Image.open(filepath)
        img = img.rotate(-90, expand=True)  # auto-rotate simple
        return pytesseract.image_to_string(img)
 
 
# -------------------------- MAIN EXECUTION ---------------------------
image_paths = [
    # # "bills_folder/invoice-4059842024232149839.pdf",
    # "bills_folder/Screenshot 2025-10-09 174619.png",
    # "bills_folder/ketan-medicalbill1052024211446776.pdf",
    # "bills_folder/rupali-medicalbill105202421167943.pdf"
]
 
known_invoice_number = "M06HL24I11684390"
 
for file in image_paths:
    print("\n--------------------------------------------")
    print("FILE:", file)
 
    text = extract_text_full(file)
    print("\nEXTRACTED TEXT (PREVIEW):")
    print(text[:500])  # only preview
 
    invoice_no = extract_invoice(text)
    print("\n>> Extracted Invoice No:", invoice_no)
 
    # Match known invoice always
    contains = check_known_invoice_in_text(text, known_invoice_number)
    print(f">> Known Invoice ({known_invoice_number}) Present?: {contains}")
import pdfplumber
import re
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# -----------------------------------------------------------
# TESSERACT PATH (add your path here)
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\VikasTiwari\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# -----------------------------------------------------------
# POPPLER PATH FOR SCANNED PDF → IMAGE CONVERSION
POPLER_PATH = r"C:\poppler-25.07.0\Library\bin"
# -----------------------------------------------------------


# -------------------------------------------------------------------------------------
# YOUR ORIGINAL FUNCTION (UNCHANGED EXACTLY)
# -------------------------------------------------------------------------------------
def extract_total(text):
    text_clean = text.replace(",", "")

    # Words that indicate address lines
    address_words = [
        "india", "karnataka", "maharashtra", "thane", "bengaluru", "mumbai",
        "road", "village", "taluka", "district", "dist", "pin", "pincode",
        "state", "west", "east", "south", "north"
    ]

    # --- 1. STRONG PATTERNS FOR TOTAL ---
    patterns = [
        r"\bGrand\s*Total\s*[₹RsINR\.\s]*([0-9]+\.[0-9]+|[0-9]+)",
        r"\bTotal\s*Due\s*[₹RsINR\.\s]*([0-9]+\.[0-9]+|[0-9]+)",
        r"\bDue\s*(Amount)?\s*[₹RsINR\.\s]*([0-9]+\.[0-9]+|[0-9]+)",
        r"\bTotal\s*(Amount|Payable|Bill)\s*[₹RsINR\.\s]*([0-9]+\.[0-9]+|[0-9]+)",
        r"\b(Invoice|Net)\s*(Total|Amount)\s*[₹RsINR\.\s]*([0-9]+\.[0-9]+|[0-9]+)",
        r"\b(Payment|Paid|VISA|Card|Cash|UPI)\s*[A-Za-z]*\s*[₹RsINR\.\s]*([0-9]+\.[0-9]+|[0-9]+)",
        r"\bTotal[\s:A-Za-z]*[₹RsINR]*\.?([0-9]+\.[0-9]+|[0-9]+)"
    ]

    def is_not_address(line):
        return not any(w in line.lower() for w in address_words)

    for pat in patterns:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            amt = m.group(m.lastindex)
            if amt and float(amt) > 50:
                return amt

    # --- 2. WEAK FALLBACK, BUT FILTERED ---
    for line in text_clean.split("\n"):
        line_strip = line.strip()
        if not line_strip:
            continue

        # Ignore address lines
        if not is_not_address(line_strip):
            continue

        # Only process lines that mention total/payable
        if any(k in line_strip.lower() for k in ["total", "due", "payable", "amount"]):
            nums = re.findall(r"[0-9]+\.[0-9]+|[0-9]+", line_strip)
            nums = [n for n in nums if float(n) > 50 and float(n) < 50000]
            if nums:
                return max(nums, key=lambda x: float(x))

    return "Total not found"


# -------------------------------------------------------------------------------------
# OCR + UNIVERSAL FILE TEXT EXTRACTOR  (same style as date code)
# -------------------------------------------------------------------------------------
def _ocr_best(img):
    best = ""
    for angle in (0, 90, 180, 270):
        text = pytesseract.image_to_string(img.rotate(angle, expand=True))
        if len(text) > len(best):
            best = text
    return best


def extract_text_full(path):

    if path.lower().endswith(".pdf"):
        text_out = ""

        try:
            pdf = pdfplumber.open(path)

            for pg in pdf.pages:
                txt = pg.extract_text()

                if txt and txt.strip():
                    text_out += "\n" + txt
                else:
                    # scanned PDF → convert that single page
                    imgs = convert_from_path(
                        path,
                        first_page=pg.page_number,
                        last_page=pg.page_number,
                        poppler_path=POPLER_PATH
                    )
                    for img in imgs:
                        text_out += "\n" + _ocr_best(img)

            pdf.close()
            return text_out

        except:
            # fallback OCR for full PDF
            imgs = convert_from_path(path, poppler_path=POPLER_PATH)
            text_all = ""
            for img in imgs:
                text_all += "\n" + _ocr_best(img)
            return text_all

    else:
        # image file
        img = Image.open(path)
        return _ocr_best(img)


# -------------------------------------------------------------------------------------
# UPDATED READER (same format as the date extractor update)
# -------------------------------------------------------------------------------------

files = [
        # "bills_folder/ketan-medicalbill1052024211446776.pdf",
        # "bills_folder/rupali-medicalbill105202421167943.pdf",
        # "bills_folder/uber-52542024183425202.pdf",
        # "bills_folder/Screenshot 2025-10-09 174619.png",
        # "bills_folder/ketan-medicalbill1052024211446776.pdf",
        # "bills_folder/rupali-medicalbill105202421167943.pdf"
]

for file in files:
    print("\n===== FILE:", file, "=====\n")

    text = extract_text_full(file)
    print(text)   # preview

    total = extract_total(text)
    print("\n>> Extracted Total:", total)

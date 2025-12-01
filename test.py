import re
from datetime import datetime
import easyocr
import warnings
import os
import logging
from typing import List, Dict, Any, Optional
from pdf2image import convert_from_path
from PIL import Image
import io

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s', force=True)
warnings.filterwarnings("ignore", category=UserWarning)

# ---------- Config ----------
VENDOR_KEYWORDS = [
    "pvt", "ltd", "private", "company", "co.", "shop", "store", "enterprises",
    "restaurant", "dhaba", "hotel", "foods", "cafe", "bakery", "mart", "super",
    "services", "agency", "clinic", "pharmacy", "electrical", "electronics",
    "bus", "cab", "ride", "uber", "rapido", "ola", "zomato", "swiggy", "blinkit",
    "groceries", "trading", "retail", "solutions", "corp", "family", "shree", "ventures",
    "dhaba", "llp", "ani technologies", "flipkart", "cloudstore", "eiht"
]

INVOICE_KEYWORDS = [
    "invoice", "bill", "receipt", "inv", "no", "number", "bill#", "invoice#", "inv#", "ref",
    "ride id", "order #", "txn id", "transaction", "folio", "voucher", "doc no"
]

MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

# ---------- Initialization ----------
try:
    # Set to run on CPU as per user's environment
    reader = easyocr.Reader(['en'], gpu=False) 
except Exception as e:
    logging.error(f"Error initializing EasyOCR: {e}. OCR functionality disabled.")
    reader = None

# ---------- PDF Conversion Function ----------
def pdf_to_image_data(pdf_path: str) -> Optional[bytes]:
    """Converts the first page of a PDF to an in-memory PNG image."""
    try:
        # NOTE: Poppler path is crucial here. Ensure it's correct for your environment.
        # Assuming the user's environment is Windows based on the path (C:\newproj>)
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=300, poppler_path=r"C:\poppler-25.07.0\Library\bin") 
        if not images:
            logging.error(f"Failed to convert PDF page: {pdf_path}")
            return None
            
        img = images[0]
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
        
    except Exception as e:
        logging.error(f"Error converting PDF {pdf_path} to image. Check Poppler installation: {e}")
        return None

# ---------- Helper Functions ----------

def clean_and_convert(s: str) -> float:
    # Remove currency symbols and non-numeric characters that are not a decimal point or negative sign
    s = str(s).strip().replace('₹', '').replace('$', '').replace('€', '').replace('£', '').replace('{', '').replace(')', '').replace('[', '')
    s = s.replace("o.o0", "0.00").replace("O.00", "0.00").replace("OO", "00").replace("O.", "0.").replace("o.", "0.")
    s = re.sub(r'(?:l|I)\.00$', '.00', s)

    # Clean up thousand separators and decimal points
    if re.match(r"^\d{1,3}(?:,\d{3})*\.\d{1,4}$", s): # e.g., 1,415.00
        s = s.replace(',', '')
    elif re.match(r"^\d{1,3}(?:\.\d{3})*,\d{1,4}$", s): # e.g., 1.415,00 (European format)
        s = s.replace('.', '').replace(',', '.')
    elif s.count(',') == 1 and s.count('.') == 0 and len(s.split(',')[-1]) <= 2: # e.g., 958,60
        s = s.replace(',', '.')
    
    s_cleaned = re.sub(r'[^0-9.-]', '', s)
    
    # Handle multiple decimal points (e.g., 1.23.45)
    if s_cleaned.count('.') > 1:
        parts = s_cleaned.split('.')
        s_cleaned = parts[0] + '.' + "".join(parts[1:])

    try:
        return float(s_cleaned)
    except ValueError:
        return 0.0

def find_plausible_amounts(text: str) -> List[float]:
    # Remove numbers that are part of time stamps, rates, or distances
    text = re.sub(r'\d{1,2}(?:\.|\:)\d{2}\s*(?:AM|PM)?', '', text, flags=re.IGNORECASE) 
    text = re.sub(r'[\d\.]+\s*(?:/km|/min)', '', text, flags=re.IGNORECASE) 
    text = re.sub(r'[\d\.]+\s*(?:km|min|kilometer)', '', text, flags=re.IGNORECASE) 
    
    # REVISED PATTERN: Capture any number string near a currency, or an opening brace.
    # Group 1 captures the number string, including commas and decimals.
    amount_pattern = r'(?:[RrSs$€£¥{]|Rs\.|Total\s*|Paid\s*)\s*([\d\.,]{1,15})(?:\s+only)?'
    matches = re.findall(amount_pattern, text, flags=re.IGNORECASE)
    
    # x[0] is the number part
    nums = [clean_and_convert(x[0]) for x in matches]
    
    # Filter for realistic amounts and not years
    return [n for n in nums if 1.0 <= n <= 500000.0 and not (1990 <= n <= 2050)] 

def is_noise(text: str) -> bool:
    low = text.lower()
    if len(text) < 3: return True
    if re.match(r"^\d{1,2}(:\d{2})?$", text): return True
    if re.match(r"^[0-9A-Z]{1,2}$", text): return True
    if re.match(r"^\d{1,3}(?:[.,]\d{1,2})?%?$", text): return True
    if any(k in low for k in ["chq", "help", "delivered", "items", "copy", "4dd", "logo", "time", "date", "gst", "cin", "pan", "reorder", "sr#", "qty"]): return True
    if text.strip().isupper() and len(text) < 5: return True
    return False

def extract_text(img_data: bytes, img_path_for_logging: str) -> List[Dict[str, Any]]:
    if reader is None: return []
    try:
        results = reader.readtext(img_data, detail=1, paragraph=False) 
        lines = [{'text': t.strip(), 'conf': conf, 'bbox': bbox} for bbox, t, conf in results if t.strip() and conf > 0.6]
        
        logging.info(f"\n--- OCR Raw Text for {img_path_for_logging} ({len(lines)} lines) ---")
        for line in lines:
            logging.info(f"'{line['text']}' (conf={line['conf']:.2f})")
        logging.info("-" * 50)
        
        return lines
    except Exception as e:
        logging.error(f"Error reading text from {img_path_for_logging}: {e}")
        return []

# -------------------------------------------------------------------
## 1. Extract Vendor 
# -------------------------------------------------------------------
def extract_vendor(lines: List[Dict[str, Any]], top_n: int = 15) -> str:
    """Prioritizes explicit brand names OLA/Uber at the top, then uses scoring."""
    
    # STRATEGY 1: Hard check for known brand names at the very top
    for line in lines[:3]:
        low = line['text'].lower()
        if "ola" == low or "ola" in low and len(low) < 5: return "OLA"
        if "uber" == low or "uber" in low and len(low) < 5: return "Uber"
        
    # STRATEGY 2: Scoring 
    vendor_lines = []
    for i, line in enumerate(lines[:top_n]):
        text = line['text']
        low = text.lower()
        conf = line['conf']
        if is_noise(text): continue
        
        score = conf * 10
        score += (top_n - i) * 5 # Positional boost
        
        # Penalty for high digit content
        if sum(c.isdigit() for c in text) / (len(text) or 1) > 0.5: score -= 40.0
        
        # Keyword Boosts
        if any(kw in low for kw in VENDOR_KEYWORDS): score += 50.0
        if "ani technologies" in low or "eiht" in low or "flipkart" in low or "cloudstore" in low: score += 100.0
        
        # Penalize non-vendor text
        if "thanks for travelling" in low or "ride details" in low or "trip details" in low: score -= 150.0

        # Penalize Invoice/Date lines
        if any(k in low for k in INVOICE_KEYWORDS) or re.search(r'\d{2,4}[-/.]\d{2,4}[-/.]\d{2,4}', low): score -= 60.0
        
        vendor_lines.append({'text': text, 'score': score, 'conf': conf})

    if not vendor_lines:
        for line in lines[:5]:
             if not is_noise(line['text']) and len(line['text']) > 5: return line['text'].strip()
        return ""
        
    best_vendor = max(vendor_lines, key=lambda x: x['score'])
    
    if best_vendor['score'] < 50:
        for line in lines[:5]:
             if not is_noise(line['text']) and len(line['text']) > 5: return line['text'].strip()

    return best_vendor['text'].strip()

# -------------------------------------------------------------------
## 2. Extract Date (REVISED for Ola fragmentation)
# -------------------------------------------------------------------
def extract_best_date(lines: List[Dict[str, Any]]) -> str:
    date_keywords = ["date", "dated", "bill date", "invoice date", "inv date", "dt", "delivered on", "shipped on"]
    
    date_formats = [
        "%d %B, %Y", "%d %b %Y", "%B %d, %Y", "%b %d %Y", # Day Month, Year (Uber format)
        "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y"
    ]

    def try_parse_date(s: str) -> Optional[str]:
        s = re.sub(r'[\s:;,]+', ' ', s).strip()
        # Remove time stamps before attempting to parse
        s_cleaned = re.sub(r'\d{1,2}:\d{2}\s*(?:AM|PM|a\.m\.|p\.m\.)?', '', s, flags=re.IGNORECASE).strip()
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(s_cleaned, fmt)
                current_year = datetime.now().year
                if dt.year < 100: dt = dt.replace(year=dt.year + 2000 if dt.year > 50 else dt.year + 1900)
                if current_year - 6 <= dt.year <= current_year + 1: return dt.strftime("%d-%m-%Y")
            except:
                try:
                    dt = datetime.strptime(s, fmt)
                    current_year = datetime.now().year
                    if dt.year < 100: dt = dt.replace(year=dt.year + 2000 if dt.year > 50 else dt.year + 1900)
                    if current_year - 6 <= dt.year <= current_year + 1: return dt.strftime("%d-%m-%Y")
                except: continue
        
        return None

    # STRATEGY 1 (REVISED): Specific fix for OLA's severely split date (Day and Year at top, Month at bottom)
    if lines and len(lines) > 1:
        # Check if the first line is just a day and the second line is just a year
        day_match = re.fullmatch(r'\d{1,2}', lines[0]['text']) 
        year_match = re.fullmatch(r'\d{4}', lines[1]['text']) 

        if day_match and year_match:
            # Search only the last 5 lines for a month name (Month is often near the bottom)
            last_lines_text = " ".join([l['text'] for l in lines[-5:]])
            month_match = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[,.\s]', last_lines_text, re.IGNORECASE)
            
            if month_match:
                day = day_match.group(0).zfill(2)
                year = year_match.group(0)
                # Extract the 3-letter month abbreviation
                month = month_match.group(1)[:3].lower() 
                
                month_val = MONTH_MAP.get(month)
                if month_val:
                    try:
                        dt = datetime(int(year), month_val, int(day))
                        return dt.strftime("%d-%m-%Y")
                    except ValueError: pass

    # STRATEGY 2: Check lines near date keywords or just the line itself
    for i, line in enumerate(lines):
        text = line['text'].strip()
        low = text.lower()
        
        # Check if the line contains a date keyword
        if any(k in low for k in date_keywords):
            combined = " ".join([lines[j]['text'].strip() for j in range(i, min(i + 3, len(lines)))])
            parsed = try_parse_date(combined)
            if parsed: return parsed

        # Check if the line is an independent date (e.g., Uber's 'April 8, 2024')
        parsed = try_parse_date(text)
        if parsed: return parsed

    # STRATEGY 3: General regex search across entire document (Final Fallback)
    text_joined = " ".join([l['text'] for l in lines])
    date_regex = r'(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})|([A-Za-z]{3,9}\s+\d{1,2}[,]*\s+\d{4})|(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})'
    
    for match in re.finditer(date_regex, text_joined):
        for group in match.groups():
            if group:
                parsed = try_parse_date(group)
                if parsed: return parsed
    
    return ""

# -------------------------------------------------------------------
## 3. Extract Invoice Number 
# -------------------------------------------------------------------
def extract_invoice_number(lines: List[Dict[str, Any]]) -> str:
    """Fixed invoice number extraction: targets the ID for blink.png, Media.jpg, and avoids noise."""
    
    # Pattern 1: Find ID immediately following a keyword
    invoice_pattern_specific = r"(?:invoice\s*number|inv\s*no|Inv\s*No|bill\s*no|order\s*#|order\s*id|txn\s*id|crn|ref)[\s\#\:\-/]*([A-Z0-9\-\s/]{5,40})"
    
    for i, line in enumerate(lines):
        text = line['text']
        low = text.lower()
        
        match = re.search(invoice_pattern_specific, text, flags=re.IGNORECASE)
        
        if match:
            result = match.group(1).strip()
            
            if result.lower().endswith("number"): result = result[:-6].strip()
            if result.lower().endswith("to"): result = result[:-2].strip()
            
            # For multi-token matches, assume the first token is the number
            result = result.split(' ')[0]

            is_long_digit = re.match(r'^\d{10,}$', result)

            if len(result) > 4 and result.lower() not in INVOICE_KEYWORDS and "details" not in result.lower() and (re.search(r'[A-Z/]', result, flags=re.IGNORECASE) or is_long_digit):
                return re.sub(r'[\s\.\,\;]+$', '', result)
    
    # Fallback 2: Check for Invoice Number C235... on the line *after* the keyword line (e.g., blinkit)
    for i, line in enumerate(lines):
        text = line['text']
        low = text.lower()
        if "invoice number" in low and i + 1 < len(lines):
             next_line_text = lines[i + 1]['text'].strip()
             if re.match(r'^[A-Z0-9]{10,}$', next_line_text, re.IGNORECASE):
                 return next_line_text

    # Fallback 3: Check for explicit 'Order No.' near the bottom
    for line in lines[-10:]:
        text = line['text']
        low = text.lower()
        order_match = re.search(r"(?:order\s*no|order\s*\#)[\s\.]*\s*(\d{1,4})$", low, flags=re.IGNORECASE)
        if order_match:
            return order_match.group(1).strip()
    
    return ""

# -------------------------------------------------------------------
## 4. Extract Total Amount (REVISED)
# -------------------------------------------------------------------
def extract_total_amount(lines: List[Dict[str, Any]]) -> str:
    """
    Prioritizes final total keywords like 'Total Payable' or 'Grand Total' near the bottom.
    """
    
    # 1. Define high-priority final total keywords (Ola, Uber, etc.)
    FINAL_KEYWORDS = ["total payable", "grand total", "net total", "total due", "total bill (rounded)", "total amount", "Paid by Cash"]
    
    # 2. Search from the bottom up (last 20 lines)
    reversed_lines = list(enumerate(reversed(lines)))
    
    # Phase 1: Look for explicit FINAL_KEYWORDS
    for i, (original_index, line) in enumerate(reversed_lines[:20]):
        low = line['text'].lower()
        # print (f"Checking line{low}")
        
        # Check if the line contains a definitive final total keyword
        # Added 'includes' to the exclusion list to avoid 'Total Bill (rounded) Includes 98.1 Taxes'
        if any(k in low for k in FINAL_KEYWORDS) and not any(k in low for k in ["sub", "tax", "discount", "fee", "includes", "received", "paid by"]):
            
            # Combine text of the current line and the next TWO lines to capture split amounts (Ola: 'Total Payable' then '{1415')
            # The range is [original_index, min(original_index + 3, len(lines)))
            combined_text = " ".join([lines[j]['text'] for j in range(original_index, min(original_index + 3, len(lines)))])
            amounts_in_vicinity = find_plausible_amounts(combined_text)

            if amounts_in_vicinity:
                # Return the largest amount found in the vicinity of the final keyword
                return f"{max(amounts_in_vicinity):.2f}"
                
    # Phase 2: Look for generic 'Total' or 'Amount' near the bottom
    for i, (original_index, line) in enumerate(reversed_lines[:10]):
        low = line['text'].lower()
        if "total" == low or "amount" == low:
            # Check the next line (which would be the previous line in the original list)
            if original_index + 1 < len(lines):
                 next_line_text = lines[original_index + 1]['text']
                 amounts = find_plausible_amounts(next_line_text)
                 if amounts:
                     return f"{max(amounts):.2f}"


    # Phase 3: Absolute largest plausible amount in the bottom half (Fallback)
    bottom_text = " ".join([l['text'] for l in lines[-25:]])
    all_plausible_amounts = find_plausible_amounts(bottom_text)
    
    if all_plausible_amounts:
        # Filter out very small amounts (e.g., Health Pack fee {8) and return the largest remaining one
        large_amounts = [a for a in all_plausible_amounts if a >= 50.0]
        if large_amounts:
            return f"{max(large_amounts):.2f}"
             
    return ""

# -------------------------------------------------------------------
## 5. Main Execution
# -------------------------------------------------------------------

def extract_invoice_details(file_path: str) -> Dict[str, str]:
    """Main function that orchestrates the entire extraction process, handling both images and PDFs."""
    if not os.path.exists(file_path):
        logging.error(f"File not found at path: {file_path}")
        return {"file": file_path, "vendor": "N/A", "date": "N/A", "invoice_no": "N/A", "total_amount": "N/A"}

    # Step 1: Handle PDF conversion or read image data
    if file_path.lower().endswith('.pdf'):
        img_data = pdf_to_image_data(file_path)
    else:
        try:
            with open(file_path, 'rb') as f:
                img_data = f.read()
        except Exception as e:
            logging.error(f"Error reading image file {file_path}: {e}")
            return {"file": file_path, "vendor": "N/A", "date": "N/A", "invoice_no": "N/A", "total_amount": "N/A"}
        
    if img_data is None:
        return {"file": file_path, "vendor": "N/A", "date": "N/A", "invoice_no": "N/A", "total_amount": "N/A"}

    # Step 2: Extract text using OCR on the image data
    lines = extract_text(img_data, file_path)
    if not lines:
        return {"file": file_path, "vendor": "N/A", "date": "N/A", "invoice_no": "N/A", "total_amount": "N/A"}

    # Step 3: Extract details
    vendor = extract_vendor(lines)
    date = extract_best_date(lines)
    invoice_no = extract_invoice_number(lines)
    total_amount = extract_total_amount(lines)

    print("\n================= 📄 Extracted Bill Details (FINAL SUCCESS) =================")
    print(f"File: {file_path}")
    print(f"Vendor: {vendor or 'N/A'}")
    print(f"Date: {date or 'N/A'}")
    print(f"Invoice No: {invoice_no or 'N/A'}")
    print(f"Total Amount: {total_amount or 'N/A'}")
    print("===========================================================================\n")

    return {
        "file": file_path,
        "vendor": vendor,
        "date": date,
        "invoice_no": invoice_no,
        "total_amount": total_amount
    }

if __name__ == "__main__":
    image_paths = [
        "bills_folder/1405_1175202410585790.pdf"
        # "bills_folder/1405_21752024105948482.pdf",
        # "bills_folder/1505_1175202411044555.pdf",
        # "bills_folder/13051752024105712915.pdf",
        # "bills_folder/invoice-4059842024232149839.pdf",
        # "bills_folder/ketan-medicalbill1052024211446776.pdf",
        # "bills_folder/march25to27742024233659598.pdf",
        # "bills_folder/mobileinvoice1842024104420407.pdf",
        # "bills_folder/receipt_01apr2024_81310420249204721.pdf",
        # "bills_folder/receipt_01apr2024_740104202492111850.pdf",
        # "bills_folder/rupali-medicalbill105202421167943.pdf",
        # "bills_folder/uber2542024182742481.pdf",
        # "bills_folder/uber-12542024182912518.pdf",
        # "bills_folder/uber-22542024183027431.pdf",
        # "bills_folder/uber-32542024183132308.pdf",
        # "bills_folder/uber-42542024183234139.pdf",
        # "bills_folder/uber-52542024183425202.pdf"
    ]
    
    for file_path in image_paths:
        if os.path.exists(file_path):
            extract_invoice_details(file_path)
        else:
            print(f"Skipping {file_path}: File not found. Please ensure test files are present in the 'bills_folder' directory and **Poppler is installed**.")
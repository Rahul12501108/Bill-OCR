import pandas as pd
import numpy as np
import os
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from tkinter import Tk, messagebox
from datetime import datetime
 
# ---------------- CONFIG ----------------
INPUT_FILE = r"C:\newproj\OPE_Samples.xlsx"          # uploaded Excel
DATABASE_FILE = r"C:\newproj\Book1.xlsx" # common database
DAILY_LIMIT = 10000                              # testing limit
UPLOADED_BY = "Taniya"                           # uploader name
 
# ---------------- READ EXCEL ----------------
df = pd.read_excel(INPUT_FILE)
 
# Strip column names (remove leading/trailing spaces)
df.columns = df.columns.str.strip()
 
# Identify key columns
amount_col = "Applied Amount/Units" if "Applied Amount/Units" in df.columns else "Amount"
date_col = "Applied Date" if "Applied Date" in df.columns else "Date"
 
# Ensure numeric amount
df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0)
 
# Ensure datetime
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
 
# ---------------- OPTIONAL: Only validate today's date ----------------
# Uncomment the following lines if you want to check only today's records
# today = pd.Timestamp(datetime.today().date())
# past_dates = df[df[date_col] != today]
# if not past_dates.empty:
#     root = Tk()
#     root.withdraw()
#     messagebox.showwarning(
#         "Invalid Date",
#         "Please enter the current date for all records."
#     )
# df = df[df[date_col] == today]
# ----------------------------------------------------------------------
 
# ---------------- DAILY TOTAL & VALIDATION ----------------
daily_total = df.groupby(["Employee Code", date_col])[amount_col].transform("sum")
 
df["Validation"] = np.where(
    (daily_total > DAILY_LIMIT) | (df[amount_col] > DAILY_LIMIT),
    "Exceeded daily limit",
    "Within limit"
)
 
df["UploadedBy"] = UPLOADED_BY
 
# ---------------- MERGE INTO DATABASE ----------------
if os.path.exists(DATABASE_FILE):
    old_df = pd.read_excel(DATABASE_FILE)
    final_df = pd.concat([old_df, df], ignore_index=True)
else:
    final_df = df
 
final_df.to_excel(DATABASE_FILE, index=False)
 
# ---------------- HIGHLIGHT ONLY EXCEEDED ----------------
wb = load_workbook(DATABASE_FILE)
ws = wb.active
 
red_fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
 
# Find Validation column index
validation_col = None
for idx, cell in enumerate(ws[1], start=1):
    if cell.value == "Validation":
        validation_col = idx
        break
 
# Apply red highlight only to exceeded rows
for row in range(2, ws.max_row + 1):
    if ws.cell(row=row, column=validation_col).value == "Exceeded daily limit":
        for col in range(1, ws.max_column + 1):
            ws.cell(row=row, column=col).fill = red_fill
 
wb.save(DATABASE_FILE)
 
# ---------------- POPUP WARNING ----------------
root = Tk()
root.withdraw()  # hide main window
 
# Daily limit exceeded warning
if (df["Validation"] == "Exceeded daily limit").any():
    messagebox.showwarning(
        "Daily Limit Exceeded",
        f"One or more employees have exceeded the ₹{DAILY_LIMIT} daily limit."
    )
 
print("✔ Data saved successfully:", DATABASE_FILE)
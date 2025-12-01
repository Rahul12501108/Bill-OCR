import pdfplumber

pdf = pdfplumber.open("bills_folder/ketan-medicalbill1052024211446776.pdf")
for i, page in enumerate(pdf.pages):
    print("\n===== PAGE", i+1, "=====\n")
    print(page.extract_text())
    # for dta in page:
    #     print(dta) 


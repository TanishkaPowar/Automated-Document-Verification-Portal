import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
from engine import extract_text, detect_document_type, process_document

pdf = r"dataset\PDF_Documents\PDF_Documents\APP0001_Application_Form.pdf"

print("=== RAW OCR LINES ===")
lines = extract_text(pdf)
for i, line in enumerate(lines):
    print(f"{i:02d}: {repr(line)}")

print("\n=== DETECTED TYPE ===")
print(detect_document_type(lines))

print("\n=== EXTRACTED FIELDS ===")
result = process_document(pdf)
for k, v in result['extracted_data'].items():
    print(f"  {k:20s} = {repr(v)}")

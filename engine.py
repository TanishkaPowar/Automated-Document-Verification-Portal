import os
import re
import cv2
import numpy as np
from pdf2image import convert_from_path
from paddleocr import PaddleOCR
from datetime import datetime

# ================= CONFIG =================

DEFAULT_POPPLER_PATH = r"D:\Projects\python\poppler-25.12.0\Library\bin"
POPPLER_PATH = os.environ.get("POPPLER_PATH", DEFAULT_POPPLER_PATH)
if not os.path.exists(POPPLER_PATH):
    POPPLER_PATH = None
DPI = 120

ocr = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=False)

# ================= PDF TO IMAGE =================

def pdf_to_images(pdf_path):
    return convert_from_path(
        pdf_path,
        dpi=DPI,
        poppler_path=POPPLER_PATH,
        first_page=1,
        last_page=1
    )

# ================= PREPROCESS =================

def preprocess(pil_image):
    img = np.array(pil_image)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray)
    clahe = cv2.createCLAHE(clipLimit=3.0)
    gray = clahe.apply(gray)
    return gray

# ================= OCR =================

def is_label(text):
    known_labels = [
        "student name", "father's name", "mother's name", "date of birth",
        "school", "board", "year of passing", "overall percentage",
        "education type", "institution", "rank", "category", "gender",
        "reason for leaving", "character", "date of issue",
        "certificate number", "issuing authority"
    ]
    return text.lower() in known_labels


def extract_text(pdf_path):
    pages = pdf_to_images(pdf_path)
    lines = []

    for page in pages:
        processed = preprocess(page)
        result = ocr.ocr(processed)

        if result is None:
            continue

        for res in result:
            if res is None:
                continue
            for line in res:
                try:
                    text = line[1][0].strip()
                    if text:
                        lines.append(text)
                except Exception:
                    continue

    return lines

# ================= FIELD EXTRACTION =================

def normalize_to_ddmmyyyy(date_str):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d/%m/%Y")
        except:
            continue
    return date_str


def extract_dob(text_lines):
    text = " ".join(text_lines)
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if match:
        return match.group()
    match = re.search(r"\b\d{2}-\d{2}-\d{4}\b", text)
    if match:
        return match.group()
    return None


def extract_field(label, text_lines):
    for i, line in enumerate(text_lines):
        clean_line = line.strip()
        if clean_line.lower().startswith(label.lower()):
            value = clean_line[len(label):].strip(" :.-")
            if value:
                return value
            for j in range(i + 1, min(i + 3, len(text_lines))):
                next_line = text_lines[j].strip()
                if is_label(next_line):
                    continue
                return next_line
    return None


def extract_value(label, text_lines, max_lines_ahead=3):
    label_lower = label.lower()
    for i, line in enumerate(text_lines):
        clean_line = line.strip()
        clean_line_norm = re.sub(r'[:\-]', '', clean_line)
        if label_lower in clean_line_norm.lower():
            parts = re.split(r'[:\-]', clean_line, maxsplit=1)
            if len(parts) > 1:
                return parts[1].strip()
            for j in range(1, max_lines_ahead + 1):
                if i + j < len(text_lines):
                    next_line = text_lines[i + j].strip()
                    if re.search(r"(Name|Father|Date|Institution|Year|Reason|Character|Issue)", next_line, re.IGNORECASE):
                        continue
                    if next_line:
                        return next_line
    return None


def extract_date(label, text_lines):
    value = extract_value(label, text_lines)
    if value:
        match = re.search(r"\d{2}[-/]\d{2}[-/]\d{4}|\d{4}[-/]\d{2}[-/]\d{2}", value)
        if match:
            return normalize_to_ddmmyyyy(match.group())
    return None


def extract_date_inline(label, text_lines):
    full_text = " ".join(text_lines)
    pattern = rf"{label}\s+(\d{{4}}-\d{{2}}-\d{{2}}|\d{{2}}-\d{{2}}-\d{{4}})"
    match = re.search(pattern, full_text, re.IGNORECASE)
    if match:
        return normalize_to_ddmmyyyy(match.group(1))
    return None


def extract_date_after_label(label, text_lines):
    date_pattern = r"\d{2}[-/]\d{2}[-/]\d{4}|\d{4}[-/]\d{2}[-/]\d{2}"
    for i, line in enumerate(text_lines):
        if label.lower() in line.lower():
            match = re.search(date_pattern, line)
            if match:
                return normalize_to_ddmmyyyy(match.group())
            for j in range(i + 1, min(i + 3, len(text_lines))):
                match = re.search(date_pattern, text_lines[j])
                if match:
                    return normalize_to_ddmmyyyy(match.group())
    return None


def extract_address_block(text_lines):
    address_lines = []
    capture = False
    date_pattern = r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}"
    for line in text_lines:
        clean = line.strip()
        lower = clean.lower()
        if lower.startswith("address"):
            capture = True
            continue
        if capture:
            if "date of issue" in lower or "issuing authority" in lower or "certificate number" in lower:
                break
            clean = re.sub(date_pattern, "", clean)
            address_lines.append(clean.strip())
    return " ".join(address_lines).strip() if address_lines else None

# ================= DOCUMENT TYPE DETECTION =================
# (detect_document_type is defined below near process_document)

# ================= PARSERS =================

def parse_10th(text_lines):
    return {
        "name": extract_field("Student Name", text_lines),
        "father_name": extract_field("Father's Name", text_lines),
        "mother_name": extract_field("Mother's Name", text_lines),
        "dob": extract_dob(text_lines),
        "school": extract_field("School", text_lines),
        "board": extract_field("Board", text_lines),
        "year": extract_field("Year of Passing", text_lines),
        "percentage": extract_field("Overall Percentage", text_lines)
    }


def parse_diploma(text_lines):
    return {
        "name": extract_field("Student Name", text_lines),
        "father_name": extract_field("Father's Name", text_lines),
        "education_type": extract_field("Education Type", text_lines),
        "institution": extract_field("Institution", text_lines),
        "board": extract_field("Board", text_lines),
        "year": extract_field("Year of Passing", text_lines),
        "percentage": extract_field("Overall Percentage", text_lines)
    }


def parse_leaving(text_lines):
    return {
        "name": extract_value("Student Name", text_lines),
        "father_name": extract_value("Father's Name", text_lines),
        "dob": extract_dob(text_lines) or extract_date("Date of Birth", text_lines),
        "last_institution": extract_value("Last Institution Attended", text_lines),
        "year_of_leaving": extract_value("Year of Leaving", text_lines),
        "reason": extract_value("Reason for Leaving", text_lines),
        "character": extract_value("Character", text_lines),
        "issue_date": extract_date("Date of Issue", text_lines)
    }


def parse_cet(text_lines):
    return {
        "name": extract_field("Candidate Name", text_lines),
        "father_name": extract_field("Father's Name", text_lines),
        "mother_name": extract_field("Mother's Name", text_lines),
        "dob": extract_dob(text_lines),
        "gender": extract_field("Gender", text_lines),
        "category": extract_field("Category", text_lines),
        "percentile": extract_field("CET Percentile", text_lines),
        "rank": extract_field("Rank", text_lines),
        "test_date": extract_dob(text_lines),
        "test_center": extract_field("Test Center", text_lines)
    }


def parse_caste(text_lines):
    full_text = " ".join(text_lines)
    full_text = re.sub(r"\s+", " ", full_text)

    def extract(pattern):
        match = re.search(pattern, full_text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    name = extract(r"Applicant Name\s*[:\-]?\s*(.*?)\s*Father's Name")
    father_name = extract(r"Father's Name\s*[:\-]?\s*(.*?)\s*Date of Birth")
    category = extract(r"Category\s*[:\-]?\s*([A-Za-z]+)")
    certificate_number = extract(r"Certificate Number\s*[:\-]?\s*([A-Z0-9\/]+)")

    date_pattern = r"\b\d{4}[-/.\s]\d{2}[-/.\s]\d{2}\b|\b\d{2}[-/.\s]\d{2}[-/.\s]\d{4}\b"
    all_dates = re.findall(date_pattern, full_text)

    dob = None
    issue_date = None
    for date in all_dates:
        if re.match(r"\d{4}", date):
            dob = date
        else:
            issue_date = date

    address = None
    for i, line in enumerate(text_lines):
        if "address" in line.lower():
            clean_line = re.sub(r"Address", "", line, flags=re.IGNORECASE).strip()
            clean_line = re.sub(date_pattern, "", clean_line).strip()
            address_parts = []
            if clean_line:
                address_parts.append(clean_line)
            if i >= 1:
                prev1 = text_lines[i - 1].strip()
                if not any(x in prev1.lower() for x in ["category", "birth", "father", "name"]):
                    address_parts.insert(0, prev1)
            if i >= 2:
                prev2 = text_lines[i - 2].strip()
                if not any(x in prev2.lower() for x in ["category", "birth", "father", "name"]):
                    address_parts.insert(0, prev2)
            address = " ".join(address_parts).strip()
            break

    issuing_authority = None
    certificate_pattern = r"[A-Z]{2,}\/\d+\/\d+"
    for i, line in enumerate(text_lines):
        if "issuing authority" in line.lower():
            for j in range(i + 1, min(i + 6, len(text_lines))):
                candidate = text_lines[j].strip()
                if not candidate:
                    continue
                if "certificate" in candidate.lower():
                    continue
                if re.search(certificate_pattern, candidate):
                    continue
                if re.fullmatch(r"[A-Z0-9\/\-]+", candidate):
                    continue
                if any(word in candidate.lower() for word in ["office", "magistrate", "collector", "government", "district"]):
                    issuing_authority = candidate
                    break
            break

    return {
        "name": name,
        "father_name": father_name,
        "dob": dob,
        "category": category,
        "address": address,
        "issue_date": issue_date,
        "issuing_authority": issuing_authority,
        "certificate_number": certificate_number
    }

def parse_application(text_lines):
    return {
        "name": (extract_field("Full Name", text_lines)
                 or extract_field("Student Name", text_lines)
                 or extract_field("Applicant Name", text_lines)
                 or extract_field("Name", text_lines)),
        "father_name": extract_field("Father's Name", text_lines),
        "mother_name": extract_field("Mother's Name", text_lines),
        "dob": extract_dob(text_lines),
        "category": extract_field("Category", text_lines),
        "gender": extract_field("Gender", text_lines),
    }

# ================= MAIN =================

def detect_document_type(text_lines):
    text = " ".join(text_lines).lower()
    if "secondary school certificate" in text:
        return "10th_marksheet"
    elif "diploma marksheet" in text:
        return "diploma_marksheet"
    elif "leaving certificate" in text:
        return "leaving_certificate"
    elif "cet scorecard" in text:
        return "cet_scorecard"
    elif "caste certificate" in text:
        return "caste_certificate"
    elif "application" in text and ("full name" in text or "admission" in text):
        return "application_form"
    return "unknown"

def process_document(pdf_path):
    text_lines = extract_text(pdf_path)
    doc_type = detect_document_type(text_lines)

    if doc_type == "10th_marksheet":
        data = parse_10th(text_lines)
    elif doc_type == "diploma_marksheet":
        data = parse_diploma(text_lines)
    elif doc_type == "leaving_certificate":
        data = parse_leaving(text_lines)
    elif doc_type == "cet_scorecard":
        data = parse_cet(text_lines)
    elif doc_type == "caste_certificate":
        data = parse_caste(text_lines)
    elif doc_type == "application_form":
        data = parse_application(text_lines)
    else:
        data = {"raw_text": text_lines}

    return {
        "document_type": doc_type,
        "extracted_data": data
    }

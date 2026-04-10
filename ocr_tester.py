"""
OCR Accuracy Testing Framework
================================
Tests the OCR engine (engine.py) against a ground truth CSV.
Calculates field-level, document-level, and student-level accuracy.
Generates a detailed Excel report.

Usage:
    python ocr_tester.py \
        --pdf_dir ./documents \
        --ground_truth ./ground_truth.csv \
        --output ./ocr_report.xlsx \
        --threshold 80

Ground Truth CSV columns:
    app_id, doc_type, name, father_name, mother_name, dob, school, board,
    year, percentage, education_type, institution, category, gender, rank,
    percentile, reason, character, issue_date, certificate_number,
    issuing_authority, last_institution, year_of_leaving
"""

import os
import re
import glob
import argparse
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
from difflib import SequenceMatcher
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Import your OCR engine ──────────────────────────────────────────────────
from engine import process_document

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
DOC_TYPE_MAP = {
    "10th_marksheet":      "10th_Marksheet",
    "diploma_marksheet":   "12th_Diploma_Marksheet",
    "leaving_certificate": "Leaving_Certificate",
    "cet_scorecard":       "CET_Scorecard",
    "caste_certificate":   "Caste_Certificate",
    "application_form":    "Application_Form",
}

# Fields expected per document type
DOC_FIELDS = {
    "10th_marksheet":      ["name", "father_name", "mother_name", "dob", "school", "board", "year", "percentage"],
    "diploma_marksheet":   ["name", "father_name", "education_type", "institution", "board", "year", "percentage"],
    "leaving_certificate": ["name", "father_name", "dob", "last_institution", "year_of_leaving", "reason", "character", "issue_date"],
    "cet_scorecard":       ["name", "father_name", "mother_name", "dob", "gender", "category", "percentile", "rank"],
    "caste_certificate":   ["name", "father_name", "dob", "category", "issue_date", "certificate_number", "issuing_authority"],
    "application_form":    ["name", "father_name", "mother_name", "dob", "category", "gender"],
}

# ── Similarity helpers ───────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def similarity(a: str, b: str) -> float:
    """Return 0-100 similarity score between two strings."""
    a, b = normalize(a), normalize(b)
    if not a and not b:
        return 100.0
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio() * 100, 2)


def field_match(extracted, expected, threshold: float = 80.0):
    """
    Returns (score, status) where status is 'PASS' / 'FAIL' / 'MISSING' / 'N/A'.
    If expected is empty, return N/A (not testable - no ground truth provided).
    """
    expected_empty  = (expected  is None or str(expected ).strip() == "")
    extracted_empty = (extracted is None or str(extracted).strip() == "")

    if expected_empty:
        return 100.0, "N/A"   # no ground truth = not testable, skip from scoring

    if extracted_empty:
        return 0.0, "MISSING"

    score = similarity(str(extracted), str(expected))
    status = "PASS" if score >= threshold else "FAIL"
    return score, status


# ── PDF path resolver ────────────────────────────────────────────────────────

def find_pdf(pdf_dir: str, app_id: str, doc_type: str) -> str | None:
    """
    Looks for files like APP0001_10th_Marksheet.pdf (case-insensitive glob).
    """
    suffix = DOC_TYPE_MAP.get(doc_type, "")
    pattern = os.path.join(pdf_dir, f"{app_id}_{suffix}.pdf")
    matches = glob.glob(pattern, recursive=False)
    if matches:
        return matches[0]

    # Fallback: case-insensitive search
    for f in Path(pdf_dir).glob(f"{app_id}_*.pdf"):
        if doc_type.replace("_", "").lower() in f.stem.replace("_", "").lower():
            return str(f)

    return None


# ── Core testing logic ───────────────────────────────────────────────────────

def test_document(pdf_path: str, gt_row: pd.Series, threshold: float, doc_type: str) -> dict:
    """
    Run OCR on one PDF and compare against ground truth.
    Returns a result dict with per-field scores.
    """
    result = {
        "app_id":       gt_row.get("app_id", ""),
        "doc_type":     doc_type,
        "pdf_path":     pdf_path,
        "ocr_success":  False,
        "fields":       {},
        "doc_accuracy": 0.0,
        "doc_status":   "FAIL",
        "error":        "",
    }

    try:
        ocr_output = process_document(pdf_path)
        extracted  = ocr_output.get("extracted_data", {})
        result["ocr_success"] = True
    except Exception as e:
        result["error"] = str(e)
        log.error("OCR failed for %s: %s", pdf_path, e)
        return result

    fields = DOC_FIELDS.get(doc_type, [])
    scores = []

    for field in fields:
        ext_val = extracted.get(field)
        gt_val  = gt_row.get(field)

        score, status = field_match(ext_val, gt_val, threshold)

        result["fields"][field] = {
            "extracted": ext_val,
            "expected":  gt_val,
            "score":     score,
            "status":    status,
        }

        if status != "N/A":
            scores.append(score)

    result["doc_accuracy"] = round(sum(scores) / len(scores), 2) if scores else 0.0
    result["doc_status"]   = "PASS" if result["doc_accuracy"] >= threshold else "FAIL"
    return result


# ── Report generator ─────────────────────────────────────────────────────────

FILL_GREEN  = PatternFill("solid", fgColor="C6EFCE")
FILL_RED    = PatternFill("solid", fgColor="FFC7CE")
FILL_ORANGE = PatternFill("solid", fgColor="FFEB9C")
FILL_BLUE   = PatternFill("solid", fgColor="BDD7EE")
FILL_HEADER = PatternFill("solid", fgColor="2F5496")
FILL_GREY   = PatternFill("solid", fgColor="D9D9D9")

FONT_WHITE  = Font(color="FFFFFF", bold=True)
FONT_BOLD   = Font(bold=True)

THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"),  bottom=Side(style="thin"),
)


def _header(ws, row, col, value, fill=FILL_HEADER, font=FONT_WHITE):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill   = fill
    cell.font   = font
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = THIN_BORDER
    return cell


def _cell(ws, row, col, value, fill=None, bold=False, wrap=False):
    cell = ws.cell(row=row, column=col, value=value)
    if fill:
        cell.fill = fill
    if bold:
        cell.font = FONT_BOLD
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=wrap)
    cell.border = THIN_BORDER
    return cell


def build_report(results: list[dict], output_path: str, threshold: float):
    wb = Workbook()

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    ws_sum = wb.active
    ws_sum.title = "Summary"

    headers_sum = [
        "App ID", "Doc Type", "PDF Found", "OCR Success",
        "Doc Accuracy (%)", "Status", "Error"
    ]
    for col, h in enumerate(headers_sum, 1):
        _header(ws_sum, 1, col, h)

    for r, res in enumerate(results, 2):
        pdf_found = "YES" if res["pdf_path"] else "NO"
        fill_status = FILL_GREEN if res["doc_status"] == "PASS" else FILL_RED
        fill_pdf    = FILL_GREEN if pdf_found == "YES" else FILL_RED
        fill_ocr    = FILL_GREEN if res["ocr_success"] else FILL_RED

        _cell(ws_sum, r, 1, res["app_id"], bold=True)
        _cell(ws_sum, r, 2, res["doc_type"])
        _cell(ws_sum, r, 3, pdf_found, fill=fill_pdf)
        _cell(ws_sum, r, 4, "YES" if res["ocr_success"] else "NO", fill=fill_ocr)
        _cell(ws_sum, r, 5, res["doc_accuracy"])
        _cell(ws_sum, r, 6, res["doc_status"], fill=fill_status)
        _cell(ws_sum, r, 7, res["error"] or "", wrap=True)

    ws_sum.column_dimensions["A"].width = 12
    ws_sum.column_dimensions["B"].width = 22
    ws_sum.column_dimensions["C"].width = 12
    ws_sum.column_dimensions["D"].width = 14
    ws_sum.column_dimensions["E"].width = 18
    ws_sum.column_dimensions["F"].width = 10
    ws_sum.column_dimensions["G"].width = 40

    # ── Sheet 2: Field Details ────────────────────────────────────────────────
    ws_fd = wb.create_sheet("Field Details")

    headers_fd = ["App ID", "Doc Type", "Field", "Expected", "Extracted", "Score (%)", "Status"]
    for col, h in enumerate(headers_fd, 1):
        _header(ws_fd, 1, col, h)

    r = 2
    for res in results:
        for field, info in res.get("fields", {}).items():
            status = info["status"]
            if status == "PASS":
                fill = FILL_GREEN
            elif status == "FAIL":
                fill = FILL_RED
            elif status == "MISSING":
                fill = FILL_ORANGE
            else:
                fill = None

            _cell(ws_fd, r, 1, res["app_id"], bold=True)
            _cell(ws_fd, r, 2, res["doc_type"])
            _cell(ws_fd, r, 3, field)
            _cell(ws_fd, r, 4, str(info["expected"] or ""), wrap=True)
            _cell(ws_fd, r, 5, str(info["extracted"] or ""), wrap=True)
            _cell(ws_fd, r, 6, info["score"])
            _cell(ws_fd, r, 7, status, fill=fill)
            r += 1

    for col, width in zip(range(1, 8), [12, 22, 22, 30, 30, 12, 12]):
        ws_fd.column_dimensions[get_column_letter(col)].width = width

    # ── Sheet 3: Student Pivot ────────────────────────────────────────────────
    ws_pv = wb.create_sheet("Student Pivot")

    doc_types = list(DOC_TYPE_MAP.keys())
    pivot_headers = ["App ID"] + [DOC_TYPE_MAP[d] for d in doc_types] + ["Overall %", "Overall Status"]
    for col, h in enumerate(pivot_headers, 1):
        _header(ws_pv, 1, col, h)

    # Group by app_id
    by_student: dict[str, dict] = {}
    for res in results:
        aid = res["app_id"]
        if aid not in by_student:
            by_student[aid] = {}
        by_student[aid][res["doc_type"]] = res

    r = 2
    for aid, docs in sorted(by_student.items()):
        _cell(ws_pv, r, 1, aid, bold=True)
        accs = []
        for col, dt in enumerate(doc_types, 2):
            doc = docs.get(dt)
            if doc:
                acc = doc["doc_accuracy"]
                accs.append(acc)
                fill = FILL_GREEN if doc["doc_status"] == "PASS" else FILL_RED
                if not doc["ocr_success"]:
                    fill = FILL_ORANGE
                _cell(ws_pv, r, col, f"{acc}%", fill=fill)
            else:
                _cell(ws_pv, r, col, "N/A", fill=FILL_GREY)

        overall = round(sum(accs) / len(accs), 2) if accs else 0.0
        overall_status = "PASS" if overall >= threshold else "FAIL"
        _cell(ws_pv, r, len(doc_types) + 2, f"{overall}%",
              fill=FILL_GREEN if overall_status == "PASS" else FILL_RED)
        _cell(ws_pv, r, len(doc_types) + 3, overall_status,
              fill=FILL_GREEN if overall_status == "PASS" else FILL_RED, bold=True)
        r += 1

    for col in range(1, len(pivot_headers) + 1):
        ws_pv.column_dimensions[get_column_letter(col)].width = 20

    # ── Sheet 4: Stats ────────────────────────────────────────────────────────
    ws_st = wb.create_sheet("Stats")

    total = len(results)
    passed = sum(1 for r in results if r["doc_status"] == "PASS")
    failed = total - passed
    missing_pdf = sum(1 for r in results if not r["pdf_path"])
    ocr_errors  = sum(1 for r in results if not r["ocr_success"])
    avg_acc = round(sum(r["doc_accuracy"] for r in results) / total, 2) if total else 0

    stats = [
        ("Total Documents Tested",   total),
        ("Documents Passed",         passed),
        ("Documents Failed",         failed),
        ("Missing PDFs",             missing_pdf),
        ("OCR Errors",               ocr_errors),
        ("Average Accuracy (%)",     avg_acc),
        ("Pass Threshold (%)",       threshold),
        ("Report Generated",         datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
    ]

    _header(ws_st, 1, 1, "Metric", fill=FILL_HEADER)
    _header(ws_st, 1, 2, "Value",  fill=FILL_HEADER)
    for i, (k, v) in enumerate(stats, 2):
        _cell(ws_st, i, 1, k, bold=True)
        _cell(ws_st, i, 2, v)

    ws_st.column_dimensions["A"].width = 30
    ws_st.column_dimensions["B"].width = 25

    wb.save(output_path)
    log.info("Report saved → %s", output_path)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OCR Accuracy Tester")
    parser.add_argument("--pdf_dir",      required=True, help="Directory containing PDFs")
    parser.add_argument("--ground_truth", required=True, help="CSV/Excel with expected values")
    parser.add_argument("--output",       default="ocr_report.xlsx", help="Output Excel report path")
    parser.add_argument("--threshold",    type=float, default=80.0,  help="Accuracy threshold %% (default 80)")
    parser.add_argument("--limit",        type=int,   default=None,  help="Test only first N rows (for quick smoke tests)")
    args = parser.parse_args()

    # Load ground truth
    gt_path = args.ground_truth
    if gt_path.endswith(".xlsx") or gt_path.endswith(".xls"):
        gt_df = pd.read_excel(gt_path, dtype=str)
    else:
        gt_df = pd.read_csv(gt_path, dtype=str)

    gt_df = gt_df.fillna("")

    if args.limit:
        gt_df = gt_df.head(args.limit)

    log.info("Loaded %d rows from ground truth.", len(gt_df))

    results = []

    for idx, row in gt_df.iterrows():
        app_id   = row.get("app_id", "").strip()
        doc_type = row.get("doc_type", "").strip().lower()

        if not app_id or not doc_type:
            log.warning("Row %d: missing app_id or doc_type — skipped.", idx)
            continue

        pdf_path = find_pdf(args.pdf_dir, app_id, doc_type)

        if not pdf_path:
            log.warning("PDF not found: %s / %s", app_id, doc_type)
            results.append({
                "app_id":       app_id,
                "doc_type":     doc_type,
                "pdf_path":     None,
                "ocr_success":  False,
                "fields":       {},
                "doc_accuracy": 0.0,
                "doc_status":   "FAIL",
                "error":        "PDF not found",
            })
            continue

        log.info("Testing %-12s  %-25s", app_id, doc_type)
        res = test_document(pdf_path, row, args.threshold, doc_type)
        results.append(res)

    build_report(results, args.output, args.threshold)

    # Print quick summary
    total  = len(results)
    passed = sum(1 for r in results if r["doc_status"] == "PASS")
    print(f"\n{'='*50}")
    print(f"  Total tested : {total}")
    print(f"  Passed       : {passed}  ({100*passed//total if total else 0}%)")
    print(f"  Failed       : {total - passed}")
    print(f"  Report       : {args.output}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()

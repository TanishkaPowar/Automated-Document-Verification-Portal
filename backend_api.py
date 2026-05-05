import csv
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Flask, jsonify, request, send_file

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATE_FILE = BASE_DIR / "verification_state.json"
FRONTEND_FILE = BASE_DIR / "frontend.html"
APPLICANTS_CSV = BASE_DIR / "whole dataset" / "Applicants_Complete_Dataset.csv"

DOCUMENTS = {
    "cetScorecard": "CET Scorecard",
    "tenthMarksheet": "10th Marksheet",
    "twelfthMarksheet": "12th/Diploma Marksheet",
    "leavingCertificate": "Leaving Certificate",
    "casteCertificate": "Caste Certificate",
}

EXPECTED_DOCUMENT_TYPES = {
    "cetScorecard": "cet_scorecard",
    "tenthMarksheet": "10th_marksheet",
    "twelfthMarksheet": "diploma_marksheet",
    "leavingCertificate": "leaving_certificate",
    "casteCertificate": "caste_certificate",
}

ALLOWED_EXTENSIONS = {".pdf"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024


def default_state():
    applicants = {}

    if APPLICANTS_CSV.exists():
        with APPLICANTS_CSV.open("r", encoding="utf-8-sig", newline="") as file:
            for index, row in enumerate(csv.DictReader(file), start=1):
                applicant_id = row["Application_ID"].strip().upper()
                applicants[applicant_id.lower()] = {
                    "id": applicant_id,
                    "password": f"pass{index}",
                    "name": row.get("Applicant_name", "").strip(),
                    "fatherName": row.get("Father_name", "").strip(),
                    "motherName": row.get("Mother_name", "").strip(),
                    "dob": row.get("DOB", "").strip(),
                    "category": row.get("Category_Caste", "").strip(),
                    "documents": {key: None for key in DOCUMENTS},
                    "status": "Not Submitted",
                    "submitted": False,
                    "submissionDate": None,
                    "remarks": "",
                    "verificationPercentage": 0,
                }

    return {"applicants": applicants}


def load_state():
    default = default_state()

    if not STATE_FILE.exists():
        save_state(default)
        return default

    with STATE_FILE.open("r", encoding="utf-8") as file:
        state = json.load(file)

    saved_ids = set((state.get("applicants") or {}).keys())
    dataset_ids = set(default["applicants"].keys())
    if dataset_ids and (not saved_ids or saved_ids != dataset_ids):
        save_state(default)
        return default

    for applicant_id, applicant in state.get("applicants", {}).items():
        source = default["applicants"].get(applicant_id)
        if source:
            for key in ("name", "fatherName", "motherName", "dob", "category"):
                applicant[key] = source[key]
            applicant.setdefault("verificationPercentage", calculate_verification_percentage(applicant))

    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def public_applicant(applicant):
    data = dict(applicant)
    data.pop("password", None)
    return data


def normalize(value):
    if not value:
        return None
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9/ -]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value or None


def normalize_date(value):
    cleaned = normalize(value)
    if not cleaned:
        return None

    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value).strip(), pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def values_match(actual, expected, is_date=False):
    if is_date:
        return normalize_date(actual) == normalize_date(expected)
    return normalize(actual) == normalize(expected)


def most_common(values):
    cleaned = [normalize(value) for value in values if normalize(value)]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def extract_value(extracted_data, keys):
    if not isinstance(extracted_data, dict):
        return None
    for key in keys:
        value = extracted_data.get(key)
        if value:
            return value
    return None


def calculate_verification_percentage(applicant):
    total_score = 0

    for doc_key, document in applicant.get("documents", {}).items():
        if not document:
            continue

        doc_score = 0
        if document.get("document_type") == EXPECTED_DOCUMENT_TYPES[doc_key]:
            doc_score += 5

        extracted = document.get("extracted_data") or {}
        if values_match(
            extract_value(extracted, ["name", "student_name", "candidate_name", "applicant_name"]),
            applicant.get("name"),
        ):
            doc_score += 5
        if values_match(
            extract_value(extracted, ["father_name", "father", "father's_name"]),
            applicant.get("fatherName"),
        ):
            doc_score += 5
        if values_match(extract_value(extracted, ["dob", "date_of_birth"]), applicant.get("dob"), is_date=True):
            doc_score += 5

        total_score += doc_score

    return total_score


def verification_result(applicant):
    missing_docs = [DOCUMENTS[key] for key, document in applicant["documents"].items() if not document]
    if missing_docs:
        applicant["verificationPercentage"] = calculate_verification_percentage(applicant)
        return "Not Submitted", f"Missing documents: {', '.join(missing_docs)}"

    percentage = calculate_verification_percentage(applicant)
    applicant["verificationPercentage"] = percentage

    wrong_slots = []
    for doc_key, document in applicant["documents"].items():
        if document and document.get("document_type") != EXPECTED_DOCUMENT_TYPES[doc_key]:
            wrong_slots.append(f"{DOCUMENTS[doc_key]} uploaded as {document.get('document_type', 'unknown')}")

    if percentage == 100:
        return "Approved", "All uploaded documents match the applicant dataset and expected document types."

    if percentage >= 70:
        detail = f"Verification score is {percentage}%."
        if wrong_slots:
            detail += f" Document type issue: {', '.join(wrong_slots)}."
        return "Under Scrutiny", detail

    detail = f"Verification score is {percentage}% against Applicants_Complete_Dataset.csv."
    if wrong_slots:
        detail += f" Document type issue: {', '.join(wrong_slots)}."
    return "Rejected", detail


@app.get("/")
def index():
    return send_file(FRONTEND_FILE)


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    role = payload.get("role")
    user_id = str(payload.get("userId", "")).lower().strip()
    password = str(payload.get("password", ""))

    if role == "admin":
        if user_id == "admin" and password == "admin123":
            return jsonify({"role": "admin"})
        return jsonify({"error": "Invalid Admin ID or password"}), 401

    state = load_state()
    applicant = state["applicants"].get(user_id)
    if not applicant or applicant.get("password") != password:
        return jsonify({"error": "Invalid Applicant ID or password"}), 401

    return jsonify({"role": "applicant", "applicant": public_applicant(applicant)})


@app.get("/api/applicants/<applicant_id>")
def get_applicant(applicant_id):
    state = load_state()
    applicant = state["applicants"].get(applicant_id.lower())
    if not applicant:
        return jsonify({"error": "Applicant not found"}), 404
    return jsonify(public_applicant(applicant))


@app.post("/api/applicants/<applicant_id>/documents/<document_key>")
def upload_document(applicant_id, document_key):
    applicant_id = applicant_id.lower()
    if document_key not in DOCUMENTS:
        return jsonify({"error": "Invalid document type"}), 400

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Please select a PDF file"}), 400

    extension = Path(uploaded.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only PDF files are supported by the OCR backend"}), 400

    state = load_state()
    applicant = state["applicants"].get(applicant_id)
    if not applicant:
        return jsonify({"error": "Applicant not found"}), 404

    applicant_folder = UPLOAD_DIR / applicant_id
    applicant_folder.mkdir(parents=True, exist_ok=True)
    filename = f"{document_key}_{secure_filename(uploaded.filename)}"
    file_path = applicant_folder / filename
    uploaded.save(file_path)

    try:
        from engine import process_document

        result = process_document(str(file_path))
        extracted_data = result.get("extracted_data", {})
        detected_type = result.get("document_type", "unknown")
        ocr_error = None
    except Exception as exc:
        extracted_data = {}
        detected_type = "ocr_error"
        ocr_error = str(exc)

    applicant["documents"][document_key] = {
        "name": uploaded.filename,
        "stored_path": str(file_path),
        "document_type": detected_type,
        "extracted_data": extracted_data,
        "ocr_error": ocr_error,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    applicant["submitted"] = False
    applicant["status"] = "Not Submitted"
    applicant["remarks"] = ""
    applicant["verificationPercentage"] = calculate_verification_percentage(applicant)

    save_state(state)
    return jsonify({"applicant": public_applicant(applicant), "document": applicant["documents"][document_key]})


@app.post("/api/applicants/<applicant_id>/submit")
def submit_documents(applicant_id):
    state = load_state()
    applicant = state["applicants"].get(applicant_id.lower())
    if not applicant:
        return jsonify({"error": "Applicant not found"}), 404

    status, remarks = verification_result(applicant)
    if status == "Not Submitted":
        return jsonify({"error": remarks}), 400

    applicant["submitted"] = True
    applicant["status"] = status
    applicant["remarks"] = remarks
    applicant["submissionDate"] = datetime.now().strftime("%d/%m/%Y")

    save_state(state)
    return jsonify({"applicant": public_applicant(applicant)})


@app.get("/api/admin/applicants")
def admin_applicants():
    state = load_state()
    applicants = []
    for applicant in state["applicants"].values():
        applicant["verificationPercentage"] = calculate_verification_percentage(applicant)
        applicants.append(public_applicant(applicant))
    return jsonify(applicants)


@app.post("/api/admin/applicants/<applicant_id>/status")
def update_status(applicant_id):
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in {"Approved", "Rejected", "Under Scrutiny"}:
        return jsonify({"error": "Invalid status"}), 400

    state = load_state()
    applicant = state["applicants"].get(applicant_id.lower())
    if not applicant:
        return jsonify({"error": "Applicant not found"}), 404

    applicant["status"] = status
    applicant["submitted"] = True
    applicant["remarks"] = f"Status changed by admin to {status}."
    applicant["verificationPercentage"] = calculate_verification_percentage(applicant)
    save_state(state)
    return jsonify({"applicant": public_applicant(applicant)})


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=True)

# Automated-Document-Verification-Portal
An automated document verification system using NLP, OCR, and Deep Learning to extract, classify, and validate information from academic certificates, identity documents, and supporting files.

## Run connected frontend + backend

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. If Poppler is not available globally, set its path before starting:

```bash
set POPPLER_PATH=C:\path\to\poppler\Library\bin
```

3. Start the backend:

```bash
python backend_api.py
```

4. Open the portal:

```text
http://127.0.0.1:5000
```

Sample applicant login: `APP0001` / `pass1`

Admin login: `admin` / `admin123`

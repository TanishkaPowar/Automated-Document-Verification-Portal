import os
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="admission_db",
    user="postgres",
    password="08112004"
)
cursor = conn.cursor()

folder_path = r"D:\Projects\python\Automated-Document-Verification-Portal-main\dataset\PDF_Documents\PDF_Documents"

files = os.listdir(folder_path)
# print("FILES FOUND:", files)

students = {}

# Step 1: Group files by Application ID
for file in files:
    app_id = file.split("_")[0]  # APP0001
    
    if app_id not in students:
        students[app_id] = []
    
    students[app_id].append(file)

# Step 2: Insert into DB
for app_id, docs in students.items():
    
    # Create user
    cursor.execute("INSERT INTO users DEFAULT VALUES RETURNING id;")
    user_id = cursor.fetchone()[0]

    for file in docs:
        file_path = f"{folder_path}/{file}"

        # Detect document type
        if "10th" in file:
            doc_type = "10th"
        elif "12th" in file or "Diploma" in file:
            doc_type = "diploma"
        elif "Caste" in file:
            doc_type = "caste"
        elif "CET" in file:
            doc_type = "cet"
        elif "Leaving" in file:
            doc_type = "leaving"
        elif "application" in file:
            doc_type = "application"
        else:
            continue

        # Insert into documents table
        cursor.execute("""
            INSERT INTO documents (user_id, document_type, file_path)
            VALUES (%s, %s, %s)
        """, (user_id, doc_type, file_path))

conn.commit()
cursor.close()
conn.close()

print("All documents inserted successfully!")
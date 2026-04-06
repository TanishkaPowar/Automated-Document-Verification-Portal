import json
import psycopg2

# ================= DB CONNECTION =================
conn = psycopg2.connect(
    host="localhost",
    database="admission_db",
    user="postgres",
    password="08112004"
)

cursor = conn.cursor()

# ================= HELPERS =================
def normalize(text):
    return text.lower().strip() if text else ""

def safe_get(data, key):
    return normalize(data.get(key)) if data and key in data else None

def get_value(data, keys):
    for key in keys:
        if key in data and data[key]:
            return data[key].lower().strip()
    return None


# ================= FETCH USERS =================
cursor.execute("SELECT id, name, father_name, dob FROM users")
users = cursor.fetchall()

for user in users:
    user_id = user[0]

    # Get documents
    cursor.execute("""
        SELECT document_type, extracted_data
        FROM documents
        WHERE user_id = %s
    """, (user_id,))
    
    docs = cursor.fetchall()

    status = "rejected"
    remarks = ""
    name_list = []
    father_list = []
    dob_list = []

    try:
        for doc_type, extracted in docs:

            if not extracted:
                continue

            if isinstance(extracted, str):
                extracted = json.loads(extracted)

            # Extract fields safely
            doc_name = get_value(extracted, ["name", "student_name", "candidate_name", "applicant_name"])
            doc_father = get_value(extracted, ["father_name", "father", "father's_name"])
            doc_dob = get_value(extracted, ["dob", "date_of_birth"])
            if doc_name:
                name_list.append(doc_name)

            if doc_father:
                father_list.append(doc_father)

            if doc_dob:
                dob_list.append(doc_dob)
           # ================= DATA CLEANING =================
            name_list = list(set(name_list))
            father_list = list(set(father_list))
            dob_list = list(set(dob_list))

# ================= HANDLE MISSING =================
            if not name_list or not father_list or not dob_list:
                status = "error"
                remarks = "Missing data in documents"

            else:
    # ================= CONSISTENCY CHECK =================
                unique_names = set(name_list)
                unique_fathers = set(father_list)
                unique_dobs = set(dob_list)

                name_consistency = len(unique_names)
                father_consistency = len(unique_fathers)
                dob_consistency = len(unique_dobs)

                if name_consistency == 1 and father_consistency == 1 and dob_consistency == 1:
                    status = "verified"

                elif name_consistency <= 2 and father_consistency <= 2 and dob_consistency <= 2:
                    status = "flagged"

                else:
                    status = "rejected"

                remarks = f"Names: {unique_names}, Fathers: {unique_fathers}, DOBs: {unique_dobs}"

    except Exception as e:
        print(f"Error for user {user_id}: {e}")
        status = "error"
        remarks = str(e)

    # ================= INSERT RESULT =================
    cursor.execute("""
        INSERT INTO verification_results (user_id, status, remarks)
        VALUES (%s, %s, %s)
    """, (user_id, status, remarks))


# ================= CLEANUP =================
conn.commit()
cursor.close()
conn.close()

print("Verification completed!")
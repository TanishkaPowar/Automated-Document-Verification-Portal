import json
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="admission_db",
    user="postgres",
    password="08112004"
)

cursor = conn.cursor()

def get_value(data, keys):
    for key in keys:
        if key in data and data[key]:
            return data[key].strip()
    return None

def normalize(text):
    return text.strip() if text else None

cursor.execute("SELECT id FROM users")
users = cursor.fetchall()

for user in users:
    user_id = user[0]

    cursor.execute("""
        SELECT extracted_data
        FROM documents
        WHERE user_id = %s
    """, (user_id,))
    
    docs = cursor.fetchall()

    name_list = []
    father_list = []
    dob_list = []

    for (extracted,) in docs:
        if not extracted:
            continue

        if isinstance(extracted, str):
            extracted = json.loads(extracted)

        name = get_value(extracted, ["name", "student_name", "candidate_name", "applicant_name"])
        father_name = get_value(extracted, ["father_name", "father", "father's_name"])
        dob = get_value(extracted, ["dob", "date_of_birth"])

        if name:
            name_list.append(normalize(name))

        if father_name:
            father_list.append(normalize(father_name))

        if dob:
            dob_list.append(normalize(dob))

    # 🔥 pick most frequent value (important improvement)
    name = max(set(name_list), key=name_list.count) if name_list else None
    father_name = max(set(father_list), key=father_list.count) if father_list else None
    dob = max(set(dob_list), key=dob_list.count) if dob_list else None

    cursor.execute("""
        UPDATE users
        SET name = %s,
            father_name = %s,
            dob = %s
        WHERE id = %s
    """, (name, father_name, dob, user_id))

conn.commit()
cursor.close()
conn.close()

print("✅ Users table populated!")
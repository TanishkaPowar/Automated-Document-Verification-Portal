import psycopg2
from engine import process_document
import gc
import time
import json

conn = psycopg2.connect(
    dbname="admission_db",
    user="postgres",
    password="08112004",
    host="localhost",
    port="5432"
)

cursor = conn.cursor()

BATCH_SIZE = 20   # 🔥 only 20 at a time

while True:
    cursor.execute("""
        SELECT id, file_path 
        FROM documents
        WHERE extracted_data IS NULL
        LIMIT %s
    """, (BATCH_SIZE,))

    docs = cursor.fetchall()

    if not docs:
        print("✅ All documents processed!")
        break

    for doc_id, path in docs:
        try:
            result = process_document(path)

            cursor.execute("""
                UPDATE documents
                SET extracted_data = %s
                WHERE id = %s
            """, (json.dumps(result["extracted_data"]), doc_id))

            conn.commit()   # ✅ commit per document

            print(f"Processed {doc_id}")

        except Exception as e:
            print(f"Error in {doc_id}: {e}")

        # 🔥 MEMORY CONTROL
        gc.collect()
        time.sleep(0.2)
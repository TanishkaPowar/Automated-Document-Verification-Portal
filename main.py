import os
import json
from engine import process_document

def user_input_mode():
    print("===================================")
    print(" Automated Document Verification")
    print("===================================\n")

    pdf_path = input("Enter full path of PDF document: ").strip()

    if not os.path.exists(pdf_path):
        print("\n❌ File not found. Please check the path.")
        return

    if not pdf_path.lower().endswith(".pdf"):
        print("\n❌ Only PDF files are allowed.")
        return

    print("\n🔄 Processing document...\n")

    result = process_document(pdf_path)

    print("✅ Extraction Completed!\n")
    print(json.dumps(result, indent=4))


def folder_mode():
    folder_path = input("Enter folder path containing PDFs: ").strip()

    if not os.path.exists(folder_path):
        print("❌ Folder not found.")
        return

    for file in os.listdir(folder_path):
        if file.lower().endswith(".pdf"):
            pdf_path = os.path.join(folder_path, file)
            print(f"\n📄 Processing: {file}")
            result = process_document(pdf_path)
            print(json.dumps(result, indent=4))


if __name__ == "__main__":

    print("Select Mode:")
    print("1. Single Document")
    print("2. Folder Processing")

    choice = input("Enter choice (1 or 2): ")

    if choice == "1":
        user_input_mode()

    elif choice == "2":
        folder_mode()

    else:
        print("Invalid choice.")

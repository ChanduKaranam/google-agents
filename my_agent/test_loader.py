from tools.pdf_loader import load_documents

documents = load_documents()

print(f"Loaded {len(documents)} documents.\n")

for doc in documents:
    print("=" * 50)
    print("Subject :", doc["subject"])
    print("File    :", doc["file_name"])
    print("Preview :")
    print(doc["content"][:500])
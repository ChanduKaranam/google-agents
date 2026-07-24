from tools.pdf_loader import load_documents

# Load all documents once when the application starts
DOCUMENTS = load_documents()


def search_documents(query: str) -> str:
    """
    Searches the loaded documents and returns relevant content.
    """

    query = query.lower()

    results = []

    for doc in DOCUMENTS:
        if query in doc["content"].lower():
            results.append(
                f"Source: {doc['file_name']}\n\n{doc['content'][:3000]}"
            )

    if not results:
        return "No relevant information found in the uploaded documents."

    return "\n\n----------------------------\n\n".join(results)
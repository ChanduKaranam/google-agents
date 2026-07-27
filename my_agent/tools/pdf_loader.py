from pathlib import Path
from pypdf import PdfReader


KNOWLEDGE_FOLDER = Path("knowledge")


def load_documents():
    """
    Reads all PDFs inside the knowledge folder and
    returns their extracted text.
    """

    documents = []

    for pdf_file in KNOWLEDGE_FOLDER.rglob("*.pdf"):
        reader = PdfReader(pdf_file)

        text = ""

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

        documents.append(
            {
                "file_name": pdf_file.name,
                "subject": pdf_file.parent.name,
                "content": text,
            }
        )

    return documents
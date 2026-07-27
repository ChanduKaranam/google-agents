import os
from pathlib import Path
from dotenv import load_dotenv
import vertexai
from vertexai.preview import rag

# Load environment variables from .env
load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")
RAG_CORPUS = os.getenv("RAG_CORPUS")

if not all([PROJECT_ID, LOCATION, RAG_CORPUS]):
    raise ValueError("Missing required environment variables (GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, or RAG_CORPUS) in .env file.")

print(f"Initializing Vertex AI for project: {PROJECT_ID} in {LOCATION}...")
vertexai.init(project=PROJECT_ID, location=LOCATION)

print(f"Uploading files from local 'knowledge' folder to corpus: {RAG_CORPUS}")
print("This may take a few minutes depending on the number of PDFs...")

knowledge_folder = Path("knowledge")
pdf_files = list(knowledge_folder.rglob("*.pdf"))

if not pdf_files:
    print("No PDF files found in the 'knowledge' folder.")
else:
    for pdf in pdf_files:
        print(f"Uploading {pdf.name}...")
        try:
            # Upload a single local file directly to Vertex AI RAG Corpus.
            # Without display_name Vertex invents one ("vertex-<timestamp>-<hash>"),
            # which leaves retrieved chunks with an empty source_display_name and
            # makes the agents' "cite the source document" instructions unusable.
            response = rag.upload_file(
                corpus_name=RAG_CORPUS,
                path=str(pdf),
                display_name=pdf.name,
            )
            print(f"  -> Success! File registered in cloud as: {response.name}")
        except Exception as e:
            print(f"  -> Failed to upload {pdf.name}: {e}")

print("All uploads finished!")

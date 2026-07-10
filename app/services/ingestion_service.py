import os
import uuid
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.utils.text import clean_text, chunk_text
from app.retrieval.embedder import Embedder
from app.repositories.document_repository import DocumentRepository
from app.core.logging import get_logger

logger = get_logger("app.services.ingestion")

# --- MOCK EXTRACTION FUNCTION ---
# TODO: Replace this with imports from your actual pipeline.py / ocr_engine.py
def extract_text_from_file(file_path: str) -> tuple[str, str]:
    """
    Simulates your OCR/Parsing logic.
    Returns: (raw_text, classification)
    """
    # Example: if file_path.endswith('.pdf'): return run_pdf_ocr(file_path), "pdf"
    return "This is simulated extracted text from the document.", "generic"

class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.embedder = Embedder()
        self.repo = DocumentRepository(db)

    async def process_upload(self, file: UploadFile):
        """
        1. Saves file temporarily
        2. Extracts text (OCR/Parsing)
        3. Chunks & Embeds
        4. Saves to PostgreSQL via Repository
        """
        # 1. Save file temporarily
        temp_dir = "temp_uploads"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file.filename)
        
        with open(temp_path, "wb") as buffer:
            buffer.write(await file.read())

        logger.info("file_received", filename=file.filename)

        try:
            # 2. Extract Text (Plug your existing pipeline here)
            raw_text, classification = extract_text_from_file(temp_path)
            cleaned = clean_text(raw_text)

            # 3. Chunking
            chunks = chunk_text(cleaned, lines_per_chunk=15, overlap_lines=5)
            if not chunks:
                chunks = [cleaned]

            # 4. Embedding
            logger.info("generating_embeddings", filename=file.filename, chunks=len(chunks))
            embeddings = self.embedder.model.encode(chunks)

            # 5. Format data for repository
            chunks_data = []
            for i, chunk in enumerate(chunks):
                chunks_data.append({
                    "chunk_index": i,
                    "text": chunk,
                    "embedding": embeddings[i].tolist()
                })

            # 6. Save to Database
            doc_id = str(uuid.uuid4())
            self.repo.create_document_with_chunks(
                doc_id=doc_id,
                title=file.filename,
                classification=classification,
                chunks_data=chunks_data
            )
            
            logger.info("ingestion_successful", doc_id=doc_id, filename=file.filename)
            return {"status": "success", "doc_id": doc_id}

        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
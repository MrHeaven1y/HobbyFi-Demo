from sqlalchemy.orm import Session
from app.models.document import Document, DocumentChunk
from app.core.logging import get_logger

logger = get_logger("app.repositories.document")

class DocumentRepository:
    
    def __init__(self, db: Session):
    
        self.db = db

    def create_document_with_chunks(self, doc_id: str, title: str, classification: str, chunks_data: list[dict]) -> Document:
        """
        Creates a document and its associated chunks in a single transaction.
        chunks_data expects: [{"text": "...", "embedding": [...], "chunk_index": 0}, ...]
        """

        db_doc = Document( # creating a document row with required field
            id=doc_id,
            title=title,
            classification=classification
        )

        self.db.add(db_doc) # db_doc is a ORM object now yet committed

        chunks_objects = []
        for c_data in chunks_data:
            chunks_objects.append(DocumentChunk(
                document_id=doc_id,
                chunk_index=c_data["chunk_index"],
                text=c_data["text"],
                embedding=c_data["embedding"]
            ))

        self.db.bulk_save_objects(chunks_objects)

        self.db.commit()
        self.db.refresh(db_doc)

        logger.info("document_ingested", doc_id=doc_id, chunks=len(chunks_objects))

        return db_doc
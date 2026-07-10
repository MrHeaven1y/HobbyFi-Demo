"""
Document & DocumentChunk ORM Models
====================================
Defines the SQLAlchemy models for document storage and vector embeddings.
Documents are uploaded by vendors and chunked for RAG (Retrieval-Augmented Generation).
Each chunk's embedding is stored as a pgvector column for semantic search.

Tables:
    - documents: Stores uploaded document metadata
    - document_chunks: Stores text chunks with their vector embeddings
"""

import uuid
from sqlalchemy import String, ForeignKey, Text, DateTime, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime
from typing import Optional

from app.database.base import Base

# Embedding dimension for all-MiniLM-L6-v2 model
EMBEDDING_DIM = 384

class Document(Base):
    """
    Represents an uploaded document (PDF, text file, etc.).
    Documents belong to a vendor and are chunked for vector search.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(100), nullable=True)
    upload_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Vendor who uploaded this document (nullable for backward compatibility)
    vendor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base):
    """
    A text chunk from a document, with its vector embedding for semantic search.
    Used by pgvector for cosine similarity queries.
    """
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # pgvector column — stores 384-dimensional embedding vectors
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")

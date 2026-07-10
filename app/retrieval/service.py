"""
Retrieval Service
==================
Handles semantic search over document chunks using pgvector's
cosine distance operator. Embeds the user's query and retrieves
the most similar document chunks from PostgreSQL.
"""

from sqlalchemy.orm import Session
from typing import List, Dict
from app.models.document import DocumentChunk
from app.retrieval.embedder import Embedder
from app.core.logging import get_logger

logger = get_logger("app.retrieval.service")


class RetrievalService:
    """Performs vector similarity search over document chunks using pgvector."""

    def __init__(self, db: Session):
        self.db = db
        self.embedder = Embedder()

    def search_context(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Embeds the query and searches pgvector for the most similar chunks.

        Returns a list of dicts with keys: doc_id, text, score
        """
        query_vector = self.embedder.embed(query)

        # Query both the chunk AND the cosine distance as a computed column
        # so we can return similarity scores alongside the text.
        distance_col = DocumentChunk.embedding.cosine_distance(query_vector)

        results = (
            self.db.query(DocumentChunk, distance_col.label("distance"))
            .order_by(distance_col)
            .limit(top_k)
            .all()
        )

        # Format results for the LLM prompt
        context_data = []
        for chunk, distance in results:
            # cosine_distance ∈ [0, 2] → similarity = 1 - distance/2 ∈ [0, 1]
            similarity = 1.0 - (float(distance) / 2.0)
            context_data.append({
                "doc_id": chunk.document_id,
                "text": chunk.text,
                "score": round(similarity, 4)
            })

        return context_data
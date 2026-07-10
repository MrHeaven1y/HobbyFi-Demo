"""
Conversation model for persisting agent chat history.

Stores messages as a JSON array so the copilot can reload context
across requests, enabling multi-turn conversations with sliding
window memory.
"""

import uuid
from sqlalchemy import String, ForeignKey, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Any

from app.database.base import Base


class Conversation(Base):
    """
    Persists a vendor's conversation thread with the copilot.

    The `messages` column stores a JSON array of message dicts, each with:
        - role: 'user' | 'assistant'
        - content: str
    """
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), index=True, nullable=False
    )
    messages: Mapped[Any] = mapped_column(
        JSON, default=list,
        comment="JSON array of {role, content} message dicts"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

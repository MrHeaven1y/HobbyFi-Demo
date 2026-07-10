"""
RuntimeEvent model for operational audit events.

This table records non-business workflow events such as LLM quota exhaustion,
local model fallback, and deterministic demo fallback. Business mutations still
belong in audit_logs; this table explains runtime decisions.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RuntimeEvent(Base):
    """Operational audit entry for fallback and runtime-mode decisions."""

    __tablename__ = "runtime_events"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

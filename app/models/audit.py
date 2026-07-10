"""
AuditLog model for the human-in-the-loop approval workflow.

Tracks write operations that require vendor approval before execution.
Each audit log entry stores the action type, its payload, and the
current approval status, enabling a full audit trail of mutations.
"""

import uuid
from sqlalchemy import String, ForeignKey, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional

from app.database.base import Base


class AuditLog(Base):
    """
    Represents a pending or resolved action that requires vendor approval.

    Lifecycle:
        1. Created with status='pending' when a write tool is invoked.
        2. Vendor reviews via the approval endpoint.
        3. Status transitions to 'approved' -> 'executed', or 'rejected'.
    """
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="e.g. 'update_membership', 'initiate_payout', 'update_user_free_trial'"
    )
    action_payload: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="JSON-serialized payload of the action to be executed"
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending",
        comment="One of: 'pending', 'approved', 'rejected', 'executed'"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when the action was approved/rejected/executed"
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Identifier of who resolved this action (vendor user, system, etc.)"
    )

"""
Approval endpoints for the human-in-the-loop audit workflow.

Provides endpoints for vendors to review, approve, or reject
pending write operations that were drafted by the copilot agent.
Approved actions are executed against the database immediately.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.audit import AuditLog
from app.models.crm import Game, Membership
from app.core.logging import get_logger

logger = get_logger("app.api.approval")

router = APIRouter(prefix="/approvals", tags=["Approvals"])


# ──────────────────────────── Request / Response schemas ────────────────────────

class ApproveRequest(BaseModel):
    """Request body for approving a pending action."""
    audit_log_id: str
    resolved_by: Optional[str] = "vendor"


class RejectRequest(BaseModel):
    """Request body for rejecting a pending action."""
    audit_log_id: str
    resolved_by: Optional[str] = "vendor"


class AuditLogResponse(BaseModel):
    """Serialized view of an audit log entry."""
    id: str
    vendor_id: str
    action_type: str
    action_payload: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


# ──────────────────────────── Action executors ─────────────────────────────────

def _execute_action(db: Session, audit_log: AuditLog) -> None:
    """
    Execute the stored action payload against the database.

    Dispatches to the correct handler based on ``action_type``.
    New action types should be added here as the tool set grows.

    Raises:
        ValueError: If the action type is not recognized.
    """
    payload = json.loads(audit_log.action_payload)
    action = audit_log.action_type

    if action == "update_membership":
        _execute_update_membership(db, audit_log.vendor_id, payload)
    elif action == "update_user_free_trial":
        _execute_update_user_free_trial(db, audit_log.vendor_id, payload)
    else:
        raise ValueError(f"Unknown action type: {action}")


def _execute_update_membership(db: Session, vendor_id: str, payload: dict) -> None:
    """Update a user's membership status."""
    membership = (
        db.query(Membership)
        .join(Game, Game.id == Membership.game_id)
        .filter(
            Membership.user_id == payload["user_id"],
            Membership.game_id == payload["game_id"],
            Game.vendor_id == vendor_id,
        )
        .first()
    )
    if not membership:
        raise ValueError(
            f"Membership not found for user={payload['user_id']}, game={payload['game_id']}"
        )
    membership.status = payload["new_status"]
    db.flush()
    logger.info("membership_updated", user_id=payload["user_id"], new_status=payload["new_status"])


def _execute_update_user_free_trial(db: Session, vendor_id: str, payload: dict) -> None:
    """Extend or modify a user's free trial expiry date."""
    membership = (
        db.query(Membership)
        .join(Game, Game.id == Membership.game_id)
        .filter(
            Membership.user_id == payload["user_id"],
            Membership.game_id == payload["game_id"],
            Game.vendor_id == vendor_id,
        )
        .first()
    )
    if not membership:
        raise ValueError(
            f"Membership not found for user={payload['user_id']}, game={payload['game_id']}"
        )
    membership.expires_at = datetime.fromisoformat(payload["new_expiry_date"])
    db.flush()
    logger.info(
        "free_trial_updated",
        user_id=payload["user_id"],
        new_expiry=payload["new_expiry_date"],
    )


# ──────────────────────────── Endpoints ────────────────────────────────────────

def _get_vendor_id(request: Request) -> str:
    vendor_id = getattr(request.state, "vendor_id", None)
    if not vendor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated vendor scope is required.",
        )
    return vendor_id


@router.post("/approve", response_model=AuditLogResponse)
def approve_action(
    payload: ApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Approve and execute a pending audit log action.

    1. Looks up the AuditLog entry.
    2. Validates it is still 'pending'.
    3. Executes the stored action (e.g. updates membership in DB).
    4. Marks the entry as 'executed' with a resolution timestamp.
    """
    vendor_id = _get_vendor_id(request)
    audit_log = (
        db.query(AuditLog)
        .filter(AuditLog.id == payload.audit_log_id, AuditLog.vendor_id == vendor_id)
        .first()
    )
    if not audit_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AuditLog '{payload.audit_log_id}' not found for this vendor.",
        )

    if audit_log.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"AuditLog is already '{audit_log.status}', cannot approve.",
        )

    try:
        _execute_action(db, audit_log)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Mark as executed
    audit_log.status = "executed"
    audit_log.resolved_at = datetime.now(timezone.utc)
    audit_log.resolved_by = payload.resolved_by
    db.commit()
    db.refresh(audit_log)

    logger.info("action_approved_and_executed", audit_log_id=audit_log.id)
    return audit_log


@router.post("/reject", response_model=AuditLogResponse)
def reject_action(
    payload: RejectRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reject a pending audit log action. The action payload is NOT executed.
    """
    vendor_id = _get_vendor_id(request)
    audit_log = (
        db.query(AuditLog)
        .filter(AuditLog.id == payload.audit_log_id, AuditLog.vendor_id == vendor_id)
        .first()
    )
    if not audit_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AuditLog '{payload.audit_log_id}' not found for this vendor.",
        )

    if audit_log.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"AuditLog is already '{audit_log.status}', cannot reject.",
        )

    audit_log.status = "rejected"
    audit_log.resolved_at = datetime.now(timezone.utc)
    audit_log.resolved_by = payload.resolved_by
    db.commit()
    db.refresh(audit_log)

    logger.info("action_rejected", audit_log_id=audit_log.id)
    return audit_log


@router.get("/pending", response_model=List[AuditLogResponse])
def list_pending_approvals(request: Request, db: Session = Depends(get_db)):
    """
    List all pending approval entries for a specific vendor.

    Query parameter:
        Uses the authenticated X-Vendor-ID scope.
    """
    vendor_id = _get_vendor_id(request)
    pending = (
        db.query(AuditLog)
        .filter(AuditLog.vendor_id == vendor_id, AuditLog.status == "pending")
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    return pending

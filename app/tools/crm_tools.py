"""
CRM tools exposed to the LangGraph copilot agent.

Each tool is a LangChain ``@tool`` decorated function that queries or
mutates vendor data. Tools are instantiated inside a factory function
(``get_crm_tools``) which captures the DB session via closure, because
LangChain tools don't natively support dependency injection.

Write tools (mutations) return ``requires_approval=True`` so the
LangGraph workflow can intercept and create an AuditLog entry
instead of executing the change immediately.
"""

from typing import Dict, Any, List, Optional
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.crm import Vendor, Order, User, Game, Membership
from app.core.logging import get_logger
from langchain.tools import tool
from pydantic import BaseModel, Field

logger = get_logger("app.tools.crm")


# ──────────────────────────── Input schemas ─────────────────────────────────────

class GetVendorInfoInput(BaseModel):
    vendor_id: Optional[str] = Field(default=None, description="Optional vendor id; authenticated vendor scope is enforced server-side.")


class GetTrialUsersInput(BaseModel):
    game_name: str = Field(..., description="The name of the game/hobby to list trial users for.")
    vendor_id: Optional[str] = Field(default=None, description="Optional vendor id; authenticated vendor scope is enforced server-side.")


class UpdateMembershipInput(BaseModel):
    user_id: str = Field(..., description="The exact UUID of the user.")
    game_id: str = Field(..., description="The exact UUID of the game.")
    new_status: str = Field(..., description="The new status to set (e.g., 'active', 'expired').")


class GetTodaysRevenueInput(BaseModel):
    vendor_id: Optional[str] = Field(default=None, description="Optional vendor id; authenticated vendor scope is enforced server-side.")


class ListVendorOrdersInput(BaseModel):
    vendor_id: Optional[str] = Field(default=None, description="Optional vendor id; authenticated vendor scope is enforced server-side.")
    limit: int = Field(default=10, description="Maximum number of recent orders to return.")


class UpdateUserFreeTrialInput(BaseModel):
    user_id: str = Field(..., description="The exact UUID of the user.")
    game_id: str = Field(..., description="The exact UUID of the game.")
    new_expiry_date: str = Field(
        ..., description="The new trial expiry date in ISO 8601 format (e.g. '2025-12-31')."
    )


# ──────────────────────────── Tool factory ──────────────────────────────────────

def get_crm_tools(db: Session, authenticated_vendor_id: Optional[str] = None) -> List[Any]:
    """
    Factory that returns LangChain tools bound to the given DB session.

    Tools are defined as inner functions so they capture ``db`` via closure.
    """

    def scoped_vendor_id(requested_vendor_id: Optional[str] = None) -> Optional[str]:
        """Prefer the authenticated request scope over model-supplied arguments."""
        return authenticated_vendor_id or requested_vendor_id

    @tool("get_vendor_info", args_schema=GetVendorInfoInput)
    def get_vendor_info(vendor_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetches vendor profile info including name, status, and payout balance."""
        effective_vendor_id = scoped_vendor_id(vendor_id)
        if not effective_vendor_id:
            return {"error": "Authenticated vendor scope is required."}

        vendor = db.query(Vendor).filter(Vendor.id == effective_vendor_id).first()
        if not vendor:
            return {"error": "Vendor not found"}
        return {
            "id": vendor.id,
            "name": vendor.name,
            "status": vendor.status,
            "payout_balance": vendor.payout_balance,
        }

    @tool("get_trial_users", args_schema=GetTrialUsersInput)
    def get_trial_users(game_name: str, vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists users who have a trial membership for a specific game belonging to the vendor."""
        effective_vendor_id = scoped_vendor_id(vendor_id)
        if not effective_vendor_id:
            return [{"error": "Authenticated vendor scope is required."}]

        results = (
            db.query(User, Membership)
            .join(Membership, User.id == Membership.user_id)
            .join(Game, Game.id == Membership.game_id)
            .filter(Game.name.ilike(f"%{game_name}%"))
            .filter(Game.vendor_id == effective_vendor_id)
            .filter(Membership.status == "trial")
            .all()
        )

        return [
            {
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "membership_id": membership.id,
                "status": membership.status,
            }
            for user, membership in results
        ]

    @tool("update_membership", args_schema=UpdateMembershipInput)
    def update_membership(user_id: str, game_id: str, new_status: str) -> Dict[str, Any]:
        """
        Drafts a membership status update (e.g. trial -> active).
        This is a WRITE operation that requires vendor approval before execution.
        """
        # Return a draft payload; the LangGraph workflow will intercept this
        # and create an AuditLog entry instead of executing immediately.
        return {
            "action": "update_membership",
            "requires_approval": True,
            "payload": {
                "action": "update_membership",
                "user_id": user_id,
                "game_id": game_id,
                "new_status": new_status,
            },
        }

    @tool("get_todays_revenue", args_schema=GetTodaysRevenueInput)
    def get_todays_revenue(vendor_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates total revenue from completed orders placed today for a vendor."""
        effective_vendor_id = scoped_vendor_id(vendor_id)
        if not effective_vendor_id:
            return {"error": "Authenticated vendor scope is required."}

        today_start = datetime.combine(date.today(), datetime.min.time())

        result = (
            db.query(sa_func.coalesce(sa_func.sum(Order.amount), 0.0))
            .filter(
                Order.vendor_id == effective_vendor_id,
                Order.status == "completed",
                Order.created_at >= today_start,
            )
            .scalar()
        )

        return {
            "vendor_id": effective_vendor_id,
            "date": str(date.today()),
            "total_revenue": float(result),
        }

    @tool("list_vendor_orders", args_schema=ListVendorOrdersInput)
    def list_vendor_orders(vendor_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists the most recent orders for a vendor, newest first."""
        effective_vendor_id = scoped_vendor_id(vendor_id)
        if not effective_vendor_id:
            return [{"error": "Authenticated vendor scope is required."}]

        orders = (
            db.query(Order)
            .filter(Order.vendor_id == effective_vendor_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "order_id": order.id,
                "amount": order.amount,
                "status": order.status,
                "created_at": str(order.created_at) if order.created_at else None,
            }
            for order in orders
        ]

    @tool("update_user_free_trial", args_schema=UpdateUserFreeTrialInput)
    def update_user_free_trial(
        user_id: str, game_id: str, new_expiry_date: str
    ) -> Dict[str, Any]:
        """
        Drafts an update to extend or modify a user's free trial expiry date.
        This is a WRITE operation that requires vendor approval before execution.
        """
        return {
            "action": "update_user_free_trial",
            "requires_approval": True,
            "payload": {
                "action": "update_user_free_trial",
                "user_id": user_id,
                "game_id": game_id,
                "new_expiry_date": new_expiry_date,
            },
        }

    return [
        get_vendor_info,
        get_trial_users,
        update_membership,
        get_todays_revenue,
        list_vendor_orders,
        update_user_free_trial,
    ]

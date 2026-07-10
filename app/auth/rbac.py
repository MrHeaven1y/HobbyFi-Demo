"""
Simple Role-Based Access Control (RBAC) helpers for vendor-scoped operations.

This module provides lightweight permission checks that ensure vendors
can only access and modify their own data. This is a simulated RBAC layer
(no real JWT verification) suitable for the assessment phase.
"""

from fastapi import HTTPException, Request, status


def require_vendor(request: Request) -> str:
    """
    Extract and return the authenticated vendor_id from request state.

    The vendor_id is set by the VendorAuthMiddleware from the X-Vendor-ID
    header. If the middleware hasn't set it, the request is unauthorized.

    Returns:
        The vendor_id string.

    Raises:
        HTTPException 401 if no vendor context is found.
    """
    vendor_id = getattr(request.state, "vendor_id", None)
    if not vendor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Vendor-ID header.",
        )
    return vendor_id


def enforce_vendor_scope(request: Request, target_vendor_id: str) -> None:
    """
    Ensure the authenticated vendor is only accessing their own resources.

    Raises:
        HTTPException 403 if the requesting vendor doesn't match the target.
    """
    requesting_vendor_id = require_vendor(request)
    if requesting_vendor_id != target_vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access another vendor's data.",
        )

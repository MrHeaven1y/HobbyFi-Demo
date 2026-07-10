"""
Vendor authentication middleware (simulated).

Reads the ``X-Vendor-ID`` header from incoming requests, validates that
the vendor exists in the database, and attaches the ``vendor_id`` to
``request.state`` so downstream endpoints and RBAC helpers can use it.

This is a lightweight simulation—no JWT or OAuth involved. In production,
this would be replaced with proper token verification.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.database.session import SessionLocal
from app.models.crm import Vendor
from app.core.logging import get_logger

logger = get_logger("app.middleware.vendor_auth")

# Paths that should bypass vendor authentication (health checks, docs, etc.)
_PUBLIC_PATHS = frozenset({
    "/",
    "/dashboard",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/health",
    "/api/v1/health/",
})


class VendorAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates the X-Vendor-ID header on every request.

    Skips validation for public paths (health, docs).
    Sets ``request.state.vendor_id`` on success.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Allow public endpoints through without auth
        if (
            request.url.path in _PUBLIC_PATHS
            or request.url.path.startswith("/docs")
            or request.url.path.startswith("/static/")
        ):
            return await call_next(request)

        vendor_id = request.headers.get("X-Vendor-ID")

        if not vendor_id:
            logger.warning("missing_vendor_header", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"detail": "X-Vendor-ID header is required."},
            )

        # Validate that this vendor actually exists in the database
        db = SessionLocal()
        try:
            vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
            if not vendor:
                logger.warning("invalid_vendor_id", vendor_id=vendor_id)
                return JSONResponse(
                    status_code=401,
                    content={"detail": f"Vendor '{vendor_id}' not found."},
                )
        finally:
            db.close()

        # Attach the validated vendor_id to request state for downstream use
        request.state.vendor_id = vendor_id
        logger.debug("vendor_authenticated", vendor_id=vendor_id, path=request.url.path)

        return await call_next(request)

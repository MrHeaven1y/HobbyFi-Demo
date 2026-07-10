"""
HobbyFi Copilot — FastAPI application entry point.

Configures the ASGI application, registers middleware, mounts routers,
runs database migrations (via create_all), and seeds initial CRM data
on first startup.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api.v1.endpoints import health, chat, documents, approval, pages
from app.database.session import engine, SessionLocal
from app.database.base import Base
from app.middleware.vendor_auth import VendorAuthMiddleware

# ── Import ALL models so Base.metadata.create_all picks them up ─────────────
from app.models import document, crm  # noqa: F401
from app.models import audit  # noqa: F401  (Phase 7 — AuditLog)
from app.models import conversation  # noqa: F401  (Phase 8 — Conversation)
from app.models import runtime  # noqa: F401  (Runtime fallback audit events)

setup_logging()
logger = get_logger("app.main")

# ── Jinja2 template directory (used if we serve any HTML pages) ─────────────
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)  # Ensure the directory exists
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.

    Startup:
        - Enables pgvector extension.
        - Runs create_all for all registered models.
        - Seeds initial CRM data if the database is empty.

    Shutdown:
        - Disposes of the SQLAlchemy engine pool.
    """
    logger.info("application_starting", app_name=settings.APP_NAME, env=settings.APP_ENV)
    logger.info("initializing_database")

    # Open a direct connection to ensure vector extension exists.
    # Then create ORM tables through the engine so SQLAlchemy uses its normal
    # DDL path for every registered model.
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    logger.info("database_ready")

    # ── Seed initial CRM data ──────────────────────────────────────────────
    db = SessionLocal()
    try:
        if db.query(crm.Vendor).count() == 0:
            logger.info("seeding_initial_crm_data")

            v1 = crm.Vendor(id="v_12345_abc", name="Acme Corp", status="active", payout_balance=5000.00)
            v2 = crm.Vendor(id="v_67890_xyz", name="Globex Inc", status="active", payout_balance=1250.50)

            o1 = crm.Order(id="o_001", vendor_id="v_12345_abc", amount=1500.00, status="completed")
            o2 = crm.Order(id="o_002", vendor_id="v_12345_abc", amount=350.00, status="pending")

            u1 = crm.User(id="u_001", name="Alice Smith", email="alice@example.com")
            u2 = crm.User(id="u_002", name="Bob Jones", email="bob@example.com")

            g1 = crm.Game(id="g_001", name="Badminton", vendor_id="v_12345_abc")
            g2 = crm.Game(id="g_002", name="Tennis", vendor_id="v_12345_abc")

            m1 = crm.Membership(id="m_001", user_id="u_001", game_id="g_001", status="trial")
            m2 = crm.Membership(id="m_002", user_id="u_002", game_id="g_001", status="active")

            db.add_all([v1, v2, o1, o2, u1, u2, g1, g2, m1, m2])
            db.commit()
            logger.info("crm_data_seeded_successfully")
    finally:
        db.close()

    yield

    logger.info("application_shutting_down")
    engine.dispose()


# ── Application factory ────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    description="AI Copilot for HobbyFi Vendor Portal",
    version="0.2.0",
    lifespan=lifespan,
)

# ── Middleware (order matters — outermost first) ───────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vendor authentication middleware (simulated via X-Vendor-ID header)
app.add_middleware(VendorAuthMiddleware)

# ── Static files mount (CSS/JS if needed) ─────────────────────────────────────
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(health.router, prefix="/api/v1", tags=["System"])
app.include_router(chat.router, prefix="/api/v1", tags=["Copilot"])
app.include_router(documents.router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(approval.router, prefix="/api/v1", tags=["Approvals"])
app.include_router(pages.router, tags=["Pages"])

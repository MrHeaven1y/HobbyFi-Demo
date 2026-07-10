"""
Page routes — serves the Jinja2 frontend templates.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

# Resolve templates directory relative to the app package
_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def chat_page(request: Request):
    """Render the main chat interface."""
    return templates.TemplateResponse(request=request, name="chat.html")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request):
    """Render a placeholder dashboard page."""
    return templates.TemplateResponse(request=request, name="dashboard.html")

"""
This file defines a simple health check HTTP endpoint for the FastAPI app. 
It registers a route on an APIRouter, 
uses the application settings for metadata, 
and logs a structured event when the endpoint is called.
"""

from fastapi import APIRouter
from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter() # a reachable router from main FastAPI app, that creates a router object that groups related routes.
logger = get_logger(__name__) # Obtains a structured logger instance for this module

@router.get("/health", tags=['System'])
async def health_check(): # async coroutine called alongside with main api when requested health.
    """
    V1 health check endpoint to verify API is running.
    """
    logger.info("Health_check_requested", status="ok")
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }
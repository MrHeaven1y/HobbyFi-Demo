"""
Application Configuration
==========================
Loads environment variables into a validated, type-safe Settings object
using pydantic-settings. The application fails fast on startup if any
required variable is missing.

Environment variables are loaded from a .env file in the project root.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    Fails fast if required variables are missing on startup.
    """
    APP_NAME: str = "HobbyFi Copilot"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # PostgreSQL connection string (includes pgvector extension)
    DATABASE_URL: str

    # Hugging Face token for Inference API
    HUGGINGFACE_TOKEN: str

    # Google Gemini API key (free tier from Google AI Studio)
    GEMINI_API_KEY: str
    LLM_MODEL_NAME: str = "gemini-2.5-flash"

    # Demo controls: the free Gemini tier is quota-limited, so the app can
    # intentionally fall back to deterministic local CRM answers.
    ENABLE_LOCAL_DEMO_FALLBACK: bool = True
    DEMO_LLM_CALL_BUDGET: int = 6

    # Optional local LLM fallback. Ollama is used as the default local runtime
    # because it is free and can run fully on the developer machine.
    LOCAL_MODEL_ENABLED: bool = True
    LOCAL_MODEL_BASE_URL: str = "http://127.0.0.1:11434"
    LOCAL_MODEL_NAME: str = "qwen2.5:3b"
    LOCAL_MODEL_TIMEOUT_SECONDS: int = 120

    # How many fallback messages to process before trying Gemini again
    GEMINI_RETRY_AFTER_MESSAGES: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Validated global settings object — imported throughout the application
settings = Settings()

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.llm.provider import BaseLLMProvider
from app.llm.gemini import GeminiProvider

# Singleton LLM Provider, module level variable
_llm_provider: BaseLLMProvider = None


def get_llm_provider() -> BaseLLMProvider:
    
    global _llm_provider

    if _llm_provider is None:
        _llm_provider = GeminiProvider()

    return _llm_provider

def get_copilot_service(
    request: Request,
    db: Session = Depends(get_db),
) -> 'CopilotService':
    """Inject the DB session and authenticated vendor into CopilotService."""
    from app.services.copilot_service import CopilotService
    return CopilotService(db=db, vendor_id=getattr(request.state, "vendor_id", None))

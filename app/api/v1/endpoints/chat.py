from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

from app.core.deps import get_copilot_service
from app.services.copilot_service import CopilotService

router = APIRouter()

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    chat_history: Optional[List[Dict]] = None
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
    requires_approval: bool = False
    approval_payload: Optional[Dict[str, Any]] = None
    audit_log_id: Optional[str] = None
    conversation_id: Optional[str] = None
    mode: str = "llm"
    warning: Optional[str] = None
    remaining_llm_calls: Optional[int] = None


@router.post("/chat", response_model=ChatResponse)
async def chat_with_copilot(
        request: ChatRequest,
        copilot: CopilotService = Depends(get_copilot_service)
    ):
    """
    Main endpoint to interact with the HobbyFi Copilot.
    """
    
    result = await copilot.answer_query(
        request.question,
        request.chat_history,
        conversation_id=request.conversation_id,
    )

    return ChatResponse(**result)


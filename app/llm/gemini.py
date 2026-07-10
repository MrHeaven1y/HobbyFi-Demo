from asyncio import to_thread
import google.generativeai as genai
from typing import List, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.provider import BaseLLMProvider # abstract class

logger = get_logger("app.llm.gemini")

class GeminiProvider(BaseLLMProvider):
    """
    Concrete Implementation of the LLM provider using gemini from google.
    """

    def __init__(self):
        
        genai.configure(api_key=settings.GEMINI_API_KEY) # api authentication
        self.model = genai.GenerativeModel(
            settings.LLM_MODEL_NAME, # model name
            generation_config={
                "temperature": 0.2,  # control randomness in output, lower = more deterministic
                "top_p": 0.4, # nucleus sampling (limit prob mass)
                "max_output_tokens": 1024, # cap on response length
            }
        )

        logger.info("gemini_provider_initialized", model=settings.LLM_MODEL_NAME)

    async def generate_response(
            self,
            system_prompt: str,
            user_prompt: str,
            chat_history: Optional[List[Dict]] = None
    ) -> str:
        """
        calls Gemini API. Note: we wrap the synchronous genai call in asyncio.to_thread
        to prevent blocking the FastAPI async event Loop.
        """
        # Gemini handles system instructions natively in newer SDKs, 
        # but for compatibility we prepend it to the first user message or history.
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        # Format history for Gemini (expects list of {"role": "user"/"model", "parts": [text]})
        gemini_history = []
        if chat_history:
            for msg in chat_history:  # loop converts generic dict into gemini format
                
                role = "user" if msg.get("role") == "user" else "model"
                gemini_history.append({"role":role, "parts": [msg.get("content", "")]}) 

        # starts a chat session with gemini
        def _sync_call():
            
            try:
                
                chat = self.model.start_chat(history=gemini_history)
                response = chat.send_message(full_prompt)
                
                return response.txt

            except Exception as e:
                
                logger.error("gemini_api_error", error=str(e))

                # in production, exception can be changed to DomainException here
                return f"I encountered an error processing your request: {str(e)}"


        # Run Synchronous Google SDK in a thread pool to not block async FastAPI
        result = await to_thread(_sync_call)
        return result
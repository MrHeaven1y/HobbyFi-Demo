from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class BaseLLMProvider(ABC):
    """
    Abstract interface for LLM providers to ensure loose coupling.
    """

    @abstractmethod                 # forces subclass to implement this method
    async def generate_response(   # non blocking I/O (requried for llm calls because they use network request)
        self, 
        system_prompt: str,         # instructions for the method (dev give it to llm)
        user_prompt: str,           # the actual user's input
        chat_history: Optional[List[Dict]] = None, #optional past convo context
    ) -> str:
        """Generates a text response from the LLM"""
        pass
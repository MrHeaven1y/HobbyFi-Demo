"""
Conversation memory service with sliding-window strategy.

Provides persistent, per-vendor conversation memory backed by the
``conversations`` table. Uses a sliding window to keep only the
most recent N messages, preventing unbounded context growth.
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.core.logging import get_logger

logger = get_logger("app.services.memory")

# Default number of message pairs to keep in the sliding window.
# Each "pair" is a user message + assistant response, so the actual
# number of message dicts stored is up to 2 * DEFAULT_WINDOW_SIZE.
DEFAULT_WINDOW_SIZE = 10


class ConversationMemory:
    """
    Manages conversation history with a sliding-window strategy.

    Usage:
        memory = ConversationMemory(db, vendor_id, conversation_id)
        history = memory.load()            # Get past messages
        memory.save(user_msg, ai_msg)      # Append & trim
    """

    def __init__(
        self,
        db: Session,
        vendor_id: str,
        conversation_id: Optional[str] = None,
        window_size: int = DEFAULT_WINDOW_SIZE,
    ):
        self.db = db
        self.vendor_id = vendor_id
        self.conversation_id = conversation_id
        self.window_size = window_size
        self._conversation: Optional[Conversation] = None

    def _get_or_create_conversation(self) -> Conversation:
        """Retrieve existing conversation or create a new one."""
        if self._conversation:
            return self._conversation

        if self.conversation_id:
            self._conversation = (
                self.db.query(Conversation)
                .filter(
                    Conversation.id == self.conversation_id,
                    Conversation.vendor_id == self.vendor_id,
                )
                .first()
            )

        # If not found or no id provided, create a new conversation
        if not self._conversation:
            self._conversation = Conversation(
                vendor_id=self.vendor_id,
                messages=[],
            )
            self.db.add(self._conversation)
            self.db.flush()  # Populate the auto-generated id
            self.conversation_id = self._conversation.id
            logger.info(
                "conversation_created",
                conversation_id=self.conversation_id,
                vendor_id=self.vendor_id,
            )

        return self._conversation

    def load(self) -> List[Dict[str, str]]:
        """
        Load conversation messages from the database.

        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        conversation = self._get_or_create_conversation()
        messages = conversation.messages or []
        logger.debug(
            "memory_loaded",
            conversation_id=self.conversation_id,
            message_count=len(messages),
        )
        return messages

    def save(self, user_message: str, assistant_message: str, mode: str = "llm") -> str:
        """
        Append user and assistant messages, then apply the sliding window.

        Args:
            user_message: The user's query text.
            assistant_message: The assistant's response text.
            mode: The mode used for generation (e.g. 'llm', 'local_model', 'deterministic').

        Returns:
            The conversation_id (useful when a new conversation was created).
        """
        conversation = self._get_or_create_conversation()

        # Get current messages (or empty list)
        current_messages = list(conversation.messages or [])

        # Append the new exchange
        current_messages.append({"role": "user", "content": user_message})
        current_messages.append({"role": "assistant", "content": assistant_message, "mode": mode})

        # Apply sliding window: keep the last N*2 messages (N exchanges)
        max_messages = self.window_size * 2
        if len(current_messages) > max_messages:
            current_messages = current_messages[-max_messages:]
            logger.debug(
                "memory_window_trimmed",
                conversation_id=self.conversation_id,
                kept=max_messages,
            )

        # Persist — reassign the list so SQLAlchemy detects the mutation
        conversation.messages = current_messages
        self.db.commit()

        logger.debug(
            "memory_saved",
            conversation_id=self.conversation_id,
            total_messages=len(current_messages),
        )
        return self.conversation_id

    def clear(self) -> None:
        """Reset conversation history to an empty list."""
        conversation = self._get_or_create_conversation()
        conversation.messages = []
        self.db.commit()
        logger.info("memory_cleared", conversation_id=self.conversation_id)

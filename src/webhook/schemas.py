"""Response bodies."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, JsonValue

from webhook.models import Message


class Receipt(BaseModel):
    """Confirmation that a message was stored."""

    id: UUID
    inbox: str
    received_at: datetime
    expires_at: datetime


class StoredMessage(BaseModel):
    """A message as returned to a reader."""

    id: UUID
    received_at: datetime
    payload: JsonValue

    @classmethod
    def from_model(cls, message: Message) -> StoredMessage:
        """
        Convert a stored item.

        Parameters
        ----------
        message : Message
            Item read from DynamoDB, whose payload passed validation
            when it was stored.

        Returns
        -------
        StoredMessage
            The message's public fields.
        """
        return cls(
            id=message.message_id,
            received_at=message.received_at,
            payload=message.payload,
        )


class InboxContents(BaseModel):
    """A batch of pending messages from one inbox."""

    inbox: str
    more: bool
    messages: list[StoredMessage]

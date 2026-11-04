"""Stores, lists and deletes messages in DynamoDB."""

from datetime import datetime, timedelta
from typing import Final
from uuid import uuid7

from pydantic import JsonValue

from webhook.models import Message

RETENTION: Final[timedelta] = timedelta(days=3)


def add_message(inbox: str, payload: JsonValue, now: datetime) -> Message:
    """
    Store a new message in an inbox.

    Parameters
    ----------
    inbox : str
        Inbox name.
    payload : JsonValue
        Message content.
    now : datetime
        Timezone-aware arrival time.

    Returns
    -------
    Message
        The stored message, expiring ``RETENTION`` after ``now``.
    """
    message = Message(
        inbox=inbox,
        message_id=uuid7(),
        received_at=now,
        payload=payload,
        expires_at=now + RETENTION,
    )
    message.save()
    return message


def pending_messages(
    inbox: str,
    limit: int,
    now: datetime,
) -> tuple[list[Message], bool]:
    """
    Read the oldest unexpired messages in an inbox.

    Parameters
    ----------
    inbox : str
        Inbox name.
    limit : int
        Most messages to return.
    now : datetime
        Timezone-aware current time; messages expiring by then are
        skipped.

    Returns
    -------
    tuple[list[Message], bool]
        Up to ``limit`` messages, oldest first, and whether more are
        waiting.
    """
    found = list(
        Message.query(
            hash_key=inbox,
            filter_condition=Message.expires_at > now,
            limit=limit + 1,
        ),
    )
    return found[:limit], len(found) > limit


def delete_messages(messages: list[Message]) -> None:
    """
    Delete messages.

    Parameters
    ----------
    messages : list[Message]
        Messages to delete.
    """
    with Message.batch_write() as batch:
        for message in messages:
            batch.delete(message)

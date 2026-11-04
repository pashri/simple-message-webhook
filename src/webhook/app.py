"""HTTP routes for posting to and reading from inboxes."""

from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from aws_lambda_powertools import Logger
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import JsonValue

from webhook.auth import Access, require
from webhook.parsing import MAX_BODY, inbox_name, inbox_problems, parse_payload
from webhook.repository import add_message, delete_messages, pending_messages
from webhook.schemas import InboxContents, Receipt, StoredMessage

logger = Logger(child=True)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def utc_now() -> datetime:
    """
    Give the current time.

    Returns
    -------
    datetime
        Now, in UTC.
    """
    return datetime.now(UTC)


def resolve_inbox(path: str) -> str:
    """
    Name and check the inbox for the request path.

    Parameters
    ----------
    path : str
        Request path, without its leading slash.

    Returns
    -------
    str
        Inbox name.

    Raises
    ------
    HTTPException
        422 when the name cannot be stored.
    """
    inbox = inbox_name(path=path)
    problems = inbox_problems(inbox=inbox)
    if problems:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
            detail=problems,
        )
    return inbox


async def read_payload(request: Request) -> JsonValue:
    """
    Read the request body as a payload.

    Parameters
    ----------
    request : Request
        Incoming request.

    Returns
    -------
    JsonValue
        Parsed JSON, or the body text when it is not JSON.

    Raises
    ------
    HTTPException
        413 when the body is over ``MAX_BODY``; 422 when it is not
        UTF-8.
    """
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            detail=f'Body is larger than {MAX_BODY} bytes',
        )
    try:
        text = body.decode('utf-8')
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
            detail='Body is not UTF-8',
        ) from error
    return parse_payload(body=text)


Now = Annotated[datetime, Depends(utc_now)]
Inbox = Annotated[str, Depends(resolve_inbox)]
Payload = Annotated[JsonValue, Depends(read_payload)]


@app.post(
    '/{path:path}',
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require(Access.WRITE))],
)
def post_message(inbox: Inbox, payload: Payload, now: Now) -> Receipt:
    """
    Store a message in the inbox named by the path.

    Parameters
    ----------
    inbox : str
        Inbox name.
    payload : JsonValue
        Message content.
    now : datetime
        Arrival time.

    Returns
    -------
    Receipt
        The new message's id and times.
    """
    message = add_message(inbox=inbox, payload=payload, now=now)
    logger.info(
        'Stored message',
        extra={
            'inbox': inbox,
            'id': str(message.message_id),
            'payload': payload,
        },
    )
    return Receipt(
        id=message.message_id,
        inbox=inbox,
        received_at=message.received_at,
        expires_at=message.expires_at,
    )


@app.get(
    '/{path:path}',
    dependencies=[Depends(require(Access.READ))],
)
def get_messages(
    inbox: Inbox,
    now: Now,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    clear: bool = False,
) -> InboxContents:
    """
    Return the oldest pending messages, deleting them when asked.

    Parameters
    ----------
    inbox : str
        Inbox name.
    now : datetime
        Current time.
    limit : int
        Most messages to return.
    clear : bool
        Delete the returned messages.

    Returns
    -------
    InboxContents
        Messages oldest first, and whether more are waiting. The
        response is built before anything is deleted.
    """
    messages, more = pending_messages(inbox=inbox, limit=limit, now=now)
    contents = InboxContents(
        inbox=inbox,
        more=more,
        messages=[
            StoredMessage.from_model(message=message)
            for message in messages
        ],
    )
    if clear:
        delete_messages(messages=messages)
    logger.info(
        'Read inbox',
        extra={
            'inbox': inbox,
            'count': len(messages),
            'cleared': clear,
            'more': more,
        },
    )
    return contents

"""Turns request paths and bodies into inbox names and payloads."""

import json
import math
from typing import Final

from pydantic import JsonValue, TypeAdapter

MAX_BODY: Final[int] = 4096  # bytes
MAX_INBOX: Final[int] = 256  # characters
JSON_VALUE: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)


def inbox_name(path: str) -> str:
    """
    Name the inbox for a request path.

    Parameters
    ----------
    path : str
        Request path, with or without its leading slash.

    Returns
    -------
    str
        The path with one leading slash and no trailing slash. A blank
        path gives ``'/'``, because DynamoDB keys cannot be empty.
    """
    return '/' + path.removeprefix('/').rstrip('/')


def inbox_problems(inbox: str) -> list[str]:
    """
    Check that an inbox name can be stored.

    Parameters
    ----------
    inbox : str
        Inbox name from ``inbox_name``.

    Returns
    -------
    list[str]
        Problems found; empty when the name is fine.
    """
    if len(inbox) > MAX_INBOX:
        return [f'Inbox name is longer than {MAX_INBOX} characters']
    return []


def reject_constant(name: str) -> None:
    """
    Refuse ``NaN`` and ``Infinity``, which are not valid JSON.

    Parameters
    ----------
    name : str
        The constant ``json.loads`` found.

    Raises
    ------
    ValueError
        Always.
    """
    raise ValueError(f'{name} is not valid JSON')


def finite_float(text: str) -> float:
    """
    Parse a JSON number, refusing ones too large for a float.

    Parameters
    ----------
    text : str
        The number as written, such as ``1.5`` or ``1e400``.

    Returns
    -------
    float
        The number.

    Raises
    ------
    ValueError
        When the number overflows to infinity.
    """
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f'{text} is out of range')
    return value


def parse_payload(body: str) -> JsonValue:
    """
    Read a request body as JSON, falling back to plain text.

    The JSON must also pass the same validation the responses use, so
    anything stored can be returned. Nesting deeper than that allows,
    or a number too large for a float, falls back to text.

    Parameters
    ----------
    body : str
        Decoded request body.

    Returns
    -------
    JsonValue
        The parsed JSON, or the body itself as a string when it cannot
        be stored as JSON.
    """
    try:
        parsed = json.loads(
            body,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
        payload = JSON_VALUE.validate_python(parsed)
    except (ValueError, RecursionError):
        return body
    return payload

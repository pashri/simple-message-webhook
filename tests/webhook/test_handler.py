"""Tests for the Lambda entry point, using function URL events."""

import json
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, cast

from aws_lambda_powertools.utilities.typing import LambdaContext

from tests.conftest import READ_KEY, WRITE_KEY
from webhook.handler import handler


@dataclass
class Context:  # pylint: disable=too-few-public-methods
    """The Lambda context fields Powertools reads."""

    function_name: str = 'simple-message-webhook'
    memory_limit_in_mb: int = 256
    invoked_function_arn: str = (
        'arn:aws:lambda:ap-southeast-2:123456789012:function:webhook'
    )
    aws_request_id: str = 'request-1'


def url_event(
    method: str,
    path: str,
    key: str,
    body: str | None = None,
    query: str = '',
) -> dict[str, Any]:
    """
    Build a function URL (payload format 2.0) event.

    Parameters
    ----------
    method : str
        HTTP method.
    path : str
        Request path.
    key : str
        Bearer key.
    body : str | None
        Request body.
    query : str
        Raw query string.

    Returns
    -------
    dict[str, Any]
        The event.
    """
    return {
        'version': '2.0',
        'routeKey': '$default',
        'rawPath': path,
        'rawQueryString': query,
        'headers': {
            'authorization': f'Bearer {key}',
            'content-type': 'application/json',
            'host': 'abc.lambda-url.ap-southeast-2.on.aws',
        },
        'requestContext': {
            'accountId': 'anonymous',
            'apiId': 'abc',
            'domainName': 'abc.lambda-url.ap-southeast-2.on.aws',
            'domainPrefix': 'abc',
            'http': {
                'method': method,
                'path': path,
                'protocol': 'HTTP/1.1',
                'sourceIp': '203.0.113.1',
                'userAgent': 'pytest',
            },
            'requestId': 'request-1',
            'routeKey': '$default',
            'stage': '$default',
            'time': '04/Nov/2026:10:02:11 +0000',
            'timeEpoch': 1793786531123,
        },
        'body': body,
        'isBase64Encoded': False,
    }


def test_handler_posts_and_reads_through_function_url(_aws: None) -> None:
    posted = handler(
        url_event(
            method='POST',
            path='/home/desk',
            key=WRITE_KEY,
            body='{"source": "teams"}',
        ),
        cast(LambdaContext, Context()),
    )
    read = handler(
        url_event(
            method='GET',
            path='/home/desk',
            key=READ_KEY,
            query='clear=true',
        ),
        cast(LambdaContext, Context()),
    )
    assert posted['statusCode'] == HTTPStatus.CREATED
    assert read['statusCode'] == HTTPStatus.OK
    messages = json.loads(read['body'])['messages']
    assert [m['payload'] for m in messages] == [{'source': 'teams'}]

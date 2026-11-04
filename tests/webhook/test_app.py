"""Tests for the HTTP routes."""

from datetime import timedelta
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from tests.conftest import NOW, Clock
from webhook.parsing import MAX_BODY, MAX_INBOX


def test_post_message_returns_receipt(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.post(
        '/kitchen',
        json={'source': 'mail'},
        headers=write_auth,
    )
    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body['inbox'] == '/kitchen'
    assert body['received_at'] == '2026-11-04T10:02:11.123456Z'
    assert body['expires_at'] == '2026-11-07T10:02:11Z'
    assert list(body) == ['id', 'inbox', 'received_at', 'expires_at']


def test_get_messages_returns_stored_payload(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    posted = client.post(
        '/kitchen',
        json={'source': 'mail', 'from': 'Alex Example', 'n': 1.5},
        headers=write_auth,
    ).json()
    response = client.get('/kitchen', headers=read_auth)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        'inbox': '/kitchen',
        'more': False,
        'messages': [
            {
                'id': posted['id'],
                'received_at': '2026-11-04T10:02:11.123456Z',
                'payload': {'source': 'mail', 'from': 'Alex Example', 'n': 1.5},
            },
        ],
    }


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        ('"hello"', 'hello'),
        ('[1, 2]', [1, 2]),
        ('42', 42),
        ('null', None),
        ('hello', 'hello'),
        ('NaN', 'NaN'),
        ('', ''),
        ('{"broken": ', '{"broken": '),
        ('Grüße', 'Grüße'),
        ('1e400', '1e400'),
        ('{"a": -1e999}', '{"a": -1e999}'),
        ('[[[1]]]', [[[1]]]),
        ('[' * 300 + ']' * 300, '[' * 300 + ']' * 300),
        ('[' * 2000 + ']' * 2000, '[' * 2000 + ']' * 2000),
        (str(10**400), 10**400),
    ],
)
def test_post_message_stores_any_body(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
    body: str,
    expected: object,
) -> None:
    client.post('/', content=body.encode(), headers=write_auth)
    messages = client.get('/', headers=read_auth).json()['messages']
    assert [message['payload'] for message in messages] == [expected]


def test_get_messages_clear_after_deeply_nested_body(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    deep = '[' * 300 + ']' * 300
    client.post('/', json='before', headers=write_auth)
    client.post('/', content=deep.encode(), headers=write_auth)
    client.post('/', json='after', headers=write_auth)
    response = client.get('/?clear=true', headers=read_auth)
    assert response.status_code == HTTPStatus.OK
    payloads = [m['payload'] for m in response.json()['messages']]
    assert payloads == ['before', deep, 'after']


@pytest.mark.parametrize(
    ('path', 'inbox'),
    [
        ('/', '/'),
        ('/kitchen', '/kitchen'),
        ('/kitchen/', '/kitchen'),
        ('/home/desk', '/home/desk'),
        ('/Kitchen', '/Kitchen'),
        ('/docs', '/docs'),
        ('/openapi.json', '/openapi.json'),
    ],
)
def test_post_message_names_inbox_from_path(
    client: TestClient,
    write_auth: dict[str, str],
    path: str,
    inbox: str,
) -> None:
    response = client.post(path, json='x', headers=write_auth)
    assert response.json()['inbox'] == inbox


def test_get_messages_keeps_inboxes_apart(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    client.post('/kitchen', json='a', headers=write_auth)
    client.post('/', json='b', headers=write_auth)
    client.post('/kitchen/', json='c', headers=write_auth)
    kitchen = client.get('/kitchen', headers=read_auth).json()
    blank = client.get('/', headers=read_auth).json()
    assert [m['payload'] for m in kitchen['messages']] == ['a', 'c']
    assert [m['payload'] for m in blank['messages']] == ['b']


def test_get_messages_empty_inbox(
    client: TestClient,
    read_auth: dict[str, str],
) -> None:
    response = client.get('/nothing-here', headers=read_auth)
    assert response.json() == {
        'inbox': '/nothing-here',
        'more': False,
        'messages': [],
    }


def test_get_messages_limits_oldest_first(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    for number in range(5):
        client.post('/', json=number, headers=write_auth)
    body = client.get('/?limit=3', headers=read_auth).json()
    assert [m['payload'] for m in body['messages']] == [0, 1, 2]
    assert body['more'] is True


def test_get_messages_default_limit(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    for number in range(21):
        client.post('/', json=number, headers=write_auth)
    body = client.get('/', headers=read_auth).json()
    assert len(body['messages']) == 20
    assert body['more'] is True


def test_get_messages_without_clear_keeps_messages(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    client.post('/', json='a', headers=write_auth)
    client.get('/', headers=read_auth)
    body = client.get('/', headers=read_auth).json()
    assert [m['payload'] for m in body['messages']] == ['a']


def test_get_messages_clear_deletes_only_returned(
    client: TestClient,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    for number in range(3):
        client.post('/', json=number, headers=write_auth)
    first = client.get('/?limit=2&clear=true', headers=read_auth).json()
    second = client.get('/?clear=true', headers=read_auth).json()
    third = client.get('/', headers=read_auth).json()
    assert [m['payload'] for m in first['messages']] == [0, 1]
    assert first['more'] is True
    assert [m['payload'] for m in second['messages']] == [2]
    assert second['more'] is False
    assert third['messages'] == []


def test_get_messages_hides_expired(
    client: TestClient,
    clock: Clock,
    write_auth: dict[str, str],
    read_auth: dict[str, str],
) -> None:
    client.post('/', json='old', headers=write_auth)
    clock.now = NOW + timedelta(days=2)
    client.post('/', json='new', headers=write_auth)
    clock.now = NOW + timedelta(days=3, seconds=1)
    body = client.get('/', headers=read_auth).json()
    assert [m['payload'] for m in body['messages']] == ['new']


@pytest.mark.parametrize('limit', ['0', '101', 'many'])
def test_get_messages_rejects_bad_limit(
    client: TestClient,
    read_auth: dict[str, str],
    limit: str,
) -> None:
    response = client.get(f'/?limit={limit}', headers=read_auth)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_post_message_rejects_large_body(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.post(
        '/',
        content=b'x' * (MAX_BODY + 1),
        headers=write_auth,
    )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_post_message_accepts_body_at_limit(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.post('/', content=b'x' * MAX_BODY, headers=write_auth)
    assert response.status_code == HTTPStatus.CREATED


def test_post_message_rejects_non_utf8(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.post('/', content=b'\xff\xfe', headers=write_auth)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_post_message_rejects_long_inbox(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.post('/' + 'a' * MAX_INBOX, json=1, headers=write_auth)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_post_message_accepts_inbox_at_limit(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    path = '/' + 'a' * (MAX_INBOX - 1)
    response = client.post(path, json=1, headers=write_auth)
    assert response.status_code == HTTPStatus.CREATED


@pytest.mark.parametrize(
    'headers',
    [
        {},
        {'Authorization': 'Bearer nope'},
        {'Authorization': 'Bearer '},
        {'Authorization': 'Basic d3JpdGUtc2VjcmV0'},
        {'Authorization': 'write-secret'},
    ],
)
def test_post_message_unauthorised(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    response = client.post('/', json=1, headers=headers)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers['WWW-Authenticate'] == 'Bearer'


def test_get_messages_unauthorised(client: TestClient) -> None:
    response = client.get('/')
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_post_message_checks_key_before_body(client: TestClient) -> None:
    response = client.post('/', content=b'x' * (MAX_BODY + 1))
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_post_message_with_read_key_forbidden(
    client: TestClient,
    read_auth: dict[str, str],
) -> None:
    response = client.post('/', json=1, headers=read_auth)
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_get_messages_with_write_key_forbidden(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.get('/', headers=write_auth)
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_get_messages_bearer_scheme_case_insensitive(
    client: TestClient,
) -> None:
    response = client.get('/', headers={'Authorization': 'bearer read-secret'})
    assert response.status_code == HTTPStatus.OK


def test_app_other_methods_not_allowed(
    client: TestClient,
    write_auth: dict[str, str],
) -> None:
    response = client.put('/', json=1, headers=write_auth)
    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED

"""Shared test fixtures."""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from webhook.app import app, utc_now
from webhook.models import Message

WRITE_KEY: Final[str] = 'write-secret'
READ_KEY: Final[str] = 'read-secret'
NOW: Final[datetime] = datetime(2026, 11, 4, 10, 2, 11, 123456, tzinfo=UTC)


@dataclass
class Clock:
    """A settable stand-in for the current time."""

    now: datetime


@pytest.fixture
def _aws() -> Iterator[None]:
    """Mock DynamoDB with an empty table, and SSM holding both keys."""
    with mock_aws():
        Message.create_table(billing_mode='PAY_PER_REQUEST', wait=True)
        ssm = boto3.client('ssm')
        for name, value in (
            (os.environ['WRITE_KEY_PARAMETER'], WRITE_KEY),
            (os.environ['READ_KEY_PARAMETER'], READ_KEY),
        ):
            ssm.put_parameter(Name=name, Value=value, Type='SecureString')
        yield


@pytest.fixture
def clock() -> Clock:
    """Fixed current time, which a test may move."""
    return Clock(now=NOW)


@pytest.fixture
def client(_aws: None, clock: Clock) -> Iterator[TestClient]:
    """Test client whose clock reads from ``clock``."""
    app.dependency_overrides[utc_now] = lambda: clock.now
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def write_auth() -> dict[str, str]:
    """Headers carrying the write key."""
    return {'Authorization': f'Bearer {WRITE_KEY}'}


@pytest.fixture
def read_auth() -> dict[str, str]:
    """Headers carrying the read key."""
    return {'Authorization': f'Bearer {READ_KEY}'}

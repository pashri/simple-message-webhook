"""DynamoDB model for stored messages."""

import os

from pynamodb.attributes import (
    JSONAttribute,
    TTLAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from pynamodb.models import Model
from pynamodb_attributes import UUIDAttribute


class Message(Model):
    """
    A message waiting in an inbox.

    Items in an inbox sort by ``message_id``, a UUIDv7, so a query
    returns them oldest first. DynamoDB deletes expired items lazily,
    sometimes days late, so readers must also check ``expires_at``.
    A JSON ``null`` payload is stored as a missing attribute.
    """

    class Meta:  # pylint: disable=too-few-public-methods
        """Table settings."""

        table_name = os.environ['TABLE_NAME']
        region = os.environ['AWS_REGION']

    inbox = UnicodeAttribute(hash_key=True)
    message_id = UUIDAttribute(range_key=True, attr_name='id')
    received_at = UTCDateTimeAttribute()
    payload = JSONAttribute(null=True)
    expires_at = TTLAttribute()

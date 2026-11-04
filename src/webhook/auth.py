"""Bearer key checks for writing and reading."""

import hmac
import os
from collections.abc import Callable
from enum import StrEnum
from functools import cache
from http import HTTPStatus
from typing import Annotated, Final

from aws_lambda_powertools.utilities.parameters import SSMProvider
from fastapi import Header, HTTPException

KEY_MAX_AGE: Final[int] = 300  # seconds


class Access(StrEnum):
    """What a key allows."""

    WRITE = 'write'
    READ = 'read'


@cache
def ssm_provider() -> SSMProvider:
    """
    Build the shared SSM reader, which caches values.

    Returns
    -------
    SSMProvider
        The provider, created on first use.
    """
    return SSMProvider()


def current_keys() -> dict[Access, str]:
    """
    Read the write and read keys from SSM in one call.

    Values are cached for ``KEY_MAX_AGE``, so a rotated key takes
    effect within that time.

    Returns
    -------
    dict[Access, str]
        Each key, by the access it grants.
    """
    names = {
        Access.WRITE: os.environ['WRITE_KEY_PARAMETER'],
        Access.READ: os.environ['READ_KEY_PARAMETER'],
    }
    values = ssm_provider().get_parameters_by_name(
        parameters={name: {} for name in names.values()},
        decrypt=True,
        max_age=KEY_MAX_AGE,
    )
    return {access: str(values[name]) for access, name in names.items()}


def bearer_token(authorization: str | None) -> str | None:
    """
    Take the token from an ``Authorization: Bearer`` header.

    Parameters
    ----------
    authorization : str | None
        Header value, if any.

    Returns
    -------
    str | None
        The token, or None when the header is missing or not Bearer.
    """
    scheme, _, token = (authorization or '').partition(' ')
    if scheme.lower() != 'bearer':
        return None
    return token.strip() or None


def granted_access(token: str, keys: dict[Access, str]) -> set[Access]:
    """
    Find which keys a token matches, in constant time.

    Parameters
    ----------
    token : str
        Token from the request.
    keys : dict[Access, str]
        Configured keys.

    Returns
    -------
    set[Access]
        Access the token grants; empty when it matches no key.
    """
    return {
        access
        for access, key in keys.items()
        if hmac.compare_digest(token.encode(), key.encode())
    }


def require(access: Access) -> Callable[[str | None], None]:
    """
    Build a FastAPI dependency that demands a key.

    Parameters
    ----------
    access : Access
        Access the route needs.

    Returns
    -------
    Callable[[str | None], None]
        Dependency raising 401 for a missing or unknown key, and 403
        for a valid key of the other kind.
    """

    def check(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        """
        Check the request's key.

        Parameters
        ----------
        authorization : str | None
            ``Authorization`` header.

        Raises
        ------
        HTTPException
            401 or 403 when the key does not allow ``access``.
        """
        token = bearer_token(authorization=authorization)
        granted = (
            granted_access(token=token, keys=current_keys())
            if token
            else set()
        )
        if not granted:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail='Missing or invalid key',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        if access not in granted:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=f'This key cannot {access}',
            )

    return check

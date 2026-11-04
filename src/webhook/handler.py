"""Lambda entry point for the function URL."""

from typing import Any, Final, cast

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from mangum import Mangum
from mangum.types import LambdaContext as MangumContext

from webhook.app import app

logger = Logger()

ASGI: Final[Mangum] = Mangum(app=app, lifespan='off')


@logger.inject_lambda_context
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """
    Serve one function URL request.

    Parameters
    ----------
    event : dict[str, Any]
        Function URL event.
    context : LambdaContext
        Lambda runtime context.

    Returns
    -------
    dict[str, Any]
        Function URL response.
    """
    return dict(ASGI(event, cast(MangumContext, context)))

"""Every non-2xx response uses the contract's shape: {"error": {"code", "message"}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)

CODE_BY_STATUS = {
    400: "INVALID_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "DOCUMENT_NOT_READY",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_TYPE",
    422: "INVALID_REQUEST",
    429: "RATE_LIMITED",
    502: "UPSTREAM_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def error_response(
    status: int, message: str, *, code: str | None = None, headers: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code or CODE_BY_STATUS.get(status, "INTERNAL_ERROR"),
                "message": message,
            }
        },
        headers=headers,
    )


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "The request is invalid."
    first = errors[0]
    where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = str(first.get("msg", "is invalid"))
    return f"{where}: {message}" if where else message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        del request
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(exc.status_code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        return error_response(400, _validation_message(exc))

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        del request
        return error_response(400, str(exc))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error path=%s", request.url.path, exc_info=exc)
        return error_response(500, "Something went wrong on the server.")

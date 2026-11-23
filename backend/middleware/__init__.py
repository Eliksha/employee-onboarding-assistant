"""Middleware: request IDs, request logging, and friendly error responses."""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.logging_config import install_request_id_filter, request_id_var

logger = logging.getLogger("app")
install_request_id_filter(logger)

GENERIC_ERROR = "Something went wrong on our side. Please try again."


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Adds an X-Request-ID header, logs every request, and turns crashes into clean JSON 500s."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("request_id=%s unhandled error on %s %s", request_id, request.method, request.url.path)
                response = JSONResponse(status_code=500, content={"detail": GENERIC_ERROR, "request_id": request_id})
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = request_id
            logger.info("request_id=%s %s %s -> %s in %.0f ms", request_id, request.method, request.url.path, response.status_code, elapsed_ms)
            return response
        finally:
            request_id_var.reset(token)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    if first.get("type") == "json_invalid":
        detail = "Invalid input: request body is not valid JSON"
    else:
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = str(first.get("msg", "invalid value")).replace("Value error, ", "")
        detail = f"Invalid input ({field}): {message}" if field else f"Invalid input: {message}"
    logger.warning("request_id=%s validation failed: %s", getattr(request.state, "request_id", "-"), detail)
    return JSONResponse(status_code=422, content={"detail": detail})


DATABASE_TIMEOUT = "The database took too long to respond. Please try again."


async def query_timeout_handler(request: Request, exc: Exception):
    # No SQL text or parameters in the log or the response.
    logger.warning("request_id=%s database query timed out on %s %s",
                   getattr(request.state, "request_id", "-"), request.method, request.url.path)
    return JSONResponse(status_code=503, content={"detail": DATABASE_TIMEOUT}, headers={"Retry-After": "5"})


def install(app: FastAPI) -> None:
    from backend.services.readonly_query import QueryTimeoutError

    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(QueryTimeoutError, query_timeout_handler)

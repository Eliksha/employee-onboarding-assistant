"""Middleware: request IDs, request logging, and friendly error responses."""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app")

GENERIC_ERROR = "Something went wrong on our side. Please try again."


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Adds an X-Request-ID header, logs every request, and turns crashes into clean JSON 500s."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_id=%s unhandled error on %s %s", request_id, request.method, request.url.path)
            response = JSONResponse(status_code=500, content={"detail": GENERIC_ERROR, "request_id": request_id})
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info("request_id=%s %s %s -> %s in %.0f ms", request_id, request.method, request.url.path, response.status_code, elapsed_ms)
        return response


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    message = str(first.get("msg", "invalid value")).replace("Value error, ", "")
    detail = f"Invalid input ({field}): {message}" if field else f"Invalid input: {message}"
    logger.warning("request_id=%s validation failed: %s", getattr(request.state, "request_id", "-"), detail)
    return JSONResponse(status_code=422, content={"detail": detail})


def install(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

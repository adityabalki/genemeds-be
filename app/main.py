from __future__ import annotations

import logging
import time
import json

from fastapi import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from app.config import get_settings
from app.logging_config import configure_logging
from app.routers.auth import router as auth_router
from app.schemas import HealthResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled_exception",
            extra={"method": request.method, "path": request.url.path},
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request_complete",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response


@app.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


_mangum_handler = Mangum(app, api_gateway_base_path="/v2")


def handler(event, context):
    request_context = event.get("requestContext") or {}
    request_id = request_context.get("requestId")
    http_ctx = request_context.get("http") or {}
    path = event.get("rawPath") or http_ctx.get("path")
    method = http_ctx.get("method")

    logger.info(
        "lambda_invoke",
        extra={
            "apigw_request_id": request_id,
            "routeKey": event.get("routeKey"),
            "method": method,
            "path": path,
            "stage": request_context.get("stage"),
        },
    )

    try:
        response = _mangum_handler(event, context)
    except Exception:
        logger.exception("lambda_handler_error", extra={"apigw_request_id": request_id})
        raise

    logger.info("raw_mangum_response", extra={
    "response": response,
    "statusCode": response.get("statusCode"),
    "headers": response.get("headers"),
    "isBase64Encoded": response.get("isBase64Encoded"),
    "body_type": type(response.get("body")).__name__,
    "body_length": len(response.get("body", "") or ""),
    "body_preview": (response.get("body") or "")[:200],
    })

    # Defensive normalization: API Gateway requires a strict "Lambda proxy" shape.
    # If something returns a non-string body or non-serializable headers, API Gateway
    # may respond with 5xx even though the app ran.
    if isinstance(response, dict):
        if "statusCode" in response and not isinstance(response["statusCode"], int):
            try:
                response["statusCode"] = int(response["statusCode"])
            except Exception:
                response["statusCode"] = 502

        headers = response.get("headers")
        if isinstance(headers, dict):
            safe_headers: dict[str, str] = {}
            for key, value in headers.items():
                if value is None:
                    continue
                safe_headers[str(key)] = str(value)
            response["headers"] = safe_headers

    logger.info(
        "lambda_response",
        extra={
            "apigw_request_id": request_id,
            "statusCode": response.get("statusCode"),
            "response_keys": sorted(response.keys()) if isinstance(response, dict) else None,
        },
    )
    return response
from __future__ import annotations

import math
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


async def json_safe_request_validation_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = jsonable_encoder(exc.errors())
    return JSONResponse(status_code=422, content={"detail": _json_safe(errors)})

from __future__ import annotations

from fastapi.responses import JSONResponse

from aigateway.contracts import AuthenticationError, AuthorizationError


def error_body(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def json_error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(code, detail))


def register_exception_handlers(app) -> None:
    @app.exception_handler(AuthenticationError)
    async def _unauthenticated(_, exc: AuthenticationError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(AuthorizationError)
    async def _forbidden(_, exc: AuthorizationError) -> JSONResponse:
        return json_error(exc.status_code, exc.code, exc.detail)

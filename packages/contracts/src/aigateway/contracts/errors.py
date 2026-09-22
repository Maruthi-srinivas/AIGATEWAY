class AuthenticationError(Exception):
    """Raised when credentials are missing or invalid (HTTP 401)."""

    def __init__(
        self,
        detail: str = "unauthenticated",
        code: str = "unauthenticated",
    ) -> None:
        self.detail = detail
        self.code = code
        self.status_code = 401
        super().__init__(detail)


class AuthorizationError(Exception):
    """Raised when the caller is authenticated but not allowed (HTTP 403)."""

    def __init__(
        self,
        detail: str = "forbidden",
        code: str = "forbidden",
    ) -> None:
        self.detail = detail
        self.code = code
        self.status_code = 403
        super().__init__(detail)


class ValidationFailedError(Exception):
    """Raised for schema or semantic request errors (HTTP 400)."""

    def __init__(
        self,
        detail: str = "invalid request",
        code: str = "validation_error",
    ) -> None:
        self.detail = detail
        self.code = code
        self.status_code = 400
        super().__init__(detail)


class PayloadTooLargeError(Exception):
    def __init__(self, detail: str = "payload too large") -> None:
        self.detail = detail
        self.code = "payload_too_large"
        self.status_code = 400
        super().__init__(detail)


class ConversationNotFoundError(Exception):
    def __init__(self, detail: str = "conversation not found") -> None:
        self.detail = detail
        self.code = "conversation_not_found"
        self.status_code = 404
        super().__init__(detail)


class RateLimitedError(Exception):
    def __init__(
        self,
        detail: str = "rate limited",
        *,
        retry_after: int = 1,
        limit: int = 0,
        remaining: int = 0,
        reset_at: int = 0,
    ) -> None:
        self.detail = detail
        self.code = "rate_limited"
        self.status_code = 429
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        super().__init__(detail)


class RateLimiterUnavailableError(Exception):
    def __init__(self, detail: str = "rate limiter unavailable") -> None:
        self.detail = detail
        self.code = "rate_limiter_unavailable"
        self.status_code = 503
        super().__init__(detail)

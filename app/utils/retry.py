"""
app/utils/retry.py — Retry decorator for external API calls.

Wraps a function so it automatically retries on transient network errors
or specific HTTP status codes.  Used by payment_service and
notification_service to make Paystack / OneSignal calls more resilient.

Usage:
    from app.utils.retry import with_retry

    @with_retry(max_attempts=3, backoff=0.5)
    def call_paystack():
        ...

    # Or inline:
    result = with_retry(max_attempts=2)(some_function)(arg1, arg2)
"""

import time
import functools
from typing import Callable, Tuple, Type, Any
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Transient errors that are safe to retry
_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Import requests exceptions lazily to avoid hard dependency at import time
def _get_retryable_exceptions():
    try:
        import requests.exceptions as req_exc
        return _RETRYABLE_EXCEPTIONS + (
            req_exc.ConnectionError,
            req_exc.Timeout,
            req_exc.ChunkedEncodingError,
        )
    except ImportError:
        return _RETRYABLE_EXCEPTIONS


def with_retry(
    max_attempts: int = 3,
    backoff: float = 0.5,
    backoff_multiplier: float = 2.0,
    retryable_statuses: Tuple[int, ...] = (429, 500, 502, 503, 504),
) -> Callable:
    """
    Decorator factory that retries the wrapped function on transient failures.

    Args:
        max_attempts:      Total number of attempts (1 = no retry).
        backoff:           Initial wait in seconds between attempts.
        backoff_multiplier: Each retry multiplies the wait by this factor.
        retryable_statuses: HTTP status codes that trigger a retry (when the
                            wrapped function returns a requests.Response).

    The decorator transparently propagates the final exception if all
    attempts fail, so callers keep their existing error handling.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retryable = _get_retryable_exceptions()
            delay = backoff
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = fn(*args, **kwargs)

                    # If the result is a requests.Response, check status code
                    try:
                        import requests
                        if isinstance(result, requests.Response) and result.status_code in retryable_statuses:
                            if attempt < max_attempts:
                                logger.warning(
                                    "Retryable HTTP %s from %s (attempt %d/%d) — retrying in %.1fs",
                                    result.status_code, fn.__name__, attempt, max_attempts, delay,
                                )
                                time.sleep(delay)
                                delay *= backoff_multiplier
                                continue
                    except ImportError:
                        pass

                    return result

                except retryable as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        logger.warning(
                            "%s raised %s (attempt %d/%d) — retrying in %.1fs",
                            fn.__name__, type(exc).__name__, attempt, max_attempts, delay,
                        )
                        time.sleep(delay)
                        delay *= backoff_multiplier
                    else:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            fn.__name__, max_attempts, exc,
                        )
                        raise

            # Should not be reached, but guard just in case
            if last_exc:
                raise last_exc

        return wrapper
    return decorator

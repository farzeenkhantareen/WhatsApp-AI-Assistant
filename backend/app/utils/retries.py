"""Retry helpers built on tenacity."""

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


def async_retryable(
    *,
    attempts: int = 3,
    min_wait: float = 0.5,
    max_wait: float = 8.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
):
    """Decorator factory for async HTTP client retries."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
    )

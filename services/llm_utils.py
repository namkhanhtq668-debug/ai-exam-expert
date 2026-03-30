from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable, TypeVar


T = TypeVar("T")


def call_with_timeout(
    func: Callable[[], T],
    *,
    timeout: int | float,
    fallback: T,
    on_error: Callable[[Exception], None] | None = None,
) -> T:
    if timeout is None or timeout <= 0:
        try:
            return func()
        except Exception as exc:  # pragma: no cover - fallback path
            if on_error:
                on_error(exc)
            return fallback

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        if on_error:
            on_error(exc)
        future.cancel()
        return fallback
    except Exception as exc:
        if on_error:
            on_error(exc)
        future.cancel()
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

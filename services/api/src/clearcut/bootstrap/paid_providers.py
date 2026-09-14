"""Paid provider enablement and concurrency bounding gate."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import threading
from collections import deque
from collections.abc import Mapping, Set
from typing import Any

from clearcut.bootstrap.settings import ClearcutSettings

DEFAULT_CONCURRENCY_LIMITS: dict[str, int] = {
    "parallel": 5,
    "gemini": 5,
    "bedrock": 5,
}

_ACTIVE_PERMIT_CONTEXT: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "_ACTIVE_PERMIT_CONTEXT", default=frozenset()
)


class PaidProviderError(RuntimeError):
    """Base exception for paid provider governance errors."""


class PaidProviderDisabledError(PaidProviderError):
    """Raised when an action attempts to call a paid provider that is not explicitly enabled."""


class PaidProviderConcurrencyError(PaidProviderError):
    """Raised when paid provider concurrency limits are exceeded."""


class ConcurrencyLimitExceededError(PaidProviderConcurrencyError):
    """Raised when the concurrency limit for a paid provider is exceeded and non-blocking acquisition fails."""


class NestedPermitAcquisitionError(PaidProviderConcurrencyError):
    """Raised when an execution context attempts to acquire a permit while already holding one."""


class _SyncWaiter:
    """Waiter node for synchronous threads."""

    __slots__ = ("cancelled", "event")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.cancelled = False


class _AsyncWaiter:
    """Waiter node for asynchronous tasks."""

    __slots__ = ("cancelled", "future", "loop", "granted")

    def __init__(self, loop: asyncio.AbstractEventLoop, future: asyncio.Future[None]) -> None:
        self.loop = loop
        self.future = future
        self.cancelled = False
        self.granted = False


def _safe_fulfill_future(future: asyncio.Future[None]) -> None:
    if not future.done():
        with contextlib.suppress(asyncio.InvalidStateError, RuntimeError):
            future.set_result(None)


class _SharedPermitPool:
    """Threadsafe permit pool shared across synchronous and asynchronous callers."""

    def __init__(self, provider: str, limit: int, lock: threading.Lock) -> None:
        self.provider = provider
        self.limit = limit
        self.available = limit
        self.active = 0
        self._lock = lock
        self._waiters: deque[_SyncWaiter | _AsyncWaiter] = deque()

    def acquire_sync(self, timeout: float | None = None) -> bool:
        with self._lock:
            if self.available > 0:
                self.available -= 1
                self.active += 1
                return True
            waiter = _SyncWaiter()
            self._waiters.append(waiter)

        signaled = waiter.event.wait(timeout=timeout if timeout is not None and timeout >= 0 else None)
        if signaled:
            return True

        with self._lock:
            if waiter.event.is_set():
                # Race: permit was granted right as timeout fired
                return True
            waiter.cancelled = True
            with contextlib.suppress(ValueError):
                self._waiters.remove(waiter)
            return False

    async def acquire_async(self, timeout: float | None = None) -> bool:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self.available > 0:
                self.available -= 1
                self.active += 1
                return True
            future: asyncio.Future[None] = loop.create_future()
            waiter = _AsyncWaiter(loop=loop, future=future)
            self._waiters.append(waiter)

        try:
            if timeout is not None:
                await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            else:
                await future
            return True
        except (TimeoutError, asyncio.CancelledError) as err:
            with self._lock:
                waiter.cancelled = True
                if waiter.granted:
                    # Permit was granted in race window before or during cancellation/timeout;
                    # release it back to pool to prevent permit leak.
                    self.release_locked()
                else:
                    with contextlib.suppress(ValueError):
                        self._waiters.remove(waiter)
                if isinstance(err, TimeoutError):
                    return False
                raise

    def release(self) -> None:
        with self._lock:
            self.release_locked()

    def release_locked(self) -> None:
        self.active = max(0, self.active - 1)
        while self._waiters:
            waiter = self._waiters.popleft()
            if waiter.cancelled:
                continue
            if isinstance(waiter, _SyncWaiter):
                self.active += 1
                waiter.event.set()
                return
            if isinstance(waiter, _AsyncWaiter):
                if waiter.future.done():
                    continue
                try:
                    self.active += 1
                    waiter.granted = True
                    waiter.loop.call_soon_threadsafe(_safe_fulfill_future, waiter.future)
                    return
                except RuntimeError:
                    self.active = max(0, self.active - 1)
                    waiter.granted = False
                    continue
        self.available = min(self.limit, self.available + 1)


class _ProviderLeaseContext:
    """Unified sync and async context manager for paid provider concurrency gating."""

    def __init__(
        self,
        gate: PaidProviderGate,
        provider: str,
        timeout: float | None = None,
        *,
        allow_nested: bool = True,
    ) -> None:
        self._gate = gate
        self._provider = provider.lower()
        self._timeout = timeout
        self._allow_nested = allow_nested
        self._acquired = False
        self._token: contextvars.Token[frozenset[str]] | None = None

    def __enter__(self) -> _ProviderLeaseContext:
        if not self._gate.is_enabled(self._provider):
            raise PaidProviderDisabledError(
                f"Paid provider '{self._provider}' is not enabled in settings."
            )
        current = _ACTIVE_PERMIT_CONTEXT.get()
        if not self._allow_nested and current:
            raise NestedPermitAcquisitionError(
                f"Cannot acquire permit for '{self._provider}' while already holding permit(s) for "
                f"{sorted(current)}. Permits must only be held during inference."
            )
        pool = self._gate._get_pool(self._provider)
        acquired = pool.acquire_sync(timeout=self._timeout)
        if not acquired:
            raise PaidProviderConcurrencyError(
                f"Concurrency limit exceeded for paid provider '{self._provider}'."
            )
        self._acquired = True
        self._token = _ACTIVE_PERMIT_CONTEXT.set(current | {self._provider})
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._acquired:
            self._acquired = False
            if self._token is not None:
                _ACTIVE_PERMIT_CONTEXT.reset(self._token)
                self._token = None
            pool = self._gate._get_pool(self._provider)
            pool.release()

    async def __aenter__(self) -> _ProviderLeaseContext:
        if not self._gate.is_enabled(self._provider):
            raise PaidProviderDisabledError(
                f"Paid provider '{self._provider}' is not enabled in settings."
            )
        current = _ACTIVE_PERMIT_CONTEXT.get()
        if not self._allow_nested and current:
            raise NestedPermitAcquisitionError(
                f"Cannot acquire permit for '{self._provider}' while already holding permit(s) for "
                f"{sorted(current)}. Permits must only be held during inference."
            )
        pool = self._gate._get_pool(self._provider)
        acquired = await pool.acquire_async(timeout=self._timeout)
        if not acquired:
            raise PaidProviderConcurrencyError(
                f"Concurrency limit exceeded for paid provider '{self._provider}'."
            )
        self._acquired = True
        self._token = _ACTIVE_PERMIT_CONTEXT.set(current | {self._provider})
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._acquired:
            self._acquired = False
            if self._token is not None:
                _ACTIVE_PERMIT_CONTEXT.reset(self._token)
                self._token = None
            pool = self._gate._get_pool(self._provider)
            pool.release()


class PaidProviderGate:
    """Enforces explicit enablement and bounded concurrency for paid external providers."""

    def __init__(
        self,
        enabled_providers: Set[str] | None = None,
        concurrency_limits: Mapping[str, int] | None = None,
    ) -> None:
        self._enabled_providers = frozenset(
            p.lower() for p in (enabled_providers or ())
        )
        limits = dict(DEFAULT_CONCURRENCY_LIMITS)
        if concurrency_limits:
            for k, v in concurrency_limits.items():
                limits[k.lower()] = v
        for provider, limit in limits.items():
            if limit <= 0:
                raise ValueError(
                    f"Concurrency limit for provider '{provider}' must be positive, got {limit}."
                )
        self._limits = limits
        self._lock = threading.Lock()
        self._pools: dict[str, _SharedPermitPool] = {}

    def is_enabled(self, provider: str) -> bool:
        return provider.lower() in self._enabled_providers

    def concurrency_limit(self, provider: str) -> int:
        return self._limits.get(provider.lower(), 5)

    def active_count(self, provider: str) -> int:
        with self._lock:
            pool = self._pools.get(provider.lower())
            return pool.active if pool is not None else 0

    def available_count(self, provider: str) -> int:
        with self._lock:
            pool = self._get_pool_locked(provider.lower())
            return pool.available

    def _get_pool(self, provider: str) -> _SharedPermitPool:
        with self._lock:
            return self._get_pool_locked(provider.lower())

    def _get_pool_locked(self, key: str) -> _SharedPermitPool:
        if key not in self._pools:
            limit = self._limits.get(key, 5)
            self._pools[key] = _SharedPermitPool(key, limit, self._lock)
        return self._pools[key]

    def acquire(
        self,
        provider: str,
        timeout: float | None = None,
        *,
        allow_nested: bool = True,
    ) -> _ProviderLeaseContext:
        """Acquire a bounded permit for the given paid provider; denies by default if disabled."""
        return _ProviderLeaseContext(
            self, provider, timeout=timeout, allow_nested=allow_nested
        )

    def acquire_sync(
        self,
        provider: str,
        timeout: float | None = None,
        *,
        allow_nested: bool = True,
    ) -> _ProviderLeaseContext:
        """Explicit synchronous context manager."""
        return _ProviderLeaseContext(
            self, provider, timeout=timeout, allow_nested=allow_nested
        )


def build_paid_provider_gate(
    settings: ClearcutSettings | None = None,
    *,
    enabled_providers: Set[str] | None = None,
    concurrency_limits: Mapping[str, int] | None = None,
) -> PaidProviderGate:
    """Construct a PaidProviderGate from settings or explicit parameters."""
    limits: dict[str, int] | None
    if settings is not None:
        providers = settings.paid_providers_enabled
        limits = {
            str(provider): limit
            for provider, limit in settings.paid_provider_concurrency_limits.items()
        }
    else:
        providers = frozenset(enabled_providers or ())
        limits = dict(concurrency_limits) if concurrency_limits is not None else None
    return PaidProviderGate(enabled_providers=providers, concurrency_limits=limits)

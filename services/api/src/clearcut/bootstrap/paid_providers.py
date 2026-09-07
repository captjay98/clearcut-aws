"""Paid provider enablement and concurrency bounding gate."""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Set
from typing import Any

from clearcut.bootstrap.settings import ClearcutSettings

DEFAULT_CONCURRENCY_LIMITS: dict[str, int] = {
    "parallel": 5,
    "gemini": 5,
}


class PaidProviderError(RuntimeError):
    """Base exception for paid provider governance errors."""


class PaidProviderDisabledError(PaidProviderError):
    """Raised when an action attempts to call a paid provider that is not explicitly enabled."""


class PaidProviderConcurrencyError(PaidProviderError):
    """Raised when paid provider concurrency limits are exceeded."""


class _ProviderLeaseContext:
    """Unified sync and async context manager for paid provider concurrency gating."""

    def __init__(self, gate: PaidProviderGate, provider: str, timeout: float | None = None) -> None:
        self._gate = gate
        self._provider = provider
        self._timeout = timeout
        self._sync_acquired = False
        self._async_acquired = False

    def __enter__(self) -> _ProviderLeaseContext:
        if not self._gate.is_enabled(self._provider):
            raise PaidProviderDisabledError(
                f"Paid provider '{self._provider}' is not enabled in settings."
            )
        sem = self._gate._get_sync_semaphore(self._provider)
        acquired = sem.acquire(timeout=self._timeout if self._timeout is not None else -1)
        if not acquired:
            raise PaidProviderConcurrencyError(
                f"Concurrency limit exceeded for paid provider '{self._provider}'."
            )
        self._sync_acquired = True
        self._gate._increment_active(self._provider)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._sync_acquired:
            self._sync_acquired = False
            self._gate._decrement_active(self._provider)
            sem = self._gate._get_sync_semaphore(self._provider)
            sem.release()

    async def __aenter__(self) -> _ProviderLeaseContext:
        if not self._gate.is_enabled(self._provider):
            raise PaidProviderDisabledError(
                f"Paid provider '{self._provider}' is not enabled in settings."
            )
        sem = self._gate._get_async_semaphore(self._provider)
        if self._timeout is not None:
            try:
                await asyncio.wait_for(sem.acquire(), timeout=self._timeout)
            except TimeoutError:
                raise PaidProviderConcurrencyError(
                    f"Concurrency limit exceeded for paid provider '{self._provider}'."
                ) from None
        else:
            await sem.acquire()
        self._async_acquired = True
        self._gate._increment_active(self._provider)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._async_acquired:
            self._async_acquired = False
            self._gate._decrement_active(self._provider)
            sem = self._gate._get_async_semaphore(self._provider)
            sem.release()


class PaidProviderGate:
    """Enforces explicit enablement and bounded concurrency for paid external providers."""

    def __init__(
        self,
        enabled_providers: Set[str] | None = None,
        concurrency_limits: dict[str, int] | None = None,
    ) -> None:
        self._enabled_providers = frozenset(enabled_providers or ())
        limits = dict(DEFAULT_CONCURRENCY_LIMITS)
        if concurrency_limits:
            limits.update(concurrency_limits)
        for provider, limit in limits.items():
            if limit <= 0:
                raise ValueError(
                    f"Concurrency limit for provider '{provider}' must be positive, got {limit}."
                )
        self._limits = limits
        self._lock = threading.Lock()
        self._sync_semaphores: dict[str, threading.Semaphore] = {}
        self._async_semaphores: dict[str, asyncio.Semaphore] = {}
        self._active_counts: dict[str, int] = {}

    def is_enabled(self, provider: str) -> bool:
        return provider.lower() in self._enabled_providers

    def concurrency_limit(self, provider: str) -> int:
        return self._limits.get(provider.lower(), 5)

    def active_count(self, provider: str) -> int:
        with self._lock:
            return self._active_counts.get(provider.lower(), 0)

    def _increment_active(self, provider: str) -> None:
        with self._lock:
            key = provider.lower()
            self._active_counts[key] = self._active_counts.get(key, 0) + 1

    def _decrement_active(self, provider: str) -> None:
        with self._lock:
            key = provider.lower()
            current = self._active_counts.get(key, 0)
            self._active_counts[key] = max(0, current - 1)

    def _get_sync_semaphore(self, provider: str) -> threading.Semaphore:
        key = provider.lower()
        with self._lock:
            if key not in self._sync_semaphores:
                limit = self._limits.get(key, 5)
                self._sync_semaphores[key] = threading.Semaphore(limit)
            return self._sync_semaphores[key]

    def _get_async_semaphore(self, provider: str) -> asyncio.Semaphore:
        key = provider.lower()
        with self._lock:
            if key not in self._async_semaphores:
                limit = self._limits.get(key, 5)
                self._async_semaphores[key] = asyncio.Semaphore(limit)
            return self._async_semaphores[key]

    def acquire(self, provider: str, timeout: float | None = None) -> _ProviderLeaseContext:
        """Acquire a bounded permit for the given paid provider; denies by default if disabled."""
        return _ProviderLeaseContext(self, provider, timeout=timeout)


def build_paid_provider_gate(
    settings: ClearcutSettings | None = None,
    *,
    enabled_providers: Set[str] | None = None,
    concurrency_limits: dict[str, int] | None = None,
) -> PaidProviderGate:
    """Construct a PaidProviderGate from settings or explicit parameters."""
    if settings is not None:
        providers = settings.paid_providers_enabled
    else:
        providers = frozenset(enabled_providers or ())
    return PaidProviderGate(enabled_providers=providers, concurrency_limits=concurrency_limits)

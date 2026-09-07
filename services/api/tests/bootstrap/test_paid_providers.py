"""Paid provider enablement and concurrency control conformance."""
from __future__ import annotations

import asyncio
import contextlib

import pytest
from clearcut.bootstrap.paid_providers import (
    PaidProviderDisabledError,
    PaidProviderGate,
    build_paid_provider_gate,
)
from clearcut.bootstrap.settings import ClearcutSettings


class FakePaidClient:
    """Mock client tracking invocations to prove zero calls when disabled."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "result"

    async def async_call(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "async_result"


def test_default_denial_for_unenabled_providers() -> None:
    gate = build_paid_provider_gate(enabled_providers=frozenset())
    assert isinstance(gate, PaidProviderGate)
    assert not gate.is_enabled("parallel")
    assert not gate.is_enabled("gemini")

    fake_client = FakePaidClient()

    with pytest.raises(PaidProviderDisabledError) as exc_info, gate.acquire("parallel"):
        fake_client.call(query="test")

    assert "parallel" in str(exc_info.value)
    assert fake_client.calls == []
    assert gate.active_count("parallel") == 0


@pytest.mark.asyncio
async def test_async_default_denial_for_unenabled_providers() -> None:
    gate = build_paid_provider_gate(enabled_providers=frozenset())
    fake_client = FakePaidClient()

    with pytest.raises(PaidProviderDisabledError):
        async with gate.acquire("gemini"):
            await fake_client.async_call(prompt="test")

    assert fake_client.calls == []
    assert gate.active_count("gemini") == 0


@pytest.mark.parametrize("limit", [0, -1, -10])
def test_non_positive_concurrency_limit_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        PaidProviderGate(
            enabled_providers=frozenset({"parallel"}),
            concurrency_limits={"parallel": limit},
        )


def test_sync_concurrency_bounding_and_release_on_exception() -> None:
    gate = PaidProviderGate(
        enabled_providers=frozenset({"parallel"}),
        concurrency_limits={"parallel": 2},
    )
    fake_client = FakePaidClient()

    with gate.acquire("parallel"):
        assert gate.active_count("parallel") == 1
        with gate.acquire("parallel"):
            assert gate.active_count("parallel") == 2
            fake_client.call(op="1")

    assert gate.active_count("parallel") == 0
    assert len(fake_client.calls) == 1

    # Exception inside block releases permit
    with pytest.raises(RuntimeError), gate.acquire("parallel"):
        assert gate.active_count("parallel") == 1
        raise RuntimeError("simulated error")

    assert gate.active_count("parallel") == 0


@pytest.mark.asyncio
async def test_async_concurrency_bounding_and_release_on_cancellation() -> None:
    gate = PaidProviderGate(
        enabled_providers=frozenset({"gemini"}),
        concurrency_limits={"gemini": 1},
    )

    acquired_event = asyncio.Event()
    release_event = asyncio.Event()

    async def worker():
        async with gate.acquire("gemini"):
            acquired_event.set()
            await release_event.wait()

    task = asyncio.create_task(worker())
    await acquired_event.wait()
    assert gate.active_count("gemini") == 1

    # Second acquire will wait; we cancel the first task
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert gate.active_count("gemini") == 0

    # New acquisition can succeed now
    async with gate.acquire("gemini"):
        assert gate.active_count("gemini") == 1

    assert gate.active_count("gemini") == 0


def test_gate_from_settings_factory() -> None:
    settings = ClearcutSettings.model_validate(
        {
            "profile": "local",
            "database": {"url": "sqlite+aiosqlite:////tmp/cc-test.db"},
            "storage": {"path": "/tmp/cc-storage"},
            "paid_providers_enabled": ["parallel"],
        }
    )
    gate = build_paid_provider_gate(settings=settings)
    assert gate.is_enabled("parallel")
    assert not gate.is_enabled("gemini")

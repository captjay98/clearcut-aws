"""Paid provider enablement and concurrency control conformance."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

import pytest
from clearcut.bootstrap.paid_providers import (
    DEFAULT_CONCURRENCY_LIMITS,
    NestedPermitAcquisitionError,
    PaidProviderConcurrencyError,
    PaidProviderDisabledError,
    PaidProviderGate,
    build_paid_provider_gate,
)
from clearcut.bootstrap.settings import ClearcutSettings
from clearcut.main import _ConfiguredDetectionRuntime, _ConfiguredResearchRuntime
from pydantic import ValidationError


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
            "paid_provider_cost_acknowledged": True,
            "paid_provider_concurrency_limits": {"parallel": 1, "gemini": 2},
        }
    )
    gate = build_paid_provider_gate(settings=settings)
    assert gate.is_enabled("parallel")
    assert not gate.is_enabled("gemini")
    assert gate.concurrency_limit("parallel") == 1
    assert gate.concurrency_limit("gemini") == 2


def test_enabled_provider_requires_cost_acknowledgement() -> None:
    with pytest.raises(ValidationError, match="cost acknowledgement"):
        ClearcutSettings.model_validate(
            {
                "profile": "local",
                "database": {"url": "sqlite+aiosqlite:////tmp/cc-test.db"},
                "storage": {"path": "/tmp/cc-storage"},
                "paid_providers_enabled": ["parallel"],
            }
        )


@pytest.mark.asyncio
async def test_runtime_boundaries_deny_before_resolving_paid_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved: list[str] = []
    monkeypatch.setattr(
        "clearcut.main.get_detection_runtime",
        lambda: resolved.append("gemini"),
    )
    monkeypatch.setattr(
        "clearcut.main.get_research_runtime",
        lambda: resolved.append("parallel"),
    )
    gate = build_paid_provider_gate(enabled_providers=frozenset())

    with pytest.raises(PaidProviderDisabledError):
        await _ConfiguredDetectionRuntime(gate).detect_element(cast(Any, object()))
    with pytest.raises(PaidProviderDisabledError):
        _ConfiguredResearchRuntime(gate).search(cast(Any, object()))

    assert resolved == []


def test_default_concurrency_limits_includes_bedrock() -> None:
    assert "bedrock" in DEFAULT_CONCURRENCY_LIMITS
    assert DEFAULT_CONCURRENCY_LIMITS["bedrock"] == 5


@pytest.mark.asyncio
async def test_cross_context_sync_async_mutual_exclusion() -> None:
    gate = PaidProviderGate(
        enabled_providers=frozenset({"bedrock"}),
        concurrency_limits={"bedrock": 1},
    )
    fake_client = FakePaidClient()

    async with gate.acquire("bedrock"):
        assert gate.active_count("bedrock") == 1

        # Synchronous acquisition from thread must time out and fail
        def try_sync_acquire() -> None:
            with pytest.raises(PaidProviderConcurrencyError), gate.acquire_sync("bedrock", timeout=0.05):
                fake_client.call(op="sync_during_async")

        await asyncio.to_thread(try_sync_acquire)

    assert gate.active_count("bedrock") == 0

    # Conversely: acquire in sync thread, async acquire must time out
    def hold_sync(held_event, release_event) -> None:
        with gate.acquire_sync("bedrock"):
            held_event.set()
            release_event.wait(timeout=2.0)

    import threading

    held = threading.Event()
    release = threading.Event()
    thread = threading.Thread(target=hold_sync, args=(held, release))
    thread.start()

    await asyncio.to_thread(held.wait)
    assert gate.active_count("bedrock") == 1

    with pytest.raises(PaidProviderConcurrencyError):
        async with gate.acquire("bedrock", timeout=0.05):
            await fake_client.async_call(op="async_during_sync")

    release.set()
    await asyncio.to_thread(thread.join)
    assert gate.active_count("bedrock") == 0


@pytest.mark.asyncio
async def test_mixed_sync_async_concurrency_limit_enforced() -> None:
    import threading
    import time

    limit = 3
    gate = PaidProviderGate(
        enabled_providers=frozenset({"bedrock"}),
        concurrency_limits={"bedrock": limit},
    )

    peak_lock = threading.Lock()
    peak_active = 0

    def update_peak():
        nonlocal peak_active
        with peak_lock:
            cur = gate.active_count("bedrock")
            if cur > peak_active:
                peak_active = cur
            assert cur <= limit

    async def async_worker():
        async with gate.acquire("bedrock"):
            update_peak()
            await asyncio.sleep(0.01)

    def sync_worker():
        with gate.acquire_sync("bedrock"):
            update_peak()
            time.sleep(0.01)

    async_tasks = [asyncio.create_task(async_worker()) for _ in range(15)]
    sync_tasks = [asyncio.to_thread(sync_worker) for _ in range(15)]

    await asyncio.gather(*async_tasks, *sync_tasks)
    assert peak_active <= limit
    assert gate.active_count("bedrock") == 0
    assert gate.available_count("bedrock") == limit


@pytest.mark.asyncio
async def test_async_cancellation_while_waiting_does_not_leak_permit() -> None:
    gate = PaidProviderGate(
        enabled_providers=frozenset({"bedrock"}),
        concurrency_limits={"bedrock": 1},
    )

    started = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with gate.acquire("bedrock"):
            started.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await started.wait()
    assert gate.active_count("bedrock") == 1
    assert gate.available_count("bedrock") == 0

    # Waiter task starts waiting
    waiter_started = asyncio.Event()

    async def waiter():
        waiter_started.set()
        async with gate.acquire("bedrock"):
            pass

    waiter_task = asyncio.create_task(waiter())
    await waiter_started.wait()
    await asyncio.sleep(0.01)

    # Cancel waiter while it is in the queue
    waiter_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await waiter_task

    # Release the holder permit
    release.set()
    await holder_task

    # Permit must not leak: active=0, available=1
    assert gate.active_count("bedrock") == 0
    assert gate.available_count("bedrock") == 1

    # Next caller can acquire cleanly
    async with gate.acquire("bedrock"):
        assert gate.active_count("bedrock") == 1
    assert gate.active_count("bedrock") == 0


def test_nested_acquisition_prevention_when_disallowed() -> None:
    gate = PaidProviderGate(
        enabled_providers=frozenset({"bedrock"}),
        concurrency_limits={"bedrock": 2},
    )

    with (
        gate.acquire("bedrock", allow_nested=False),
        pytest.raises(NestedPermitAcquisitionError),
        gate.acquire("bedrock", allow_nested=False),
    ):
        pass


@pytest.mark.asyncio
async def test_requested_model_property_does_not_acquire_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockRuntime:
        @property
        def requested_model(self) -> str:
            return "anthropic.claude-3-5-sonnet-20241022-v2:0"

    monkeypatch.setattr(
        "clearcut.bootstrap.runtime.get_detection_runtime",
        lambda: MockRuntime(),
    )
    # Even with provider disabled in gate, property read does not acquire permit or fail
    disabled_gate = build_paid_provider_gate(enabled_providers=frozenset())
    configured = _ConfiguredDetectionRuntime(disabled_gate, model_provider="bedrock")

    # Accessing requested_model property must succeed without permit error
    model_name = configured.requested_model
    assert model_name == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert disabled_gate.active_count("bedrock") == 0


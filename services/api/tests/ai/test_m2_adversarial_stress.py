"""Adversarial stress tests for Milestone M2 concurrency and budget enforcement.

Stress-tests:
1. _SharedPermitPool / PaidProviderGate under high concurrency (mixed sync threads + async tasks).
2. Cancellation and timeout injection with zero permit leakage.
3. Nested permit acquisition failure and deadlock freedom.
4. JobBudgetTracker concurrency, exact boundary crossings, and state serialization fidelity.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import json
import threading
import time

import pytest
from clearcut.ai.budgets import BudgetExceededError, JobBudget, JobBudgetTracker
from clearcut.bootstrap.paid_providers import (
    NestedPermitAcquisitionError,
    PaidProviderConcurrencyError,
    PaidProviderGate,
    _SharedPermitPool,
)


class TestConcurrencyPermitPoolStress:
    """Stress tests for _SharedPermitPool and PaidProviderGate."""

    def test_mixed_sync_and_async_concurrency_bounds(self) -> None:
        """50+ mixed sync threads and async tasks competing for 2 permits.

        Invariants tested:
        1. At no point in time does active concurrency exceed the configured limit (2).
        2. All competing callers eventually acquire and complete (no starvation/deadlock).
        3. Upon completion, active permits == 0 and available permits == limit (2).
        """
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock"}),
            concurrency_limits={"bedrock": 2},
        )

        concurrent_count = 0
        max_concurrent_seen = 0
        counter_lock = threading.Lock()
        completed_sync = 0
        completed_async = 0

        def sync_worker(worker_id: int) -> None:
            nonlocal concurrent_count, max_concurrent_seen, completed_sync
            with gate.acquire_sync("bedrock", timeout=10.0):
                with counter_lock:
                    concurrent_count += 1
                    if concurrent_count > max_concurrent_seen:
                        max_concurrent_seen = concurrent_count
                    assert concurrent_count <= 2, f"Active count exceeded limit: {concurrent_count}"
                time.sleep(0.005)
                with counter_lock:
                    concurrent_count -= 1
                    completed_sync += 1

        async def async_worker(worker_id: int) -> None:
            nonlocal concurrent_count, max_concurrent_seen, completed_async
            async with gate.acquire("bedrock", timeout=10.0):
                with counter_lock:
                    concurrent_count += 1
                    if concurrent_count > max_concurrent_seen:
                        max_concurrent_seen = concurrent_count
                    assert concurrent_count <= 2, f"Active count exceeded limit: {concurrent_count}"
                await asyncio.sleep(0.005)
                with counter_lock:
                    concurrent_count -= 1
                    completed_async += 1

        def run_async_event_loop(task_count: int) -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tasks = [async_worker(i) for i in range(task_count)]
                loop.run_until_complete(asyncio.gather(*tasks))
            finally:
                loop.close()

        num_sync = 30
        num_async = 30

        # Launch async tasks inside a dedicated thread running an event loop,
        # plus synchronous threads competing simultaneously.
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_sync + 1) as executor:
            async_future = executor.submit(run_async_event_loop, num_async)
            sync_futures = [executor.submit(sync_worker, i) for i in range(num_sync)]

            for f in sync_futures:
                f.result(timeout=15.0)
            async_future.result(timeout=15.0)

        assert completed_sync == num_sync
        assert completed_async == num_async
        assert max_concurrent_seen <= 2
        assert max_concurrent_seen > 0
        assert gate.active_count("bedrock") == 0
        assert gate.available_count("bedrock") == 2

    @pytest.mark.asyncio
    async def test_rapid_async_cancellations_zero_permit_leak(self) -> None:
        """Rapid cancellations injected into waiting async tasks must never leak permits."""
        limit = 2
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock"}),
            concurrency_limits={"bedrock": limit},
        )

        rounds = 25
        for r in range(rounds):
            # Step 1: Saturate the pool
            ctx1 = gate.acquire("bedrock")
            ctx2 = gate.acquire("bedrock")
            await ctx1.__aenter__()
            await ctx2.__aenter__()
            assert gate.active_count("bedrock") == 2
            assert gate.available_count("bedrock") == 0

            # Step 2: Queue 15 waiting tasks
            waiting_tasks: list[asyncio.Task[None]] = []

            async def waiter(idx: int) -> None:
                async with gate.acquire("bedrock"):
                    await asyncio.sleep(0.001)

            for i in range(15):
                waiting_tasks.append(asyncio.create_task(waiter(i)))

            # Allow tasks to hit the waiting queue
            await asyncio.sleep(0.005)

            # Step 3: Rapidly cancel all waiting tasks
            for t in waiting_tasks:
                t.cancel()

            # Step 4: Simultaneously release the active permits
            await ctx1.__aexit__(None, None, None)
            await ctx2.__aexit__(None, None, None)

            # Step 5: Gather cancelled tasks
            for t in waiting_tasks:
                with pytest.raises((asyncio.CancelledError, Exception)):
                    await t

            # Allow event loop to process callbacks
            await asyncio.sleep(0.01)

            # INVARIANT: Zero permit leak!
            assert gate.active_count("bedrock") == 0, (
                f"Round {r}: Permit leak detected in active_count! Expected 0, got {gate.active_count('bedrock')}"
            )
            assert gate.available_count("bedrock") == limit, (
                f"Round {r}: Permit leak detected in available_count! Expected {limit}, got {gate.available_count('bedrock')}"
            )

    @pytest.mark.asyncio
    async def test_async_timeout_injection_zero_permit_leak(self) -> None:
        """Timeouts injected into waiting async tasks must return permits with zero leak."""
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock"}),
            concurrency_limits={"bedrock": 1},
        )

        # Holder task holds permit for 100ms
        async with gate.acquire("bedrock"):
            assert gate.active_count("bedrock") == 1

            # 10 tasks attempt to acquire with a 10ms timeout
            async def timed_waiter() -> bool:
                try:
                    async with gate.acquire("bedrock", timeout=0.01):
                        return True
                except PaidProviderConcurrencyError:
                    return False

            results = await asyncio.gather(*(timed_waiter() for _ in range(10)))
            assert all(res is False for res in results)

        # Holder has released
        await asyncio.sleep(0.01)
        assert gate.active_count("bedrock") == 0
        assert gate.available_count("bedrock") == 1

        # Clean acquisition by next caller
        async with gate.acquire("bedrock"):
            assert gate.active_count("bedrock") == 1
        assert gate.active_count("bedrock") == 0

    def test_sync_timeout_injection_zero_permit_leak(self) -> None:
        """Timeouts in sync threads must not leak permits."""
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock"}),
            concurrency_limits={"bedrock": 1},
        )

        with gate.acquire_sync("bedrock"):
            assert gate.active_count("bedrock") == 1

            def sync_timed_waiter() -> bool:
                try:
                    with gate.acquire_sync("bedrock", timeout=0.02):
                        return True
                except PaidProviderConcurrencyError:
                    return False

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(sync_timed_waiter) for _ in range(8)]
                results = [f.result() for f in futures]
                assert all(res is False for res in results)

        assert gate.active_count("bedrock") == 0
        assert gate.available_count("bedrock") == 1

        # Clean acquisition succeeds immediately
        with gate.acquire_sync("bedrock"):
            assert gate.active_count("bedrock") == 1
        assert gate.active_count("bedrock") == 0

    def test_nested_permit_acquisition_fails_immediately_without_deadlock(self) -> None:
        """Attempting to acquire while already holding a permit fails with NestedPermitAcquisitionError."""
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock", "parallel"}),
            concurrency_limits={"bedrock": 2, "parallel": 2},
        )

        # 1. Sync nested acquisition failure
        with gate.acquire_sync("bedrock", allow_nested=False):
            assert gate.active_count("bedrock") == 1
            t0 = time.perf_counter()
            with (
                pytest.raises(NestedPermitAcquisitionError) as exc_info,
                gate.acquire_sync("bedrock", allow_nested=False),
            ):
                pass
            t_elapsed = time.perf_counter() - t0
            assert t_elapsed < 0.1, f"Nested acquire hung for {t_elapsed}s"
            assert "already holding permit" in str(exc_info.value)
            # Outer permit still held intact
            assert gate.active_count("bedrock") == 1

        assert gate.active_count("bedrock") == 0
        assert gate.available_count("bedrock") == 2

    @pytest.mark.asyncio
    async def test_async_nested_permit_acquisition_fails_immediately_without_deadlock(self) -> None:
        """Async nested acquisition fails immediately without hanging."""
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock", "parallel"}),
            concurrency_limits={"bedrock": 2, "parallel": 2},
        )

        async with gate.acquire("bedrock", allow_nested=False):
            assert gate.active_count("bedrock") == 1
            t0 = time.perf_counter()
            with pytest.raises(NestedPermitAcquisitionError) as exc_info:
                async with gate.acquire("bedrock", allow_nested=False):
                    pass
            t_elapsed = time.perf_counter() - t0
            assert t_elapsed < 0.1, f"Nested acquire hung for {t_elapsed}s"
            assert "already holding permit" in str(exc_info.value)
            assert gate.active_count("bedrock") == 1

        assert gate.active_count("bedrock") == 0
        assert gate.available_count("bedrock") == 2

    def test_cross_provider_nested_acquisition_fails_when_disallowed(self) -> None:
        """Holding 'parallel' and trying to acquire 'bedrock' with allow_nested=False fails."""
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock", "parallel"}),
            concurrency_limits={"bedrock": 2, "parallel": 2},
        )

        with (
            gate.acquire_sync("parallel", allow_nested=False),
            pytest.raises(NestedPermitAcquisitionError),
            gate.acquire_sync("bedrock", allow_nested=False),
        ):
            pass
            assert gate.active_count("parallel") == 1
            assert gate.active_count("bedrock") == 0

        assert gate.active_count("parallel") == 0


class TestJobBudgetTrackerStress:
    """Stress tests for JobBudgetTracker boundary crossings, concurrency, and serialization."""

    def test_all_budget_boundary_exact_and_crossings(self) -> None:
        """Exact boundary (limit == consumed) is permitted; limit + 1 raises BudgetExceededError."""
        # 1. Model calls
        tracker = JobBudgetTracker(JobBudget(max_model_calls=3))
        for _ in range(3):
            tracker.record_model_call(input_tokens=10, output_tokens=10)
        assert tracker.model_calls == 3

        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.record_model_call(input_tokens=1, output_tokens=1)
        assert exc_info.value.resource == "model_calls"
        assert exc_info.value.limit == 3
        assert exc_info.value.consumed == 4

        # 2. Input tokens
        tracker = JobBudgetTracker(JobBudget(max_input_tokens=100))
        tracker.record_model_call(input_tokens=100)
        assert tracker.input_tokens == 100
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_model_call(input_tokens=1)
        assert exc.value.resource == "input_tokens"
        assert exc.value.limit == 100
        assert exc.value.consumed == 101

        # 3. Output tokens
        tracker = JobBudgetTracker(JobBudget(max_output_tokens=50))
        tracker.record_model_call(output_tokens=50)
        assert tracker.output_tokens == 50
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_model_call(output_tokens=1)
        assert exc.value.resource == "output_tokens"
        assert exc.value.limit == 50
        assert exc.value.consumed == 51

        # 4. Total tokens
        tracker = JobBudgetTracker(JobBudget(max_total_tokens=200))
        tracker.record_model_call(input_tokens=100, output_tokens=100)
        assert tracker.total_tokens == 200
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_model_call(total_tokens=1)
        assert exc.value.resource == "total_tokens"

        # 5. Tool calls
        tracker = JobBudgetTracker(JobBudget(max_tool_calls=2))
        tracker.record_tool_call()
        tracker.record_tool_call()
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_tool_call()
        assert exc.value.resource == "tool_calls"

        # 6. Search calls
        tracker = JobBudgetTracker(JobBudget(max_search_calls=2))
        tracker.record_search_call()
        tracker.record_search_call()
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_search_call()
        assert exc.value.resource == "search_calls"

        # 7. Extract calls
        tracker = JobBudgetTracker(JobBudget(max_extract_calls=2))
        tracker.record_extract_call()
        tracker.record_extract_call()
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_extract_call()
        assert exc.value.resource == "extract_calls"

        # 8. Repairs
        tracker = JobBudgetTracker(JobBudget(max_repairs=2))
        tracker.record_repair()
        tracker.record_repair()
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_repair()
        assert exc.value.resource == "repairs"

        # 9. Elapsed seconds
        tracker = JobBudgetTracker(JobBudget(max_elapsed_seconds=1.5))
        tracker.record_elapsed_seconds(1.5)
        assert tracker.elapsed_seconds == 1.5
        with pytest.raises(BudgetExceededError) as exc:
            tracker.record_elapsed_seconds(0.1)
        assert exc.value.resource == "elapsed_seconds"
        assert exc.value.limit == 1.5
        assert exc.value.consumed == 1.6

    def test_serialization_roundtrip_fidelity(self) -> None:
        """to_dict and from_dict preserve exact consumption state across job persistence."""
        budget = JobBudget(
            max_model_calls=10,
            max_input_tokens=5000,
            max_output_tokens=2000,
            max_total_tokens=7000,
            max_tool_calls=20,
            max_search_calls=5,
            max_extract_calls=10,
            max_elapsed_seconds=60.0,
            max_repairs=3,
        )
        tracker = JobBudgetTracker(budget)
        tracker.record_model_call(input_tokens=150, output_tokens=50, total_tokens=200)
        tracker.record_search_call()
        tracker.record_extract_call()
        tracker.record_repair()
        tracker.record_elapsed_seconds(12.34)

        # Serialize
        serialized = tracker.to_dict()

        # Validate JSON compatibility
        json_str = json.dumps(serialized)
        restored_dict = json.loads(json_str)

        # Restore from dict
        restored_tracker = JobBudgetTracker.from_dict(budget, restored_dict)

        assert restored_tracker.model_calls == 1
        assert restored_tracker.input_tokens == 150
        assert restored_tracker.output_tokens == 50
        assert restored_tracker.total_tokens == 200
        assert restored_tracker.tool_calls == 2  # 1 search + 1 extract
        assert restored_tracker.search_calls == 1
        assert restored_tracker.extract_calls == 1
        assert restored_tracker.repairs == 1
        assert abs(restored_tracker.elapsed_seconds - 12.34) < 1e-6

        # Enforce budget continuing from restored counters
        # We used 1 search call out of max 5. 4 more should succeed, 5th must fail.
        for _ in range(4):
            restored_tracker.record_search_call()
        assert restored_tracker.search_calls == 5

        with pytest.raises(BudgetExceededError) as exc:
            restored_tracker.record_search_call()
        assert exc.value.resource == "search_calls"
        assert exc.value.limit == 5
        assert exc.value.consumed == 6

    def test_concurrent_multithreaded_updates(self) -> None:
        """Concurrent calls to record methods from multiple threads accumulate without error."""
        budget = JobBudget(
            max_model_calls=10000,
            max_input_tokens=100000,
            max_output_tokens=100000,
            max_total_tokens=200000,
            max_tool_calls=10000,
        )
        tracker = JobBudgetTracker(budget)

        num_threads = 10
        calls_per_thread = 50

        def worker() -> None:
            for _ in range(calls_per_thread):
                tracker.record_model_call(input_tokens=5, output_tokens=5, total_tokens=10)
                tracker.record_tool_call()
                tracker.record_elapsed_seconds(0.01)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for f in futures:
                f.result(timeout=5.0)

        # Check total values accumulated
        expected_calls = num_threads * calls_per_thread
        assert tracker.model_calls == expected_calls
        assert tracker.tool_calls == expected_calls
        assert tracker.input_tokens == expected_calls * 5
        assert tracker.output_tokens == expected_calls * 5
        assert tracker.total_tokens == expected_calls * 10
        assert abs(tracker.elapsed_seconds - (expected_calls * 0.01)) < 1e-4

    def test_budget_monotonicity_and_serialization_invariant(self) -> None:
        """Property: Budget tracker counters are strictly monotonic, and serialization is isomorphic."""
        import random

        rng = random.Random(42)
        budget = JobBudget(max_total_tokens=100000, max_model_calls=1000)
        tracker = JobBudgetTracker(budget)

        prev_state = tracker.to_dict()

        for _ in range(100):
            in_tok = rng.randint(0, 100)
            out_tok = rng.randint(0, 100)
            tracker.record_model_call(input_tokens=in_tok, output_tokens=out_tok)
            if rng.random() > 0.5:
                tracker.record_tool_call()
            if rng.random() > 0.7:
                tracker.record_search_call()
            if rng.random() > 0.7:
                tracker.record_extract_call()
            if rng.random() > 0.9:
                tracker.record_repair()
            tracker.record_elapsed_seconds(rng.uniform(0.01, 0.5))

            curr_state = tracker.to_dict()

            # Monotonicity check across all metrics
            for key, val in curr_state.items():
                assert val >= prev_state[key], f"Metric {key} decreased: {val} < {prev_state[key]}"

            # Serialization round-trip isomorphism
            restored = JobBudgetTracker.from_dict(budget, curr_state)
            restored_dict = restored.to_dict()
            assert restored_dict == curr_state, f"Mismatch in restored state: {restored_dict} != {curr_state}"

            prev_state = curr_state


class TestAdversarialPermitInvariants:
    """Randomized property tests for permit pool invariant preservation."""

    @pytest.mark.asyncio
    async def test_randomized_cancellation_fuzzing(self) -> None:
        """Fuzz cancellation timing against permit releases across multiple random delays."""
        import random

        rng = random.Random(1337)
        limit = 3
        gate = PaidProviderGate(
            enabled_providers=frozenset({"bedrock"}),
            concurrency_limits={"bedrock": limit},
        )

        rounds = 20
        for r in range(rounds):
            tasks: list[asyncio.Task[bool]] = []

            async def contestant(cid: int) -> bool:
                try:
                    async with gate.acquire("bedrock", timeout=0.1):
                        # Random hold duration
                        await asyncio.sleep(rng.uniform(0.001, 0.01))
                        return True
                except (PaidProviderConcurrencyError, asyncio.CancelledError):
                    return False

            # Launch 20 contestants
            for i in range(20):
                tasks.append(asyncio.create_task(contestant(i)))

            # Randomly cancel a subset of tasks after varying tiny delays
            for t in tasks:
                if rng.random() > 0.5:
                    await asyncio.sleep(rng.uniform(0.0001, 0.003))
                    t.cancel()

            # Wait for all tasks to complete or handle cancellation
            results = await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.01)

            pool = gate._get_pool("bedrock")
            if gate.active_count("bedrock") != 0 or gate.available_count("bedrock") != limit:
                print(f"\n[DIAGNOSTIC] Round {r}: active={pool.active}, available={pool.available}, waiters={len(pool._waiters)}")
                for i, res in enumerate(results):
                    print(f"  task {i}: res={type(res).__name__ if isinstance(res, Exception) else res}")
                for i, w in enumerate(pool._waiters):
                    print(f"  waiter {i}: cancelled={w.cancelled}, done={w.future.done()}")

            # Invariant: All permits MUST be restored, active MUST be 0
            assert gate.active_count("bedrock") == 0, (
                f"Fuzz round {r}: Leaked active permits: {gate.active_count('bedrock')}"
            )
            assert gate.available_count("bedrock") == limit, (
                f"Fuzz round {r}: Available permits not restored: {gate.available_count('bedrock')} != {limit}"
            )

    @pytest.mark.asyncio
    async def test_deterministic_cancelled_waiter_with_timeout_permit_leak(self) -> None:
        """Deterministic reproduction of permit leak when a timed-out/cancelled async waiter

        races with permit release.
        Trigger: A waiting task with timeout is cancelled while queued in _waiters.
        Before the event loop runs the task's cancellation handler, release_locked() runs,
        pops the waiter, increments self.active, and schedules _safe_fulfill_future via call_soon_threadsafe.
        When the task's cancellation handler runs, future.done() is False because call_soon_threadsafe
        has not executed yet.
        The task takes the `if not future.done():` branch, removing the waiter (which is a no-op
        because it was already popped), and never calls release_locked().
        The active permit is permanently leaked.
        """
        import threading

        from clearcut.bootstrap.paid_providers import _SharedPermitPool

        lock = threading.Lock()
        pool = _SharedPermitPool("bedrock", 1, lock)

        # Holder acquires the only permit
        assert pool.acquire_sync() is True
        assert pool.active == 1
        assert pool.available == 0

        # Waiter task starts acquire with a timeout (wrapping future with shield)
        task = asyncio.create_task(pool.acquire_async(timeout=0.5))
        await asyncio.sleep(0)  # Yield to allow task to append waiter to pool._waiters
        assert len(pool._waiters) == 1

        # Cancel the task while it is waiting in _waiters
        task.cancel()

        # In the same event loop step, holder releases the permit
        with lock:
            pool.release_locked()

        # Await task cancellation
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Allow any queued callbacks to settle
        await asyncio.sleep(0.01)

        # Invariant check: Pool MUST return to 0 active and 1 available.
        # If bug is present, active == 1 and available == 0 (pool permanently bricked).
        assert pool.active == 0, f"PERMIT LEAK BUG: pool.active is {pool.active}, expected 0"
        assert pool.available == 1, f"PERMIT LEAK BUG: pool.available is {pool.available}, expected 1"

    @pytest.mark.asyncio
    async def test_high_concurrency_cancellation_fuzzing_100_rounds(self) -> None:
        """Adversarial stress: 100 rounds of randomized high-concurrency cancellations & timeouts.

        Across each round:
        - 25 concurrent tasks compete for varying capacity (1, 2, or 3 permits).
        - Random delays, random timeouts (from 1ms to 30ms), and random cancellation points.
        - Verifies that pool.active returns to 0 and pool.available returns to limit EVERY single round.
        - Verifies that after cancellation, a new acquisition succeeds immediately without hang.
        """
        import random

        rng = random.Random(20260914)
        rounds = 100

        for r in range(rounds):
            limit = (r % 3) + 1  # Limits: 1, 2, 3
            gate = PaidProviderGate(
                enabled_providers=frozenset({"bedrock"}),
                concurrency_limits={"bedrock": limit},
            )
            pool = gate._get_pool("bedrock")

            num_contestants = 25
            tasks: list[asyncio.Task[bool]] = []

            async def contestant(cid: int, current_gate: PaidProviderGate = gate) -> bool:
                timeout = rng.choice([None, 0.005, 0.01, 0.02])
                try:
                    async with current_gate.acquire("bedrock", timeout=timeout):
                        await asyncio.sleep(rng.uniform(0.0005, 0.002))
                        return True
                except (PaidProviderConcurrencyError, asyncio.CancelledError):
                    return False

            for i in range(num_contestants):
                tasks.append(asyncio.create_task(contestant(i)))

            # Randomly cancel a large fraction of tasks at various intervals
            for t in tasks:
                if rng.random() > 0.3:
                    await asyncio.sleep(rng.uniform(0.0001, 0.001))
                    t.cancel()

            # Await all contestants
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.005)

            # Assert invariants
            assert pool.active == 0, f"Round {r} (limit={limit}): Leaked active permits: {pool.active}"
            assert pool.available == limit, (
                f"Round {r} (limit={limit}): Available count incorrect: {pool.available} != {limit}"
            )
            assert len(pool._waiters) == 0, f"Round {r}: Lingering waiters: {len(pool._waiters)}"

            # Fresh acquisition must succeed immediately
            assert pool.acquire_sync(timeout=0.1) is True
            pool.release()
            assert pool.active == 0
            assert pool.available == limit

    def test_mixed_threads_and_async_heavy_cancellation_stress(self) -> None:
        """Stress: 25 rounds of mixed synchronous threads and asynchronous tasks competing

        for a shared permit pool with rapid cancellation and timeouts.
        """
        import random

        rng = random.Random(4242)
        rounds = 25

        for r in range(rounds):
            limit = 2
            gate = PaidProviderGate(
                enabled_providers=frozenset({"bedrock"}),
                concurrency_limits={"bedrock": limit},
            )
            pool = gate._get_pool("bedrock")

            num_sync = 8
            num_async = 15

            def sync_worker(wid: int, current_gate: PaidProviderGate = gate) -> bool:
                try:
                    with current_gate.acquire_sync("bedrock", timeout=rng.uniform(0.005, 0.02)):
                        time.sleep(rng.uniform(0.001, 0.003))
                        return True
                except PaidProviderConcurrencyError:
                    return False

            async def async_worker(wid: int, current_gate: PaidProviderGate = gate) -> bool:
                try:
                    async with current_gate.acquire("bedrock", timeout=rng.uniform(0.005, 0.02)):
                        await asyncio.sleep(rng.uniform(0.001, 0.003))
                        return True
                except (PaidProviderConcurrencyError, asyncio.CancelledError):
                    return False

            def run_async_loop(task_count: int = num_async) -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    tasks = [asyncio.ensure_future(async_worker(i), loop=loop) for i in range(task_count)]
                    for t in tasks:
                        if rng.random() > 0.5:
                            loop.call_later(rng.uniform(0.001, 0.005), t.cancel)
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_sync + 1) as executor:
                async_future = executor.submit(run_async_loop)
                sync_futures = [executor.submit(sync_worker, i) for i in range(num_sync)]

                for f in sync_futures:
                    f.result(timeout=5.0)
                async_future.result(timeout=5.0)

            assert pool.active == 0, f"Mixed round {r}: Leaked active: {pool.active}"
            assert pool.available == limit, f"Mixed round {r}: Available mismatch: {pool.available}"
            assert len(pool._waiters) == 0, f"Mixed round {r}: Leftover waiters: {len(pool._waiters)}"

    def test_closed_event_loop_waiter_rollback(self) -> None:
        """If an async waiter's event loop is closed before permit grant,

        release_locked rolls back active count and awards permit to next valid waiter.
        """
        from clearcut.bootstrap.paid_providers import _AsyncWaiter, _SharedPermitPool, _SyncWaiter

        lock = threading.Lock()
        pool = _SharedPermitPool("bedrock", 1, lock)

        # Saturate pool
        assert pool.acquire_sync() is True
        assert pool.active == 1
        assert pool.available == 0

        # Create loop, enqueue waiter, then close loop
        dead_loop = asyncio.new_event_loop()
        future: asyncio.Future[None] = dead_loop.create_future()
        dead_waiter = _AsyncWaiter(loop=dead_loop, future=future)
        pool._waiters.append(dead_waiter)
        dead_loop.close()

        # Enqueue second valid sync waiter
        valid_waiter = _SyncWaiter()
        pool._waiters.append(valid_waiter)

        # Release the active permit
        with lock:
            pool.release_locked()

        # Invariant: The dead waiter could not accept the permit (RuntimeError),
        # so active was rolled back and the permit was passed to the valid waiter!
        assert valid_waiter.event.is_set() is True
        assert pool.active == 1
        assert pool.available == 0

        # Release the permit held by the valid waiter
        with lock:
            pool.release_locked()

        assert pool.active == 0
        assert pool.available == 1


class TestExtremeConcurrencyAndIEEE754Fuzzing:
    """Adversarial stress and fuzz tests covering IEEE 754 edge cases and extreme concurrency."""

    def test_50_threads_10k_mixed_calls_zero_lost_updates_zero_permit_leak(self) -> None:
        """50 concurrent threads execute 10,000 mixed operations across JobBudgetTracker

        and _SharedPermitPool simultaneously.
        Verifies:
        1. Zero lost updates: Every recorded call, token, cost increment, and elapsed second
           is accounted for exactly.
        2. Zero state corruption: All internal state remains fully coherent and strictly monotonic.
        3. Zero permit leaks: Active permits return to 0, available permits return to limit,
           and waiter queue is completely drained.
        """
        permit_limit = 5
        lock = threading.Lock()
        pool = _SharedPermitPool("stress_provider", permit_limit, lock)

        budget = JobBudget(
            max_model_calls=1_000_000,
            max_input_tokens=10_000_000,
            max_output_tokens=10_000_000,
            max_total_tokens=20_000_000,
            max_tool_calls=1_000_000,
            max_search_calls=1_000_000,
            max_extract_calls=1_000_000,
            max_repairs=1_000_000,
            max_elapsed_seconds=100_000.0,
            max_cost_usd=100_000.0,
        )
        tracker = JobBudgetTracker(budget)

        num_threads = 50
        calls_per_thread = 200  # Exactly 10,000 mixed calls total

        # Track expected counts per thread to verify zero lost updates
        thread_stats: list[dict[str, float]] = [
            {
                "model_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "tool_calls": 0,
                "search_calls": 0,
                "extract_calls": 0,
                "repairs": 0,
                "elapsed_seconds": 0.0,
                "cost_usd": 0.0,
                "permits_acquired": 0,
            }
            for _ in range(num_threads)
        ]

        def worker(tid: int) -> None:
            stats = thread_stats[tid]
            for i in range(calls_per_thread):
                op = (tid + i) % 8
                if op == 0:
                    in_t = 10 + (i % 5)
                    out_t = 5 + (i % 3)
                    c = 0.001
                    tracker.record_model_call(
                        input_tokens=in_t,
                        output_tokens=out_t,
                        cost_usd=c,
                    )
                    stats["model_calls"] += 1
                    stats["input_tokens"] += in_t
                    stats["output_tokens"] += out_t
                    stats["total_tokens"] += (in_t + out_t)
                    stats["cost_usd"] += c
                elif op == 1:
                    tracker.record_tool_call()
                    stats["tool_calls"] += 1
                elif op == 2:
                    tracker.record_search_call()
                    stats["tool_calls"] += 1
                    stats["search_calls"] += 1
                elif op == 3:
                    tracker.record_extract_call()
                    stats["tool_calls"] += 1
                    stats["extract_calls"] += 1
                elif op == 4:
                    tracker.record_repair()
                    stats["repairs"] += 1
                elif op == 5:
                    c = 0.0025
                    tracker.record_cost(c)
                    stats["cost_usd"] += c
                elif op == 6:
                    sec = 0.001
                    tracker.record_elapsed_seconds(sec)
                    stats["elapsed_seconds"] += sec
                elif op == 7:
                    # Concurrently acquire and release permit from pool
                    acquired = pool.acquire_sync(timeout=5.0)
                    if acquired:
                        try:
                            stats["permits_acquired"] += 1
                        finally:
                            pool.release()

        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, tid) for tid in range(num_threads)]
            for f in futures:
                f.result(timeout=10.0)
        t_duration = time.perf_counter() - t0
        assert t_duration > 0.0

        # Sum expected stats across all 50 threads
        expected_model_calls = sum(s["model_calls"] for s in thread_stats)
        expected_input_tokens = sum(s["input_tokens"] for s in thread_stats)
        expected_output_tokens = sum(s["output_tokens"] for s in thread_stats)
        expected_total_tokens = sum(s["total_tokens"] for s in thread_stats)
        expected_tool_calls = sum(s["tool_calls"] for s in thread_stats)
        expected_search_calls = sum(s["search_calls"] for s in thread_stats)
        expected_extract_calls = sum(s["extract_calls"] for s in thread_stats)
        expected_repairs = sum(s["repairs"] for s in thread_stats)
        expected_elapsed_seconds = sum(s["elapsed_seconds"] for s in thread_stats)
        expected_cost_usd = sum(s["cost_usd"] for s in thread_stats)
        total_permits_acquired = sum(s["permits_acquired"] for s in thread_stats)

        # 1. Verify ZERO LOST UPDATES in JobBudgetTracker
        assert tracker.model_calls == expected_model_calls
        assert tracker.input_tokens == expected_input_tokens
        assert tracker.output_tokens == expected_output_tokens
        assert tracker.total_tokens == expected_total_tokens
        assert tracker.tool_calls == expected_tool_calls
        assert tracker.search_calls == expected_search_calls
        assert tracker.extract_calls == expected_extract_calls
        assert tracker.repairs == expected_repairs
        assert abs(tracker.elapsed_seconds - expected_elapsed_seconds) < 1e-4
        assert abs(tracker.cost_usd - expected_cost_usd) < 1e-4

        # 2. Verify ZERO STATE CORRUPTION & strict serialization roundtrip
        state = tracker.to_dict()
        assert state["model_calls"] == expected_model_calls
        assert state["tool_calls"] == expected_tool_calls
        serialized = json.dumps(state, allow_nan=False)
        restored = JobBudgetTracker.from_dict(budget, json.loads(serialized))
        assert restored.model_calls == tracker.model_calls
        assert restored.total_tokens == tracker.total_tokens
        assert abs(restored.cost_usd - tracker.cost_usd) < 1e-6

        # 3. Verify ZERO PERMIT LEAKS in _SharedPermitPool
        assert total_permits_acquired > 0
        assert pool.active == 0, f"Leaked active permits: {pool.active}"
        assert pool.available == permit_limit, f"Leaked available permits: {pool.available} != {permit_limit}"
        assert len(pool._waiters) == 0, f"Lingering waiters: {len(pool._waiters)}"

        # 4. Verify immediate clean re-acquisition
        assert pool.acquire_sync(timeout=0.1) is True
        pool.release()
        assert pool.active == 0
        assert pool.available == permit_limit

    def test_ieee754_extreme_floating_point_fuzzing(self) -> None:
        """Adversarial testing of IEEE 754 floating point boundary values:

        - float("-inf"): strictly rejected with ValueError across all fields & methods.
        - float("inf"): unbounded in budget limit, strictly bounded when consumed against finite limit.
        - -0.0: accepted as non-negative (>= 0), behaves identically to 0.0.
        - 1e308, 1e-308, 5e-324 (subnormal): handled without overflow or underflow crashes.
        """
        all_budget_fields = [
            "max_model_calls",
            "max_tokens",
            "max_input_tokens",
            "max_output_tokens",
            "max_total_tokens",
            "max_tool_calls",
            "max_search_calls",
            "max_extract_calls",
            "max_elapsed_seconds",
            "max_repairs",
            "max_cost_usd",
        ]

        # 1. float("-inf") MUST BE REJECTED with ValueError across all 11 fields
        for field in all_budget_fields:
            with pytest.raises(ValueError) as exc_info:
                JobBudget(**{field: float("-inf")})
            assert "must be non-negative" in str(exc_info.value)
            assert field in str(exc_info.value)

        # 2. float("-inf") MUST BE REJECTED in all JobBudgetTracker methods
        budget = JobBudget(max_cost_usd=100.0, max_elapsed_seconds=100.0)
        t = JobBudgetTracker(budget)

        with pytest.raises(ValueError, match="cost_usd must be non-negative"):
            JobBudgetTracker(budget, cost_usd=float("-inf"))

        with pytest.raises(ValueError, match="elapsed_seconds must be non-negative"):
            JobBudgetTracker(budget, elapsed_seconds=float("-inf"))

        with pytest.raises(ValueError, match="Cost amount must be non-negative"):
            t.record_cost(float("-inf"))

        with pytest.raises(ValueError, match="cost_usd must be non-negative"):
            t.record_model_call(cost_usd=float("-inf"))

        with pytest.raises(ValueError, match="seconds must be non-negative"):
            t.record_elapsed_seconds(float("-inf"))

        with pytest.raises(ValueError, match="cost_usd must be non-negative"):
            JobBudgetTracker.from_dict(budget, {"cost_usd": float("-inf")})

        with pytest.raises(ValueError, match="elapsed_seconds must be non-negative"):
            JobBudgetTracker.from_dict(budget, {"elapsed_seconds": float("-inf")})

        # 3. -0.0 MUST BE ACCEPTED as non-negative (>= 0)
        b_neg_zero = JobBudget(max_cost_usd=-0.0, max_elapsed_seconds=-0.0)
        t_neg_zero = JobBudgetTracker(b_neg_zero, cost_usd=-0.0, elapsed_seconds=-0.0)
        t_neg_zero.record_cost(-0.0)
        t_neg_zero.record_model_call(cost_usd=-0.0)
        t_neg_zero.record_elapsed_seconds(-0.0)
        assert t_neg_zero.cost_usd == 0.0
        assert t_neg_zero.elapsed_seconds == 0.0

        # Boundary enforcement with -0.0: consuming positive amount exceeds 0.0
        with pytest.raises(BudgetExceededError) as exc_info:
            t_neg_zero.record_cost(0.0001)
        assert exc_info.value.resource == "cost_usd"

        # 4. float("inf"): Unbounded in budget, bounded in consumption
        b_inf = JobBudget(max_cost_usd=float("inf"), max_elapsed_seconds=float("inf"))
        t_inf = JobBudgetTracker(b_inf)
        t_inf.record_cost(1e300)
        t_inf.record_elapsed_seconds(1e300)
        t_inf.check_budget()  # Does not raise because limit is inf

        b_finite = JobBudget(max_cost_usd=50.0, max_elapsed_seconds=10.0)
        t_finite = JobBudgetTracker(b_finite)
        with pytest.raises(BudgetExceededError):
            t_finite.record_cost(float("inf"))
        with pytest.raises(BudgetExceededError):
            t_finite.record_elapsed_seconds(float("inf"))

        # 5. Extreme magnitude: 1e308, 1e-308, subnormal 5e-324
        b_huge = JobBudget(max_cost_usd=1e308, max_elapsed_seconds=1e308)
        t_huge = JobBudgetTracker(b_huge)
        t_huge.record_cost(1e-308)
        t_huge.record_cost(5e-324)
        t_huge.record_elapsed_seconds(1e-308)
        t_huge.record_elapsed_seconds(5e-324)
        assert t_huge.cost_usd > 0
        assert t_huge.elapsed_seconds > 0
        t_huge.check_budget()

        # Strict JSON serialization works for finite extreme values
        data = t_huge.to_dict()
        serialized = json.dumps(data, allow_nan=False)
        rehydrated = JobBudgetTracker.from_dict(b_huge, json.loads(serialized))
        assert rehydrated.cost_usd > 0





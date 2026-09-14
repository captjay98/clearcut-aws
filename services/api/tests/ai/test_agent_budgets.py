"""Unit tests for JobBudget and JobBudgetTracker."""

from __future__ import annotations

import concurrent.futures
import json
import threading

import pytest
from clearcut.ai.budgets import BudgetExceededError, JobBudget, JobBudgetTracker


def test_job_budget_initialization_and_alias() -> None:
    budget = JobBudget(
        max_model_calls=5,
        max_tokens=1000,
        max_tool_calls=10,
        max_search_calls=3,
        max_extract_calls=2,
        max_elapsed_seconds=30.0,
        max_repairs=1,
    )
    assert budget.max_model_calls == 5
    assert budget.max_total_tokens == 1000
    assert budget.max_tokens == 1000
    assert budget.max_tool_calls == 10
    assert budget.max_search_calls == 3
    assert budget.max_extract_calls == 2
    assert budget.max_elapsed_seconds == 30.0
    assert budget.max_repairs == 1


def test_consumption_within_budget() -> None:
    budget = JobBudget(
        max_model_calls=3,
        max_tokens=500,
        max_search_calls=2,
        max_extract_calls=1,
    )
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=100, output_tokens=50)
    assert tracker.model_calls == 1
    assert tracker.input_tokens == 100
    assert tracker.output_tokens == 50
    assert tracker.total_tokens == 150

    tracker.record_search_call()
    assert tracker.tool_calls == 1
    assert tracker.search_calls == 1

    tracker.record_extract_call()
    assert tracker.tool_calls == 2
    assert tracker.extract_calls == 1

    tracker.record_model_call(input_tokens=50, output_tokens=50, total_tokens=100)
    assert tracker.model_calls == 2
    assert tracker.total_tokens == 250


def test_model_calls_exceeded() -> None:
    budget = JobBudget(max_model_calls=2)
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=10, output_tokens=10)
    tracker.record_model_call(input_tokens=10, output_tokens=10)

    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_model_call(input_tokens=10, output_tokens=10)

    err = exc_info.value
    assert err.resource == "model_calls"
    assert err.limit == 2
    assert err.consumed == 3
    assert "Job budget exceeded for 'model_calls'" in str(err)


def test_total_tokens_exceeded() -> None:
    budget = JobBudget(max_tokens=100)
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=40, output_tokens=40)
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_model_call(input_tokens=20, output_tokens=20)

    err = exc_info.value
    assert err.resource == "total_tokens"
    assert err.limit == 100
    assert err.consumed == 120


def test_input_tokens_exceeded() -> None:
    budget = JobBudget(max_input_tokens=50)
    tracker = JobBudgetTracker(budget)

    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_model_call(input_tokens=60, output_tokens=5)

    assert exc_info.value.resource == "input_tokens"
    assert exc_info.value.limit == 50
    assert exc_info.value.consumed == 60


def test_output_tokens_exceeded() -> None:
    budget = JobBudget(max_output_tokens=30)
    tracker = JobBudgetTracker(budget)

    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_model_call(input_tokens=10, output_tokens=40)

    assert exc_info.value.resource == "output_tokens"
    assert exc_info.value.limit == 30
    assert exc_info.value.consumed == 40


def test_search_calls_exceeded() -> None:
    budget = JobBudget(max_search_calls=1)
    tracker = JobBudgetTracker(budget)

    tracker.record_search_call()
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_search_call()
    assert exc_info.value.resource == "search_calls"
    assert exc_info.value.limit == 1
    assert exc_info.value.consumed == 2


def test_extract_calls_exceeded() -> None:
    budget = JobBudget(max_extract_calls=1)
    tracker = JobBudgetTracker(budget)

    tracker.record_extract_call()
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_extract_call()
    assert exc_info.value.resource == "extract_calls"
    assert exc_info.value.limit == 1
    assert exc_info.value.consumed == 2


def test_tool_calls_exceeded() -> None:
    budget = JobBudget(max_tool_calls=2)
    tracker = JobBudgetTracker(budget)

    tracker.record_tool_call("tool1")
    tracker.record_tool_call("tool2")
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_tool_call("tool3")
    assert exc_info.value.resource == "tool_calls"
    assert exc_info.value.limit == 2
    assert exc_info.value.consumed == 3


def test_repairs_exceeded() -> None:
    budget = JobBudget(max_repairs=1)
    tracker = JobBudgetTracker(budget)

    tracker.record_repair()
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_repair()
    assert exc_info.value.resource == "repairs"


def test_elapsed_seconds_exceeded() -> None:
    budget = JobBudget(max_elapsed_seconds=10.0)
    tracker = JobBudgetTracker(budget)

    tracker.record_elapsed_seconds(5.0)
    tracker.record_elapsed_seconds(4.5)
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_elapsed_seconds(2.0)
    assert exc_info.value.resource == "elapsed_seconds"
    assert exc_info.value.limit == 10.0
    assert exc_info.value.consumed == 11.5


def test_persistence_and_rehydration_prevents_resetting_budget() -> None:
    budget = JobBudget(max_model_calls=3, max_search_calls=2)
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=100, output_tokens=50)
    tracker.record_search_call()

    # Worker crashes or job interrupted; state is saved to DB
    persisted = tracker.to_dict()
    assert persisted == {
        "model_calls": 1,
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "tool_calls": 1,
        "search_calls": 1,
        "extract_calls": 0,
        "repairs": 0,
        "elapsed_seconds": 0.0,
        "cost_usd": 0.0,
    }

    # Worker resumes job by re-hydrating persisted consumption state
    rehydrated = JobBudgetTracker.from_dict(budget, persisted)
    assert rehydrated.model_calls == 1
    assert rehydrated.search_calls == 1

    # Additional calls accumulate against the original limit
    rehydrated.record_search_call()
    assert rehydrated.search_calls == 2
    with pytest.raises(BudgetExceededError) as exc_info:
        rehydrated.record_search_call()
    assert exc_info.value.resource == "search_calls"
    assert exc_info.value.limit == 2
    assert exc_info.value.consumed == 3


def test_persistence_rehydration_model_calls() -> None:
    budget = JobBudget(max_model_calls=2)
    tracker = JobBudgetTracker(budget)
    tracker.record_model_call(input_tokens=50, output_tokens=20)
    persisted = tracker.to_dict()

    rehydrated = JobBudgetTracker.from_dict(budget, persisted)
    rehydrated.record_model_call(input_tokens=10, output_tokens=10)
    assert rehydrated.model_calls == 2

    # Third model call exceeds budget of 2
    with pytest.raises(BudgetExceededError) as exc_info:
        rehydrated.record_model_call(input_tokens=10, output_tokens=10)
    assert exc_info.value.resource == "model_calls"
    assert exc_info.value.limit == 2
    assert exc_info.value.consumed == 3


def test_job_budget_negative_limits_rejected() -> None:
    """Every numeric budget field must reject negative numbers with ValueError."""
    fields_to_test = [
        ("max_model_calls", -1),
        ("max_tokens", -10),
        ("max_input_tokens", -50),
        ("max_output_tokens", -25),
        ("max_total_tokens", -100),
        ("max_tool_calls", -2),
        ("max_search_calls", -1),
        ("max_extract_calls", -1),
        ("max_elapsed_seconds", -0.5),
        ("max_repairs", -1),
        ("max_cost_usd", -0.01),
    ]
    for field, neg_val in fields_to_test:
        with pytest.raises(ValueError) as exc_info:
            JobBudget(**{field: neg_val})
        assert "must be non-negative (>= 0)" in str(exc_info.value)
        assert field in str(exc_info.value)


def test_job_budget_type_validation_rejected() -> None:
    """Non-numeric values (including booleans) must be rejected with TypeError."""
    with pytest.raises(TypeError):
        JobBudget(max_model_calls=True)  # bool is not accepted as count

    with pytest.raises(TypeError):
        JobBudget(max_cost_usd="10.0")  # string not accepted


def test_job_budget_zero_limits_allowed() -> None:
    """Zero limits are valid non-negative thresholds that immediately trigger enforcement on consumption."""
    budget = JobBudget(
        max_model_calls=0,
        max_tokens=0,
        max_input_tokens=0,
        max_output_tokens=0,
        max_total_tokens=0,
        max_tool_calls=0,
        max_search_calls=0,
        max_extract_calls=0,
        max_elapsed_seconds=0.0,
        max_repairs=0,
        max_cost_usd=0.0,
    )
    assert budget.max_model_calls == 0
    assert budget.max_cost_usd == 0.0

    tracker = JobBudgetTracker(budget)
    # Zero cost limit permits 0 consumption
    tracker.record_cost(0.0)
    assert tracker.cost_usd == 0.0

    # Consuming any positive amount exceeds 0 budget
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_cost(0.01)
    assert exc_info.value.resource == "cost_usd"
    assert exc_info.value.limit == 0.0
    assert exc_info.value.consumed == 0.01
    assert exc_info.value.code == "budget_exceeded"


def test_budget_exceeded_error_code_and_properties() -> None:
    """BudgetExceededError must expose code='budget_exceeded' by default and on the class."""
    assert BudgetExceededError.code == "budget_exceeded"

    err = BudgetExceededError("cost_usd", 5.0, 5.5)
    assert err.code == "budget_exceeded"
    assert err.resource == "cost_usd"
    assert err.limit == 5.0
    assert err.consumed == 5.5
    assert "Job budget exceeded for 'cost_usd': limit is 5.0, but consumed 5.5." in str(err)

    custom_err = BudgetExceededError("cost_usd", 5.0, 5.5, code="custom_exceeded")
    assert custom_err.code == "custom_exceeded"


def test_cost_usd_tracking_and_boundary() -> None:
    """JobBudgetTracker accumulates cost and triggers at exact boundary (limit < consumed)."""
    budget = JobBudget(max_cost_usd=2.50)
    tracker = JobBudgetTracker(budget)

    tracker.record_cost(1.00)
    assert tracker.cost_usd == 1.00

    # Exact boundary: consumed == limit is permitted
    tracker.record_cost(1.50)
    assert tracker.cost_usd == 2.50

    # Exceed boundary: consumed > limit raises BudgetExceededError
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_cost(0.01)

    err = exc_info.value
    assert err.resource == "cost_usd"
    assert err.limit == 2.50
    assert abs(err.consumed - 2.51) < 1e-6
    assert err.code == "budget_exceeded"


def test_record_cost_flexible_calling_conventions_and_validation() -> None:
    """record_cost accepts positional, amount_usd, and cost_usd arguments, and rejects negative."""
    budget = JobBudget(max_cost_usd=10.0)
    tracker = JobBudgetTracker(budget)

    tracker.record_cost(1.0)
    tracker.record_cost(amount_usd=2.0)
    tracker.record_cost(cost_usd=3.0)
    assert tracker.cost_usd == 6.0

    with pytest.raises(ValueError):
        tracker.record_cost(-1.0)

    with pytest.raises(ValueError):
        tracker.record_cost(amount_usd=-0.5)


def test_record_model_call_accumulates_cost() -> None:
    """record_model_call optionally accepts and accumulates cost_usd."""
    budget = JobBudget(max_model_calls=5, max_cost_usd=0.10)
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=100, output_tokens=50, cost_usd=0.04)
    assert tracker.cost_usd == 0.04
    assert tracker.model_calls == 1
    assert tracker.total_tokens == 150

    tracker.record_model_call(input_tokens=50, output_tokens=25, cost_usd=0.05)
    assert abs(tracker.cost_usd - 0.09) < 1e-6

    # Exceeding cost limit via model call raises BudgetExceededError
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_model_call(input_tokens=10, output_tokens=10, cost_usd=0.02)
    assert exc_info.value.resource == "cost_usd"
    assert exc_info.value.limit == 0.10
    assert abs(exc_info.value.consumed - 0.11) < 1e-6


def test_tracker_thread_safety_concurrent_updates() -> None:
    """Concurrent updates across threads accumulate with zero lost updates and no deadlock."""
    budget = JobBudget(max_cost_usd=100.0, max_model_calls=5000)
    tracker = JobBudgetTracker(budget)
    assert hasattr(tracker, "_lock")
    assert isinstance(tracker._lock, type(threading.Lock()))

    num_threads = 8
    calls_per_thread = 50

    def worker() -> None:
        for _ in range(calls_per_thread):
            tracker.record_cost(0.01)
            tracker.record_model_call(input_tokens=10, output_tokens=10, cost_usd=0.01)
            tracker.record_tool_call()
            tracker.record_elapsed_seconds(0.001)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for f in futures:
            f.result(timeout=5.0)

    expected_calls = num_threads * calls_per_thread
    assert tracker.model_calls == expected_calls
    assert tracker.tool_calls == expected_calls
    # 0.01 from record_cost + 0.01 from record_model_call = 0.02 per iteration
    assert abs(tracker.cost_usd - (expected_calls * 0.02)) < 1e-5


def test_persistence_and_rehydration_with_cost() -> None:
    """to_dict and from_dict preserve cost_usd and enforce limits on rehydrated tracker."""
    budget = JobBudget(max_cost_usd=2.00, max_model_calls=5)
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=100, output_tokens=50, cost_usd=0.50)
    tracker.record_cost(0.75)
    assert tracker.cost_usd == 1.25

    persisted = tracker.to_dict()
    assert persisted["cost_usd"] == 1.25

    rehydrated = JobBudgetTracker.from_dict(budget, persisted)
    assert rehydrated.cost_usd == 1.25

    # 1.25 used of 2.00. 0.75 more reaches boundary. 0.76 exceeds limit.
    rehydrated.record_cost(0.75)
    assert rehydrated.cost_usd == 2.00

    with pytest.raises(BudgetExceededError) as exc_info:
        rehydrated.record_cost(0.01)
    assert exc_info.value.resource == "cost_usd"
    assert exc_info.value.limit == 2.00
    assert abs(exc_info.value.consumed - 2.01) < 1e-6


def test_rehydration_backwards_compatibility_without_cost_key() -> None:
    """from_dict gracefully handles legacy payloads that omit cost_usd."""
    budget = JobBudget(max_cost_usd=1.00)
    legacy_payload = {
        "model_calls": 2,
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }
    rehydrated = JobBudgetTracker.from_dict(budget, legacy_payload)
    assert rehydrated.cost_usd == 0.0
    assert rehydrated.model_calls == 2


def test_tracker_record_request_and_tokens_and_reset() -> None:
    """record_request, record_tokens, and reset work with lock synchronization."""
    budget = JobBudget(max_model_calls=10, max_input_tokens=500)
    tracker = JobBudgetTracker(budget)

    tracker.record_request(2)
    assert tracker.model_calls == 2

    tracker.record_tokens(input_tokens=100, output_tokens=50)
    assert tracker.input_tokens == 100
    assert tracker.output_tokens == 50
    assert tracker.total_tokens == 150

    tracker.reset()
    assert tracker.model_calls == 0
    assert tracker.input_tokens == 0
    assert tracker.output_tokens == 0
    assert tracker.total_tokens == 0
    assert tracker.cost_usd == 0.0


def test_job_budget_nan_limits_rejected() -> None:
    """Every numeric budget field must reject NaN with ValueError."""
    fields_to_test = [
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
    for field in fields_to_test:
        with pytest.raises(ValueError) as exc_info:
            JobBudget(**{field: float("nan")})
        assert "cannot be NaN" in str(exc_info.value)
        assert field in str(exc_info.value)


def test_tracker_record_cost_nan_rejected() -> None:
    """record_cost must reject NaN with ValueError."""
    tracker = JobBudgetTracker(JobBudget(max_cost_usd=10.0))

    with pytest.raises(ValueError) as exc_info:
        tracker.record_cost(float("nan"))
    assert "cost amount cannot be NaN" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        tracker.record_cost(cost_usd=float("nan"))
    assert "cost amount cannot be NaN" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        tracker.record_cost(amount=float("nan"))
    assert "cost amount cannot be NaN" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        tracker.record_cost(amount_usd=float("nan"))
    assert "cost amount cannot be NaN" in str(exc_info.value)


def test_tracker_record_model_call_cost_nan_rejected() -> None:
    """record_model_call must reject NaN in cost_usd with ValueError."""
    tracker = JobBudgetTracker(JobBudget(max_model_calls=5))

    with pytest.raises(ValueError) as exc_info:
        tracker.record_model_call(cost_usd=float("nan"))
    assert "cost_usd cannot be NaN" in str(exc_info.value)


def test_tracker_record_elapsed_seconds_nan_rejected() -> None:
    """record_elapsed_seconds must reject NaN with ValueError."""
    tracker = JobBudgetTracker(JobBudget(max_elapsed_seconds=10.0))

    with pytest.raises(ValueError) as exc_info:
        tracker.record_elapsed_seconds(float("nan"))
    assert "seconds cannot be NaN" in str(exc_info.value)


def test_tracker_from_dict_nan_rejected() -> None:
    """from_dict must reject NaN cost_usd and elapsed_seconds with ValueError."""
    budget = JobBudget()

    with pytest.raises(ValueError) as exc_info:
        JobBudgetTracker.from_dict(budget, {"cost_usd": float("nan")})
    assert "cost_usd cannot be NaN" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        JobBudgetTracker.from_dict(budget, {"elapsed_seconds": float("nan")})
    assert "elapsed_seconds cannot be NaN" in str(exc_info.value)


def test_tracker_init_nan_rejected() -> None:
    """JobBudgetTracker __init__ must reject NaN cost_usd and elapsed_seconds with ValueError."""
    budget = JobBudget()

    with pytest.raises(ValueError) as exc_info:
        JobBudgetTracker(budget, cost_usd=float("nan"))
    assert "cost_usd cannot be NaN" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        JobBudgetTracker(budget, elapsed_seconds=float("nan"))
    assert "elapsed_seconds cannot be NaN" in str(exc_info.value)


def test_tracker_strict_json_serialization_roundtrip() -> None:
    """JSON serialization with allow_nan=False succeeds and produces strict valid JSON."""
    budget = JobBudget(max_model_calls=10, max_cost_usd=5.0)
    tracker = JobBudgetTracker(budget)

    tracker.record_model_call(input_tokens=150, output_tokens=75, cost_usd=0.03)
    tracker.record_search_call()
    tracker.record_extract_call()
    tracker.record_elapsed_seconds(1.25)
    tracker.record_cost(0.02)

    data = tracker.to_dict()
    # Strict JSON serialization disallows NaN, Infinity, -Infinity
    serialized = json.dumps(data, allow_nan=False)
    assert isinstance(serialized, str)

    deserialized = json.loads(serialized)
    assert deserialized["model_calls"] == 1
    assert deserialized["input_tokens"] == 150
    assert deserialized["output_tokens"] == 75
    assert deserialized["total_tokens"] == 225
    assert deserialized["tool_calls"] == 2
    assert deserialized["search_calls"] == 1
    assert deserialized["extract_calls"] == 1
    assert deserialized["elapsed_seconds"] == 1.25
    assert abs(deserialized["cost_usd"] - 0.05) < 1e-6

    # Re-hydrate from JSON deserialized payload
    rehydrated = JobBudgetTracker.from_dict(budget, deserialized)
    assert rehydrated.model_calls == 1
    assert rehydrated.elapsed_seconds == 1.25
    assert abs(rehydrated.cost_usd - 0.05) < 1e-6


def test_job_budget_and_tracker_negative_infinity_rejected() -> None:
    """Negative infinity (float('-inf')) must be rejected with ValueError across all limits and counters."""
    fields = [
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
    for field in fields:
        with pytest.raises(ValueError) as exc_info:
            JobBudget(**{field: float("-inf")})
        assert "must be non-negative (>= 0)" in str(exc_info.value)
        assert field in str(exc_info.value)

    budget = JobBudget(max_cost_usd=10.0, max_elapsed_seconds=10.0)
    tracker = JobBudgetTracker(budget)

    with pytest.raises(ValueError, match="cost_usd must be non-negative"):
        JobBudgetTracker(budget, cost_usd=float("-inf"))

    with pytest.raises(ValueError, match="elapsed_seconds must be non-negative"):
        JobBudgetTracker(budget, elapsed_seconds=float("-inf"))

    with pytest.raises(ValueError, match="Cost amount must be non-negative"):
        tracker.record_cost(float("-inf"))

    with pytest.raises(ValueError, match="cost_usd must be non-negative"):
        tracker.record_model_call(cost_usd=float("-inf"))

    with pytest.raises(ValueError, match="seconds must be non-negative"):
        tracker.record_elapsed_seconds(float("-inf"))

    with pytest.raises(ValueError, match="cost_usd must be non-negative"):
        JobBudgetTracker.from_dict(budget, {"cost_usd": float("-inf")})

    with pytest.raises(ValueError, match="elapsed_seconds must be non-negative"):
        JobBudgetTracker.from_dict(budget, {"elapsed_seconds": float("-inf")})


def test_job_budget_and_tracker_negative_zero_accepted() -> None:
    """Negative zero (-0.0) is mathematically equal to 0.0 and must be accepted as non-negative (>= 0)."""
    budget = JobBudget(
        max_model_calls=5,
        max_cost_usd=-0.0,
        max_elapsed_seconds=-0.0,
    )
    assert budget.max_cost_usd == 0.0
    assert budget.max_elapsed_seconds == 0.0

    tracker = JobBudgetTracker(budget, cost_usd=-0.0, elapsed_seconds=-0.0)
    assert tracker.cost_usd == 0.0
    assert tracker.elapsed_seconds == 0.0

    # Recording -0.0 does not raise and preserves 0.0 value
    tracker.record_cost(-0.0)
    tracker.record_model_call(cost_usd=-0.0)
    tracker.record_elapsed_seconds(-0.0)
    assert tracker.cost_usd == 0.0

    # Consuming any positive amount exceeds 0.0 limit
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.record_cost(0.0001)
    assert exc_info.value.resource == "cost_usd"


def test_job_budget_and_tracker_positive_infinity_and_extreme_floats() -> None:
    """Positive infinity (float('inf')), extreme values (1e308, 1e-308), and subnormals (5e-324)."""
    # Infinite budget acts as unbounded limit
    inf_budget = JobBudget(max_cost_usd=float("inf"), max_elapsed_seconds=float("inf"))
    inf_tracker = JobBudgetTracker(inf_budget)
    inf_tracker.record_cost(1e300)
    inf_tracker.record_elapsed_seconds(1e300)
    inf_tracker.check_budget()  # Should not raise

    # Infinite consumption against finite budget is caught and triggers BudgetExceededError
    finite_budget = JobBudget(max_cost_usd=50.0)
    finite_tracker = JobBudgetTracker(finite_budget)
    with pytest.raises(BudgetExceededError) as exc_info:
        finite_tracker.record_cost(float("inf"))
    assert exc_info.value.resource == "cost_usd"

    # Extreme normal floats: 1e308 and 1e-308
    huge_budget = JobBudget(max_cost_usd=1e308)
    huge_tracker = JobBudgetTracker(huge_budget)
    huge_tracker.record_cost(1e-308)
    huge_tracker.record_cost(5e-324)  # subnormal float
    assert huge_tracker.cost_usd > 0
    huge_tracker.check_budget()

    # Serialization preserves values
    serialized = json.dumps(huge_tracker.to_dict(), allow_nan=False)
    rehydrated = JobBudgetTracker.from_dict(huge_budget, json.loads(serialized))
    assert rehydrated.cost_usd == huge_tracker.cost_usd



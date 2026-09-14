"""Execution and consumption budgets for AI and agentic workflows."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any


class BudgetError(RuntimeError):
    """Base exception for budget errors."""


class BudgetExceededError(BudgetError):
    """Raised when an execution or resource budget limit is exceeded."""

    code: str = "budget_exceeded"

    def __init__(
        self,
        resource: str,
        limit: int | float,
        consumed: int | float,
        message: str | None = None,
        *,
        code: str = "budget_exceeded",
    ) -> None:
        self.resource = resource
        self.limit = limit
        self.consumed = consumed
        self.code = code
        msg = (
            message
            or f"Job budget exceeded for '{resource}': limit is {limit}, but consumed {consumed}."
        )
        super().__init__(msg)


@dataclass(frozen=True)
class JobBudget:
    """Configured limits for a single job or agent workflow execution."""

    max_model_calls: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_total_tokens: int | None = None
    max_tool_calls: int | None = None
    max_search_calls: int | None = None
    max_extract_calls: int | None = None
    max_elapsed_seconds: float | None = None
    max_repairs: int | None = None
    max_cost_usd: float | None = None

    def __init__(
        self,
        *,
        max_model_calls: int | None = None,
        max_tokens: int | None = None,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
        max_total_tokens: int | None = None,
        max_tool_calls: int | None = None,
        max_search_calls: int | None = None,
        max_extract_calls: int | None = None,
        max_elapsed_seconds: float | None = None,
        max_repairs: int | None = None,
        max_cost_usd: float | None = None,
    ) -> None:
        fields = (
            ("max_model_calls", max_model_calls),
            ("max_tokens", max_tokens),
            ("max_input_tokens", max_input_tokens),
            ("max_output_tokens", max_output_tokens),
            ("max_total_tokens", max_total_tokens),
            ("max_tool_calls", max_tool_calls),
            ("max_search_calls", max_search_calls),
            ("max_extract_calls", max_extract_calls),
            ("max_elapsed_seconds", max_elapsed_seconds),
            ("max_repairs", max_repairs),
            ("max_cost_usd", max_cost_usd),
        )
        for name, val in fields:
            if val is not None:
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    raise TypeError(f"{name} must be numeric, got {type(val).__name__}")
                if math.isnan(val):
                    raise ValueError(f"{name} cannot be NaN")
                if val < 0:
                    raise ValueError(f"{name} must be non-negative (>= 0), got {val}")

        resolved_total = max_total_tokens if max_total_tokens is not None else max_tokens
        object.__setattr__(self, "max_model_calls", max_model_calls)
        object.__setattr__(self, "max_input_tokens", max_input_tokens)
        object.__setattr__(self, "max_output_tokens", max_output_tokens)
        object.__setattr__(self, "max_total_tokens", resolved_total)
        object.__setattr__(self, "max_tool_calls", max_tool_calls)
        object.__setattr__(self, "max_search_calls", max_search_calls)
        object.__setattr__(self, "max_extract_calls", max_extract_calls)
        object.__setattr__(
            self,
            "max_elapsed_seconds",
            float(max_elapsed_seconds) if max_elapsed_seconds is not None else None,
        )
        object.__setattr__(self, "max_repairs", max_repairs)
        object.__setattr__(
            self,
            "max_cost_usd",
            float(max_cost_usd) if max_cost_usd is not None else None,
        )

    @property
    def max_tokens(self) -> int | None:
        return self.max_total_tokens


class JobBudgetTracker:
    """Accumulates and enforces resource consumption against a JobBudget.

    Supports serialization and re-hydration so that restarting or retrying
    jobs resumes from previously consumed counts rather than granting a fresh budget.
    Thread-safe across concurrent reader and writer threads.
    """

    def __init__(
        self,
        budget: JobBudget,
        *,
        model_calls: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        tool_calls: int = 0,
        search_calls: int = 0,
        extract_calls: int = 0,
        repairs: int = 0,
        elapsed_seconds: float = 0.0,
        cost_usd: float = 0.0,
    ) -> None:
        if isinstance(cost_usd, bool) or not isinstance(cost_usd, (int, float)):
            raise TypeError(f"cost_usd must be numeric, got {type(cost_usd).__name__}")
        if math.isnan(cost_usd):
            raise ValueError("cost_usd cannot be NaN")
        if cost_usd < 0:
            raise ValueError(f"cost_usd must be non-negative (>= 0), got {cost_usd}")
        if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)):
            raise TypeError(f"elapsed_seconds must be numeric, got {type(elapsed_seconds).__name__}")
        if math.isnan(elapsed_seconds):
            raise ValueError("elapsed_seconds cannot be NaN")
        if elapsed_seconds < 0:
            raise ValueError(f"elapsed_seconds must be non-negative (>= 0), got {elapsed_seconds}")
        self.budget = budget
        self.model_calls = model_calls
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.tool_calls = tool_calls
        self.search_calls = search_calls
        self.extract_calls = extract_calls
        self.repairs = repairs
        self.elapsed_seconds = float(elapsed_seconds)
        self.cost_usd = float(cost_usd)
        self._lock = threading.Lock()

    def check_budget(self) -> None:
        """Check all limits and raise BudgetExceededError if any limit is exceeded."""
        with self._lock:
            self._check_budget_locked()

    def _check_budget_locked(self) -> None:
        b = self.budget
        if b.max_model_calls is not None and self.model_calls > b.max_model_calls:
            raise BudgetExceededError("model_calls", b.max_model_calls, self.model_calls)
        if b.max_input_tokens is not None and self.input_tokens > b.max_input_tokens:
            raise BudgetExceededError("input_tokens", b.max_input_tokens, self.input_tokens)
        if b.max_output_tokens is not None and self.output_tokens > b.max_output_tokens:
            raise BudgetExceededError("output_tokens", b.max_output_tokens, self.output_tokens)
        if b.max_total_tokens is not None and self.total_tokens > b.max_total_tokens:
            raise BudgetExceededError("total_tokens", b.max_total_tokens, self.total_tokens)
        if b.max_tool_calls is not None and self.tool_calls > b.max_tool_calls:
            raise BudgetExceededError("tool_calls", b.max_tool_calls, self.tool_calls)
        if b.max_search_calls is not None and self.search_calls > b.max_search_calls:
            raise BudgetExceededError("search_calls", b.max_search_calls, self.search_calls)
        if b.max_extract_calls is not None and self.extract_calls > b.max_extract_calls:
            raise BudgetExceededError("extract_calls", b.max_extract_calls, self.extract_calls)
        if b.max_repairs is not None and self.repairs > b.max_repairs:
            raise BudgetExceededError("repairs", b.max_repairs, self.repairs)
        if b.max_elapsed_seconds is not None and self.elapsed_seconds > b.max_elapsed_seconds:
            raise BudgetExceededError("elapsed_seconds", b.max_elapsed_seconds, self.elapsed_seconds)
        if b.max_cost_usd is not None and self.cost_usd > b.max_cost_usd:
            raise BudgetExceededError("cost_usd", b.max_cost_usd, self.cost_usd)

    def record_cost(
        self,
        amount_usd: float = 0.0,
        *,
        cost_usd: float | None = None,
        amount: float | None = None,
    ) -> None:
        """Record an operational or provider cost in USD and enforce budget."""
        resolved = cost_usd if cost_usd is not None else (amount if amount is not None else amount_usd)
        if isinstance(resolved, bool) or not isinstance(resolved, (int, float)):
            raise TypeError(f"cost amount must be numeric, got {type(resolved).__name__}")
        if math.isnan(resolved):
            raise ValueError("cost amount cannot be NaN")
        if resolved < 0:
            raise ValueError(f"Cost amount must be non-negative (>= 0), got {resolved}")
        with self._lock:
            self.cost_usd += float(resolved)
            self._check_budget_locked()

    def record_model_call(
        self,
        *,
        input_tokens: int | None = 0,
        output_tokens: int | None = 0,
        total_tokens: int | None = 0,
        cost_usd: float | None = None,
    ) -> None:
        """Record one model inference call and its token usage, then enforce budget."""
        in_tok = input_tokens or 0
        out_tok = output_tokens or 0
        tot_tok = total_tokens if total_tokens is not None and total_tokens > 0 else (in_tok + out_tok)
        if cost_usd is not None:
            if isinstance(cost_usd, bool) or not isinstance(cost_usd, (int, float)):
                raise TypeError(f"cost_usd must be numeric, got {type(cost_usd).__name__}")
            if math.isnan(cost_usd):
                raise ValueError("cost_usd cannot be NaN")
            if cost_usd < 0:
                raise ValueError(f"cost_usd must be non-negative (>= 0), got {cost_usd}")

        with self._lock:
            self.model_calls += 1
            self.input_tokens += in_tok
            self.output_tokens += out_tok
            self.total_tokens += tot_tok
            if cost_usd is not None:
                self.cost_usd += float(cost_usd)
            self._check_budget_locked()

    def record_request(self, count: int = 1) -> None:
        """Record request count and enforce budget."""
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError(f"count must be an integer, got {type(count).__name__}")
        if count < 0:
            raise ValueError(f"count must be non-negative (>= 0), got {count}")
        with self._lock:
            self.model_calls += count
            self._check_budget_locked()

    def record_tokens(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> None:
        """Record token consumption and enforce budget."""
        for name, val in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if isinstance(val, bool) or not isinstance(val, int):
                raise TypeError(f"{name} must be an integer, got {type(val).__name__}")
            if val < 0:
                raise ValueError(f"{name} must be non-negative (>= 0), got {val}")
        if total_tokens is not None:
            if isinstance(total_tokens, bool) or not isinstance(total_tokens, int):
                raise TypeError(f"total_tokens must be an integer, got {type(total_tokens).__name__}")
            if total_tokens < 0:
                raise ValueError(f"total_tokens must be non-negative (>= 0), got {total_tokens}")
        tot = total_tokens if total_tokens is not None and total_tokens > 0 else (input_tokens + output_tokens)
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.total_tokens += tot
            self._check_budget_locked()

    def record_tool_call(self, tool_name: str | None = None) -> None:
        """Record a generic tool invocation and enforce budget."""
        with self._lock:
            self.tool_calls += 1
            self._check_budget_locked()

    def record_search_call(self) -> None:
        """Record a search tool invocation and enforce budget."""
        with self._lock:
            self.tool_calls += 1
            self.search_calls += 1
            self._check_budget_locked()

    def record_extract_call(self) -> None:
        """Record a URL extract tool invocation and enforce budget."""
        with self._lock:
            self.tool_calls += 1
            self.extract_calls += 1
            self._check_budget_locked()

    def record_repair(self) -> None:
        """Record a model repair attempt and enforce budget."""
        with self._lock:
            self.repairs += 1
            self._check_budget_locked()

    def record_elapsed_seconds(self, seconds: float) -> None:
        """Accumulate elapsed wall-clock seconds and enforce budget."""
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise TypeError(f"seconds must be numeric, got {type(seconds).__name__}")
        if math.isnan(seconds):
            raise ValueError("seconds cannot be NaN")
        if seconds < 0:
            raise ValueError(f"seconds must be non-negative (>= 0), got {seconds}")
        with self._lock:
            if seconds > 0:
                self.elapsed_seconds += float(seconds)
            self._check_budget_locked()

    def reset(self) -> None:
        """Reset all consumption counters to zero."""
        with self._lock:
            self.model_calls = 0
            self.input_tokens = 0
            self.output_tokens = 0
            self.total_tokens = 0
            self.tool_calls = 0
            self.search_calls = 0
            self.extract_calls = 0
            self.repairs = 0
            self.elapsed_seconds = 0.0
            self.cost_usd = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize consumption counters for persistence in DB job/run state."""
        with self._lock:
            return {
                "model_calls": self.model_calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "tool_calls": self.tool_calls,
                "search_calls": self.search_calls,
                "extract_calls": self.extract_calls,
                "repairs": self.repairs,
                "elapsed_seconds": self.elapsed_seconds,
                "cost_usd": self.cost_usd,
            }

    @classmethod
    def from_dict(cls, budget: JobBudget, data: dict[str, Any]) -> JobBudgetTracker:
        """Re-hydrate a tracker from persisted consumption state."""
        cost_val = data.get("cost_usd", 0.0)
        if isinstance(cost_val, bool) or not isinstance(cost_val, (int, float)):
            raise TypeError("cost_usd must be numeric")
        if math.isnan(cost_val):
            raise ValueError("cost_usd cannot be NaN")
        elapsed_val = data.get("elapsed_seconds", 0.0)
        if isinstance(elapsed_val, bool) or not isinstance(elapsed_val, (int, float)):
            raise TypeError("elapsed_seconds must be numeric")
        if math.isnan(elapsed_val):
            raise ValueError("elapsed_seconds cannot be NaN")
        return cls(
            budget=budget,
            model_calls=int(data.get("model_calls", 0)),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
            tool_calls=int(data.get("tool_calls", 0)),
            search_calls=int(data.get("search_calls", 0)),
            extract_calls=int(data.get("extract_calls", 0)),
            repairs=int(data.get("repairs", 0)),
            elapsed_seconds=float(elapsed_val),
            cost_usd=float(cost_val),
        )

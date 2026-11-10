"""Recommend Kubernetes CPU and memory requests from usage samples.

This module implements percentile-based resource recommendation with exact
quantity parsing of Kubernetes resource.Quantity strings, margin and step
rounding rules, and ready-to-paste YAML patch rendering.
"""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Literal, TextIO

__all__ = [
    "AdvisorError",
    "Policy",
    "Recommendation",
    "Resources",
    "Sample",
    "__version__",
    "assess",
    "main",
    "parse_quantity",
    "read_samples_csv",
    "recommend",
    "render_patch",
]

__version__ = "0.1.0"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

ErrorCode = Literal[
    "invalid_quantity",
    "missing_column",
    "invalid_sample",
    "too_many_rows",
    "invalid_policy",
]


class AdvisorError(Exception):
    """Base error for the library.

    Attributes:
        code: machine-readable error code.
    """

    def __init__(self, code: ErrorCode, message: str = "") -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sample:
    """One usage observation for a container.

    Attributes:
        timestamp: observation timestamp as free-form string (not parsed).
        namespace: Kubernetes namespace.
        workload: workload name (Deployment, StatefulSet, etc.).
        container: container name.
        cpu_m: CPU usage in millicores (non-negative integer).
        memory_bytes: memory usage in bytes (non-negative integer).
    """

    timestamp: str
    namespace: str
    workload: str
    container: str
    cpu_m: int
    memory_bytes: int

    def __post_init__(self) -> None:
        if self.cpu_m < 0:
            raise AdvisorError("invalid_sample", "cpu_m must be non-negative")
        if self.memory_bytes < 0:
            raise AdvisorError("invalid_sample", "memory_bytes must be non-negative")


@dataclass(frozen=True)
class Policy:
    """Recommendation policy knobs."""

    cpu_percentile: int = 90
    memory_percentile: int = 100
    margin_pct: int = 15
    cpu_step_m: int = 10
    memory_step_b: int = 1_048_576
    min_cpu_m: int = 10
    min_memory_b: int = 16_777_216
    min_samples: int = 10
    cpu_limit_factor: float | None = None
    memory_limit_equals_request: bool = True

    def __post_init__(self) -> None:
        # Validate ranges: percentiles 1..100, margin >=0, steps >=1, floors >=0, min_samples >=1.
        if not (1 <= self.cpu_percentile <= 100):
            raise AdvisorError("invalid_policy", "cpu_percentile must be in [1, 100]")
        if not (1 <= self.memory_percentile <= 100):
            raise AdvisorError("invalid_policy", "memory_percentile must be in [1, 100]")
        if self.margin_pct < 0:
            raise AdvisorError("invalid_policy", "margin_pct must be non-negative")
        if self.cpu_step_m <= 0:
            raise AdvisorError("invalid_policy", "cpu_step_m must be positive")
        if self.memory_step_b <= 0:
            raise AdvisorError("invalid_policy", "memory_step_b must be positive")
        if self.min_cpu_m < 0:
            raise AdvisorError("invalid_policy", "min_cpu_m must be non-negative")
        if self.min_memory_b < 0:
            raise AdvisorError("invalid_policy", "min_memory_b must be non-negative")
        if self.min_samples < 1:
            raise AdvisorError("invalid_policy", "min_samples must be at least 1")
        if self.cpu_limit_factor is not None and self.cpu_limit_factor < 1.0:
            raise AdvisorError("invalid_policy", "cpu_limit_factor must be >= 1.0")


_DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Recommendation:
    """Computed recommendation for one container."""

    namespace: str
    workload: str
    container: str
    samples: int
    cpu_request_m: int
    memory_request_b: int
    cpu_limit_m: int
    memory_limit_b: int
    status: Literal["ok", "insufficient_data"] = "ok"


@dataclass(frozen=True)
class Resources:
    """Current resource requests for comparison."""

    cpu_request: str | None = None
    memory_request: str | None = None


# ---------------------------------------------------------------------------
# Quantity parsing
# ---------------------------------------------------------------------------

_MEMORY_SUFFIX_FACTORS: dict[str, int] = {
    "k": 1_000,
    "M": 1_000**2,
    "G": 1_000**3,
    "T": 1_000**4,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
}

_CPU_SUFFIXES = {"", "m"}


def _parse_decimal(number: str) -> Decimal:
    """Parse a decimal string, raising AdvisorError for invalid syntax."""
    try:
        return Decimal(number)
    except InvalidOperation as exc:
        raise AdvisorError("invalid_quantity", f"invalid number: {number}") from exc


def parse_quantity(q: str, kind: Literal["cpu", "memory"]) -> int:
    """Parse a Kubernetes resource.Quantity subset into an integer.

    Args:
        q: quantity string, at most 32 characters.
        kind: resource type; 'cpu' returns millicores, 'memory' returns bytes.

    Returns:
        Integer value after suffix multiplication, rounded up.

    Raises:
        AdvisorError: with code 'invalid_quantity' if the string is invalid.
    """
    if not isinstance(q, str):
        raise AdvisorError("invalid_quantity", "quantity must be a string")
    if len(q) > 32:
        raise AdvisorError("invalid_quantity", "quantity too long (max 32 chars)")
    if not q:
        raise AdvisorError("invalid_quantity", "empty quantity")

    # Split into numeric part and suffix.
    # Use a regex that accepts a decimal number (no sign, no exponent) followed by optional letters.
    match = re.fullmatch(r"(\d+(?:\.\d*)?|\.\d+)([A-Za-z]*)", q)
    if match is None:
        raise AdvisorError("invalid_quantity", f"invalid format: {q}")

    number_str = match.group(1)
    suffix = match.group(2)
    value = _parse_decimal(number_str)

    if kind == "cpu":
        if suffix not in _CPU_SUFFIXES:
            raise AdvisorError("invalid_quantity", f"invalid cpu suffix: {suffix}")
        # suffix == "" means cores
        result = value if suffix == "m" else value * 1000
    else:  # memory
        if suffix == "":
            result = value
        elif suffix in _MEMORY_SUFFIX_FACTORS:
            result = value * _MEMORY_SUFFIX_FACTORS[suffix]
        else:
            raise AdvisorError("invalid_quantity", f"invalid memory suffix: {suffix}")

    # Round up to integer
    rounded = int(result.to_integral_value(rounding=ROUND_CEILING))
    return rounded


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS = ("timestamp", "namespace", "workload", "container", "cpu_m", "memory_bytes")


def read_samples_csv(stream: TextIO, *, max_rows: int = 1_000_000) -> list[Sample]:
    """Read usage samples from a CSV stream.

    Args:
        stream: text stream with CSV data and header row.
        max_rows: maximum number of data rows to accept.

    Returns:
        List of Sample instances.

    Raises:
        AdvisorError: with code 'missing_column' if a required column
            is absent; 'invalid_sample' if a row cannot be parsed;
            'too_many_rows' if more than max_rows data rows are present.
    """
    reader = csv.DictReader(stream)
    if reader.fieldnames is None:
        raise AdvisorError("missing_column", "no header row found")

    missing = [col for col in _REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise AdvisorError("missing_column", f"missing columns: {', '.join(missing)}")

    samples: list[Sample] = []
    for row_num, row in enumerate(reader, start=1):
        if row_num > max_rows:
            raise AdvisorError("too_many_rows", f"exceeded max_rows={max_rows}")
        try:
            cpu_m = int(row["cpu_m"])
            memory_bytes = int(row["memory_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AdvisorError(
                "invalid_sample", f"row {row_num}: invalid cpu_m or memory_bytes"
            ) from exc
        if cpu_m < 0:
            raise AdvisorError("invalid_sample", f"row {row_num}: cpu_m cannot be negative")
        if memory_bytes < 0:
            raise AdvisorError("invalid_sample", f"row {row_num}: memory_bytes cannot be negative")
        samples.append(
            Sample(
                timestamp=row["timestamp"],
                namespace=row["namespace"],
                workload=row["workload"],
                container=row["container"],
                cpu_m=cpu_m,
                memory_bytes=memory_bytes,
            )
        )
    return samples


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------


def _nearest_rank_percentile(sorted_values: list[int], p: int) -> int:
    """Return the nearest-rank percentile from a sorted list (ascending)."""
    n = len(sorted_values)
    if n == 0:
        return 0
    idx = (p * n + 99) // 100 - 1
    # Clamp to valid index in case of extremely small n.
    if idx < 0:
        idx = 0
    if idx >= n:
        idx = n - 1
    return sorted_values[idx]


def _ceil_div(a: int, b: int) -> int:
    """Integer ceiling division for positive a,b."""
    return (a + b - 1) // b


def _round_up(value: int, step: int) -> int:
    """Round up to the nearest multiple of step."""
    return _ceil_div(value, step) * step


def _apply_margin_and_round(value: int, margin_pct: int, step: int, floor: int) -> int:
    """Apply margin, round up to step, then apply floor."""
    margin_num = 100 + margin_pct
    with_margin = _ceil_div(value * margin_num, 100)
    rounded = _round_up(with_margin, step)
    return max(rounded, floor)


def recommend(
    samples: Iterable[Sample], *, policy: Policy = _DEFAULT_POLICY
) -> list[Recommendation]:
    """Compute recommendations grouped by namespace/workload/container.

    Args:
        samples: iterable of Sample instances.
        policy: recommendation policy.

    Returns:
        List of Recommendation sorted by (namespace, workload, container).
    """
    # Group samples
    groups: dict[tuple[str, str, str], list[Sample]] = {}
    for s in samples:
        key = (s.namespace, s.workload, s.container)
        groups.setdefault(key, []).append(s)

    recommendations: list[Recommendation] = []
    for key in sorted(groups):
        ns, workload, container = key
        group = groups[key]
        n = len(group)
        if n < policy.min_samples:
            recommendations.append(
                Recommendation(
                    namespace=ns,
                    workload=workload,
                    container=container,
                    samples=n,
                    cpu_request_m=0,
                    memory_request_b=0,
                    cpu_limit_m=0,
                    memory_limit_b=0,
                    status="insufficient_data",
                )
            )
            continue

        cpu_values = sorted(s.cpu_m for s in group)
        mem_values = sorted(s.memory_bytes for s in group)

        cpu_percentile_value = _nearest_rank_percentile(cpu_values, policy.cpu_percentile)
        mem_percentile_value = _nearest_rank_percentile(mem_values, policy.memory_percentile)

        cpu_req = _apply_margin_and_round(
            cpu_percentile_value, policy.margin_pct, policy.cpu_step_m, policy.min_cpu_m
        )
        mem_req = _apply_margin_and_round(
            mem_percentile_value, policy.margin_pct, policy.memory_step_b, policy.min_memory_b
        )

        # CPU limit
        cpu_limit_m = 0
        if policy.cpu_limit_factor is not None:
            # Use Decimal for precise multiplication
            factor = Decimal(str(policy.cpu_limit_factor))
            limit_raw = (Decimal(cpu_req) * factor).to_integral_value(rounding=ROUND_CEILING)
            limit_int = int(limit_raw)
            cpu_limit_m = _round_up(limit_int, policy.cpu_step_m)

        # Memory limit
        memory_limit_b = mem_req if policy.memory_limit_equals_request else 0

        recommendations.append(
            Recommendation(
                namespace=ns,
                workload=workload,
                container=container,
                samples=n,
                cpu_request_m=cpu_req,
                memory_request_b=mem_req,
                cpu_limit_m=cpu_limit_m,
                memory_limit_b=memory_limit_b,
                status="ok",
            )
        )

    return recommendations


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------


def assess(rec: Recommendation, current: Resources) -> dict[str, str]:
    """Compare a recommendation to current resources.

    Args:
        rec: the recommendation (must have status 'ok').
        current: current resource requests (quantities as strings).

    Returns:
        Dictionary with keys 'cpu' and 'memory' and values one of:
        'ok', 'over_provisioned', 'under_provisioned', 'unset'.
    """
    result: dict[str, str] = {}
    # CPU assessment
    if current.cpu_request is None:
        result["cpu"] = "unset"
    else:
        current_cpu = parse_quantity(current.cpu_request, "cpu")
        recommended_cpu = rec.cpu_request_m
        if current_cpu * 2 > recommended_cpu * 3:  # > 1.5x, exact integer math
            result["cpu"] = "over_provisioned"
        elif current_cpu < recommended_cpu:
            result["cpu"] = "under_provisioned"
        else:
            result["cpu"] = "ok"

    # Memory assessment
    if current.memory_request is None:
        result["memory"] = "unset"
    else:
        current_mem = parse_quantity(current.memory_request, "memory")
        recommended_mem = rec.memory_request_b
        if current_mem * 2 > recommended_mem * 3:  # > 1.5x, exact integer math
            result["memory"] = "over_provisioned"
        elif current_mem < recommended_mem:
            result["memory"] = "under_provisioned"
        else:
            result["memory"] = "ok"

    return result


# ---------------------------------------------------------------------------
# Patch rendering
# ---------------------------------------------------------------------------


def _format_cpu(millicores: int) -> str:
    return f"{millicores}m"


def _format_memory(bytes_: int) -> str:
    if bytes_ % 1_048_576 == 0:
        return f"{bytes_ // 1_048_576}Mi"
    return str(bytes_)


def render_patch(rec: Recommendation) -> str:
    """Render the recommendation as a YAML resources patch.

    Args:
        rec: the recommendation.

    Returns:
        A string with the resources block.
    """
    lines = ["resources:", "  requests:"]
    if rec.cpu_request_m > 0:
        lines.append(f"    cpu: {_format_cpu(rec.cpu_request_m)}")
    if rec.memory_request_b > 0:
        lines.append(f"    memory: {_format_memory(rec.memory_request_b)}")
    lines.append("  limits:")
    if rec.cpu_limit_m > 0:
        lines.append(f"    cpu: {_format_cpu(rec.cpu_limit_m)}")
    if rec.memory_limit_b > 0:
        lines.append(f"    memory: {_format_memory(rec.memory_limit_b)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI re-export
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv: command-line arguments; if None, sys.argv[1:] is used.

    Returns:
        Exit code: 0 success, 1 under-provisioned container(s), 2 error.
    """
    from .__main__ import main as _main

    return _main(argv)

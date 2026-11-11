# trysac-k8s-resource-advisor

Recommend Kubernetes CPU and memory requests and limits from usage samples with percentile math, exact quantity parsing and ready-to-paste resources YAML.

## Features

- Parse the documented subset of Kubernetes resource quantities: non-negative decimals, CPU suffix `m`, memory suffixes `k`, `M`, `G`, `T`, `Ki`, `Mi`, `Gi`, `Ti`; quantities are limited to 32 characters.
- Compute nearest-rank percentiles with integer arithmetic.
- Apply a margin percentage, round up to CPU and memory steps, and enforce floors.
- Compare a recommendation with current requests.
- Render a `resources` block for requests and limits.
- Read CSV samples and run the same pipeline from the `k8s-resource-advisor` CLI.

## Installation

```bash
pip install trysac-k8s-resource-advisor
```

Runtime code uses only the Python standard library.

## Usage

```python
from k8s_resource_advisor import Policy, Sample, recommend, render_patch

samples = [Sample("t", "default", "web", "app", 100, 251658240) for _ in range(10)]
rec = recommend(samples, policy=Policy())[0]
print(render_patch(rec), end="")
```

## Public API

- `parse_quantity(q: str, kind: Literal['cpu', 'memory']) -> int`: CPU returns millicores, memory returns bytes. Raises `AdvisorError` with code `invalid_quantity` for non-strings, empty or over-32-character strings, exponent or signed values, and unsupported suffixes.
- `read_samples_csv(stream: TextIO, *, max_rows: int = 1_000_000) -> list[Sample]`: requires `timestamp,namespace,workload,container,cpu_m,memory_bytes`; `cpu_m` and `memory_bytes` must parse as non-negative integers. Raises `AdvisorError` with `missing_column`, `invalid_sample`, or `too_many_rows`.
- `Policy(...)`: defaults are `cpu_percentile=90`, `memory_percentile=100`, `margin_pct=15`, `cpu_step_m=10`, `memory_step_b=1_048_576`, `min_cpu_m=10`, `min_memory_b=16_777_216`, `min_samples=10`, `cpu_limit_factor=None`, `memory_limit_equals_request=True`. Invalid values raise `invalid_policy`.
- `recommend(samples, *, policy=Policy()) -> list[Recommendation]`: one result per `(namespace, workload, container)`, sorted by that key. Fewer than `min_samples` returns `status='insufficient_data'` and zero values.
- `assess(rec, current: Resources) -> dict[str, str]`: values are `ok`, `over_provisioned` when current is greater than 1.5 times the recommendation, `under_provisioned` when current is less than the recommendation, or `unset`.
- `render_patch(rec) -> str`: CPU as `<n>m`; memory as `<n>Mi` when divisible by 1,048,576, otherwise `<n>` bytes.
- `main(argv=None) -> int`: CLI exit codes 0 success, 1 any under-provisioned container, 2 usage, IO or invalid input.
- `AdvisorError.code` is one of `invalid_quantity`, `missing_column`, `invalid_sample`, `too_many_rows`, `invalid_policy`.
- `Sample`, `Recommendation` and `Resources` are frozen dataclasses. `__version__` is `0.1.0`.

The CLI takes a CSV path plus `--current <json>`, `--margin` (default 15) and `--cpu-percentile` (default 90). Limits: percentiles are 1 to 100, margin is non-negative, steps are positive, floors are non-negative, `min_samples` is at least 1, and `cpu_limit_factor` is either `None` or at least 1.0. The code does not read the Metrics API or Prometheus, apply patches, or model HPA/VPA behavior.

## Why not Vertical Pod Autoscaler

This utility runs offline on exported usage samples. The percentile, margin, step and floor rules are explicit and reviewable in the code, and the output is a YAML resources block that a human can inspect before applying it. It does not run a cluster component, read the Metrics API or Prometheus, or change workloads.

## Documentation

See [docs/SECURITY.md](docs/SECURITY.md) for the threat model, [docs/PROJECT.md](docs/PROJECT.md) for scope and [docs/TESTING.md](docs/TESTING.md) for the test module.

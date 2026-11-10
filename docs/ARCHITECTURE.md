# Architecture

## Purpose

`trysac-k8s-resource-advisor` is a stdlib-only Python package that recommends Kubernetes CPU and memory requests and limits from usage samples with nearest-rank percentiles, margin and step rounding, floors, quantity parsing and YAML rendering.

## Shape

```text
k8s_resource_advisor/
  __init__.py   models, parsing, CSV reading, recommendation, assessment, rendering, version
  __main__.py   argparse CLI
```

- Public API: names in `__all__` of `k8s_resource_advisor.__init__`: `AdvisorError`, `Policy`, `Recommendation`, `Resources`, `Sample`, `__version__`, `assess`, `main`, `parse_quantity`, `read_samples_csv`, `recommend` and `render_patch`.
- Errors: `AdvisorError` carries a `code` of `invalid_quantity`, `missing_column`, `invalid_sample`, `too_many_rows` or `invalid_policy`.
- Library functions do not print or exit. `read_samples_csv` reads from a caller-supplied stream; the CLI opens files, prints patches and returns exit codes.
- No global state. Logging uses `logging.getLogger(__name__)` with `NullHandler`.

## Quality contract

The provided tree contains the package and a pytest test module. No `scripts/check.py` or `fabrica.json` is included.

## Decisions

No `docs/decisions/` directory or ADR files are included in the provided tree.

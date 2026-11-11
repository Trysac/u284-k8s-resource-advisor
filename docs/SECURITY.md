# Security notes

## Threat model

`trysac-k8s-resource-advisor` is a pure Python library; the CLI reads files named by the caller and prints to stdout or stderr.

Defended:

- Quantity strings: `parse_quantity` rejects non-strings, empty strings, strings longer than 32 characters, formats outside a non-negative decimal plus optional letters, negative values, exponent forms, and unsupported CPU or memory suffixes. It raises `AdvisorError` with `invalid_quantity`.
- CSV: `read_samples_csv` requires `timestamp`, `namespace`, `workload`, `container`, `cpu_m` and `memory_bytes`; converts `cpu_m` and `memory_bytes` with `int`; rejects negative values; enforces `max_rows`, default 1,000,000, with `too_many_rows`.
- Current resources: the CLI requires a JSON object, per-key objects, and string `cpu_request` or `memory_request` values. Invalid structures raise `ValueError` and exit 2.
- No `eval`, no `exec` and no unsafe deserialization. Runtime code has no third-party dependencies.

Not defended:

- File paths and file size are not sandboxed. The CLI reads the CSV and JSON paths given on the command line. `max_rows` limits CSV data rows, but the `timestamp`, `namespace`, `workload` and `container` field strings are not length-limited.
- Inputs are not authenticated or authorized; the library does not know who produced the samples.
- Recommendations are advisory. The code does not contact a cluster, apply patches, read the Metrics API or Prometheus, or enforce limits.
- Secrets in CSV or JSON are not redacted. Library logging uses a `NullHandler`; CLI errors print messages to stderr.

## Publishing

No release workflow or publishing credentials are present in the repository. The distribution name is `trysac-k8s-resource-advisor`; the import package is `k8s_resource_advisor`.

# Testing

## Running

```sh
pytest tests/test_k8s_resource_advisor.py
```

## Policy

The provided test module exercises the public API through `import k8s_resource_advisor`. The compiled test artifact `tests/__pycache__/test_k8s_resource_advisor.cpython-312-pytest-9.2.0.pyc` references these test functions:

- `test_parse_quantity_cpu_no_suffix`, `test_parse_quantity_cpu_millicores`, `test_parse_quantity_memory_no_suffix`, `test_parse_quantity_memory_suffixes` cover quantity suffix parsing.
- `test_parse_quantity_acceptance_specific` covers specific acceptance values.
- `test_parse_quantity_invalid_cpu_suffix`, `test_parse_quantity_invalid_memory_suffix`, `test_parse_quantity_exponent_invalid`, `test_parse_quantity_negative_invalid`, `test_parse_quantity_length_limit`, `test_parse_quantity_non_string_invalid` cover invalid quantity errors.
- `test_parse_quantity_rounding_up_memory` covers fractional memory rounding.
- `test_read_samples_csv_valid` covers valid CSV reading.

No coverage threshold or conformance marker configuration is present in the provided repository.

## Tiers

No local or CI conformance split is configured in the provided repository.

## Layout

The only test module is `tests/test_k8s_resource_advisor.py`. No `tests/conftest.py` is present in the provided tree.

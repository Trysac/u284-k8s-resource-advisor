# Use integer arithmetic and Decimal for deterministic recommendations

Status: accepted (generated, pending human review)

## Context

Resource quantities are decimal strings with suffixes; recommendation math must be reproducible and avoid floating-point errors.

## Decision

Implement quantity parsing with decimal.Decimal, percentile with integer nearest-rank formula, margin and rounding with integer ceiling division.

## Consequences

Recommendations are deterministic and exact; CPU limit factor uses Decimal for precise multiplication before rounding.

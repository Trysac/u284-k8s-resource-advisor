"""Command-line interface for k8s-resource-advisor."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any

from . import (
    AdvisorError,
    Policy,
    Resources,
    assess,
    read_samples_csv,
    recommend,
    render_patch,
)


def _resource_value(current: dict[str, Any], name: str) -> str | None:
    """Return a current resource quantity, validating it is a string."""
    value = current.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string quantity")
    return value


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: command-line arguments; if None, sys.argv[1:] is used.

    Returns:
        Exit code: 0 success, 1 under-provisioned container(s), 2 error.
    """
    parser = argparse.ArgumentParser(prog="k8s-resource-advisor")
    parser.add_argument("csv_path", help="Path to CSV file with usage samples")
    parser.add_argument("--current", help="Path to JSON file with current resources")
    parser.add_argument("--margin", type=int, default=15, help="Margin percentage (default: 15)")
    parser.add_argument(
        "--cpu-percentile", type=int, default=90, help="CPU percentile (default: 90)"
    )
    args = parser.parse_args(argv)

    try:
        with open(args.csv_path, encoding="utf-8") as f:
            samples = read_samples_csv(f)

        policy = Policy(margin_pct=args.margin, cpu_percentile=args.cpu_percentile)
        recs = recommend(samples, policy=policy)

        current_map: dict[str, dict[str, Any]] = {}
        if args.current:
            with open(args.current, encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("current resources file must contain a JSON object")
            current_map = loaded

        under_provisioned = False
        for rec in recs:
            key = f"{rec.namespace}/{rec.workload}/{rec.container}"
            if rec.status != "ok":
                print(f"# {key} insufficient_data ({rec.samples} < {policy.min_samples} samples)")
                continue
            print(f"# {key}")
            print(render_patch(rec))
            if args.current:
                current = current_map.get(key, {})
                if not isinstance(current, dict):
                    raise ValueError(f"current resources for {key} must be a JSON object")
                current_resources = Resources(
                    cpu_request=_resource_value(current, "cpu_request"),
                    memory_request=_resource_value(current, "memory_request"),
                )
                assessment = assess(rec, current_resources)
                if (
                    assessment.get("cpu") == "under_provisioned"
                    or assessment.get("memory") == "under_provisioned"
                ):
                    under_provisioned = True
        return 1 if under_provisioned else 0
    except (OSError, ValueError, TypeError, csv.Error, AttributeError, AdvisorError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

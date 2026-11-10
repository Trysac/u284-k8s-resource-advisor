"""Behavior tests for the public API of k8s_resource_advisor."""

from __future__ import annotations

import pytest

import k8s_resource_advisor


def test_normalize_trims_and_lowercases() -> None:
    assert k8s_resource_advisor.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        k8s_resource_advisor.normalize(value)


def test_version_is_semver() -> None:
    parts = k8s_resource_advisor.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)

# k8s-resource-advisor

[![PyPI version](https://img.shields.io/pypi/v/trysac-k8s-resource-advisor)](https://pypi.org/project/trysac-k8s-resource-advisor/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-k8s-resource-advisor)](LICENSE)
[![CI](https://github.com/Trysac/u284-k8s-resource-advisor/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u284-k8s-resource-advisor/actions/workflows/ci.yml)

Recommend Kubernetes CPU and memory requests and limits from usage samples with percentile math, exact quantity parsing and ready-to-paste resources YAML

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-k8s-resource-advisor
# or
uv add trysac-k8s-resource-advisor
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import k8s_resource_advisor

# normalize() trims surrounding whitespace and lower-cases the text.
print(k8s_resource_advisor.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    k8s_resource_advisor.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez

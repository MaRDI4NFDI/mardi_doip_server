#!/usr/bin/env bash
set -euo pipefail

# Run all tests with DEBUG log output enabled.
PYTHONPATH=. pytest --log-cli-level=DEBUG "$@"

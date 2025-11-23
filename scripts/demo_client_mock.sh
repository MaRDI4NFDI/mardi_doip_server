#!/usr/bin/env bash
set -euo pipefail

# Run the mock client CLI to exercise hello/retrieve/invoke flows.
PYTHONPATH=. python -m client_cli.main "$@"

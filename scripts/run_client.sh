#!/usr/bin/env bash
set -euo pipefail

# Run the strict DOIP client CLI to exercise hello/retrieve flows.
PYTHONPATH=. python -m client_cli.main "$@"

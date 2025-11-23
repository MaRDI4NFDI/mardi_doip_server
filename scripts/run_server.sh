#!/usr/bin/env bash
set -euo pipefail

# Start the DOIP server with the default port/settings.
PYTHONPATH=. python -m doip_server.main "$@"

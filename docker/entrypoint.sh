#!/usr/bin/env bash
set -euo pipefail

# Start a lightweight static server on port 80 for the landing page.
python -m http.server 80 --directory /app/landing &

# Run the DOIP server in the foreground so PID 1 gets signals.
exec python -m doip_server.main "$@"

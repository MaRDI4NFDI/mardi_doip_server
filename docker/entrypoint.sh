#!/usr/bin/env bash
set -euo pipefail

# Start the DOIP server in the background so the HTTP gateway can run in the foreground.
python -m doip_server.main "$@" &

# Run the FastAPI download gateway (PID 1 receives signals).
exec uvicorn doip_server.http_gateway:app --host 0.0.0.0 --port 80

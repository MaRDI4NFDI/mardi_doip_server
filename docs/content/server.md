# Server

## Overview
The server implements strict DOIP v2.0 framing with the following operations:

- Hello (0x01)
- Retrieve (0x02)
- Invoke (0x05)

It listens on port 3567 by default (3568 for the compatibility JSON listener).

## Entrypoint
- Module: `doip_server.main`
- Run: `python -m doip_server.main`

Example (plaintext):
```bash
PYTHONPATH=. python -m doip_server.main --port 3567
```

## Handlers
- `handle_hello`: returns server status and capabilities.
- `handle_retrieve`: streams components based on object and component IDs.
- `handle_invoke`: runs workflows (currently equation extraction).

## Protocol
- Header: `>BBBBHI`
- Blocks: metadata, component, workflow.

See `doip_server/protocol.py` for framing details.

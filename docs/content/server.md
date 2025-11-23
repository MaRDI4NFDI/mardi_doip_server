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
- `handle_hello`
  - **Motivation**: Allow clients to verify connectivity and discover supported operations without performing data transfers.
  - **Use case**: A monitoring probe or client bootstrap issues `hello` to confirm the endpoint is alive and reads the `availableOperations` map.
- `handle_retrieve`
  - **Motivation**: Deliver FAIR Digital Object bitstreams/components via strict DOIP framing.
  - **Use case**: A client requests `doip:bitstream/Q123/main-pdf` to download the canonical PDF for object `Q123`; the handler fetches the bytes from storage and streams component blocks back.
- `handle_invoke`
  - **Motivation**: Trigger server-side workflows that derive new components or metadata from an object.
  - **Use case**: A client invokes the `equation_extraction` workflow on `Q123` to produce a JSON of extracted equations and receive the derived component and workflow result metadata.

## Protocol
- Header: `>BBBBHI`
- Blocks: metadata, component, workflow.

See `doip_server/protocol.py` for framing details.

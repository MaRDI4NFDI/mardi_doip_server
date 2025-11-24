# Client

## Overview
`doip_client` implements a strict DOIP v2.0 client that matches the server framing.

### Key operations
- `hello()`: Perform hello/health check.
- `list_ops()`: Fetch available operations.
- `retrieve(object_id, component=None)`: Retrieve metadata and components.
- `invoke(object_id, workflow, params=None)`: Trigger a workflow on the server.

## Usage
```python
from doip_client import StrictDOIPClient

client = StrictDOIPClient(host="127.0.0.1", port=3567, use_tls=False)
hello = client.hello()
retrieve = client.retrieve("Q123")
invoke = client.invoke("Q123", workflow="equation_extraction", params={})
```

Command-line example:
```bash
PYTHONPATH=. python -m client_cli.main --host 127.0.0.1 --port 3567 --no-tls --object-id Q123
```

## Protocol
- Header: `>BBBBHI`
- Blocks: metadata (0x01), component (0x02), workflow (0x03)

See `doip_client/protocol.py` for client-side framing helpers.

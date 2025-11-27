# Client

`doip_client` implements a strict DOIP v2.0 client that mirrors the server framing (binary envelope, metadata/component/workflow blocks) and supports TLS.

## Core operations
- `hello()`: Health check and capability discovery.
- `list_ops()`: Fetch the `availableOperations` map.
- `retrieve(object_id, component=None)`: Return metadata blocks or a specific component.
- `invoke(object_id, workflow, params=None)`: Trigger a workflow; receives workflow metadata and derived components.

## Usage
```python
from doip_client import StrictDOIPClient

client = StrictDOIPClient(host="127.0.0.1", port=3567, use_tls=False)
hello = client.hello()
ops = client.list_ops()
metadata = client.retrieve("Q123").metadata_blocks
pdf = client.retrieve("Q123", component="doip:bitstream/Q123/main-pdf")

# Invoke a workflow with parameters
result = client.invoke("Q123", workflow="equation_extraction", params={"pages": [1, 2, 3]})
```

### TLS & verification
Pass `use_tls=True` to wrap the socket. If you use self-signed certs during development, combine `use_tls=True` with `verify=False` to skip hostname verification.

### Timeouts & clean up
The client uses blocking sockets; wrap calls in your own timeout logic if needed. Always close the client when finished:
```python
client.close()
```

## Component handling
- For metadata-only requests, send no `component` and inspect `response.metadata_blocks`.
- For binaries, pass the component ID; the client returns `ComponentBlock` objects containing `component_id`, `media_type`, and `content` bytes.

## Compatibility listener support
The Python client speaks strict DOIP. To talk to the compatibility JSON-segment listener (`port + 1`), use the **Client CLI** which wraps the same client but performs JSON bridging for you.

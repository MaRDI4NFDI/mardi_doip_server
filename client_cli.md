# Client CLI

The `client_cli` module provides a minimal command-line interface around the DOIP client.

## Running
```bash
PYTHONPATH=. python -m client_cli.main --object-id Q123 --action retrieve 
```

Options:
- `--host`: DOIP server host (default `doip.staging.mardi4nfdi.org`)
- `--port`: DOIP server port (default `3567`)
- `--no-tls`: Disable TLS wrapping (useful for local plaintext servers)
- `--insecure`: Disable TLS certificate/hostname verification
- `--object-id`: Object identifier to retrieve (default `Q123`)
- `--action`: One of `demo`, `hello`, `retrieve`, `invoke` (default `demo`)
- `--component`: Component ID to retrieve (retrieve/demo actions)
- `--workflow`: Workflow name (invoke action, default `equation_extraction`)
- `--params`: Workflow parameters as JSON string (invoke action)
- `--output`: Path or directory to save the first retrieved component (retrieve action)
  - When saving to a directory, the original filename provided by the server is preserved when present.

### Actions
- `demo`: Runs `hello` then `retrieve`.
- `hello`: Runs only the hello operation.
- `retrieve`: Runs retrieve for the given object (and optional component).
- `invoke`: Runs a workflow for the given object with optional params.

### Example: Download a PDF
```bash
PYTHONPATH=. python -m client_cli.main --action retrieve --object-id Q6190920 --component fulltext --output .
```

### Example: Download a RO-CRATE
```bash
python -m client_cli.main --host localhost --no-tls --action retrieve --object-id Q6032968 --component rocrate --output crate.zip
```



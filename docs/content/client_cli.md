# Client CLI

The `client_cli` module provides a minimal command-line interface around the strict DOIP client.

## Running
```bash
PYTHONPATH=. python -m client_cli.main --host 127.0.0.1 --port 3567 --no-tls --object-id Q123
```

Options:
- `--host`: Server host (default `127.0.0.1`)
- `--port`: Server port (default `3567`)
- `--no-tls`: Disable TLS wrapping (useful for local plaintext servers)
- `--insecure`: Disable TLS certificate/hostname verification
- `--object-id`: Object identifier to retrieve (default `Q123`)
- `--action`: One of `demo`, `hello`, `retrieve`, `invoke` (default `demo`)
- `--component`: Component ID to retrieve (retrieve/demo actions)
- `--workflow`: Workflow name (invoke action, default `equation_extraction`)
- `--params`: Workflow parameters as JSON string (invoke action)

### Actions
- `demo`: Runs `hello` then `retrieve`.
- `hello`: Runs only the hello operation.
- `retrieve`: Runs retrieve for the given object (and optional component).
- `invoke`: Runs a workflow for the given object with optional params.

The CLI prints the resulting metadata and component counts for each action.

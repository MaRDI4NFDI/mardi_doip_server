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

The CLI issues `hello` and `retrieve` requests and prints the resulting metadata and component count.

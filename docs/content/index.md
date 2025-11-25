# Mardi DOIP Server & Client

Welcome to the documentation for the strict DOIP v2.0 server and client.

## Why DOIP and FDO?
- **FAIR Digital Objects (FDOs)** provide a persistent, structured way to describe research outputs. They carry metadata, identifiers, and links to content, enabling interoperability and long-term access.
- **Digital Object Interface Protocol (DOIP)** defines how to retrieve and operate on FDOs over the network using a consistent binary envelope. DOIP 2.0 specifies headers, block framing, and operation codes so clients and servers can exchange objects reliably.
- This implementation offers a strict DOIP v2.0 server and client so MARDI services can publish and consume FDO content (bitstreams, derived components, workflows) in a predictable, standards-based way.

## What’s here
- Server listens on TCP (default 3567) and uses strict DOIP framing.
- Client implements strict DOIP v2.0 over TCP/TLS with hello, list_ops, and retrieve.

Use the navigation to learn more about server handlers and client usage.

## Quick start example
Run the server (plaintext for local testing) and call it with the client:
```bash
# Terminal 1
PYTHONPATH=. python -m doip_server.main --port 3567

# Terminal 2
PYTHONPATH=. python -m client_cli.main --host 127.0.0.1 --port 3567 --no-tls --action retrieve --object-id Q6190920 --output .
```
The client will issue `hello` and `retrieve` requests using strict DOIP framing, print the returned metadata and component counts, and save the first component (using the server-provided filename when available).

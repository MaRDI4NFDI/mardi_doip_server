# Docker

Build and run the DOIP server in a container.

## Build
From the project root:
```bash
docker build -f docker/Dockerfile -t mardi-doip-server .
```

## Run
Expose the default DOIP port (plaintext) and the compatibility listener:
```bash
docker run --rm -p 3567:3567 -p 3568:3568 mardi-doip-server
```

### TLS
The server auto-enables TLS when both `certs/server.crt` and `certs/server.key` are present.

With Docker, mount your certificate directory into `/app/certs` so the container can detect and load them:
```bash
docker run --rm -p 3567:3567 -p 3568:3568 \
  -v $(pwd)/certs:/app/certs \
  mardi-doip-server
```

Inside the container, the entrypoint checks for `/app/certs/server.crt` and `/app/certs/server.key` and, if found, starts TLS listeners on 3567/3568. Without the mount, the server stays in plaintext mode.

The container entrypoint runs `python -m doip_server.main`.

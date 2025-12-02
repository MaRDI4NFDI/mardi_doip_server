# Server HTTP Gateway

This component provides a thin HTTP layer that forwards browser-friendly download requests to the internal DOIP server. It is served by FastAPI in `doip_server/http_gateway.py` and is intended for environments where a simple REST-style endpoint is preferred over the native DOIP protocol.

## Endpoint

- `GET /doip/retrieve/{object_id}/{component_id}`
  - Streams the first matching component block for the given object/component pair.
  - Sets `Content-Type` from the component's `media_type` (defaults to `application/octet-stream`).
  - Adds `Content-Disposition: attachment; filename="<component_id_basename>"` so browsers download instead of render.
  - Returns `404` if no component blocks are present; `502` for backend failures.

### Example

```bash
curl -OJ http://localhost/doip/retrieve/Q123/fulltext
```

## Backend connection

The gateway talks to the colocated DOIP server through `StrictDOIPClient` using these environment variables:

- `DOIP_HOST` (default `127.0.0.1`): hostname for the DOIP TCP endpoint; values like `tcp://host:port` are accepted.
- `DOIP_PORT` (default `3567`): port number; also parsed from `tcp://` or `host:port` forms.
- `DOIP_VERIFY_TLS` (default `false`): set to `true` to enable certificate verification when TLS is active.
- TLS is automatically enabled when `certs/server.crt` exists alongside the gateway image; override by setting `use_tls` in code or removing the cert.

## Static assets

The root path `/` serves the legacy landing page and associated assets from `/app/landing` using FastAPI's `StaticFiles` mount. This keeps the former download UI available without the DOIP protocol in the browser.

## Running locally

The Docker entrypoint starts the gateway with Uvicorn:

```bash
uvicorn doip_server.http_gateway:app --host 0.0.0.0 --port 80
```

For development you can run the same command from the repository root (inside an activated virtualenv) and then issue the `curl` example above.

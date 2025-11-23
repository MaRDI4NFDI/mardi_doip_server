"""Lightweight CLI for exercising the strict DOIP client."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser

from doip_client import StrictDOIPClient


def main(argv: list[str] | None = None) -> int:
    """Run a small demo CLI that exercises the strict client."""
    parser = ArgumentParser(description="Demo DOIP client CLI")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=3567, help="Server port")
    parser.add_argument("--no-tls", action="store_true", help="Disable TLS wrapping")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification")
    parser.add_argument("--object-id", default="Q123", help="Object identifier to use for demo calls")
    args = parser.parse_args(argv)

    client = StrictDOIPClient(
        host=args.host,
        port=args.port,
        use_tls=not args.no_tls,
        verify_tls=not args.insecure,
    )

    try:
        hello = client.hello()
        retrieve = client.retrieve(args.object_id)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"Error contacting DOIP server {args.host}:{args.port} "
            f"(tls={'off' if args.no_tls else 'on'}, verify={'off' if args.insecure else 'on'}): {exc}\n"
        )
        return 1

    print("Hello:", json.dumps(hello, indent=2))
    print("Retrieve metadata:", json.dumps(retrieve.metadata_blocks, indent=2))
    print(f"Retrieve components: {len(retrieve.component_blocks)} block(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Lightweight CLI for exercising the strict DOIP client."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser

from doip_client import StrictDOIPClient


def main(argv: list[str] | None = None) -> int:
    """Run a small demo CLI that exercises the strict client."""
    parser = ArgumentParser(description="MaRDI DOIP client CLI")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=3567, help="Server port")
    parser.add_argument("--no-tls", action="store_true", help="Disable TLS wrapping")
    parser.add_argument("--secure", action="store_true", help="Enable TLS verification (if you do not use a self-certified cert)")
    parser.add_argument("--object-id", default="Q123", help="Object identifier to use for demo calls")
    parser.add_argument(
        "--action",
        choices=["demo", "hello", "retrieve", "invoke"],
        default="demo",
        help="Action to execute",
    )
    parser.add_argument("--component", default=None, help="Component ID (for retrieve)")
    parser.add_argument("--workflow", default="equation_extraction", help="Workflow name (for invoke)")
    parser.add_argument("--params", default="{}", help="Workflow params as JSON string (for invoke)")
    args = parser.parse_args(argv)

    client = StrictDOIPClient(
        host=args.host,
        port=args.port,
        use_tls=not args.no_tls,
        verify_tls=args.secure,
    )

    try:
        if args.action == "hello":
            hello = client.hello()
            print("Hello:", json.dumps(hello, indent=2))
            return 0

        if args.action == "retrieve":
            retrieve = client.retrieve(args.object_id, component=args.component)
            print("Retrieve metadata:", json.dumps(retrieve.metadata_blocks, indent=2))
            print(f"Retrieve components: {len(retrieve.component_blocks)} block(s)")
            return 0

        if args.action == "invoke":
            try:
                params = json.loads(args.params)
            except Exception:  # noqa: BLE001
                params = {}
            invoke = client.invoke(args.object_id, args.workflow, params=params)
            print("Invoke metadata:", json.dumps(invoke.metadata_blocks, indent=2))
            print(f"Invoke components: {len(invoke.component_blocks)} block(s)")
            print("Workflow blocks:", json.dumps(invoke.workflow_blocks, indent=2))
            return 0

        # demo
        hello = client.hello()
        retrieve = client.retrieve(args.object_id, component=args.component)
        print("Hello:", json.dumps(hello, indent=2))
        print("Retrieve metadata:", json.dumps(retrieve.metadata_blocks, indent=2))
        print(f"Retrieve components: {len(retrieve.component_blocks)} block(s)")
        return 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"Error contacting DOIP server {args.host}:{args.port} "
            f"(tls={'off' if args.no_tls else 'on'}, verify={'off' if args.insecure else 'on'}): {exc}\n"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

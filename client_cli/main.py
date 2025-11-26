"""Lightweight CLI for exercising the strict DOIP client."""
# Example:
# python -m client_cli.main --action retrieve --object-id Q6190920 --output .

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser

from doip_client import StrictDOIPClient


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="MaRDI DOIP client CLI")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=3567, help="Server port")
    parser.add_argument("--no-tls", action="store_true", help="Disable TLS wrapping")
    parser.add_argument(
        "--secure",
        action="store_true",
        help="Enable TLS verification (if you do not use a self-certified cert)",
    )
    parser.add_argument(
        "--object-id",
        default="Q123",
        help="Object identifier to use for demo calls",
    )
    parser.add_argument(
        "--action",
        choices=["demo", "hello", "list_ops", "retrieve", "invoke"],
        default="demo",
        help="Action to execute",
    )
    # component removed: server no longer supports component selection
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save first component (retrieve only). If not specified, component is not saved.",
    )
    parser.add_argument(
        "--workflow",
        default="equation_extraction",
        help="Workflow name (for invoke)",
    )
    parser.add_argument(
        "--params",
        default="{}",
        help="Workflow params as JSON string (for invoke)",
    )

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

        if args.action == "list_ops":
            ops = client.list_ops()
            print("Available operations:", json.dumps(ops, indent=2))
            return 0

        if args.action == "retrieve":
            resp = client.retrieve(args.object_id)
            print("Retrieve metadata:", json.dumps(resp.metadata_blocks, indent=2))
            print(f"Retrieve components: {len(resp.component_blocks)} block(s)")
            if args.output:
                path = StrictDOIPClient.save_first_component(resp, output_path=args.output)
                print(f"Saved first component to: {path}")
            return 0

        if args.action == "invoke":
            try:
                params = json.loads(args.params)
            except Exception:
                params = {}
            resp = client.invoke(args.object_id, args.workflow, params=params)
            print("Invoke metadata:", json.dumps(resp.metadata_blocks, indent=2))
            print(f"Invoke components: {len(resp.component_blocks)} block(s)")
            print("Workflow blocks:", json.dumps(resp.workflow_blocks, indent=2))
            return 0

        # demo mode
        hello = client.hello()
        resp = client.retrieve(args.object_id)
        print("Hello:", json.dumps(hello, indent=2))
        print("Retrieve metadata:", json.dumps(resp.metadata_blocks, indent=2))
        print(f"Retrieve components: {len(resp.component_blocks)} block(s)")
        return 0

    except Exception as exc:
        sys.stderr.write(
            f"Error contacting DOIP server {args.host}:{args.port} "
            f"(tls={'off' if args.no_tls else 'on'}, verify_tls={'on' if args.secure else 'off'}): {exc}\n"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

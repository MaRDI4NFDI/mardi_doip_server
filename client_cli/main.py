"""Lightweight CLI for exercising the strict DOIP client."""
# Example:
# python -m client_cli.main --action retrieve --object-id Q6190920 --output .

from __future__ import annotations

import json
import logging
import sys
from argparse import ArgumentParser

from doip_client import StrictDOIPClient

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True
)

def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for interacting with the strict DOIP client.

    Args:
        argv: Optional list of arguments (defaults to ``sys.argv``).

    Returns:
        int: Process exit code (0 on success, non-zero on error).
    """
    parser = ArgumentParser(description="MaRDI DOIP client CLI")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=3567, help="Server port")
    parser.add_argument("--no-tls", action="store_true", help="Disable TLS wrapping")
    parser.add_argument("--secure", action="store_true", help="Enable TLS verification (if you do not use a self-certified cert)")
    parser.add_argument("--object-id", default="Q123", help="Object identifier")
    parser.add_argument("--component", default=None, help="Component ID for selective retrieve; if absent, list components")
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

    logging.getLogger().debug("Handling action: %s", args.action)

    try:
        if args.action == "hello":
            r = client.hello()
            print(json.dumps(r, indent=2))
            return 0

        if args.action == "list_ops":
            r = client.list_ops()
            print(json.dumps(r, indent=2))
            return 0

        if args.action == "retrieve":
            if args.component:
                r = client.retrieve(args.object_id, component_id=args.component)
                blocks = r.component_blocks
                if not blocks:
                    logging.getLogger().error("Component %s not found.", args.component)
                    return 1
                media_type = blocks[0].media_type
                content = blocks[0].content
                if args.output:
                    with open(args.output, "wb") as f:
                        f.write(content)
                    logging.getLogger().info(f"Wrote to file %s - contains media type '%s' ", args.output, media_type )
                    return 0
                # stdout binary
                sys.stdout.buffer.write(content)
                logging.getLogger().info(f"\n\n Output contains media type '%s' ", args.output, media_type )
                return 0

            # Show only meta data - no binary data
            r = client.retrieve(args.object_id)
            print("Metadata:")
            print(json.dumps(r.metadata_blocks, indent=2))

            return 0

        if args.action == "invoke":
            try:
                p = json.loads(args.params)
            except Exception:
                p = {}
            r = client.invoke(args.object_id, args.workflow, params=p)
            print(json.dumps(r.metadata_blocks, indent=2))
            return 0

        r = client.hello()
        print(json.dumps(r, indent=2))
        meta = client.retrieve(args.object_id)
        print(json.dumps(meta.metadata_blocks, indent=2))
        return 0

    except Exception as exc:
        sys.stderr.write(
            f"Error contacting DOIP server {args.host}:{args.port}: {exc}\n"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

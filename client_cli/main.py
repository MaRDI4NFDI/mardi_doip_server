"""Lightweight CLI stub for experimenting with the DOIP client."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser

from doip_client.mock import MockDoipClient


def main(argv: list[str] | None = None) -> int:
    """Run a small demo CLI that exercises the mock client."""
    parser = ArgumentParser(description="Demo DOIP client CLI")
    parser.add_argument("--object-id", default="Q123", help="Object identifier to use for demo calls")
    parser.add_argument("--workflow", default="equation_extraction", help="Workflow name for invoke demo")
    args = parser.parse_args(argv)

    client = MockDoipClient(responses={})

    hello = client.hello()
    retrieve = client.retrieve(args.object_id)
    invoke = client.invoke(args.object_id, args.workflow)

    print("Hello:", json.dumps(hello, indent=2))
    print("Retrieve:", json.dumps(retrieve, indent=2))
    print("Invoke:", json.dumps(invoke, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Lightweight CLI for exercising the strict DOIP client."""
# Example:
# python -m client_cli.main --action retrieve --object-id Q6190920 --output .

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import textwrap

from doip_shared.constants import MARDI_PROFILE_TYPES

from argparse import (
    ArgumentParser,
    RawDescriptionHelpFormatter,
    ArgumentDefaultsHelpFormatter,
)

from doip_client import StrictDOIPClient

_LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

_VERSION_FILE = pathlib.Path(__file__).parent.parent / "VERSION"
_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"

_DESCRIPTION = (
    f"This is the MaRDI DOIP client (version {_VERSION}).\n\n"
    "This client enables direct interaction with the MaRDI DOIP server for retrieving object "
    "metadata or content, and executing predefined server workflows.\n"
    "To see a demo with standard values, execute: mardi-doip-cli --action demo\n"
    "For more information see: https://mardi4nfdi.github.io/mardi_doip_server/"
)

_ACTIONS = ("demo", "hello", "list_ops", "retrieve", "update", "invoke", "purge", "create", "search")

_ACTION_HELP: dict[str, dict] = {
    "hello": {
        "description": "Send a Hello request to the DOIP server.",
        "details": (
            "Checks connectivity and retrieves basic server information such as the server "
            "identifier and supported protocol version. Useful to verify that the server is "
            "reachable and responding before running other actions."
        ),
        "options": [],
        "examples": [
            ("Check the default MaRDI server", "mardi-doip-cli --action hello"),
            ("Check a local server without TLS", "mardi-doip-cli --action hello --host localhost --port 3567 --no-tls"),
        ],
    },
    "list_ops": {
        "description": "List all operations supported by the DOIP server.",
        "details": (
            "Queries the server for its advertised operation identifiers. The returned list "
            "shows which DOIP operations (e.g. retrieve, update, create) are available, and "
            "can be used to discover custom workflows exposed by a specific server deployment."
        ),
        "options": [],
        "examples": [
            ("List operations on the default server", "mardi-doip-cli --action list_ops"),
            ("List operations on a custom server", "mardi-doip-cli --action list_ops --host my.server.org --port 3567"),
        ],
    },
    "demo": {
        "description": "Run a quick demo: Hello + retrieve metadata for --object-id.",
        "details": (
            "Runs two requests in sequence: a Hello to confirm connectivity, followed by a "
            "metadata retrieve for the given object. Intended as a quick smoke-test to verify "
            "that the full request/response cycle works end-to-end."
        ),
        "options": [
            ("--object-id ID", "Object identifier (default: Q123)"),
        ],
        "examples": [
            ("Run demo with default object", "mardi-doip-cli --action demo"),
            ("Run demo with a specific object", "mardi-doip-cli --action demo --object-id Q6190920"),
        ],
    },
    "retrieve": {
        "description": "Retrieve an object's metadata or a specific component.",
        "details": (
            "Without --component, prints the object's metadata blocks as JSON. "
            "With --component, fetches only that component's binary content: use --output to "
            "write it to a file, or omit --output to stream raw bytes to stdout. "
            "Component IDs are listed in the metadata under the 'components' field."
        ),
        "options": [
            ("--object-id ID", "Object identifier (default: Q123)"),
            ("--component ID", "Component ID for selective retrieve; if absent, shows metadata"),
            ("--output PATH", "Save fetched component to this file (binary; stdout if omitted)"),
        ],
        "examples": [
            ("Show metadata for an object", "mardi-doip-cli --action retrieve --object-id Q6190920"),
            ("Download a component to a file", "mardi-doip-cli --action retrieve --object-id Q6190920 --component data --output ./data.bin"),
            ("Stream a component to stdout", "mardi-doip-cli --action retrieve --object-id Q6190920 --component data"),
        ],
    },
    "update": {
        "description": "Upload a new file component, or update Wikibase item properties.",
        "details": (
            "Two modes:\n"
            "  Component mode (--input + --component): replaces the content of a named "
            "component with the bytes from --input. The --media-type flag sets the MIME "
            "type; defaults to application/octet-stream.\n"
            "  Property mode (--properties): updates label, description, or claims on the "
            "Wikibase item identified by --object-id. Supply a JSON object with any of: "
            "label (str), description (str), claims (dict of pid→value or pid→[values]), "
            "do_override (bool). If a property already has values and do_override is not "
            "set, the call is refused and the existing values are returned. With "
            "do_override=true, supply the complete new set — existing values are replaced.\n"
            "Both modes require wiki bot credentials via --username/--password or the "
            "DOIP_USERNAME/DOIP_PASSWORD environment variables. "
            "Bot passwords can be created at Special:BotPasswords on the wiki."
        ),
        "options": [
            ("--object-id ID", "Object identifier (default: Q123)"),
            ("--component ID", "Component ID to update (required for component mode)"),
            ("--input PATH", "File to upload (required for component mode)"),
            ("--media-type TYPE", "Media type (default: application/octet-stream)"),
            ("--properties JSON", "JSON object of properties to update (property mode)"),
            ("--username USER", "Wiki bot username (User@AppName); falls back to DOIP_USERNAME"),
            ("--password PASS", "Wiki bot password; falls back to DOIP_PASSWORD"),
        ],
        "examples": [
            ("Update a PDF component",
             "mardi-doip-cli --action update --object-id Q6190920 --component paper"
             " --input paper_v2.pdf --media-type application/pdf"
             " --username MyUser@MyBot --password abc123"),
            ("Add an author claim (property not yet set)",
             "mardi-doip-cli --action update --object-id Q6190920"
             " --username MyUser@MyBot --password abc123"
             ' --properties \'{"claims": {"P16": "Q482723"}}\''),
            ("Override an author claim with two authors",
             "mardi-doip-cli --action update --object-id Q6190920"
             " --username MyUser@MyBot --password abc123"
             ' --properties \'{"claims": {"P16": ["Q111", "Q482723"]}, "do_override": true}\''),
            ("Change the item label",
             "mardi-doip-cli --action update --object-id Q6190920"
             " --username MyUser@MyBot --password abc123"
             ' --properties \'{"label": "New title"}\''),
            ("Use environment variables instead of flags",
             "DOIP_USERNAME=MyUser@MyBot DOIP_PASSWORD=abc123"
             " mardi-doip-cli --action update --object-id Q6190920"
             ' --properties \'{"label": "New title"}\''),
        ],
    },
    "invoke": {
        "description": "Invoke a server-side workflow on an object.",
        "details": (
            "Triggers a named workflow that the server applies to the specified object. "
            "Results are returned as metadata blocks. The default workflow 'equation_extraction' "
            "extracts mathematical equations from a stored document. Additional workflows may "
            "be discovered via the list_ops action."
        ),
        "options": [
            ("--object-id ID", "Object identifier (default: Q123)"),
            ("--workflow NAME", "Workflow name (default: equation_extraction)"),
            ("--params JSON", "Workflow params as JSON string (default: {})"),
        ],
        "examples": [
            ("Run equation extraction on an object",
             "mardi-doip-cli --action invoke --object-id Q6190920 --workflow equation_extraction"),
            ("Run a workflow with parameters",
             'mardi-doip-cli --action invoke --object-id Q6190920 --workflow equation_extraction'
             ' --params \'{"max_equations": 50}\''),
        ],
    },
    "purge": {
        "description": "Invalidate the server-side cached manifest for an object.",
        "details": (
            "Evicts the object's manifest from the server's in-memory cache, forcing a fresh "
            "fetch from the FDO façade on the next access. Does not delete the object or any "
            "of its components."
        ),
        "options": [
            ("--object-id ID", "Object identifier (default: Q123)"),
        ],
        "examples": [
            ("Purge an object", "mardi-doip-cli --action purge --object-id Q6190920"),
            ("Purge on a custom server",
             "mardi-doip-cli --action purge --object-id Q6190920 --host my.server.org"),
        ],
    },
    "create": {
        "description": "Create a new Wikibase item on the MaRDI portal.",
        "details": (
            "Submits a JSON description to create a new item. Two formats are accepted. "
            "Raw format: JSON must include at least a 'label' field; optionally 'description' "
            "and 'claims' (mapping of property IDs such as P31 to values) may be provided. "
            "Typed format: supply 'type': 'WORKFLOW' and a 'fields' object. "
            "Required fields: 'name', 'problem_statement'. "
            "Optional fields: 'uses' (QID), 'author' (QID), 'publication_date' (string), "
            "'copyright_license' (QID), 'cites_work' (QID). "
            "Storage fields: 'fdo_component_id' (string, e.g. rocrate.zip) may be given alone "
            "or together with 'stored_at' (QID); omitting 'stored_at' defaults to the MaRDI "
            "data store (Q6830870). "
            "The server automatically sets instance-of claims "
            "(research workflow + script-based workflow) and the MaRDI profile type. "
            "An authorization token is required either via --token or the DOIP_CREATE_TOKEN "
            "environment variable. On success, the new item's QID is returned."
        ),
        "options": [
            ("--json JSON", "Item description as a JSON string (required); raw or typed format"),
            ("--username USER", "Wiki bot username (User@AppName); falls back to DOIP_USERNAME"),
            ("--password PASS", "Wiki bot password; falls back to DOIP_PASSWORD"),
        ],
        "examples": [
            ("Create a minimal item (raw format)",
             'mardi-doip-cli --action create --json \'{"label": "My dataset"}\''
             ' --username MyUser@MyBot --password abc123'),
            ("Create with explicit MaRDI KG claims (raw format)",
             'mardi-doip-cli --action create'
             ' --json \'{"label": "My item", "description": "A test", "claims": {"<MaRDI-PID>": "<MaRDI-QID>"}}\''
             ' --username MyUser@MyBot --password abc123'),
            ("Create a workflow item (required fields only)",
             'mardi-doip-cli --action create'
             ' --json \'{"type": "WORKFLOW", "fields": {"name": "Reproduce table 1 from ...", "problem_statement": "Solve incompressible Navier-Stokes"}}\''
             ' --username MyUser@MyBot --password abc123'),
            ("Create a workflow item (all fields)",
             'mardi-doip-cli --action create'
             ' --json \'{"type": "WORKFLOW", "fields": {"name": "My workflow", "problem_statement": "...", "uses": "Q6830878", "author": "Q482723", "publication_date": "2026-04-09", "copyright_license": "Q57031", "cites_work": "Q12345", "stored_at": "Q6830870", "fdo_component_id": "rocrate.zip"}}\''
             ' --username MyUser@MyBot --password abc123'),
            ("Use environment variables instead of flags",
             'DOIP_USERNAME=MyUser@MyBot DOIP_PASSWORD=abc123 mardi-doip-cli --action create'
             ' --json \'{"type": "WORKFLOW", "fields": {"name": "My workflow", "problem_statement": "..."}}\''),
        ],
    },
    "search": {
        "description": "Search the MaRDI knowledge graph.",
        "details": (
            "Runs a fulltext search against the MaRDI portal via the MediaWiki search API. "
            "Returns a list of matching items with their QIDs, titles, and snippets. "
            "Use --type to filter by MaRDI profile type (e.g. workflow, dataset, person). "
            "At least one of --query or --type must be provided. "
            "Without --type, search is restricted to Items. "
            f"Known types: {', '.join(sorted(MARDI_PROFILE_TYPES))}."
        ),
        "options": [
            ("--query QUERY", "Fulltext search string"),
            ("--type TYPE", f"Filter by MaRDI profile type name or raw QID (e.g. workflow, dataset)"),
            ("--limit N", "Maximum results to return (1–50, default 10)"),
        ],
        "examples": [
            ("Search for a DOI",
             'mardi-doip-cli --action search --query "10.1103/PHYSREVA.88.052328"'),
            ("Find persons named Conrad",
             'mardi-doip-cli --action search --query "Conrad" --type person'),
            ("List all workflows",
             'mardi-doip-cli --action search --type workflow --limit 20'),
            ("Find datasets about quantum entanglement",
             'mardi-doip-cli --action search --query "quantum entanglement" --type dataset'),
            ("Filter by raw QID",
             'mardi-doip-cli --action search --type Q6534216 --limit 10'),
        ],
    },
}


def print_mardi_logo():
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    ORANGE = "\033[38;5;208m"
    RESET = "\033[0m"

    mardi_nfo = r"""
██▄  ▄██  ▄▄▄  █████▄  ████▄  ██   ██  ██   ███  ██ ██████ ████▄  ██
██ ▀▀ ██ ██▀██ ██▄▄██▄ ██  ██ ██   ▀█████   ██ ▀▄██ ██▄▄   ██  ██ ██
██    ██ ██▀██ ██   ██ ████▀  ██       ██   ██   ██ ██     ████▀  ██
"""
    print(ORANGE + mardi_nfo + RESET)


def _fmt_option_table(options: list[tuple[str, str]], indent: int = 2) -> str:
    if not options:
        return ""
    col_width = max(len(flag) for flag, _ in options) + 4
    pad = " " * indent
    return "\n".join(f"{pad}{flag:<{col_width}}{desc}" for flag, desc in options)


def _print_global_help() -> None:
    actions_str = "{" + ",".join(_ACTIONS) + "}"
    print(
        f"usage: mardi-doip-cli [-h] [--host HOST] [--port PORT] [--no-tls] [--secure]\n"
        f"                      [--action {actions_str}]\n"
        f"                      [action-specific options]\n"
    )
    print(_DESCRIPTION)
    print()
    global_opts = [
        ("-h, --help", "show this help; '--help action [name]' for action-specific help"),
        ("--host HOST", "DOIP Server hostname (default: doip.portal.mardi4nfdi.org)"),
        ("--port PORT", "Server port (default: 3567)"),
        ("--no-tls", "Disable TLS wrapping"),
        ("--secure", "Enable TLS verification"),
        ("--no-banner", "Suppress banner and all log output; print only raw JSON"),
        ("--action ACTION", "Action to execute: " + ", ".join(_ACTIONS)),
    ]
    print("options:")
    print(_fmt_option_table(global_opts))
    print()
    print("Use '--help action' to list all action-specific options.")
    print("Use '--help action <name>' for help on a specific action.")


def _print_all_actions_help() -> None:
    print("Action-specific options:\n")
    for name in _ACTIONS:
        info = _ACTION_HELP[name]
        print(f"  {name}")
        print(f"    {info['description']}")
        if info["options"]:
            print(_fmt_option_table(info["options"], indent=4))
        print()
    print("Use '--help action <name>' for full details and examples.")


def _print_action_help(action: str) -> None:
    if action not in _ACTION_HELP:
        print(f"Unknown action: {action!r}")
        print(f"Available actions: {', '.join(_ACTIONS)}")
        return
    info = _ACTION_HELP[action]
    print(f"Action: {action}")
    print(f"  {info['description']}\n")
    for line in textwrap.wrap(info["details"], width=78, initial_indent="  ", subsequent_indent="  "):
        print(line)
    print()
    print("Global options always apply: --host, --port, --no-tls, --secure\n")
    if info["options"]:
        print("Options:")
        print(_fmt_option_table(info["options"]))
        print()
    examples = info.get("examples", [])
    if examples:
        print("Examples:")
        for label, cmd in examples:
            print(f"  # {label}")
            print(f"  {cmd}")
            print()


class RawDescriptionDefaultsHelpFormatter(
    RawDescriptionHelpFormatter,
    ArgumentDefaultsHelpFormatter,
):
    pass


def _resolve_cli_credentials(
    explicit_username: str | None,
    explicit_password: str | None,
) -> tuple[str | None, str | None]:
    username = explicit_username or os.getenv("DOIP_USERNAME")
    password = explicit_password or os.getenv("DOIP_PASSWORD")
    return username or None, password or None


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]

    no_banner = "--no-banner" in args_list
    if no_banner:
        logging.disable(logging.CRITICAL)
    else:
        logging.basicConfig(level=logging.DEBUG, format=_LOG_FORMAT, force=True)
        print_mardi_logo()

    # Handle help before argparse so we can show global vs action-specific views.
    for flag in ("-h", "--help"):
        if flag in args_list:
            idx = args_list.index(flag)
            rest = args_list[idx + 1:]
            if rest and rest[0] == "action":
                if len(rest) >= 2:
                    _print_action_help(rest[1])
                else:
                    _print_all_actions_help()
            else:
                _print_global_help()
            return 0

    parser = ArgumentParser(
        prog="mardi-doip-cli",
        description=_DESCRIPTION,
        formatter_class=RawDescriptionDefaultsHelpFormatter,
        add_help=False,
    )

    parser.add_argument("--host", default="doip.portal.mardi4nfdi.org", help="DOIP Server hostname")
    parser.add_argument("--port", type=int, default=3567, help="Server port")
    parser.add_argument("--no-tls", action="store_true", help="Disable TLS wrapping")
    parser.add_argument("--secure", action="store_true", help="Enable TLS verification")
    parser.add_argument("--no-banner", action="store_true", help="Suppress banner and all log output; print only raw JSON")
    parser.add_argument("--object-id", default="Q123", help="Object identifier")
    parser.add_argument("--component", default=None, help="Component ID for selective retrieve")
    parser.add_argument("--action", choices=list(_ACTIONS), help="Action to execute")
    parser.add_argument("--output", default=None, help="Path to save first component (retrieve only)")
    parser.add_argument("--input", default=None, help="Path to the file to upload for update")
    parser.add_argument("--media-type", default=None, help="Media type for update uploads")
    parser.add_argument("--username", default=None, help="Wiki bot username (User@AppName); falls back to DOIP_USERNAME")
    parser.add_argument("--password", default=None, help="Wiki bot password; falls back to DOIP_PASSWORD")
    parser.add_argument("--workflow", default="equation_extraction", help="Workflow name (for invoke)")
    parser.add_argument("--params", default="{}", help="Workflow params as JSON string (for invoke)")
    parser.add_argument(
        "--properties",
        default=None,
        metavar="JSON",
        help=(
            "JSON object of Wikibase properties to update (for update action, property mode). "
            "Keys: label (str), description (str), claims (dict), do_override (bool). "
            "Mutually exclusive with --input/--component."
        ),
    )
    parser.add_argument(
        "--json",
        default=None,
        metavar="JSON",
        help=(
            "JSON string describing the item to create (for create). "
            "Raw format: '{\"label\": \"My item\", \"claims\": {\"<MaRDI-PID>\": \"<MaRDI-QID>\"}}'. "
            "Typed format: '{\"type\": \"WORKFLOW\", \"fields\": {\"name\": \"...\", \"problem_statement\": \"...\"}}'. "
            "Known types: WORKFLOW."
        ),
    )
    parser.add_argument("--query", default=None, help="Search string (for search action)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum results for search (1–50, default 10)")
    parser.add_argument(
        "--type",
        default=None,
        metavar="TYPE",
        help=(
            f"MaRDI profile type for search: name (e.g. workflow, dataset) or raw QID. "
            f"Known names: {', '.join(sorted(MARDI_PROFILE_TYPES))}."
        ),
    )
    # --token kept as a hidden alias for backwards compatibility but --username/--password are canonical


    args = parser.parse_args(args_list)

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
                    logging.getLogger().info("Wrote to file %s - contains media type '%s'", args.output, media_type)
                    return 0
                sys.stdout.buffer.write(content)
                logging.getLogger().info("\n\n Output contains media type '%s'", media_type)
                return 0

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

        if args.action == "update":
            username, password = _resolve_cli_credentials(args.username, args.password)
            if not username or not password:
                logging.getLogger().error(
                    "Update requires --username/--password or DOIP_USERNAME/DOIP_PASSWORD env vars. "
                    "Create a bot password at Special:BotPasswords on the wiki."
                )
                return 1

            if args.properties is not None:
                if args.input or args.component:
                    logging.getLogger().error(
                        "--properties and --input/--component are mutually exclusive."
                    )
                    return 1
                try:
                    props = json.loads(args.properties)
                except json.JSONDecodeError as exc:
                    logging.getLogger().error("Invalid JSON in --properties: %s", exc)
                    return 1
                if not isinstance(props, dict):
                    logging.getLogger().error("--properties must be a JSON object.")
                    return 1
                r = client.update_properties(args.object_id, props, username=username, password=password)
                print(json.dumps(r.metadata_blocks, indent=2))
                return 0

            if not args.component:
                logging.getLogger().error("--component is required for component update.")
                return 1
            if not args.input:
                logging.getLogger().error("--input is required for component update.")
                return 1

            with open(args.input, "rb") as f:
                content = f.read()

            media_type = args.media_type or "application/octet-stream"
            r = client.update_component(
                args.object_id,
                args.component,
                content,
                media_type=media_type,
                username=username,
                password=password,
            )
            print(json.dumps(r.metadata_blocks, indent=2))
            return 0

        if args.action == "purge":
            r = client.purge(args.object_id)
            print(json.dumps(r, indent=2))
            return 0

        if args.action == "create":
            if not args.json:
                logging.getLogger().error(
                    "--json is required for create. "
                    "Example: --json '{\"label\": \"My item\"}'"
                )
                return 1
            username, password = _resolve_cli_credentials(args.username, args.password)
            if not username or not password:
                logging.getLogger().error(
                    "Create requires --username/--password or DOIP_USERNAME/DOIP_PASSWORD env vars. "
                    "Create a bot password at Special:BotPasswords on the wiki."
                )
                return 1
            r = client.create(args.json, username=username, password=password)
            print(json.dumps(r.metadata_blocks, indent=2))
            return 0

        if args.action == "search":
            if not args.query and not args.type:
                logging.getLogger().error("--query or --type (or both) is required for search.")
                return 1
            r = client.search(args.query, limit=args.limit, type=args.type)
            print(json.dumps(r.metadata_blocks, indent=2))
            return 0

        if args.action == "demo":
            logging.getLogger().info("Contacting DOIP server (using: %s:%s)...", args.host, args.port)
            r = client.hello()
            print(json.dumps(r, indent=2))
            meta = client.retrieve(args.object_id)
            print(json.dumps(meta.metadata_blocks, indent=2))
            return 0

        # No action selected, show brief usage
        print(parser.format_usage(), end="")
        print(f"\n{_DESCRIPTION}\n")
        print("options:")
        print("  -h, --help            show more help")
        return 1

    except Exception as exc:
        sys.stderr.write(
            f"Error contacting DOIP server {args.host}:{args.port}: {exc}\n"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

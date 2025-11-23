#!/usr/bin/env bash
set -euo pipefail

# Build MkDocs site into docs/site using the local config.
cd "$(dirname "${BASH_SOURCE[0]}")"
mkdocs build --config-file mkdocs.yml

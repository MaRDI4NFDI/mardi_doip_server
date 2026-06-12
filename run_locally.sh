#!/usr/bin/env bash
# Run the DOIP server locally pointed at the staging or production importer.
#
# Usage:
#   ./run_locally.sh              # staging (default)
#   ./run_locally.sh production   # production
#
# Variables are pulled automatically from Kubernetes. Create a .env file in
# this directory to override any value.
#
# Importer must be port-forwarded before starting this script:
#   staging:    kubectl port-forward svc/staging-importer -n staging 8000:80
#   production: kubectl port-forward svc/importer -n production 8000:80

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV="${1:-}"
if [[ -z "$ENV" ]]; then
    echo "Usage: $0 <staging|production>"
    echo ""
    echo "Before running, port-forward the importer in a separate terminal:"
    echo "  staging:    kubectl port-forward svc/staging-importer -n staging 8000:80"
    echo "  production: kubectl port-forward svc/importer -n production 8000:80"
    exit 0
fi
if [[ "$ENV" == "production" ]]; then
    K8S_NAMESPACE="production"
    K8S_SECRET="doip-secrets"
    K8S_DEPLOYMENT="doip"
else
    K8S_NAMESPACE="staging"
    K8S_SECRET="staging-doip-secrets"
    K8S_DEPLOYMENT="staging-doip"
fi

# .env overrides everything — load first so kubectl fills only what's missing
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
    echo "Loaded $SCRIPT_DIR/.env"
fi

# Pull missing vars from Kubernetes
if command -v kubectl &>/dev/null; then
    echo "Pulling config from Kubernetes ($ENV)..."

    _secret() {
        kubectl get secret "$K8S_SECRET" -n "$K8S_NAMESPACE" \
            -o "jsonpath={.data.$1}" 2>/dev/null | base64 -d 2>/dev/null || true
    }

    _deploy_env() {
        kubectl get deployment "$K8S_DEPLOYMENT" -n "$K8S_NAMESPACE" -o json 2>/dev/null \
            | python3 -c "
import json, sys
envs = json.load(sys.stdin)['spec']['template']['spec']['containers'][0]['env']
print(next((e['value'] for e in envs if e['name'] == '$1'), ''))
" 2>/dev/null || true
    }

    LAKEFS_PASSWORD="${LAKEFS_PASSWORD:-$(_secret LAKEFS_PASSWORD)}"
    LAKEFS_USER="${LAKEFS_USER:-$(_secret LAKEFS_USER)}"
    LAKEFS_URL="${LAKEFS_URL:-$(_deploy_env LAKEFS_URL)}"
    LAKEFS_REPO="${LAKEFS_REPO:-$(_deploy_env LAKEFS_REPO)}"
fi

IMPORTER_API_URL="${IMPORTER_API_URL:-http://localhost:8000}"
FDO_API="${FDO_API:-https://fdo.portal.mardi4nfdi.de/fdo/}"

: "${LAKEFS_PASSWORD:?Could not retrieve LAKEFS_PASSWORD — check kubectl access or set it in .env}"

export LAKEFS_PASSWORD LAKEFS_USER LAKEFS_URL LAKEFS_REPO IMPORTER_API_URL FDO_API

PORT="${DOIP_PORT:-3567}"

echo "DOIP server  → localhost:$PORT"
echo "Importer API → $IMPORTER_API_URL"
echo "FDO API      → $FDO_API"
echo "lakeFS       → ${LAKEFS_URL:-<not set>} / ${LAKEFS_REPO:-<not set>}"
echo ""

VENV="$SCRIPT_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -r "$SCRIPT_DIR/requirements.txt"
# Add the repo root to the venv's path so local packages are importable
SITE_PACKAGES="$("$VENV/bin/python" -c "import site; print(site.getsitepackages()[0])")"
echo "$SCRIPT_DIR" > "$SITE_PACKAGES/doip_local.pth"

cd "$SCRIPT_DIR"
exec python -m doip_server.main --port "$PORT"

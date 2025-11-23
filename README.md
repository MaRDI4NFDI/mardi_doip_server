# Mardi DOIP Server

Asyncio-based DOIP 2.0 TCP server that fronts the MARDI FDO infrastructure. The server listens on port 3567, uses strict DOIP binary envelopes, streams components from lakeFS (S3-compatible), and integrates with the FDO FastAPI façade and a MediaWiki/Wikibase backend for derived items.

## Getting Started
- Requirements: Python 3.10+, `pip install -r requirements.txt`.
- Environment (example for lakeFS/MinIO):
  - `LAKEFS_ENDPOINT=http://localhost:8000`
  - `S3_BUCKET=mardi-fdo`
  - `AWS_ACCESS_KEY_ID=...`
  - `AWS_SECRET_ACCESS_KEY=...`
  - Optional: `FDO_API=https://fdo.portal.mardi4nfdi.de/fdo/`, `MEDIAWIKI_API=https://www.wikidata.org/w/api.php`

Run the server:
```bash
python -m doip_server.main           # binds 0.0.0.0:3567
```
Run the demo mock client:
```bash
PYTHONPATH=. python -m client_cli.main
```
TLS (optional):
- Place `certs/server.crt` and `certs/server.key` (PEM) to enable TLS automatically; otherwise the server speaks plaintext DOIP.
- A compatibility listener runs on port 3568 (same TLS setting) accepting doipy JSON-segmented requests and bridging to the DOIP handlers.
## Usage Notes
- Retrieve (op 0x02): client sends DOIP request with object ID and optional component list; server returns metadata + binary component blocks.
- Invoke (op 0x05): client includes `workflow` and params; the sample workflow generates derived components and MediaWiki items.
- Component IDs map to S3 keys by convention: `doip:bitstream/Q123/main-pdf` → `mardi-fdo/Q123/main-pdf.pdf` (suffix inferred when missing).

## Project layout
- `doip_server/`: server package and TCP handlers
- `doip_client/`: client package with a mock implementation
- `client_cli/`: CLI entry point wrapping the client
- `scripts/`: helper scripts for running server/client locally
- `config/`: sample configuration files
- `docs/`: project documentation
- `tests/server/`: server-focused test suite (PYTHONPATH=. pytest tests/server)

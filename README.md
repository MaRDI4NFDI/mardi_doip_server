# Mardi DOIP Server

Asyncio-based DOIP 2.0 TCP server that fronts the MARDI FDO infrastructure. The server listens on port 3567, uses strict DOIP binary envelopes, streams components from lakeFS (S3-compatible), and integrates with the FDO FastAPI façade and a MediaWiki/Wikibase backend for derived items.

## Documentation
[![Documentation](https://img.shields.io/badge/docs-gh--pages-blue)](https://mardi4nfdi.github.io/mardi_doip_server/)

- Built with MkDocs; see `docs/build_docs.sh` or browse source in `docs/content/`.



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
Run the client CLI:
```bash
PYTHONPATH=. python -m client_cli.main
```
Use the strict DOIP client in Python:
```python
from doip_client import StrictDOIPClient

client = StrictDOIPClient(host="127.0.0.1", port=3567, use_tls=False)
hello = client.hello()
metadata = client.retrieve("Q123").metadata_blocks
```
TLS (optional):
- Place `certs/server.crt` and `certs/server.key` (PEM) to enable TLS automatically; otherwise the server speaks plaintext DOIP.
- A compatibility listener runs on port 3568 (same TLS setting) accepting doipy JSON-segmented requests and bridging to the DOIP handlers.
## Usage Notes
- Retrieve (op 0x02): client sends DOIP request with object ID and optional component list; server returns metadata + binary component blocks.
- Invoke (op 0x05): client includes `workflow` and params; the sample workflow generates derived components and MediaWiki items.
- Component IDs map to S3 keys by convention: `doip:bitstream/Q123/main-pdf` → `mardi-fdo/Q123/main-pdf.pdf` (suffix inferred when missing).


# Mardi DOIP Server

Asyncio-based DOIP 2.0 TCP server that fronts the MARDI FDO infrastructure. The server listens on port 3567, uses strict DOIP binary envelopes, streams components from lakeFS (S3-compatible), and integrates with the FDO FastAPI façade and a MediaWiki/Wikibase backend for derived items.

## Documentation
[![Documentation](https://img.shields.io/badge/docs-gh--pages-blue)](https://mardi4nfdi.github.io/mardi_doip_server/)

- Built with MkDocs; see `docs/build_docs.sh` or browse source in `docs/content/`.



## Getting Started
- Requirements: 
  - `pip install -r requirements.txt`.
- Configuration:
  - Either create `config.yaml` and set configuration details.
  - Or use environment variables - they override values from the config file where applicable
    - `LAKEFS_USER` / `LAKEFS_PASSWORD` 
    - `LAKEFS_URL` / `LAKEFS_REPO`
    - `FDO_API`
    - `OLLAMA_API_KEY`

Run the server:
```bash
python -m doip_server.main           # binds 0.0.0.0:3567
```
or, to use a custom FDO server endpoint:
```bash
python -m doip_server.main --fdo-api http://127.0.0.1:8000/fdo/
```


Run the client CLI:

Retrieve meta-data about an FDO, e.g. a publication with QID Q6190920:

```bash
PYTHONPATH=. python -m client_cli.main --host 127.0.0.1 --no-tls --action retrieve --object-id Q6190920 
```

Retrieve the fulltext pdf from a FDO publication:

```bash
PYTHONPATH=. python -m client_cli.main --host 127.0.0.1 --no-tls --action retrieve --object-id Q6190920 --component fulltext --output pdf.pdf
```


Use the DOIP client in Python:
```python
from doip_client import StrictDOIPClient

client = StrictDOIPClient(host="127.0.0.1", port=3567, use_tls=False)
hello = client.hello()
metadata = client.retrieve("Q123").metadata_blocks
```

## TLS (optional):
- Place `certs/server.crt` and `certs/server.key` (PEM) to enable TLS automatically; otherwise the server speaks plaintext DOIP.
- A compatibility listener runs on port 3568 (same TLS setting) accepting doipy JSON-segmented requests and bridging to the DOIP handlers.

## Usage Notes
- Retrieve (op 0x02): client sends DOIP request with object ID and optional component list; server returns metadata + binary component blocks.
- Invoke (op 0x05): client includes `workflow` and params; the sample workflow generates derived components and MediaWiki items.
- Component IDs map to lakeFS keys with repo/branch/object_id: e.g., `fulltext` -> `repo/branch/Q123/fulltext.pdf`. 

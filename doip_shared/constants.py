"""Shared DOIP constants used by both server and client."""

DOIP_VERSION = 0x02

# Message types
MSG_TYPE_REQUEST = 0x01
MSG_TYPE_RESPONSE = 0x02
MSG_TYPE_ERROR = 0x7F

# Operation codes
OP_HELLO = 0x01
OP_RETRIEVE = 0x02
OP_UPDATE = 0x03
OP_LIST_OPS = 0x04
OP_INVOKE = 0x05
OP_DESCRIBE = 0x06
OP_PURGE = 0x07
OP_CREATE = 0x08
OP_SEARCH = 0x09

# Block types
BLOCK_METADATA = 0x01
BLOCK_COMPONENT = 0x02
BLOCK_WORKFLOW = 0x03

# Short type IDs of MaRDI-owned type FDOs served at {FDO_API}/types/{type_id}.
# These are advertised in HELLO responses so clients can discover the type registry.
KNOWN_TYPE_IDS = [
    "ScholarlyArticle",
    "Dataset",
    "Workflow",
    "Person",
    "SoftwareApplication",
    "SoftwareSourceCode",
]

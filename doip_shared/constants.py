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

# MaRDI profile type QIDs (values of property P1460).
MARDI_PROFILE_TYPES: dict[str, str] = {
    "formula":             "Q5981696",
    "quantity":            "Q6534271",
    "software":            "Q5976450",
    "person":              "Q5976445",
    "publication":         "Q5976449",
    "academic_discipline": "Q6534268",
    "dataset":             "Q5984635",
    "community":           "Q6205095",
    "algorithm":           "Q6503323",
    "workflow":            "Q6534216",
    "theorem":             "Q6534201",
    "service":             "Q6503324",
    "research_problem":    "Q6534269",
    "model":               "Q6534270",
    "task":                "Q6534272",
    "jupyter_notebook":    "Q6767917",
}

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

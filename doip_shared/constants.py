"""Shared DOIP constants used by both server and client."""

DOIP_VERSION = 0x02

# Message types
MSG_TYPE_REQUEST = 0x01
MSG_TYPE_RESPONSE = 0x02
MSG_TYPE_ERROR = 0x7F

# Operation codes
OP_HELLO = 0x01
OP_RETRIEVE = 0x02
OP_LIST_OPS = 0x04
OP_INVOKE = 0x05

# Block types
BLOCK_METADATA = 0x01
BLOCK_COMPONENT = 0x02
BLOCK_WORKFLOW = 0x03

"""LangGraph serialization configuration for custom types.

Registers custom types (DataFlag, Severity) with LangGraph's JsonPlusSerializer
to enable proper checkpoint serialization.
"""

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.utils.flags import DataFlag, Severity


def get_serializer() -> JsonPlusSerializer:
    """Get a JsonPlusSerializer with custom types registered.

    Returns a serializer with DataFlag and Severity added to the msgpack allowlist.
    This ensures these types can be properly serialized/deserialized in checkpoints.
    """
    base_serializer = JsonPlusSerializer()
    return base_serializer.with_msgpack_allowlist([DataFlag, Severity])

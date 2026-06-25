"""Core serial communication and sequence encoding."""

from core.comm_service import CommService, ErrorEvent, RxEvent, TxEvent
from core.sequence_codec import SequenceEncodeError, encode_sequence

__all__ = [
    "CommService",
    "ErrorEvent",
    "RxEvent",
    "TxEvent",
    "SequenceEncodeError",
    "encode_sequence",
]

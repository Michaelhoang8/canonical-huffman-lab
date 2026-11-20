"""Canonical Huffman byte codec and strict CHUF v1 container."""

from .codec import CodecError, compress, decompress, inspect_header

__all__ = ["CodecError", "compress", "decompress", "inspect_header"]

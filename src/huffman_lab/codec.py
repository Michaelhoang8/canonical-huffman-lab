"""Deterministic byte Huffman coding with a bounded, fully checked container.

This is an educational format, not an interoperable or hardened production codec.
No compression library is used for its entropy coding; zlib supplies CRC-32 only.
"""

from collections import Counter
import heapq
import struct
import zlib

MAGIC = b"CHUF"
VERSION = 1
HEADER = struct.Struct(">4sBBHQQI")
DEFAULT_MAX_OUTPUT = 16 * 1024 * 1024
DEFAULT_MAX_CONTAINER = 32 * 1024 * 1024


class CodecError(ValueError):
    """An invalid input, container or resource limit."""


def _bytes(value, limit=None):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("Expected bytes-like input")
    size = value.nbytes if isinstance(value, memoryview) else len(value)
    if limit is not None and size > limit:
        raise CodecError("Input exceeds configured byte limit")
    return bytes(value)


def _limit(value, name):
    if type(value) is not int or value < 0:
        raise CodecError(f"{name} must be a nonnegative integer")


def code_lengths(data):
    """Build lengths with deterministic (frequency, smallest-symbol) tie breaks."""
    frequencies = Counter(data)
    heap = [(count, symbol, symbol) for symbol, count in frequencies.items()]
    heapq.heapify(heap)
    if not heap:
        return {}
    if len(heap) == 1:
        return {heap[0][1]: 1}
    while len(heap) > 1:
        first_weight, first_symbol, first = heapq.heappop(heap)
        second_weight, second_symbol, second = heapq.heappop(heap)
        heapq.heappush(
            heap,
            (
                first_weight + second_weight,
                min(first_symbol, second_symbol),
                (first, second),
            ),
        )
    lengths = {}
    pending = [(heap[0][2], 0)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, int):
            lengths[node] = depth
        else:
            pending.extend([(node[0], depth + 1), (node[1], depth + 1)])
    return lengths


def canonical_codes(lengths):
    """Validate a complete prefix table and assign codes by (length, symbol)."""
    if len(lengths) > 256:
        raise CodecError("More than 256 symbols")
    for symbol, length in lengths.items():
        if type(symbol) is not int or not 0 <= symbol <= 255:
            raise CodecError("Symbol must be a byte")
        if type(length) is not int or not 1 <= length <= 255:
            raise CodecError("Code lengths must lie in 1..255")
    if not lengths:
        return {}
    if len(lengths) == 1:
        if next(iter(lengths.values())) != 1:
            raise CodecError("A single symbol must use length 1 and code 0")
    else:
        longest = max(lengths.values())
        occupied = sum(1 << (longest - length) for length in lengths.values())
        capacity = 1 << longest
        if occupied > capacity:
            raise CodecError("Oversubscribed prefix table")
        if occupied < capacity:
            raise CodecError("Incomplete prefix table")
    codes = {}
    code = previous_length = 0
    for symbol, length in sorted(lengths.items(), key=lambda pair: (pair[1], pair[0])):
        code <<= length - previous_length
        if code >= 1 << length:
            raise CodecError("Canonical code exceeds its declared width")
        codes[symbol] = code, length
        code += 1
        previous_length = length
    return codes


def compress(data, max_input=DEFAULT_MAX_OUTPUT):
    """Encode bytes. Equal inputs always produce identical CHUF bytes."""
    _limit(max_input, "max_input")
    data = _bytes(data, max_input)
    if len(data) > max_input:
        raise CodecError("Input exceeds configured limit")
    lengths = code_lengths(data)
    codes = canonical_codes(lengths)
    payload = bytearray()
    accumulator = pending_bits = payload_bits = 0
    for symbol in data:
        code, width = codes[symbol]
        accumulator = (accumulator << width) | code
        pending_bits += width
        payload_bits += width
        while pending_bits >= 8:
            pending_bits -= 8
            payload.append((accumulator >> pending_bits) & 255)
            accumulator &= (1 << pending_bits) - 1
    if pending_bits:
        payload.append(accumulator << (8 - pending_bits))
    header = HEADER.pack(
        MAGIC,
        VERSION,
        0,
        len(lengths),
        len(data),
        payload_bits,
        zlib.crc32(data) & 0xFFFFFFFF,
    )
    table = bytes(value for pair in sorted(lengths.items()) for value in pair)
    return header + table + bytes(payload)


def inspect_header(
    container, max_output=DEFAULT_MAX_OUTPUT, max_container=DEFAULT_MAX_CONTAINER
):
    """Validate structural fields without claiming that the payload is valid."""
    _limit(max_output, "max_output")
    _limit(max_container, "max_container")
    container = _bytes(container, max_container)
    if len(container) > max_container:
        raise CodecError("Container exceeds configured limit")
    if len(container) < HEADER.size:
        raise CodecError("Truncated fixed header")
    magic, version, flags, count, original_size, bit_count, checksum = (
        HEADER.unpack_from(container)
    )
    if magic != MAGIC or version != VERSION or flags != 0:
        raise CodecError("Unsupported magic, version or flags")
    if count > 256:
        raise CodecError("More than 256 symbols")
    if original_size > max_output:
        raise CodecError("Declared output exceeds configured limit")
    header_bytes = HEADER.size + 2 * count
    if len(container) < header_bytes:
        raise CodecError("Truncated symbol table")
    lengths = {}
    previous_symbol = -1
    for offset in range(HEADER.size, header_bytes, 2):
        symbol, length = container[offset : offset + 2]
        if symbol <= previous_symbol:
            raise CodecError("Symbol table must be unique and strictly sorted")
        lengths[symbol] = length
        previous_symbol = symbol
    canonical_codes(lengths)
    if original_size == 0:
        if count != 0 or bit_count != 0 or checksum != 0:
            raise CodecError(
                "Empty streams require an empty table, no bits and zero CRC"
            )
    else:
        if not count or original_size < count:
            raise CodecError("Nonempty stream has an invalid alphabet size")
        if (
            not original_size * min(lengths.values())
            <= bit_count
            <= original_size * max(lengths.values())
        ):
            raise CodecError(
                "Payload bit count is inconsistent with output size and lengths"
            )
    payload_bytes = (bit_count + 7) // 8
    if len(container) != header_bytes + payload_bytes:
        raise CodecError("Truncated payload or trailing bytes")
    padding = (-bit_count) % 8
    if padding and container[-1] & ((1 << padding) - 1):
        raise CodecError("Nonzero padding bits")
    return {
        "original_size": original_size,
        "payload_bits": bit_count,
        "header_bytes": header_bytes,
        "payload_bytes": payload_bytes,
        "symbol_count": count,
        "lengths": lengths,
        "crc32": checksum,
        "padding_bits": padding,
    }


def decompress(
    container, max_output=DEFAULT_MAX_OUTPUT, max_container=DEFAULT_MAX_CONTAINER
):
    """Decode only fully conforming streams within explicit size limits."""
    info = inspect_header(container, max_output, max_container)
    container = _bytes(container, max_container)
    codes = canonical_codes(info["lengths"])
    # At most 511 nodes for a full 256-leaf tree; the single-symbol exception
    # has only a root and its zero child. No table scales with payload size.
    children = [[-1, -1]]
    symbols = [-1]
    for symbol, (code, width) in codes.items():
        node = 0
        for shift in range(width - 1, -1, -1):
            bit = (code >> shift) & 1
            if children[node][bit] == -1:
                children[node][bit] = len(children)
                children.append([-1, -1])
                symbols.append(-1)
            node = children[node][bit]
        symbols[node] = symbol
    decoded = bytearray()
    used = set()
    node = 0
    payload = memoryview(container)[info["header_bytes"] :]
    for index in range(info["payload_bits"]):
        bit = (payload[index // 8] >> (7 - index % 8)) & 1
        node = children[node][bit]
        if node == -1:
            raise CodecError("Payload uses a nonexistent code")
        if symbols[node] != -1:
            if len(decoded) >= info["original_size"]:
                raise CodecError("Decoded output exceeds declared size")
            decoded.append(symbols[node])
            used.add(symbols[node])
            node = 0
    if node != 0:
        raise CodecError("Payload ends inside a code")
    if len(decoded) != info["original_size"]:
        raise CodecError("Decoded size differs from declaration")
    if used != set(info["lengths"]):
        raise CodecError("Table declares symbols absent from the output")
    if zlib.crc32(decoded) & 0xFFFFFFFF != info["crc32"]:
        raise CodecError("CRC-32 mismatch")
    return bytes(decoded)

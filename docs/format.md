# CHUF version 1 binary format

CHUF is this repository's educational canonical Huffman container. It is not compatible with DEFLATE, gzip, ZIP, or another existing file format. Multi-byte integer fields use unsigned big-endian encoding. Byte symbols are integers from 0 through 255.

## Fixed header

The fixed header is 28 bytes, equivalent to Python `struct.Struct(">4sBBHQQI")`.

| Offset | Bytes | Field | Required value or meaning |
| ---: | ---: | --- | --- |
| 0 | 4 | Magic | ASCII `CHUF`, hex `43 48 55 46` |
| 4 | 1 | Version | `01` |
| 5 | 1 | Flags | `00`; other values are rejected |
| 6 | 2 | Symbol count | Number of table entries, 0–256 |
| 8 | 8 | Original size | Exact number of decoded bytes |
| 16 | 8 | Payload bit count | Exact number of meaningful bits |
| 24 | 4 | CRC-32 | `zlib.crc32(original) & 0xffffffff` |

The header is followed by `symbol_count` two-byte records: one byte for the symbol, then one byte for its code length. Records are in strictly increasing symbol order. Every listed symbol must appear at least once in the decoded output.

The payload follows immediately. It has exactly `(payload_bit_count + 7) // 8` bytes. No trailer, concatenated stream or trailing byte is permitted.

## Code lengths and canonical assignment

Lengths lie in 1–255. For two or more symbols, they must satisfy the complete prefix condition:

```text
sum(2 ** (L - length[s])) == 2 ** L, where L = max(length.values())
```

This integer form avoids floating-point rounding. A larger sum is oversubscribed and cannot represent a prefix code. A smaller sum is an incomplete prefix table; CHUF deliberately rejects it. Incomplete prefix codes can be unambiguous, but they are outside this format's multi-symbol policy.

Assign codes in increasing `(length, symbol)` order:

```text
code = 0
previous_length = 0
for symbol, length in sorted entries:
    code <<= length - previous_length
    assign symbol the low 'length' bits of code
    code += 1
    previous_length = length
```

Code bits are emitted most-significant first. Complete groups of eight bits become payload bytes. Any unused low bits of the last byte must be zero. The decoder reads exactly the declared bit count and must finish at a code boundary.

The encoder constructs a Huffman tree by repeatedly joining the two smallest weights. Ties use the smallest symbol in each disjoint subtree. This makes lengths deterministic. Canonical assignment then makes wire codes deterministic. The decoder accepts any complete canonical table satisfying the container rules; it does not require that the table be optimal for the decoded frequencies.

## Empty and single-symbol inputs

Empty input requires zero original size, symbol count, payload bit count and CRC, and has no table or payload. Its complete representation is 28 bytes.

A single-symbol table must give its symbol length 1 and code `0`. It emits one zero bit for each original byte. This exception is intentionally not a complete two-branch tree. The payload bit count must equal the original size, and any `1` data bit is invalid.

## Independent fixture: ABBA

The original bytes are hex `41 42 42 41`. A and B both have length 1, with canonical codes A=`0` and B=`1`. The meaningful payload is `0110`. Four zero padding bits produce byte `60`. The CRC is `B266E56B`.

```text
43 48 55 46                         magic
01                                  version
00                                  flags
00 02                               two symbols
00 00 00 00 00 00 00 04             four original bytes
00 00 00 00 00 00 00 04             four meaningful bits
B2 66 E5 6B                         original CRC-32
41 01 42 01                         A:1, B:1
60                                  0110 + zero padding
```

The complete fixture is 33 bytes. Its test constructs these bytes independently of the encoder and header helper.

## Decoder validation and limits

`inspect_header()` validates framing, table lengths, declared sizes and padding. Its success does not imply that the payload decodes correctly. `decompress()` additionally requires valid code paths, a final code boundary, exact output size, usage of every declared symbol and the matching CRC.

Default input/output bounds are 32 MiB of container bytes and 16 MiB of decoded bytes. Both are checked before payload decoding. The implementation checks the byte size of a memoryview before copying it. It never trusts the declared output size as an instruction to allocate that size up front.

The validated complete tree uses at most 511 nodes for 256 symbols. The singleton exception uses two. Decoding performs one traversal step per meaningful bit. A byte cap limits work indirectly; it does not provide a time limit, and the Python bit loop can be slow for large permitted inputs. Callers dealing with hostile files would need a threat-model-specific process and time budget in addition to these checks.

CRC-32 detects accidental damage and does not provide authenticity. This follows the distinction in the [Python zlib documentation](https://docs.python.org/3.13/library/zlib.html#zlib.crc32).

## References

Huffman tree construction follows the minimum weighted prefix-code problem described by D. A. Huffman, [“A Method for the Construction of Minimum-Redundancy Codes,” 1952](https://web.stanford.edu/class/ee398a/handouts/papers/Huffman%20-%20Min%20Redundancy%20Codes%20-%20IRE52.pdf), DOI `10.1109/JRPROC.1952.273898`.

Canonical length ordering also appears in [RFC 1951, section 3.2.2](https://www.rfc-editor.org/rfc/rfc1951.html#section-3.2.2). CHUF uses its own container and MSB-first payload rule; it does not implement DEFLATE's packing, block layout or sequence matching.

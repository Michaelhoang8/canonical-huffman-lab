"""File CLI with bounded reads and exclusive output creation."""

import argparse
import json
from pathlib import Path
import sys
from .codec import (
    CodecError,
    DEFAULT_MAX_CONTAINER,
    DEFAULT_MAX_OUTPUT,
    compress,
    decompress,
    inspect_header,
)


def main():
    parser = argparse.ArgumentParser(description="CHUF v1 canonical Huffman codec")
    parser.add_argument("operation", choices=["compress", "decompress", "inspect"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument(
        "--max-output",
        type=int,
        default=DEFAULT_MAX_OUTPUT,
        help="Decoded byte limit (default 16 MiB)",
    )
    args = parser.parse_args()
    if args.operation == "inspect" and args.output is not None:
        parser.error("inspect writes JSON to stdout and does not accept an output file")
    if args.operation != "inspect" and args.output is None:
        parser.error("compress and decompress require an output file")
    limit = (
        DEFAULT_MAX_OUTPUT if args.operation == "compress" else DEFAULT_MAX_CONTAINER
    )
    try:
        with args.input.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise CodecError("Input file exceeds the CLI read limit")
        result = (
            compress(data)
            if args.operation == "compress"
            else decompress(data, max_output=args.max_output)
        )
        if args.operation == "inspect":
            # Full decoding above validates every payload bit, output length,
            # symbol and CRC. Structural header inspection alone cannot do so.
            info = inspect_header(data, max_output=args.max_output)
            print(
                json.dumps(
                    {
                        "format": "CHUF",
                        "version": 1,
                        "payload_validated": True,
                        "container_bytes": len(data),
                        "original_bytes": len(result),
                        "header_bytes": info["header_bytes"],
                        "payload_bytes": info["payload_bytes"],
                        "payload_bits": info["payload_bits"],
                        "padding_bits": info["padding_bits"],
                        "symbol_count": info["symbol_count"],
                        "crc32": f'{info["crc32"]:08X}',
                        "container_ratio": len(data) / len(result) if result else None,
                    },
                    indent=2,
                )
            )
            return 0
        with args.output.open("xb") as stream:
            stream.write(result)
    except (CodecError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{len(data):,} input bytes -> {len(result):,} output bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

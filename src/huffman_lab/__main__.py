"""File CLI with bounded reads and exclusive output creation."""

import argparse
from pathlib import Path
import sys
from .codec import (
    CodecError,
    DEFAULT_MAX_CONTAINER,
    DEFAULT_MAX_OUTPUT,
    compress,
    decompress,
)


def main():
    parser = argparse.ArgumentParser(description="CHUF v1 canonical Huffman codec")
    parser.add_argument("operation", choices=["compress", "decompress"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--max-output",
        type=int,
        default=DEFAULT_MAX_OUTPUT,
        help="Decoded byte limit (default 16 MiB)",
    )
    args = parser.parse_args()
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
        with args.output.open("xb") as stream:
            stream.write(result)
    except (CodecError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{len(data):,} input bytes -> {len(result):,} output bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Roundtrip properties, independent wire fixture and malformed-stream cases."""

from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huffman_lab.codec import (
    CodecError,
    canonical_codes,
    compress,
    decompress,
    inspect_header,
)


def wire(table, size, bits, payload, checksum=0, version=1, flags=0):
    return (
        struct.pack(
            ">4sBBHQQI", b"CHUF", version, flags, len(table), size, bits, checksum
        )
        + bytes(value for pair in table for value in pair)
        + payload
    )


class CodecChecks(unittest.TestCase):
    def test_independent_abba_fixture(self):
        # Fixed wire bytes: A=0, B=1, ABBA=0110, 4 low padding zeros.
        fixture = bytes.fromhex(
            "43485546 01 00 0002 0000000000000004 0000000000000004 b266e56b 4101 4201 60"
        )
        self.assertEqual(decompress(fixture), b"ABBA")
        self.assertEqual(compress(b"ABBA"), fixture)

    def test_empty_single_symbol_and_full_byte_alphabet(self):
        for source in [b"", b"X", b"X" * 33, bytes(range(256)), bytes(range(256)) * 9]:
            with self.subTest(length=len(source)):
                packed = compress(source)
                self.assertEqual(decompress(packed), source)
                info = inspect_header(packed)
                self.assertEqual(
                    len(packed), info["header_bytes"] + info["payload_bytes"]
                )
        self.assertEqual(len(compress(b"")), 28)
        self.assertEqual(inspect_header(compress(b"X" * 33))["payload_bits"], 33)
        self.assertEqual(
            inspect_header(compress(bytes(range(256))))["payload_bits"], 2048
        )

    def test_seeded_roundtrip_and_prefix_properties(self):
        rng = random.Random(11202026)
        for _ in range(250):
            alphabet = rng.sample(range(256), rng.randint(1, 256))
            source = bytes(rng.choice(alphabet) for _ in range(rng.randrange(2049)))
            packed = compress(source)
            self.assertEqual(compress(source), packed)
            self.assertEqual(decompress(packed), source)
            info = inspect_header(packed)
            self.assertEqual(
                info["payload_bits"], sum(info["lengths"][value] for value in source)
            )
            encoded = [
                format(code, f"0{width}b")
                for code, width in canonical_codes(info["lengths"]).values()
            ]
            for i, first in enumerate(encoded):
                self.assertFalse(
                    any(
                        second.startswith(first)
                        for j, second in enumerate(encoded)
                        if i != j
                    )
                )

    def test_rejects_malformed_prefix_tables(self):
        bad = [
            [(65, 0)],
            [(65, 2)],
            [(65, 1), (66, 1), (67, 1)],
            [(65, 2), (66, 2)],
            [(65, 1), (65, 1)],
            [(66, 1), (65, 1)],
            [(65, 1), (66, 255)],
        ]
        for table in bad:
            with self.subTest(table=table), self.assertRaises(CodecError):
                decompress(wire(table, max(1, len(table)), 8, b"\0"))

    def test_rejects_truncation_trailing_bytes_padding_and_checksum_changes(self):
        valid = compress(b"ABBA")
        for size in range(len(valid)):
            with self.subTest(truncate=size), self.assertRaises(CodecError):
                decompress(valid[:size])
        for altered in [valid + b"\0", valid[:-1] + b"\x61", valid[:-1] + b"\x20"]:
            with self.assertRaises(CodecError):
                decompress(altered)
        for version, flags in [(2, 0), (1, 1)]:
            with self.assertRaises(CodecError):
                decompress(wire([], 0, 0, b"", version=version, flags=flags))

    def test_rejects_dangling_code_output_mismatch_and_unused_symbols(self):
        table = [(65, 1), (66, 2), (67, 2)]
        cases = [
            wire(table, 3, 4, b"\x50"),  # 0,10,1: final code is incomplete.
            wire(table, 3, 4, b"\x00"),  # Four A symbols exceed declared size.
            wire(table, 4, 5, b"\x58"),  # ABC gives three bytes, not four.
            wire(table, 3, 3, b"\x00", zlib.crc32(b"AAA")),
            wire([(65, 1)], 1, 1, b"\x80", zlib.crc32(b"A")),
        ]
        for container in cases:
            with self.assertRaises(CodecError):
                decompress(container)

    def test_resource_limits_reject_before_output_allocation(self):
        valid = compress(b"A" * 100)
        with self.assertRaises(CodecError):
            decompress(valid, max_output=99)
        with self.assertRaises(CodecError):
            decompress(valid, max_container=len(valid) - 1)
        with self.assertRaises(CodecError):
            compress(b"AB", max_input=1)
        with self.assertRaises(CodecError):
            decompress(valid, max_output=-1)
        with self.assertRaises(CodecError):
            decompress(valid, max_output=True)
        impossible = wire([(65, 1)], 2**63, 2**63, b"")
        with self.assertRaises(CodecError):
            decompress(impossible)
        self.assertEqual(decompress(compress(b""), max_output=0), b"")

    def test_random_malformed_inputs_fail_cleanly(self):
        rng = random.Random(991)
        for _ in range(500):
            blob = rng.randbytes(rng.randrange(600))
            with self.assertRaises(CodecError):
                decompress(blob, max_output=4096, max_container=4096)

    def test_cli_roundtrip_and_exclusive_output(self):
        import os

        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "input.bin"
            source.write_bytes(b"ABCABAA" * 50)
            packed = folder / "data.chuf"
            restored = folder / "restored.bin"
            for operation, left, right in [
                ("compress", source, packed),
                ("decompress", packed, restored),
            ]:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "huffman_lab",
                        operation,
                        str(left),
                        str(right),
                    ],
                    env=env,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_bytes(), restored.read_bytes())
            retry = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "huffman_lab",
                    "decompress",
                    str(packed),
                    str(restored),
                ],
                env=env,
                capture_output=True,
            )
            self.assertEqual(retry.returncode, 2)
            self.assertEqual(source.read_bytes(), restored.read_bytes())


if __name__ == "__main__":
    unittest.main()

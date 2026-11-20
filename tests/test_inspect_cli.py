"""CLI inspection must validate the payload and leave all input bytes intact."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InspectCommand(unittest.TestCase):
    def test_inspection_validates_complete_wire_fixture_without_writing(self):
        # Independently specified ABBA fixture from the format documentation.
        wire = bytes.fromhex(
            "434855460100000200000000000000040000000000000004B266E56B4101420160"
        )
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "abba.chuf"
            source.write_bytes(wire)
            command = [sys.executable, "-m", "huffman_lab", "inspect", str(source)]
            inspected = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=10
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(
                json.loads(inspected.stdout),
                {
                    "format": "CHUF",
                    "version": 1,
                    "payload_validated": True,
                    "container_bytes": 33,
                    "original_bytes": 4,
                    "header_bytes": 32,
                    "payload_bytes": 1,
                    "payload_bits": 4,
                    "padding_bits": 4,
                    "symbol_count": 2,
                    "crc32": "B266E56B",
                    "container_ratio": 8.25,
                },
            )
            self.assertEqual(source.read_bytes(), wire)
            self.assertEqual(list(Path(folder).iterdir()), [source])
            # Structural fields and zero padding remain valid; only full decode
            # can detect the changed content against its original checksum.
            damaged = wire[:-1] + b"\x70"
            source.write_bytes(damaged)
            invalid = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=10
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual(invalid.stdout, "")
            self.assertIn("CRC-32 mismatch", invalid.stderr)
            self.assertEqual(source.read_bytes(), damaged)


if __name__ == "__main__":
    unittest.main()

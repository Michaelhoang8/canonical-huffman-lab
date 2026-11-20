from collections import Counter
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huffman_lab.codec import decompress, inspect_header


class EvidenceChecks(unittest.TestCase):
    def test_preserved_bytes_and_metrics_reconcile(self):
        folder = Path(os.environ.get("HUFFMAN_RESULTS", ROOT / "results/published"))
        environment = json.loads((folder / "environment.json").read_text())
        for relative, expected in environment["source_sha256_lf"].items():
            normalized = (
                (ROOT / relative)
                .read_bytes()
                .replace(b"\r\n", b"\n")
                .replace(b"\r", b"\n")
            )
            self.assertEqual(hashlib.sha256(normalized).hexdigest(), expected)
        manifest = json.loads((folder / "manifest.json").read_text())
        with (folder / "summary.csv").open() as stream:
            summary = list(csv.DictReader(stream))
        with (folder / "measurements.csv").open() as stream:
            timings = list(csv.DictReader(stream))
        self.assertEqual(len(timings), environment["raw_timing_rows"])
        self.assertEqual(len(timings), len(manifest) * environment["repetitions"] * 4)
        self.assertEqual(len(summary), len(manifest) * 2)
        for record in manifest:
            name = record["name"]
            data = (folder / "corpora" / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
            self.assertEqual(len(data), record["bytes"])
            histogram = Counter(data)
            entropy = (
                -sum(
                    count / len(data) * math.log2(count / len(data))
                    for count in histogram.values()
                )
                if data
                else 0.0
            )
            for method in ["chuf", "zlib"]:
                packed = (folder / "encoded" / f"{name}.{method}").read_bytes()
                self.assertEqual(
                    hashlib.sha256(packed).hexdigest(), record[f"{method}_sha256"]
                )
                self.assertEqual(
                    decompress(packed) if method == "chuf" else zlib.decompress(packed),
                    data,
                )
                row = next(
                    r for r in summary if r["corpus"] == name and r["method"] == method
                )
                self.assertEqual(int(row["container_bytes"]), len(packed))
                self.assertAlmostEqual(
                    float(row["empirical_nH_bits"]), len(data) * entropy
                )
                if data:
                    self.assertAlmostEqual(float(row["ratio"]), len(packed) / len(data))
                else:
                    self.assertEqual(row["ratio"], "")
                if method == "chuf":
                    info = inspect_header(packed)
                    self.assertEqual(int(row["header_bytes"]), info["header_bytes"])
                    self.assertEqual(int(row["payload_bits"]), info["payload_bits"])
                    self.assertGreaterEqual(
                        info["payload_bits"] + 1e-8, len(data) * entropy
                    )
                for operation in ["encode", "decode"]:
                    samples = [
                        int(t["elapsed_ns"])
                        for t in timings
                        if t["corpus"] == name
                        and t["operation"] == f"{method}_{operation}"
                    ]
                    self.assertEqual(len(samples), environment["repetitions"])
                    self.assertEqual(
                        float(row[f"{operation}_median_ns"]), statistics.median(samples)
                    )
                    self.assertEqual(int(row[f"{operation}_min_ns"]), min(samples))
                    self.assertEqual(int(row[f"{operation}_max_ns"]), max(samples))
                    self.assertTrue(all(t > 0 for t in samples))


if __name__ == "__main__":
    unittest.main()

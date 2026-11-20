"""Generate synthetic corpora and record complete-container sizes and timings."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huffman_lab.codec import compress, decompress, inspect_header


def corpora():
    rng = random.Random(20261120)
    records = []
    for index in range(1800):
        record = {
            "id": index,
            "region": rng.choice(["north", "south", "east", "west"]),
            "status": rng.choice(["ready", "ready", "ready", "queued", "failed"]),
            "quantity": rng.randint(1, 8),
            "sku": f"P{rng.randint(1,40):03d}",
        }
        records.append(json.dumps(record, separators=(",", ":")))
    sentences = [
        "The test fixture contains repeated words and predictable separators.",
        "Each record is generated for a controlled compression experiment.",
        "The report compares a byte histogram with repeated byte sequences.",
        "No document in this dataset comes from a person or an organization.",
    ]
    text = (
        "\n".join(f"{i:04d} {sentences[i%len(sentences)]}" for i in range(1400)) + "\n"
    )
    return {
        "empty.bin": b"",
        "small.txt": b"canonical Huffman example\n",
        "single_symbol.bin": b"A" * 65536,
        "skewed_symbols.bin": bytes(
            rng.choices([65, 66, 67, 68], weights=[12, 2, 1, 1], k=65536)
        ),
        "uniform_seeded.bin": rng.randbytes(65536),
        "byte_cycle.bin": bytes(range(256)) * 256,
        "structured_records.jsonl": ("\n".join(records) + "\n").encode("utf-8"),
        "repeated_text.txt": text.encode("utf-8"),
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def study(output, repetitions=7):
    output = Path(output)
    if (output / "measurements.csv").exists():
        raise FileExistsError(
            "Choose a new directory; previous measurements are preserved"
        )
    if not 1 <= repetitions <= 100:
        raise ValueError("Repetitions must lie in 1..100")
    for folder in ["corpora", "encoded"]:
        (output / folder).mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    source_hashes = {}
    for relative in ["src/huffman_lab/codec.py", "scripts/run_study.py"]:
        normalized = (
            (ROOT / relative).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        )
        source_hashes[relative] = hashlib.sha256(normalized).hexdigest()
    inputs = corpora()
    manifest = []
    summary = []
    measurements = []
    order = random.Random(55130)
    for name, data in inputs.items():
        path = output / "corpora" / name
        path.write_bytes(data)
        counts = Counter(data)
        entropy = (
            -sum(
                (count / len(data)) * math.log2(count / len(data))
                for count in counts.values()
            )
            if data
            else 0.0
        )
        packed = compress(data)
        wrapped = zlib.compress(data, level=9)
        (output / "encoded" / f"{name}.chuf").write_bytes(packed)
        (output / "encoded" / f"{name}.zlib").write_bytes(wrapped)
        assert decompress(packed) == data and zlib.decompress(wrapped) == data
        info = inspect_header(packed)
        manifest.append(
            {
                "name": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "chuf_sha256": hashlib.sha256(packed).hexdigest(),
                "zlib_sha256": hashlib.sha256(wrapped).hexdigest(),
            }
        )
        # Warm each exact operation once. The timed repeats alternate in seeded order.
        operations = {
            "chuf_encode": lambda: compress(data),
            "chuf_decode": lambda: decompress(packed),
            "zlib_encode": lambda: zlib.compress(data, level=9),
            "zlib_decode": lambda: zlib.decompress(wrapped),
        }
        for operation in operations.values():
            operation()
        for repeat in range(repetitions):
            names = list(operations)
            order.shuffle(names)
            for sequence, operation in enumerate(names):
                begin = time.perf_counter_ns()
                result = operations[operation]()
                elapsed = time.perf_counter_ns() - begin
                expected = (
                    data
                    if operation.endswith("decode")
                    else packed if operation.startswith("chuf") else wrapped
                )
                assert result == expected
                measurements.append(
                    {
                        "corpus": name,
                        "repeat": repeat,
                        "order": sequence,
                        "operation": operation,
                        "input_bytes": len(data),
                        "elapsed_ns": elapsed,
                    }
                )
        for method, encoded in [("chuf", packed), ("zlib", wrapped)]:
            durations = {
                kind: [
                    r["elapsed_ns"]
                    for r in measurements
                    if r["corpus"] == name and r["operation"] == f"{method}_{kind}"
                ]
                for kind in ["encode", "decode"]
            }
            summary.append(
                {
                    "corpus": name,
                    "method": method,
                    "input_bytes": len(data),
                    "container_bytes": len(encoded),
                    "ratio": len(encoded) / len(data) if data else "",
                    "header_bytes": info["header_bytes"] if method == "chuf" else "",
                    "payload_bits": info["payload_bits"] if method == "chuf" else "",
                    "entropy_bits_per_byte": entropy,
                    "empirical_nH_bits": len(data) * entropy,
                    "encode_median_ns": statistics.median(durations["encode"]),
                    "decode_median_ns": statistics.median(durations["decode"]),
                    "encode_min_ns": min(durations["encode"]),
                    "encode_max_ns": max(durations["encode"]),
                    "decode_min_ns": min(durations["decode"]),
                    "decode_max_ns": max(durations["decode"]),
                }
            )
    write_csv(output / "measurements.csv", measurements)
    write_csv(output / "summary.csv", summary)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    environment = {
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        "repetitions": repetitions,
        "corpus_seed": 20261120,
        "operation_order_seed": 55130,
        "corpora": len(inputs),
        "raw_timing_rows": len(measurements),
        "source_sha256_lf": source_hashes,
        "source_hash_policy": "UTF-8 source bytes with CRLF and CR normalized to LF, captured before measured calls",
        "zlib_level": 9,
        "scope": "In-memory end-to-end calls, one warmup, seeded shuffled operation order each repeat; no disk I/O timed",
        "limitations": "Python codec versus native zlib; algorithm, implementation and validation costs differ. Not an algorithm-only speed comparison.",
        "provenance": "All corpora generated synthetically by scripts/run_study.py; no external documents",
    }
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "corpora": len(inputs),
                "timing_rows": len(measurements),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/latest")
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    study(args.out, args.repetitions)

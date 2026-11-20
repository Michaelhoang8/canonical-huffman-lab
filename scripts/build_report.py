"""Render evidence charts and an offline technical report from the preserved run."""

from pathlib import Path
import csv
import html
import json
import sys
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from huffman_lab.codec import compress, inspect_header, canonical_codes

RESULTS = ROOT / "results/published"
CHARTS = ROOT / "docs/charts"
CHARTS.mkdir(parents=True, exist_ok=True)
with (RESULTS / "summary.csv").open() as stream:
    rows = list(csv.DictReader(stream))
environment = json.loads((RESULTS / "environment.json").read_text())
LABELS = {
    "single_symbol.bin": "Single symbol",
    "skewed_symbols.bin": "Skewed symbols",
    "uniform_seeded.bin": "Seeded uniform bytes",
    "byte_cycle.bin": "Repeated byte cycle",
    "structured_records.jsonl": "Structured records",
    "repeated_text.txt": "Repeated text",
}
NAMES = list(LABELS)
ORANGE = "#c95e24"
INK = "#273546"
PAPER = "#faf6ed"
MUTED = "#7b7e80"
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "figure.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "axes.edgecolor": "#d5cfc3",
        "grid.color": "#e1d9cb",
        "savefig.dpi": 180,
    }
)


def row(name, method="chuf"):
    return next(r for r in rows if r["corpus"] == name and r["method"] == method)


def export(fig, name):
    fig.text(
        0.01,
        0.01,
        "Synthetic corpora · Measured "
        + environment["started_utc"][:10]
        + " · Complete encoded containers",
        fontsize=8,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for suffix in ["png", "svg"]:
        fig.savefig(CHARTS / f"{name}.{suffix}", bbox_inches="tight")
    plt.close(fig)


fig, ax = plt.subplots(figsize=(11, 5.5))
positions = np.arange(len(NAMES))
for method, offset, color in [("chuf", -0.18, ORANGE), ("zlib", 0.18, INK)]:
    ratios = [float(row(n, method)["ratio"]) for n in NAMES]
    bars = ax.barh(
        positions + offset,
        ratios,
        height=0.34,
        color=color,
        label="CHUF" if method == "chuf" else "zlib level 9",
    )
    for bar, value in zip(bars, ratios):
        ax.text(
            max(value, 0.01) + 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.3f}",
            va="center",
            fontsize=8,
            color=color,
        )
ax.axvline(1, color=MUTED, ls="--", lw=1)
ax.set_xlim(0, 1.17)
ax.set_yticks(positions, list(LABELS.values()))
ax.invert_yaxis()
ax.set_xlabel("Container bytes / original bytes (lower is smaller)")
ax.legend(frameon=False, loc="lower right")
export(fig, "01_container_ratio")

fig, ax = plt.subplots(figsize=(11, 5.3))
for method, offset, color, label in [
    ("entropy_bits_per_byte", -0.26, "#bdb4a5", "Empirical byte entropy Ĥ"),
    ("payload_bits", 0, ORANGE, "CHUF payload bits / input byte"),
    ("container_bytes", 0.26, INK, "CHUF whole-container bits / input byte"),
]:
    values = []
    for name in NAMES:
        r = row(name)
        value = float(r[method])
        if method == "payload_bits":
            value /= int(r["input_bytes"])
        elif method == "container_bytes":
            value = value * 8 / int(r["input_bytes"])
        values.append(value)
    ax.bar(positions + offset, values, width=0.25, color=color, label=label)
ax.set_xticks(positions, list(LABELS.values()), rotation=16, ha="right")
ax.set_ylabel("Bits per original byte")
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_ylim(0, 10.2)
export(fig, "02_entropy_accounting")

fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
for ax, operation in zip(axes, ["encode", "decode"]):
    for method, offset, color in [("chuf", -0.18, ORANGE), ("zlib", 0.18, INK)]:
        values = [float(row(n, method)[f"{operation}_median_ns"]) / 1e6 for n in NAMES]
        minimum = [float(row(n, method)[f"{operation}_min_ns"]) / 1e6 for n in NAMES]
        maximum = [float(row(n, method)[f"{operation}_max_ns"]) / 1e6 for n in NAMES]
        ax.barh(
            positions + offset,
            values,
            height=0.34,
            color=color,
            label="Python CHUF" if method == "chuf" else "Native zlib / level 9",
        )
        ax.errorbar(
            values,
            positions + offset,
            xerr=[np.array(values) - minimum, np.array(maximum) - values],
            fmt="none",
            ecolor="#888174",
            capsize=2,
            elinewidth=1,
        )
    ax.set_xscale("log")
    ax.set_xlabel("Milliseconds per call · log scale")
    ax.set_title(operation.capitalize(), fontweight="bold")
    ax.legend(frameon=False, fontsize=8)
axes[0].set_yticks(positions, list(LABELS.values()))
axes[0].invert_yaxis()
export(fig, "03_measured_runtime")

fixture = compress(b"ABBA")
info = inspect_header(fixture)
hex_text = " ".join(f"{byte:02X}" for byte in fixture)
table = "".join(
    f'<tr><td>{html.escape(name)}</td><td>{int(row(name)["input_bytes"]):,}</td><td>{int(row(name)["container_bytes"]):,}</td><td>{int(row(name,"zlib")["container_bytes"]):,}</td></tr>'
    for name in ["small.txt", *NAMES]
)
report = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Canonical Huffman codec | Technical study</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:{PAPER};color:{INK};font:17px/1.6 Arial,sans-serif}}header{{border-bottom:1px solid #d5cfc3;padding:22px 5vw;display:flex;justify-content:space-between;font:12px Consolas,monospace;letter-spacing:.08em}}main{{max-width:1260px;margin:auto;padding:0 48px}}section{{padding:58px 0 44px;border-bottom:1px solid #d5cfc3}}h1{{font-size:70px;line-height:1.03;letter-spacing:-.05em;max-width:850px;margin:20px 0}}h2{{font-size:39px;line-height:1.12;letter-spacing:-.035em;margin:12px 0 20px}}h3{{font-size:17px}}.label{{font:12px Consolas,monospace;color:{ORANGE};letter-spacing:.14em;text-transform:uppercase}}.lead{{font-size:21px;max-width:900px}}p{{max-width:930px}}.stats{{display:flex;gap:70px;padding:25px 0}}.stats strong{{font:44px Consolas,monospace;display:block}}.stats span{{font-size:13px;color:{MUTED}}}a{{color:#a14819}}table{{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}}td,th{{border-bottom:1px solid #d5cfc3;padding:11px;text-align:left}}th{{font:12px Consolas,monospace;color:{MUTED}}}img{{display:block;width:100%;height:auto;margin:20px 0}}.note{{border-left:4px solid {ORANGE};padding:15px 20px;background:#f1eadd;font-size:15px}}pre{{padding:24px;background:#263341;color:#f8ead5;font:15px/1.7 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}}.split{{display:grid;grid-template-columns:1fr 1fr;gap:40px}}.bits{{display:flex;gap:10px;margin:24px 0}}.bits span{{border:1px solid #bdb4a5;padding:13px 24px;font:32px Consolas,monospace}}.bits .pad{{color:#b4a99a;background:#f1eadd}}figcaption,footer{{font-size:13px;color:{MUTED}}}footer{{padding:32px 0}}@media(max-width:800px){{main{{padding:0 20px}}h1{{font-size:45px}}.stats{{gap:24px}}.split{{display:block}}}}
</style><header><span>DATA COMPRESSION / CANONICAL BYTE CODING</span><span>CHUF v1 · {environment['started_utc'][:10]}</span></header><main>
<section id="overview"><div class="label">Canonical Huffman lab</div><h1>Canonical Huffman codec</h1><p class="lead">A source-built canonical Huffman codec, a strict binary decoder, and a reproducible comparison with zlib on eight synthetic corpora.</p><div class="stats"><div><strong>8</strong><span>committed corpora</span></div><div><strong>224</strong><span>timed calls</span></div><div><strong>28 B</strong><span>fixed header</span></div><div><strong>256</strong><span>possible byte symbols</span></div></div><table><tr><th>CORPUS</th><th>INPUT BYTES</th><th>CHUF BYTES</th><th>ZLIB BYTES</th></tr>{table}</table><p class="note">Sizes include the entire encoded container. Empty input is represented by 28 CHUF bytes or 8 zlib bytes; its compression ratio is undefined.</p></section>
<section id="sizes"><div class="label">01 / Size comparison</div><h2>Complete container sizes</h2><p>CHUF models individual byte frequencies. zlib can also exploit repeated sequences. The repeated byte cycle has a uniform histogram but compresses strongly with zlib.</p><img src="charts/01_container_ratio.png" alt="Complete container compression ratios for six synthetic corpora"><figcaption>The dashed line marks no size change. Small inputs are listed separately in the overview because header overhead dominates them.</figcaption></section>
<section id="entropy"><div class="label">02 / Bit accounting</div><h2>Empirical byte entropy</h2><p>Ĥ is computed from the observed byte histogram. nĤ is a reference lower bound for a symbol-by-symbol prefix model using those empirical weights. It excludes the table, framing, padding and sequence structure.</p><img src="charts/02_entropy_accounting.png" alt="Empirical byte entropy compared with payload and container bits"><p class="note">This is not a promise that an arbitrary finite file can be stored in nĤ bits, and not a lower bound on compressors that model sequences. A one-symbol CHUF stream uses one bit per symbol by format policy, even though its histogram entropy is zero.</p></section>
<section id="format"><div class="label">03 / Wire format</div><h2>ABBA encoding example</h2><div class="split"><div><p>A and B both have length 1. Canonical ordering assigns A=0 and B=1. The four data bits occupy the high half of the last byte; its low four bits are padding.</p><div class="bits"><span>0</span><span>1</span><span>1</span><span>0</span><span class="pad">0000</span></div></div><div><table><tr><th>FIELD</th><th>VALUE</th></tr><tr><td>Original bytes / payload bits</td><td>4 / 4</td></tr><tr><td>Alphabet / table bytes</td><td>2 / 4</td></tr><tr><td>CRC-32</td><td>B266E56B</td></tr><tr><td>Whole container</td><td>{len(fixture)} bytes</td></tr></table></div></div><pre>{hex_text}</pre><p>The decoder requires sorted unique symbols, valid complete prefix lengths, exact output and payload sizes, zero padding, full symbol usage, and a matching checksum. The one-symbol and empty cases have explicit rules.</p><p class="note">Default limits are 16 MiB decoded output and 32 MiB container input. CRC-32 detects corruption; it is not authentication. <a href="format.md">Read the binary format.</a></p></section>
<section id="runtime"><div class="label">04 / Runtime</div><h2>Measured runtime</h2><p>Median in-memory call time across seven warmed repetitions. Whiskers show the observed minimum and maximum. Operation order is shuffled with a fixed seed each repetition.</p><img src="charts/03_measured_runtime.png" alt="Measured encode and decode times with range whiskers"><p class="note">This compares Python CHUF with native zlib at level 9. Language, algorithm and validation costs all differ. It is not an algorithm-only benchmark, and the seven measurements are not confidence intervals.</p></section>
<section id="validation"><div class="label">05 / Reproduce</div><h2>Decoder validation</h2><div class="split"><div><h3>Correctness checks</h3><p>12 tests, including an independent ABBA wire fixture, an independently built 255-bit maximum-depth tree, and exhaustive prefix-length optimality checks for seven small frequency distributions. Empty and one-symbol streams. All 256 byte values. Seeded roundtrip properties. Complete-prefix validation. Malformed tables, truncated payloads, padding errors, CRC mismatch and output limits.</p><p><a href="../tests">Inspect the tests</a> · <a href="../src/huffman_lab/codec.py">Read the codec</a></p></div><div><h3>Preserved artifacts</h3><p><a href="../results/published/summary.csv">Size and timing summaries</a> · <a href="../results/published/measurements.csv">224 raw timing rows</a> · <a href="../results/published/manifest.json">Input/output hashes</a> · <a href="../results/published/corpora">Synthetic corpora</a></p><p><a href="methodology.md">Methodology</a> · <a href="findings.md">Findings</a> · <a href="../results/published/environment.json">Environment</a></p></div></div><pre>python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/run_study.py --out outputs/my-run</pre><p>New experiments refuse to overwrite an existing run. CI generates separate inputs and verifies the published artifacts independently.</p></section><footer>AI-assisted engineering study · Synthetic corpora · Educational format, not production compression software.</footer></main></html>"""
(ROOT / "docs/report.html").write_text(report, encoding="utf-8")
findings = f"""# Findings

The published study includes eight synthetic corpora, complete CHUF/zlib encoded outputs, and 224 timed calls (seven repetitions per corpus and operation). Every output is decoded and checked against its source bytes.

## Whole-container results

- The 26-byte small text expands to {row('small.txt')['container_bytes']} CHUF bytes: a 58-byte header/table plus 13 payload bytes. The 99 meaningful payload bits cannot compensate for framing overhead.
- The 65,536-byte repeated byte cycle produces {row('byte_cycle.bin')['container_bytes']} CHUF bytes but only {row('byte_cycle.bin','zlib')['container_bytes']} zlib bytes. Byte frequencies alone do not capture its repeating sequence structure.
- Seeded uniform bytes also expand under both formats in this run: {row('uniform_seeded.bin')['container_bytes']} CHUF bytes and {row('uniform_seeded.bin','zlib')['container_bytes']} zlib bytes for 65,536 input bytes.
- The skewed independent-symbol fixture produces {row('skewed_symbols.bin')['container_bytes']} CHUF bytes versus {row('skewed_symbols.bin','zlib')['container_bytes']} zlib bytes. This is one selected distribution where the standalone byte model is competitive; it does not establish general superiority.
- Structured records produce {row('structured_records.jsonl')['container_bytes']} CHUF bytes versus {row('structured_records.jsonl','zlib')['container_bytes']} zlib bytes. Repeated delimiters, field names and sequences favor a sequence-aware compressor.

## Timing interpretation

Encode/decode time is measured in memory with one warmup and seven repetitions, shuffling operation order each repeat. CHUF is Python code; zlib is native code using a different compression approach. In the skewed fixture, zlib level 9 spends substantial time encoding; elsewhere CHUF often pays significant Python loop and validation costs. Do not infer universal algorithmic rankings from this implementation comparison.

## Engineering decisions

The format transmits code lengths instead of a tree, defines deterministic ties and canonical assignment, records the exact payload bit count, and rejects malformed or resource-exceeding streams before returning output. This makes the format inspectable and testable. A production design would also need streaming APIs, broader external fuzzing, interoperability review, performance work and a threat-model-specific resource budget.

## Entropy interpretation

The empirical byte entropy is a zero-order model diagnostic. Its nĤ value omits model transmission, padding and framing, and ignores correlations. It is not a universal lower bound for finite files: zlib can exploit repeated sequences and legitimately beat this zero-order reference. The one-symbol fixture has zero histogram entropy, while this container deliberately assigns one bit per symbol.
"""
(ROOT / "docs/findings.md").write_text(findings, encoding="utf-8")
print(ROOT / "docs/report.html")

"""Independent exhaustive and extreme-depth anchors for the codec."""
import itertools
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from huffman_lab.codec import code_lengths, decompress


class IndependentCodeReview(unittest.TestCase):
    def test_weighted_lengths_match_exhaustive_small_alphabet_optimum(self):
        # Enumerate every complete prefix length assignment up to the maximum
        # useful depth n-1. This oracle builds neither a heap nor a Huffman tree.
        for frequencies in [(1, 1), (1, 9), (1, 2, 8), (7, 7, 7),
                            (1, 2, 3, 13), (1, 1, 2, 7, 12), (3, 3, 3, 3, 3)]:
            with self.subTest(frequencies=frequencies):
                count = len(frequencies)
                max_depth = count - 1
                candidates = (
                    lengths for lengths in itertools.product(range(1, count), repeat=count)
                    if sum(1 << (max_depth - width) for width in lengths) == 1 << max_depth
                )
                optimum = min(sum(f * width for f, width in zip(frequencies, lengths))
                              for lengths in candidates)
                data = b"".join(bytes([symbol]) * frequency
                                for symbol, frequency in enumerate(frequencies))
                actual = code_lengths(data)
                self.assertEqual(sum(f * actual[s] for s, f in enumerate(frequencies)), optimum)

    def test_maximum_depth_complete_tree_decodes_all_symbols(self):
        # The comb tree has codes 0,10,110,..., 254 ones then zero,
        # and 255 ones. Construct wire bytes without the implementation's
        # encoder, canonical assignment helper, or header Struct constant.
        original = bytes(range(256))
        lengths = [min(symbol + 1, 255) for symbol in range(256)]
        bit_strings = ["1" * symbol + "0" for symbol in range(255)] + ["1" * 255]
        bits = "".join(bit_strings)
        padded = bits + "0" * (-len(bits) % 8)
        payload = bytes(int(padded[i:i + 8], 2) for i in range(0, len(padded), 8))
        header = struct.pack(">4sBBHQQI", b"CHUF", 1, 0, 256, 256, len(bits), zlib.crc32(original))
        table = bytes(value for pair in enumerate(lengths) for value in pair)
        self.assertEqual(decompress(header + table + payload), original)


if __name__ == "__main__":
    unittest.main()

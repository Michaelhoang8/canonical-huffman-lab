# Findings

The published study includes eight synthetic corpora, complete CHUF/zlib encoded outputs, and 224 timed calls (seven repetitions per corpus and operation). Every output is decoded and checked against its source bytes.

## Whole-container results

- The 26-byte small text expands to 71 CHUF bytes: a 58-byte header/table plus 13 payload bytes. The 99 meaningful payload bits cannot compensate for framing overhead.
- The 65,536-byte repeated byte cycle produces 66076 CHUF bytes but only 585 zlib bytes. Byte frequencies alone do not capture its repeating sequence structure.
- Seeded uniform bytes also expand under both formats in this run: 66076 CHUF bytes and 65562 zlib bytes for 65,536 input bytes.
- The skewed independent-symbol fixture produces 11274 CHUF bytes versus 12723 zlib bytes. This is one selected distribution where the standalone byte model is competitive; it does not establish general superiority.
- Structured records produce 70417 CHUF bytes versus 10428 zlib bytes. Repeated delimiters, field names and sequences favor a sequence-aware compressor.

## Timing interpretation

Encode/decode time is measured in memory with one warmup and seven repetitions, shuffling operation order each repeat. CHUF is Python code; zlib is native code using a different compression approach. In the skewed fixture, zlib level 9 spends substantial time encoding; elsewhere CHUF often pays significant Python loop and validation costs. Do not infer universal algorithmic rankings from this implementation comparison.

## Engineering decisions

The format transmits code lengths instead of a tree, defines deterministic ties and canonical assignment, records the exact payload bit count, and rejects malformed or resource-exceeding streams before returning output. This makes the format inspectable and testable. A production design would also need streaming APIs, broader external fuzzing, interoperability review, performance work and a threat-model-specific resource budget.

## Entropy interpretation

The empirical byte entropy is a zero-order model diagnostic. Its nĤ value omits model transmission, padding and framing, and ignores correlations. It is not a universal lower bound for finite files: zlib can exploit repeated sequences and legitimately beat this zero-order reference. The one-symbol fixture has zero histogram entropy, while this container deliberately assigns one bit per symbol.

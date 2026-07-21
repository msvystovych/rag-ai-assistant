# Chunk-size experiment

`docs/homework1/reflection.md` risk #7 deferred chunk-size tuning to this homework:
*"800/150 is a best-practice guess; retrieval experiments may show 600-char chunks
retrieve more precisely."* This is that experiment.

The same corpus, the same embedding model, and the same query set — only the chunking
parameters differ. Both runs use k=3.

| | Baseline | Variant |
|---|---|---|
| Parameters | chunk_size 800 / overlap 150 | chunk_size 500 / overlap 100 |
| Chunks produced | 77 | 116 |
| Top-1 hit rate (in-corpus) | 100% | 89% |
| Mean top-1 score | 0.534 | 0.546 |
| Lowest in-corpus top-1 | 0.413 | 0.396 |
| Out-of-corpus top-1 | 0.266 | 0.295 |
| Separation margin | 0.147 | 0.101 |
| Distinct sections in top-3 | 2.00 | 1.89 |
| Distinct documents in top-3 | 1.33 | 1.11 |

## Per-query top-1 score

| Query | Category | Baseline | Variant | Delta |
|---|---|---|---|---|
| q01 | direct | 0.536 | 0.628 | +0.092 |
| q02 | direct | 0.582 | 0.607 | +0.026 |
| q03 | direct | 0.685 | 0.685 | +0.000 |
| q04 | paraphrase | 0.413 | 0.443 | +0.030 |
| q05 | paraphrase | 0.424 | 0.406 | -0.018 |
| q06 | paraphrase | 0.431 | 0.396 | -0.034 |
| q07 | cross-document | 0.602 | 0.605 | +0.004 |
| q08 | cross-document | 0.646 | 0.673 | +0.027 |
| q09 | cross-document | 0.483 | 0.471 | -0.012 |
| q10 | out-of-corpus | 0.266 | 0.295 | +0.029 |

## Analysis — where retrieval works and where it fails

This analysis ran all ten queries against the committed index. Every number below comes from a
measurement, not from an estimate.

### Where it works

**The retrieval layer solves direct queries that reuse the corpus's vocabulary.** All three scored
0.536–0.685 and returned the correct section. `q03` ("strangler-fig pattern") is the model case:
top-1 opens with the definition and all three hits are the same section in reading order.

**Retrieval survives paraphrasing — the ranking does, at least.** Every one of the nine in-corpus
queries put an expected document at rank 1, including the three paraphrases that deliberately avoid
corpus wording. `q06` asks "release new code without users noticing any interruption" and never says
*deployment*, *rolling*, or *blue-green*; all three hits are still the Zero-Downtime Deployments
section. A keyword index could not do this. This result is the clearest evidence that the embeddings
do semantic work.

**Section clustering is tight.** Across the nine in-corpus queries, mean distinct sections in a
top-3 is 2.00 and mean distinct documents is 1.33. The results concentrate where the answer is,
rather than scattering across the corpus. Including the out-of-corpus query, those two numbers
become 2.10 and 1.40.

### Where it fails

**Paraphrasing costs 30% of the similarity score.** Mean top-1 falls from 0.601 (direct) to 0.423
(paraphrase) — a 0.178 drop, 30% relative. The ranking holds, but the margin narrows sharply.
`q05` shows what that costs. Its top-3 spans three different documents, because
"keep every change as a permanent record" matches generic write-path language everywhere in the
corpus. On a larger or noisier corpus that margin is where errors would appear first.

**Chunks that open mid-sentence rank well and read badly.** The overlap carry means a chunk can
begin "time and handling risk. That distinction changes the data model…". This happens to `q01`'s
and `q09`'s top-1. The model computes the embedding over the whole chunk, so the ranking stays
unharmed. A human still gets a fragment whose first clause belongs to the previous chunk. An LLM
asked to quote a source gets that same fragment. `reflection.md` risk #3 predicted this. The fix
it proposes is the right one: snap the overlap window back to a sentence boundary.

**One high score is lexical, not semantic.** `q08` contains the exact string
"5,000 requests per second". That string appears in the document's H1. The breadcrumb prepends that
H1 to *every* chunk of that document. The 0.646 is partly keyword overlap wearing a semantic
score's clothing. The breadcrumb earns its place in readability (HW1's 15-point criterion). But it
also injects a constant, document-wide lexical signal into every vector, and that signal is a real
cost this experiment can see.

**There is no "I don't know".** `q10` asks about fine-tuning language models, and nothing in a
logistics corpus answers it. The layer still returns three cleanly formatted results. The only
signal is the score: 0.266 against an in-corpus floor of 0.413. The margin is real but thin
(0.147), and at Homework #2 the code enforced no threshold anywhere. Feeding this to an LLM
unfiltered is how a RAG system confidently answers a question it has no source for.

A floor near 0.35 was the obvious next control. **Update 2026-08-13** — Homework #4 built that
floor at exactly 0.35. `scripts/rag_answer.py` defines `DEFAULT_MIN_SCORE = 0.35`, and its
`generate()` function enforces that floor against the top semantic score.

### Chunk-size experiment — 800/150 stays

Re-chunking at 500/100 produces 116 chunks instead of 77. It also slightly *raises* mean top-1
(0.546 vs 0.534). Smaller chunks are more topically concentrated, so the best match matches harder.
500/100 is worse everywhere that matters:

- Top-1 hit rate falls from **100% to 89%**. That drop is `q05` alone. It goes from a hit to a
  partial, because the smaller chunk loses the surrounding context that anchored it to the CQRS
  document.
- The out-of-corpus score *rises* (0.266 → 0.295) while the in-corpus floor *falls* (0.413 → 0.396).
  That change collapses the separation margin from **0.147 to 0.101**.

Smaller chunks buy sharper peaks and pay in discrimination. More chunks means more chances for a
short passage to spuriously resemble an unrelated query. This closes `reflection.md` risk #7 with
a measurement rather than a guess. The pipeline keeps 800/150.

### Honest limitations

1. **The corpus and the queries share an author.**
   `reflection.md` risk #5 named this before any code existed, and it is still the biggest caveat
   on every number here. This experiment added the paraphrase category specifically to push
   against it. The 30% score drop is the size of the effect that category exposes. But a genuinely
   independent query set, written by someone who had not read the corpus, would likely score lower
   still.
2. **Ten queries and 77 chunks is an anecdote, not a benchmark.**
   This analysis reports no recall@k, MRR, or nDCG, because the evaluation design cannot support
   such a metric. Most queries have a single relevant document, and the corpus is small. So those
   metrics would dress up the same ten observations in statistical clothing they cannot support.
3. **One person wrote the corpus, wrote the queries and judged relevance.**
   The mechanical hit/miss verdict in the tables is objective; the prose comments are not.

# Limitations (honest list)

Measured failure cases for the held-out set are listed per turn in `docs/evaluation.md` §8. This page lists the mechanisms behind them and the broader caveats.

## Evaluation validity
- **No official corpus.**
  - The official Theme 4 corpus was not available. All results describe a synthetic 16-document development corpus (57 chunks).
  - They say nothing about performance on the official corpus or the official held-out replay set.
- **Same author.**
  - The corpus, the controller training data, the calibration queries, the development set and the held-out set were all written by the AI agent that built the system.
  - The held-out set was frozen before the fixes and is overlap-checked against the other sets, but it is not independent. Its phrasing style and topic coverage are shared with the system's author.
- **Small corpus.**
  - Recall saturates (8 chunks is 14% of the corpus) and the retrieval-only ablation shows little separation.
  - End-to-end metrics (citation hit rate, multi-intent, abstention) are the discriminating ones.
- **Simulated speech.**
  - Chunks arrive on a 150 wpm schedule with a fixed 0.5 s end-pointing delay.
  - Real ASR revises partial hypotheses. The controller assumes each chunk is final and never cancels a stale provisional retrieval (it only stops reusing it).
- **One machine.** Latencies were measured on one Windows laptop CPU. Ablations run at 5× pacing, so only their quality metrics are comparable.

## Component limitations
- **Abstention gate:**
  - It is a 3-feature logistic regression (cross-encoder logit, term coverage, cosine) fitted on 56 queries. Its leave-one-out balanced accuracy is about 0.88, so it errs in both directions.
  - It can **over-abstain** on paraphrases whose key words are not in the evidence ("daily allowance under the travel policy" vs "per diem").
  - **On the held-out set it is too conservative.** It refused answerable questions often enough that the full system's citation hit rate does not beat the conventional baseline, and it is below the same pipeline without the gate. It does raise correct abstention sharply. The exact counts are computed in `docs/evaluation.md` §5 ("Key finding"). This was not tuned away on the held-out set. The fix is a larger, independently written calibration set, or an answerability model trained on realistic sub-query fragments.
  - It can **answer topical questions about absent attributes** ("parking fee at the Pune venues" passes because the evidence is strongly on-topic). This is tracked as a strict expected-failure test.
- **Intent classifier:**
  - It was trained on about 120 utterances.
  - Presentation requests with an audience phrase ("put that in plain words *for a new joiner*") sit near the refinement boundary (0.51 vs 0.44). This is tracked as a strict expected-failure test.
  - Refinements without any corpus vocabulary rely on topic anchors.
  - Spoken numbers are not normalised to digits.
- **Decomposer:**
  - It is surface-cue based (coordination, wh-words, request verbs). Implicit multi-intent without a connective stays one query.
  - It detects entities only as words the corpus capitalises mid-sentence, so a name that appears only at sentence start or in headings (e.g. "Whitefield") is not carried to sibling sub-queries.
- **Extractive synthesis:**
  - Answers are verbatim corpus sentences: grounded and $0, but not fluent, and each sub-query gets at most 2 sentences, so long sections can be answered partially.
  - Some answers are relevant but not the best sentence. In the guide's workshop example, sub-query 1 cites the planning guide rather than a 30-seat venue.
- **Grounding validator:** it checks term containment and numbers, not entailment. The extractive path is safe by construction; the optional LLM path would additionally need an NLI check.
- **Conflicts:** they are resolved only through explicit `supersedes` / `superseded_by` metadata. Other numeric disagreements are flagged, not resolved.
- **Facet filter:** it only activates for document families whose titles differ by a proper noun.
- **Latency:** the full pipeline (cross-encoder reranking plus sentence scoring) costs more CPU per turn than bare dense RAG. Early retrieval and speculative synthesis prep hide much of it, but when a user stops shortly after the last informative word, the remaining work is still on the critical path (see the TTFT p95 in `docs/evaluation.md`).
- **Session store:** in-process only. A multi-worker deployment needs sticky sessions or an external ephemeral store with the same TTL.
- **Docker:** the Dockerfile and compose file are statically validated but were **not built or run**, because Docker was unavailable in the development environment. G1 is reported as NOT VERIFIED.

## Future work
1. Run on the official corpus and held-out replay; re-author gold labels, calibration queries and demo scenarios for it.
2. A streaming ASR front-end with revisable partial hypotheses, and cancellation of stale provisional retrievals.
3. A larger, independently written calibration set, or a small NLI model for answerability.
4. Optional LLM synthesis behind the existing validator, plus entailment checking.
5. A learned segmenter for implicit multi-intent requests.
6. FAISS / HNSW for corpora above about 100k chunks; the swap point is `CorpusIndex._search`.

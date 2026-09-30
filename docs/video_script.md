# Demo video script: 4 speakers, 5 minutes max

Team Fantastic 4 · SRM University · Theme 4: Streaming Live RAG

**Recording plan:**
- Purva, Agadh and Srushti each record their own segment over the slides of `SRM_Univ_Fantastic_4_Submission.pptx`.
- Sneh records the live prototype.
- The four clips are joined in the order below. Keep each clip within its time.

**Rules for everyone:**
- Say every number exactly as written here.
- Say once, early: "all numbers are from a development benchmark on a 16-document synthetic corpus".
- Never call the results official Samsung results.

| # | Speaker | Time | Shows on screen |
|---|---|---|---|
| 1 | Purva Jain | 0:00–1:15 | Slides 1–4 |
| 2 | Agadh Khanolkar | 1:15–2:30 | Slides 5, 7, 8, 9 |
| 3 | Sneh Prasad | 2:30–3:45 | Live dashboard (prototype) |
| 4 | Srushti More | 3:45–5:00 | Slides 10, 11, 12, 13, 15 |

Each person has exactly 1:15. Rehearse with a timer; if you run over, cut words rather than speaking faster.

---

## 1. Purva: problem and idea (0:00–1:15)

**Slide 1, title (0:00–0:10):**
"Hi, we're Team Fantastic 4 from SRM University. Our project for Theme 4 of the Samsung PRISM Generative AI Hackathon is Streaming Live RAG."

**Slide 2, theme (0:10–0:35):**
"Natural speech isn't a clean search query. In one sentence, people ask several things at once, add an important detail halfway through, correct themselves, or ask to change a previous answer. Conventional RAG waits for the complete utterance and then runs one search. Our objective is to retrieve useful context while the conversation is still unfolding."

**Slide 3, gaps (0:35–0:55):**
"Typical query-then-retrieve pipelines turn the whole utterance into one query. They start only after the user stops speaking, and they search the corpus on every turn, even when nothing needs searching. When a late detail arrives, they usually start over. Measured on our conventional baseline, early retrieval and multi-intent identification are both 0%, and refinement continuity is 0%."

**Slide 4, our solution (0:55–1:15):**
"Our pipeline works like this. Transcript chunks go to a controller that decides WAIT, RETRIEVE or SUPPRESS. Then multi-intent decomposition splits the request, parallel retrieval runs for each part, the evidence is fused and reranked, and a grounded answer comes out. The key idea is live retrieval before the utterance ends. In this real trace, retrieval began 1.29 seconds before the user finished."

## 2. Agadh: architecture, refinement and stack (1:15–2:30)

**Slide 5, architecture (1:15–1:45):**
"Chunks arrive one at a time. On every chunk the controller decides whether to retrieve. When it says RETRIEVE, provisional retrieval starts in the background. That's the green dashed path, and the results are reused when the user stops. Each sub-query runs dense and BM25 retrieval in parallel. The results are fused with RRF and reranked by a cross-encoder, and the grounding validator checks every citation before the answer is streamed. Every step is logged on one clock."

**Slide 7, first answer to refined answer (1:45–2:05):**
"On the left, the controller waits on a vague opening and retrieves as soon as the request is specific, while the user is still talking. On the right, a late detail arrives after the first answer. It's treated as a refinement: only the new part is searched, the version 1 claims are kept, and new claims are added in version 2. There's no full-session restart."

**Slide 8, tools (2:05–2:20):**
"It's built in Python with FastAPI and Server-Sent Events. It uses MiniLM embeddings, our own BM25 and RRF, a cross-encoder reranker and scikit-learn models. The dashboard is plain JavaScript, the tests use pytest, and it's packaged with Docker. It runs on CPU and calls no LLM at runtime."

**Slide 9, impact (2:20–2:30):**
"Potential uses include voice assistants, enterprise search and device support. It's a prototype, not a deployed product. Sneh will now show it live."

## 3. Sneh: live prototype (2:30–3:45)

**Setup before recording:**
1. Restart the server with the new code:
   ```bash
   python -m uvicorn app.main:app --app-dir backend --port 8000
   ```
2. Open http://localhost:8000. Set System to **Streaming Live RAG** and Pace to **1x (Real time)**.
3. Click **Clear Session** before each demo.
4. Demo 1 takes about 11 seconds to play, so talk while it runs. You can cut the pauses between demos in editing.

**Demo 1, Early retrieval (2:30–2:50):**
- Click **1 Early retrieval**.
- "The transcript arrives chunk by chunk. The first chunk is vague, so the controller shows WAIT in amber. Then it switches to RETRIEVE in green while I'm still talking. The hatched bars are retrievals made during speech, well before the dashed line where the utterance ends."

**Demo 2, Multi-intent, the Theme 4 guide's example (2:50–3:10):**
- Click **2 Multi-intent**.
- "One sentence becomes three sub-queries, with Pune carried into each. They're retrieved in parallel and fused. The answer names a Pune venue with rooms for 35 and 80 people, plus the cancellation terms and the catering options. Every sentence is cited."

**Demo 3, Late detail (3:10–3:25):**
- Click **3 Late-arriving detail**.
- "I add a detail: the trip was international. Only the new part is searched. The version 1 claims are kept, and the green claims are new in version 2."

**Demo 4, Suppression (3:25–3:37):**
- Click **4 Retrieval suppression**.
- "'Make your previous answer shorter' shows SUPPRESS in purple. There's no corpus search; the answer is reshaped from memory."

**Demo 5, Insufficient evidence (3:37–3:45):**
- Click **5 Insufficient evidence**.
- "When the documents don't have the answer, it says so instead of guessing."

## 4. Srushti: results, limits and close (3:45–5:00)

**Slide 10, results (3:45–4:15):**
- "All numbers are from our development benchmark on a 16-document synthetic corpus: 63 held-out cases and 77 turns. Against conventional RAG:"
  - early retrieval 90% vs 0%, with a mean lead of 4.4 seconds;
  - multi-intent identification 78% vs 0%;
  - refinement continuity 100% vs 0%;
  - correct abstention 83% vs 33%.
- "Every citation is supported, with zero fabricated. All six gates pass."
- "Two honest trade-offs. The citation hit rate is 73% for both systems, because our abstention is conservative. The baseline's first token also arrives slightly sooner, 14 versus 21 milliseconds. Without early retrieval, ours would take 187 milliseconds."

**Slide 11, innovation and limitations (4:15–4:35):**
"What's new: retrieval before the utterance ends, a learned WAIT/RETRIEVE/SUPPRESS controller, decomposition, delta refinement with versioned answers, and validated citations. The limitations: the corpus is synthetic and was written during development. The official corpus wasn't available. Abstention is conservative, and the answers are extractive rather than fluent."

**Slide 12, next steps (4:35–4:45):**
"Next, we'll evaluate on the official corpus, improve abstention, and add real streaming speech recognition."

**Slides 13 and 15, close (4:45–5:00):**
"Streaming Live RAG: RAG that starts working before the user finishes speaking. The code is on GitHub. Thank you."

---

**Final check before upload:**
- The total length is 5:00 or less.
- The numbers you said match slide 10.
- The video is uploaded to YouTube (unlisted) or Drive, and the link is shared.
- The link replaces the placeholder on slide 14 of the deck.

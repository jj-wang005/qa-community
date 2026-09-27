# RAG evaluation

This directory replaces the old ignored, title-substring-only scripts with a
reproducible evaluation baseline. The labels are **silver labels** derived from
the current seeded knowledge base, not human-verified gold labels.

## Install

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m pip install -r eval-requirements.txt
```

## Retrieval evaluation

Generate multi-document silver labels once (or whenever the corpus changes):

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.generate_silver_labels
```

This asks an independent judge to select the smallest sufficient qid set from
the union of the top vector and BM25 candidates, and to synthesize a concise
reference answer supported by that set. The output records confidence, rationale
and the candidate pool. It can still miss a relevant document outside that pool.

Start MySQL and Redis, then run both variants:

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_retrieval --mode vector
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_retrieval --mode hybrid
```

The report contains Recall@1/3/8, Precision@3, MRR@8, NDCG@3, vector
Recall@50, out-of-domain abstention and latency. Results are written under
`evals/results/` and are intentionally ignored by Git.

## Ragas evaluation

First collect answers from the same anonymous LangGraph Agent used by the API:

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_answers --limit 5
```

Collectors checkpoint after every completed sample. Resume an interrupted run
without recollecting completed case ids by reusing the same output path:

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_answers --output evals\results\answers_silver.json --resume
```

Use `--ids out_01 out_02` to collect a targeted regression subset.

Use the separate Function Calling cases to validate `get_answers` order and qid provenance:

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_answers --input evals\data\tool_cases.jsonl
```

Then pass the generated JSON to `run_ragas.py`. It consumes rows containing `user_input`,
`response`, `retrieved_contexts`, and `reference`. It evaluates faithfulness,
factual correctness, response relevancy, context precision and context recall.
The collected contexts are the redacted/isolated/truncated tool messages actually
shown to the model, not the unrestricted raw tool return.

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_ragas evals\results\answers_YYYYMMDD_HHMMSS.json
```

If a provider failure interrupts an expensive run, reuse successful per-metric
scores and fill only missing metrics:

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_ragas evals\results\answers_YYYYMMDD_HHMMSS.json --output evals\results\ragas.json --resume
```

Run the retained project-specific judge separately:

```powershell
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_custom_judge evals\results\answers_YYYYMMDD_HHMMSS.json
F:\Anaconda_envs\envs\qa\python.exe -m evals.run_tool_routing evals\results\answers_YYYYMMDD_HHMMSS.json
```

The custom LLM judge should remain for project-specific completeness, citation,
and refusal rules. Tool routing is scored separately with deterministic rules:
in-domain cases must call `search_master`; out-of-domain cases must not call a
knowledge-base tool; the weather case must call `get_weather`. Do not duplicate Ragas faithfulness/factual
correctness with the old title-only `accuracy` and `hallucination` scores.

All long-running collectors checkpoint after every sample. A provider failure
therefore preserves completed rows and records per-metric Ragas errors.

## Human review

Do not describe these silver labels as manually verified ground truth. Before
publishing a score, review all failures plus a random sample of passes. Record
accepted corrections as explicit changes to `data/cases.jsonl`.

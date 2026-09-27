# RAG evaluation report

Evaluation date: 2026-09-27

This report uses the reproducible **silver-label** dataset in
`evals/data/cases_silver.jsonl`. It is not a human-verified gold-set result.

## Current results

The answer-quality run contains 40 in-domain cases generated with the current
Agent prompt. Every Ragas metric has 40 valid samples and zero metric errors.

| Metric | Score |
| --- | ---: |
| Faithfulness | 0.6040 |
| Factual Correctness | 0.4788 |
| Response Relevancy | 0.8427 |
| Context Precision | 0.9338 |
| Context Recall | 0.9354 |

Deterministic project checks:

| Check | Result |
| --- | ---: |
| Tool routing | 50/50 (100%) |
| In-domain routing | 40/40 (100%) |
| Out-of-domain routing | 10/10 (100%) |
| Correct refusal | 9/9 applicable cases (100%) |
| Citation validity | 32/40 (80%) |

The weather case is excluded from refusal scoring because it is answered by the
dedicated weather tool. The current-prompt completeness judge was not included:
the external approval transport failed twice before that run started. An older
prompt's completeness score must not be presented as the current result.

## Backtest findings

The first full run showed strong context precision/recall but weak answer
faithfulness. Responses frequently added generic solutions, product names,
parameters, or performance claims not supported by retrieved evidence. The
Agent prompt was tightened to require concise, evidence-bounded answers.

On the targeted 12-case low-score regression set:

| Metric | Before | After |
| --- | ---: | ---: |
| Faithfulness | 0.2761 | 0.5586 |
| Factual Correctness | 0.2900 | 0.4392 |
| Response Relevancy | 0.7949 | 0.8417 |
| Context Precision | 0.8889 | 0.8443 |
| Context Recall | 0.8333 | 0.9583 |

The final full-set faithfulness improved from 0.4526 to 0.6040. Factual
correctness remains the main weakness. Some loss is caused by verbose answers,
while some cases expose silver-reference granularity differences. Citation
compliance is also incomplete: eight responses have no accepted citation or use
an unsupported citation format.

## Interpretation

The retrieval layer is strong enough for a student project baseline: relevant
evidence is usually present and focused. Tool routing and out-of-domain control
are stable on the fixed regression set. The next optimization target is the
generation layer, especially evidence-only factual coverage and guaranteed
citation formatting. These fixed-set scores are regression evidence, not proof
of production generalization.

## Reproduction

See `evals/README.md` for commands. Generated answer and metric JSON files live
under `evals/results/` and are intentionally ignored by Git.

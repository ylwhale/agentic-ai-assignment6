# ADR 0006 - RepoMind task topology

- **Status:** Accepted (retain single-agent on `main`)
- **Date:** 2026-11-13
- **Experiment:** Assignment 6, 72 real-model task-set runs (3 sweeps x 8 tasks x 3 arms)
- **Prediction commit:** `fc95363` (predictions committed before split runs)

## Context and alternatives

RepoMind currently triages tracker issues using one agent. We tested three architectures with the same model, tool registry and task set: S (existing agent), M (coordinator with independent read-only investigator / write-only writer pipelines; parallel across unrelated issues), and S-plus (sequential fresh-context attempts using task-specific matched M budget). The multi-agent code stays exclusively on `lab-06-split`; main records the measurement and decision.

## Pre-experiment gates and prediction

The four gates were evaluated in order in Part A:

- **Single issue:** gate 1 **fail** (the writer depends on the investigator); gates 2, 3, and 4 **not reached**. Decomposing the same issue into sequential roles does not create useful parallelism.
- **Batch of five unrelated issues:** gate 1 **pass** (pipelines can work independently), gate 2 **pass** (per-issue result checks are possible), gate 3 **pass, prospectively** (concurrent pipelines might reduce wall time), gate 4 **fail** (before testing, no measured benefit justified the multiplier). A pass on part-level checks never replaces checking the combined state.

The prediction committed separately in `reports/PREDICTIONS_06.md` at `fc95363` was: for a **single issue**, M would use roughly **1.5x** S's tokens, S and M would pass a similar number of issues (within about one per sweep), and S-plus would do at least as well as M. For a **batch**, M would use around **1.8x** S's tokens, potentially pass one additional batch per sweep, and S-plus would perform approximately as well as M at matched spend. These were pre-experiment hypotheses and were not retroactively edited to match the outcomes.

## Decision

**Single issue: keep one agent. Batch of five: keep one agent.** Do not merge the split implementation or worker prompts into `main`. The batch split's speed advantage did not compensate for 0/6 complete batch passes.

## Evidence

| Measure | S | M | S-plus |
|---|---:|---:|---:|
| Single task passes | 14/18 | 9/18 | 6/18 |
| Batch passes | 5/6 | 0/6 | 0/6 |
| Mean tokens, single | 51,512 | 26,258 | 26,796 |
| Mean tokens, batch | 350,079 | 158,411 | 150,147 |
| Mean seconds, single | 8.4 | 8.4 | 9.9 |
| Mean seconds, batch | 33.8 | 12.4 | 49.7 |

### Experimental constants

- **Model:** `gemini-3.5-flash-lite` (same OpenAI-compatible backend in every arm).
- **Tools:** same tool schema definitions and order, `schemas_sha=703c0002892f27ec`; the experimental split limited each worker to its allowed subset of those tools.
- **Budget:** S and M each received the same 250,000-token ceiling per single issue or 1,250,000 per five-issue batch; S-plus received each task's M mean spend via `--match split` and was audited against observed token use.
- **Evaluator and reviewer:** grounded task checker and answers held fixed with `checks_sha=55abcd67e6a3b208`; reviewer `scripted:approve-all`.
- **Task set:** `batch-a, batch-b, one-4402, one-4403, one-4405, one-4406, one-4409, one-4413`, each run for three sweeps in every arm.

### Slide 18 spending questions

| Question | One issue | Five-issue batch |
|---|---|---|
| Did M spend more than S? | **No**: M/S 0.510x tokens. | **No**: M/S 0.453x tokens. |
| Does spending more raise score? | **Observed association**: higher-spend S passed 14/18 at 51,512 mean tokens; lower-spend S-plus passed 6/18 at 26,796. This does not establish causation. | **Observed association**: S passed 5/6 at 350,079 tokens; S-plus passed 0/6 at 150,147. |
| At M's spend, did one agent do as well? | **No**: S-plus 6/18 vs M 9/18. | **Tied at zero**: S-plus 0/6 vs M 0/6. |

M/S token multipliers were 0.510x for single issues and 0.453x for batches. The lecture's quoted ~15x describes multi-agent systems relative to a chat on other workloads, **not** M relative to S on this matched task set, so the two ratios are contextual rather than directly comparable. M beat the roughly matched S-plus baseline on singles (9 vs 6 successes), so splitting provided some relative benefit at low spend; it did not reach the reliability of S. For batches, M and S-plus both passed 0/6 despite lower mean token use, and M's 12.4s mean batch time was faster than S's 33.8s. These results show why cost, accuracy and time must all be considered.

Of M's 15 failed runs, 12 included investigators hitting their nine-call limit without a usable validated return. Three others passed the structural combined check but still failed the grounded evaluator: issues that required `file: none` were assigned code files and unnecessary PRs. Other mixed batch errors included wrong issue labels. No inter-agent concurrency anomaly was evidenced by the measured traces. Detailed per-run evidence is in `reports/LAB_06.md`, `reports/LAB_06.json`, `results/runs_06.jsonl`, and `runs/`.

## Consequences and tradeoffs

- **Retained:** higher measured correctness; no extra coordinator/worker handoff failure path; no change to production agent implementation.
- **Forgone:** parallel issue pipelines, batch-latency reduction and smaller per-worker contexts from M; M's lower token use and its modest advantage over S-plus in single tasks.
- **Cost:** S spends more tokens, particularly on batches; this needs continued monitoring, but higher accuracy is the decisive objective for this assignment's triage tasks.
- **Risk in adopting M now:** stopping rules produce no writes for some issues, and the structurally valid combined check cannot prevent incorrect classifications or unneeded PRs.

## Revisit criteria

Before reconsidering, repair investigator return/retry behavior at the turn limit, add grounded semantic checks for `question -> file: none -> no PR` and classification correctness, and repeat three same-model/same-evaluator sweeps. Require at least 14/18 successful single tasks and 5/6 successful batches with at least 20% lower mean tokens **or** wall time than S, and no integrity flags. If results improve, reconsider independently for single and batch workloads.

## Repository handling

Tag the fully committed experimental branch `lab-06-split-final`, with its roles, schema, prompts and guards. Commit this ADR, final reports and measured artifacts to `main`; keep `ARCHITECTURE.md` unchanged. Tag that main commit `lab-06`.

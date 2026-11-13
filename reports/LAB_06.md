# Assignment 6 · Split it, measure it, decide

Model: Google Gemini, gemini-3.5-flash-lite (OpenAI-compatible API), to be held constant across all experimental runs.

## Part A · The gates, before you build

**The roles you considered, and what each would need from the others mid-task.**

I considered three roles:

- **Coordinator:** Assigns tasks, distributes token budgets, validates worker returns, and checks the combined result.
- **Investigator:** Reads issues, searches repository files, and identifies the appropriate label and responsible file.
- **Writer:** Applies labels, opens draft pull requests when required, and posts triage comments.

| Two roles | What one needs from the other while the task runs | How it would get it | What that costs |
|---|---|---|---|
| Coordinator and Investigator | The investigator needs the assigned issue and budget; the coordinator needs findings and supporting evidence. | Task assignment and structured worker return. | Additional communication, token usage, and return-validation overhead. |
| Investigator and Writer | The writer needs the investigator's label, responsible file, and findings before making changes. | Structured return passed through the coordinator. | Sequential dependency, possible information loss, and additional context processing. |
| Coordinator and Writer | The writer needs validated instructions; the coordinator needs confirmation of completed actions. | Task assignment, tool results, and shared trace. | Communication overhead and potential state inconsistencies. |

### For one issue

The investigator must complete its investigation before the writer can perform the required actions. This creates a sequential dependency between the two roles.

The investigator returns its findings, search history, tool-call count, and unresolved questions. It cannot determine whether downstream write operations will succeed or whether the final tracker state will be consistent.

The writer receives the validated investigation results and performs the required actions. It returns the outcomes of those actions but cannot independently establish facts the investigator did not provide.

Because the roles depend on the same investigation, there is limited opportunity for parallel execution. Additional agents may increase communication overhead and token spending without significantly improving accuracy or execution time.

### For a batch of five

Each of the five issues can be investigated and processed independently.

The coordinator can dispatch separate issue-processing pipelines. Each pipeline contains an investigator and a writer. Within each pipeline, investigation precedes writing, but different issue pipelines may run concurrently.

Each worker returns structured results for its assigned issue. However, an individual worker cannot determine whether its changes conflict with changes made by another worker.

The coordinator must therefore verify the combined tracker state after processing the batch.

Because the issues are unrelated, they require little direct communication with one another. This creates an opportunity for parallel execution and context isolation.

### The sketch

**For one issue:**

```text
                   Coordinator
                        |
                        v
                   Investigator
                        |
                        v
                 Structured Return
                        |
                        v
                   Coordinator
                        |
                        v
                      Writer
                        |
                        v
                      Tracker
                        |
                        v
             Combined Verification
```

**For a batch of five:**

```text
                       Coordinator
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
       Issue 1           Issue 2           Issue 3
          |                 |                 |
     Investigator      Investigator      Investigator
          |                 |                 |
        Writer            Writer            Writer
          |                 |                 |
          +-----------------+-----------------+
                            |
                   Same pattern for
                    Issues 4 and 5
                            |
                            v
                          Tracker
                            |
                            v
                   Combined Verification
```

Each issue-processing pipeline follows:

Investigator → Structured Return → Coordinator → Writer

There are no direct worker-to-worker messages in the proposed design. Findings pass through the coordinator, and shared state is verified after execution.

This structure aims to reduce unnecessary communication while keeping responsibilities and tool permissions separate.

### The four gates (slide 46), in order, stopping at the first no

| Gate | One issue | Why | A batch of five | Why |
|---|---|---|---|---|
| 1. The parts work mostly without talking | Fail | The writer depends on the investigator's findings, creating a sequential dependency. | Pass | The five issues are unrelated and can be processed independently. |
| 2. Each part's result can be checked on its own | Not reached | Gate 1 failed. | Pass | Each issue has independently verifiable labels, comments, and draft pull requests. |
| 3. A team buys what one agent cannot get more cheaply | Not reached | Gate 1 failed. | Pass | Concurrent processing of independent issues could reduce wall-clock time, which sequential single-agent processing cannot achieve. This advantage must be measured. |
| 4. The result is worth the multiplier | Not reached | Gate 1 failed. | Fail | Before measurement, the expected performance improvement has not demonstrated sufficient value to justify additional token spending and coordination overhead. |

The four gates provide an initial architectural assessment rather than a final performance conclusion.

For a single issue, the proposed split fails the first gate because investigation and writing are tightly dependent.

For a batch of five unrelated issues, the first three gates can potentially be satisfied, assuming real concurrent execution is implemented. However, the fourth gate is provisionally marked as Fail because the expected performance improvement has not yet been demonstrated.

Part C will test whether the measured results justify revisiting this judgment.

### The benefit you are trying to buy, and the condition it needs

The primary benefit is **parallelism**.

Parallelism can reduce wall-clock execution time when multiple independent issues are processed concurrently.

This benefit requires:

- Independent tasks that do not require frequent communication.
- Sufficient opportunities for simultaneous execution.
- Individually verifiable results.
- A measurable time or quality improvement that justifies the extra cost.

The secondary benefits are **context isolation** and **specialization**.

Context isolation allows agents to focus on smaller tasks without carrying irrelevant information from other issues. However, a single agent can also use fresh contexts or external memory, potentially achieving similar benefits at a lower cost.

Specialization assigns different tools and responsibilities to different roles. The investigator receives read-oriented tools, while the writer receives tools for modifying the tracker and creating pull requests.

This division reduces the possibility of an investigator accidentally performing an unauthorized write operation.

Specialization through restricted tool access is more meaningful than simply assigning different prompts to agents using the same model.

The overall hypothesis is that multiple agents are unlikely to provide sufficient benefits for one issue but may provide meaningful advantages for batches of independent issues.

### Your prediction, as committed in `reports/PREDICTIONS_06.md`, and its commit

The following are the proposed pre-experiment hypotheses and must match the separately committed prediction file.

**Single-issue tasks:**

- Arm M is predicted to spend approximately 1.5 times as many tokens as Arm S.
- Arm S and Arm M are expected to achieve similar pass rates, differing by no more than one task per sweep.
- Arm S-plus is expected to perform at least as well as Arm M when given approximately the same token spending.

**Batch tasks:**

- Arm M is predicted to spend approximately 1.8 times as many tokens as Arm S.
- Arm M may pass approximately one additional batch task per sweep compared with Arm S.
- Arm S-plus is expected to perform approximately as well as Arm M at matched token spending.

**Overall prediction:**

Multi-agent decomposition is unlikely to be justified for individual issues because the additional coordination overhead does not provide a substantial advantage.

Batch processing offers a stronger opportunity for parallelism and context isolation. However, the split should be adopted only if its measured performance justifies the additional token spending and implementation complexity.

These are hypotheses, not experimental findings.

Prediction commit: **`fc95363`**

---

---

## Part B · The split

**Roles and tools.** `ways/split.py` implements a deterministic coordinator and, for each issue, a read-only investigator (`read_issue`, `search`, `read_file`) followed by a write-only writer (`apply_label`, `open_pr`, `comment`). `RoleTools` derives allowed concrete registry calls from role mappings and rejects out-of-role calls. The coordinator does not make extra model calls. Every issue has its own investigator and writer; different issue pipelines run concurrently using a thread pool of up to five workers. Within an issue, the writer waits for a validated investigator result. Worker prompts live in `prompts/investigator.md` and `prompts/writer.md` on `lab-06-split`.

**Why split by tool surface.** The investigator can inspect evidence but cannot mutate the tracker; the writer can act on a finding but cannot independently search. The coordinator supplies only the validated finding and controls when writes may begin. This makes authority boundaries concrete, although it creates a serial dependency and a risk that an incorrect finding is faithfully executed.

**Return contract.** `split/contract.schema.json` requires six top-level fields: `result` (`issue`, `label`, `file`, `evidence`), `status` (`found`, `candidate`, `out_of_budget`), `searched`, `not_searched`, `calls_used`, and `could_not_determine`. In `ways/split.py`, `RoleTools.call()` validates the return and compares `searched` and `calls_used` with the actual read/search tool arguments and counts in its recorded registry calls, rather than trusting model claims. It also verifies the issue ID. Rejected returns are traced as `return_rejected` and the model receives observed values to retry. The coordinator emits `worker_return` with validity/errors and refuses to dispatch a writer on a final invalid return.

**Budget shares.** `ways/split.py` divides a per-issue budget into 64% investigator, 31% writer, and approximately 5% unassigned reserve; the investigator is capped at 9 model calls and the writer at 7. All workers count toward the shared run ceiling. In practice, nine-call investigator exhaustion was a principal measured failure mode. The run cap is 250,000 tokens per issue, but the model-call limits often stop investigation well before the token ceiling.

**Five checks and their implementations.**

1. **Structured returns:** `split/contract.schema.json` and `ways/split.py` enforce the schema and observed `searched`/`calls_used`; 10/10 automated return-contract points.
2. **Wait cycles:** `split/guards.py:WaitGraph` detects a cycle and selects a non-coordinator victim; the checker validated it with planted deadlock/no-deadlock traces (8/8). The measured coordinator recorded its actual waits; the `WaitGraph` guard was demonstrated through deterministic replay, not proven to intercept every live wait.
3. **Combined tracker result:** `split/guards.py:check_combined` checks one comment, matching label, and PR presence/absence consistent with the comment's file; called after all issue pipelines (8/8). It checks **internal consistency**, not the hidden correct answer.
4. **Lost-update prevention:** `split/guards.py:SharedState` provides versioned reads and compare-and-set writes; the lost-update replay refused a stale write and passed 8/8. This is a tested replay guard, not evidence of a lost update in the measured tracker runs.
5. **One trace and budget accounting:** `ctx.agent(...)` writes `agent`/`parent` on worker events to a single run JSONL trace, and the shared run client accounts for every worker's tokens (one-trace 6/6, budget 10/10).

The checker also passed the planted combined-result replay (8/8). Safety checks passing does not imply semantic issue triage passed.

---

## Part C · Measured

### Experimental constants

- **Model:** `gemini-3.5-flash-lite` via the same OpenAI-compatible backend.
- **Tools:** same registry definitions and ordering, `schemas_sha=703c0002892f27ec`; the split deliberately restricts tool subsets by worker role.
- **Budget:** both S and M invoked with 250,000 maximum tokens per issue (1,250,000 for five-issue batches); S-plus used `--match split` to target actual M spend for each task, not an independently invented budget.
- **Evaluator:** identical grounded `check_task` and answer set, `checks_sha=55abcd67e6a3b208`, reviewer `scripted:approve-all`.
- **Task set:** `batch-a, batch-b, one-4402, one-4403, one-4405, one-4406, one-4409, one-4413`; 3 sweeps each, 24 runs per arm.

Both the experimental roles and the S-plus alternative used this same task set and evaluator. Ground-truth `task.answers` was read by the evaluator, never passed to the agent ways.

### Results (three sweeps)

| Arm | Kind | Passes / runs | Sweep min-max | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---:|---:|---:|---:|---:|
| S | single | 14/18 | 4-5 | 4 | 51,512 | 8.4 |
| S | batch | 5/6 | 1-2 | 1 | 350,079 | 33.8 |
| M | single | 9/18 | 3-3 | 2 | 26,258 | 8.4 |
| M | batch | 0/6 | 0-0 | 0 | 158,411 | 12.4 |
| S-plus | single | 6/18 | 2-2 | 2 | 26,796 | 9.9 |
| S-plus | batch | 0/6 | 0-0 | 0 | 150,147 | 49.7 |

**Token multipliers.** M/S mean tokens: **0.510x** for single issues and **0.453x** for batches. The lecture's illustrative **15x** is a vendor-reported multi-agent/chat ratio on another workload, not the same M/S comparison, so it is context rather than an apples-to-apples benchmark. The prediction of 1.5x/1.8x *more* tokens was wrong for this implementation: M consumed substantially *fewer* tokens. It was not an unqualified efficiency win because accuracy fell from 14/18 to 9/18 for singles and from 5/6 to 0/6 for batches.

### Per-task grounded passes, token use, and wall-clock time

Each cell shows **passes / 3 runs; mean tokens; mean seconds**, measured from `results/runs_06.jsonl`. These are task-level values, not just arm totals.

| Task | S | M | S-plus |
|---|---|---|---|
| `batch-a` | 2/3; 350,551; 33.7s | 0/3; 162,160; 12.3s | 0/3; 149,920; 50.7s |
| `batch-b` | 3/3; 349,607; 33.8s | 0/3; 154,663; 12.6s | 0/3; 150,374; 48.7s |
| `one-4402` | 1/3; 63,525; 7.6s | 0/3; 29,661; 7.2s | 0/3; 30,285; 10.9s |
| `one-4403` | 3/3; 33,408; 6.6s | 0/3; 24,490; 9.0s | 0/3; 25,039; 9.8s |
| `one-4405` | 3/3; 40,945; 7.0s | 1/3; 27,615; 8.4s | 0/3; 28,251; 8.7s |
| `one-4406` | 1/3; 70,213; 11.5s | 2/3; 30,837; 9.8s | 0/3; 30,370; 11.6s |
| `one-4409` | 3/3; 65,396; 12.2s | 3/3; 23,516; 8.6s | 3/3; 24,809; 9.1s |
| `one-4413` | 3/3; 35,585; 5.2s | 3/3; 21,429; 7.6s | 3/3; 22,025; 9.1s |

### Did S-plus actually match M spending?

S-plus ran sequential, fresh-context read-only attempts on the same issue and selected an answer by deterministic majority vote before making writes. The runner supplied task-specific M mean tokens with `--match split`; the following are **observed**, not allocated, mean token counts:

| Task | M mean tokens | S-plus mean tokens | S-plus vs M |
|---|---:|---:|---:|
| `batch-a` | 162,160 | 149,920 | -7.5% |
| `batch-b` | 154,663 | 150,374 | -2.8% |
| `one-4402` | 29,661 | 30,285 | +2.1% |
| `one-4403` | 24,490 | 25,039 | +2.2% |
| `one-4405` | 27,615 | 28,251 | +2.3% |
| `one-4406` | 30,837 | 30,370 | -1.5% |
| `one-4409` | 23,516 | 24,809 | +5.5% |
| `one-4413` | 21,429 | 22,025 | +2.8% |

The overall means were M 26,258 vs S-plus 26,796 tokens on singles, and M 158,411 vs S-plus 150,147 on batches. These are close on aggregate, although actual task-by-task differences above must be considered. Both variants sometimes stopped due to their own limits; matching a budget does not force exact same token consumption.

### Slide 18's three questions

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | No. M/S = 0.510x. | No. M/S = 0.453x. |
| Does spending more raise the score? | In this sample, **higher observed spend correlated with higher pass counts**: S 14/18 at 51,512 tokens vs S-plus 6/18 at 26,796. This does not prove causation. | In this sample S spent more and passed 5/6, while S-plus passed 0/6. It is an association, not a causal estimate. |
| Given the same budget, did one agent do as well? | No: S-plus 6/18 vs M 9/18 at roughly matched tokens. | Tied at zero: both S-plus and M passed 0/6 batches. |

**Why all three arms matter.** S versus M alone suggests the single agent is more accurate but more expensive; it cannot distinguish architectural quality from spend. The matched-spend S-plus baseline shows M did provide a modest relative single-issue benefit (9 vs 6 passes at similar spend), so claiming "multi-agent never helps" would be unsupported. Nevertheless, M was far below S's absolute reliability, and on batches both low-spend designs passed zero tasks. M finished batches faster (mean 12.4s vs S 33.8s), but a fast incorrect batch is not useful. The S-plus batch mean was 49.7s.

### Every failed M run (15 of 24)

Each row is grounded in `runs/<run_id>.jsonl`, `results/runs_06.jsonl`, and the tracker-based grounded audit. Read/write details describe the recorded agents; the coordinator's waits are dependencies, **not** deadlocks. The "first identified" column lists the earliest *identified failure mode for the affected issue*, not a claim of globally ordered timestamps across independent batch pipelines.

| Run | What each agent read, wrote, and waited on | First identified failure(s) | Anomaly | MAST category |
|---|---|---|---|---|
| `split-batch-a-s01-aa5348` | Coordinator waited on 5 investigators and 3 writers. #4410: investigator read issue x1, searched x8, read files x0; writer no successful writes; #4412: investigator read issue x1, searched x7, read files x0; writer label, comment; #4414: investigator read issue x1, searched x3, read files x2 (src/api/reports.ts, src/db/repos/reportRepo.ts); writer label, PR, comment; #4420: investigator read issue x1, searched x2, read files x2 (docs/API.md, src/api/auth.ts); writer label, PR, comment; #4423: investigator read issue x1, searched x8, read files x0; writer no successful writes | #4410: investigator exhausted nine calls without a valid return; no downstream writes; #4423: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-batch-a-s02-37898e` | Coordinator waited on 5 investigators and 4 writers. #4410: investigator read issue x1, searched x1, read files x1 (src/config.ts); writer label, PR, comment; #4412: investigator read issue x1, searched x2, read files x2 (src/api/health.ts, docs/API.md); writer label, PR, comment; #4414: investigator read issue x1, searched x6, read files x2 (src/api/reports.ts, src/db/repos/reportRepo.ts); writer no successful writes; #4420: investigator read issue x1, searched x3, read files x2 (docs/API.md, src/api/auth.ts); writer label, PR, comment; #4423: investigator read issue x1, searched x1, read files x1 (src/i18n/index.ts); writer label, PR, comment | #4412: question was assigned src/api/health.ts and an unnecessary PR (expected file: none); #4414: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-batch-a-s03-bb104a` | Coordinator waited on 5 investigators and 5 writers. #4410: investigator read issue x1, searched x1, read files x1 (src/config.ts); writer label, PR, comment; #4412: investigator read issue x1, searched x2, read files x2 (src/api/health.ts, docs/API.md); writer label, PR, comment; #4414: investigator read issue x1, searched x2, read files x2 (src/api/reports.ts, src/db/repos/reportRepo.ts); writer label, PR, comment; #4420: investigator read issue x1, searched x3, read files x2 (docs/API.md, src/api/auth.ts); writer label, PR, comment; #4423: investigator read issue x1, searched x1, read files x1 (src/i18n/index.ts); writer label, PR, comment | #4412: question was assigned src/api/health.ts and an unnecessary PR (expected file: none) | `none` | `task_verification` |
| `split-batch-b-s01-e5493b` | Coordinator waited on 5 investigators and 4 writers. #4424: investigator read issue x1, searched x3, read files x1 (src/exportUtils.ts); writer label, PR, comment; #4426: investigator read issue x1, searched x2, read files x2 (src/util/money.ts, docs/ARCHITECTURE.md); writer label, PR, comment; #4429: investigator read issue x1, searched x8, read files x0; writer no successful writes; #4431: investigator read issue x1, searched x3, read files x2 (src/exportUtils.ts, src/util/strings.ts); writer label, PR, comment; #4434: investigator read issue x1, searched x1, read files x1 (src/components/UploadForm.tsx); writer label, PR, comment | #4426: question was assigned src/util/money.ts and an unnecessary PR (expected file: none); #4429: investigator exhausted nine calls without a valid return; no downstream writes; #4431: label bug instead of expected feature | `none` | `system_design` |
| `split-batch-b-s02-63f5c0` | Coordinator waited on 5 investigators and 2 writers. #4424: investigator read issue x1, searched x3, read files x1 (src/exportUtils.ts); writer label, PR, comment; #4426: investigator read issue x1, searched x4, read files x3 (src/db/client.ts, src/util/money.ts, src/types.ts); writer no successful writes; #4429: investigator read issue x1, searched x7, read files x1 (src/api/reports.ts); writer no successful writes; #4431: investigator read issue x1, searched x4, read files x3 (test/exportUtils.test.ts, src/exportUtils.ts, src/util/strings.ts); writer no successful writes; #4434: investigator read issue x1, searched x1, read files x1 (src/components/UploadForm.tsx); writer label, PR, comment | #4426: investigator exhausted nine calls without a valid return; no downstream writes; #4429: investigator exhausted nine calls without a valid return; no downstream writes; #4431: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-batch-b-s03-61e9da` | Coordinator waited on 5 investigators and 4 writers. #4424: investigator read issue x1, searched x7, read files x1 (src/exportUtils.ts); writer no successful writes; #4426: investigator read issue x1, searched x2, read files x2 (src/util/money.ts, docs/ARCHITECTURE.md); writer label, PR, comment; #4429: investigator read issue x1, searched x2, read files x2 (src/api/reports.ts, src/util/strings.ts); writer label, PR, comment; #4431: investigator read issue x1, searched x3, read files x3 (test/exportUtils.test.ts, src/exportUtils.ts, src/util/strings.ts); writer label, PR, comment; #4434: investigator read issue x1, searched x1, read files x1 (src/components/UploadForm.tsx); writer label, PR, comment | #4424: investigator exhausted nine calls without a valid return; no downstream writes; #4426: question was assigned src/util/money.ts and an unnecessary PR (expected file: none); #4431: label bug instead of expected feature | `none` | `system_design` |
| `split-one-4402-s01-b75b52` | Coordinator waited on 1 investigators and 0 writers. #4402: investigator read issue x1, searched x7, read files x1 (src/ingest/parser.ts); writer no successful writes | #4402: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-one-4402-s02-d65d7e` | Coordinator waited on 1 investigators and 0 writers. #4402: investigator read issue x1, searched x8, read files x0; writer no successful writes | #4402: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-one-4402-s03-d469bf` | Coordinator waited on 1 investigators and 0 writers. #4402: investigator read issue x1, searched x7, read files x1 (src/ingest/parser.ts); writer no successful writes | #4402: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-one-4403-s01-f77e80` | Coordinator waited on 1 investigators and 0 writers. #4403: investigator read issue x1, searched x8, read files x0; writer no successful writes | #4403: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-one-4403-s02-4ca416` | Coordinator waited on 1 investigators and 1 writers. #4403: investigator read issue x1, searched x1, read files x1 (src/export/csv.ts); writer label, PR, comment | #4403: question was assigned src/export/csv.ts and an unnecessary PR (expected file: none) | `none` | `task_verification` |
| `split-one-4403-s03-f38b46` | Coordinator waited on 1 investigators and 1 writers. #4403: investigator read issue x1, searched x4, read files x1 (src/export/csv.ts); writer label, PR, comment | #4403: question was assigned src/export/csv.ts and an unnecessary PR (expected file: none) | `none` | `task_verification` |
| `split-one-4405-s02-3e64de` | Coordinator waited on 1 investigators and 0 writers. #4405: investigator read issue x1, searched x5, read files x3 (src/components/ExportButton.tsx, src/components/ReportTable.tsx); writer no successful writes | #4405: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-one-4405-s03-0e5394` | Coordinator waited on 1 investigators and 0 writers. #4405: investigator read issue x1, searched x8, read files x0; writer no successful writes | #4405: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |
| `split-one-4406-s01-e099a8` | Coordinator waited on 1 investigators and 0 writers. #4406: investigator read issue x1, searched x7, read files x1 (src/ingest/parser.ts); writer no successful writes | #4406: investigator exhausted nine calls without a valid return; no downstream writes | `none` | `system_design` |

**Cross-run diagnosis.** Twelve of the fifteen failed M runs had at least one investigator reach its nine-model-call cap and return no valid contract, so the coordinator stopped that issue's pipeline and its required writes never occurred. Three failed M runs had only semantic errors with valid returns and a passing combined check (`split-batch-a-s03-bb104a`, `split-one-4403-s02-4ca416`, `split-one-4403-s03-f38b46`). Across all failed M runs, 23 issue-level failures comprised **15 missing-action failures**, **six no-change questions handled as file/PR changes** (issues #4412, #4426, #4403 across sweeps), and **two wrong-label failures** (issue #4431 labeled `bug`, expected `feature`). Some batch runs exhibit both worker stoppage and semantic errors.

The JSON lists one dominant MAST class for each failed *run*: 12 `system_design` (turn-limit/invalid handoff, including mixed batch cases) and three `task_verification` (structurally consistent but wrong results). Every observed concurrency anomaly is `none`: there was no traced wait cycle, stale shared-state overwrite, or inconsistent cross-worker write. No evidence here supports classifying these as deadlocks, lost updates, or write skew. Schema validation and `check_combined` are necessary safeguards, but neither verifies that a `question` should have `file: none` or that an issue deserves the correct label.

---

## Part D · The decision

**One issue: keep a single agent.** S passed 14/18 at mean 51,512 tokens. M passed 9/18 at 26,258 tokens; S-plus passed 6/18 at 26,796 tokens. Although M beat the matched-spend baseline, two sequential specialist stages introduced fragile handoffs for one dependent task. Reduced spend did not justify five fewer passes than S.

**A batch of five: keep a single agent.** S passed 5/6 at mean 350,079 tokens and 33.8s. M passed 0/6 at 158,411 tokens and 12.4s. Parallelism improved time and token usage, but all batch tasks failed the grounded check. S-plus also passed 0/6 and was slower at 49.7s on average. Do not deploy a faster architecture that cannot reliably complete the batch.

**Revisit condition.** First eliminate the dominant causes: valid recoverable investigator returns at the stopping limit; semantic verification before writing, including `question -> file: none -> no PR`; and independent final answer checking. Then rerun the same task set with the same evaluator and model for at least three sweeps per arm. Reconsider splitting only if it meets or exceeds S's baseline accuracy (at least 14/18 singles and 5/6 batches) while lowering mean tokens or latency by at least 20%, without integrity errors. This is a prospective decision threshold, not something already achieved.

**Record:** `decisions/0006-topology.md` on `main`. The prototype code and worker prompts remain on the separately tagged `lab-06-split` branch. Do not merge them into `main`; leave `ARCHITECTURE.md` unchanged.

---

## AI assistance

I used ChatGPT throughout Assignment 6 for planning the coordinator/investigator/writer split, drafting the structured schema and guard implementations, preparing and revising the worker prompts and split execution code, creating the S-plus and result-collection scripts, debugging return validation and evaluation logic, interpreting measured traces, and drafting the final report and decision record. I ran the experiments and checker commands in my repository, reviewed the outputs against trace and tracker evidence, and used those recorded results for the conclusions. The model was not used as an oracle inside the evaluated ways; known task answers were read only by the grounded evaluator. The 72-run results are the actual recorded results, not AI-generated predictions.

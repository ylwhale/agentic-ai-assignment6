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

Prediction commit: **[INSERT ACTUAL GIT COMMIT HASH]**

---

## Part B · The split

**The coordinator and the roles, and the tools each holds:**

To be completed after implementation on `lab-06-split`.

**Why they split by tool surface:**

To be completed after implementing the role-specific tool restrictions.

**The return contract, field by field, and which fields come from the worker's tool calls:**

To be completed after implementing and validating `split/contract.schema.json`.

**Each worker's share of the budget, and what is held back:**

To be completed after implementing the coordinator's shared token-budget allocation.

**The five checks, where each is in your code:**

To be completed after implementing and testing:

1. Structured worker-return contract validation.
2. Deadlock detection.
3. Combined-result verification.
4. Idempotency and compare-and-set protection for shared writes.
5. Unified multi-agent trace with agent identity, parent, and token accounting.

---

## Part C · Measured

**The five constants (slide 59): model, tools, budget, evaluator, task set.**

To be completed using the actual experiment configuration and recorded `run_start` data.

**The results.**

| Arm | Kind | Passes / runs | Lowest and highest sweep | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---|---|---|---|---|
| S | single | | | | | |
| S | batch | | | | | |
| M | single | | | | | |
| M | batch | | | | | |
| S-plus | single | | | | | |
| S-plus | batch | | | | | |

**Your multiplier (M over S), single and batch, beside the lecture's 15×:**

To be calculated using actual token spending.

**Whether S-plus's spend matched M's in fact, task by task:**

To be verified using the measured token counts.

### Slide 18's three questions, for each kind of task

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | | |
| Does spending more raise the score? | | |
| Given the same budget, did one agent do as well? | | |

**What you would have claimed from arms S and M alone, and what you claim now:**

To be completed after comparing all three arms and accounting for token spending.

### Every arm M run that failed

| Run | What each agent read, wrote and waited on | The first thing that went wrong | Anomaly | MAST category |
|---|---|---|---|---|
| | | | | |

Failure analysis must use actual run traces and classify each failed Arm M run.

The possible concurrency anomalies are lost update, write skew, deadlock, and misalignment. Use `none` when no concurrency anomaly occurred.

Each failure must also receive a MAST category: system design, inter-agent misalignment, or task verification.

---

## Part D · The decision

**One issue:**

To be decided using the measured results.

**A batch of five:**

To be decided using the measured results.

**The condition that would reopen it:**

To be defined using a measurable and reproducible condition.

**The record:**

`decisions/0006-topology.md`

The final architecture decision will be documented without merging the experimental split into `main`.

`ARCHITECTURE.md` will remain unchanged, reflecting that RepoMind retains its single-agent implementation in this repository.

---

## AI assistance

I used ChatGPT to help draft and organize the Part A analysis, including the proposed role decomposition, communication requirements, architectural sketch, four-gate evaluation, and prediction explanations.

The draft was prepared using the Assignment 6 instructions and the selected coordinator–investigator–writer architecture. The analysis and predictions must be checked against the assignment requirements and the separately committed prediction file.

Any additional AI assistance used to implement the coordinator, worker roles, return contract, safety checks, evaluation scripts, or experimental analysis will be documented here before the final submission.

All experimental results and architectural conclusions must be verified against the actual test outputs and recorded run traces.
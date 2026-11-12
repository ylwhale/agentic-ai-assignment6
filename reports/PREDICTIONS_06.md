# Assignment 6 — Predictions

## Single-Issue Tasks

- **Token multiplier:** I predict Arm M will spend approximately 1.5 times as many tokens as Arm S.
- **Task performance:** I expect Arm S and Arm M to have similar pass rates, differing by no more than one task per sweep.
- **Matched-spend comparison:** I predict Arm S-plus will perform at least as well as Arm M when given approximately the same token spending.

**Reasoning:** For one issue, investigation and writing depend on each other. Additional agents introduce communication and coordination overhead without providing substantial parallelism.

## Batch Tasks

- **Token multiplier:** I predict Arm M will spend approximately 1.8 times as many tokens as Arm S.
- **Task performance:** I predict Arm M may pass approximately one additional batch task per sweep compared with Arm S.
- **Matched-spend comparison:** I predict Arm S-plus will perform approximately as well as Arm M when given approximately the same token spending.

**Reasoning:** Five unrelated issues create opportunities for parallel processing and context isolation. However, these advantages may be offset by additional token costs and coordination overhead.

## Overall Prediction

Multi-agent decomposition is unlikely to be justified for individual issues.

Batch processing provides a stronger potential benefit, but a split should be adopted only if its measured performance justifies its additional cost and complexity.

These predictions were made before running the multi-agent experiments.
---
name: feature-dedup
description: Use when adding or editing recommendation, next-step, adaptive, or "what should I run next" logic in Continum — files analytical_reasoning.py, askdata/flow.py, askdata/ask_engine.py. Forces a check for an existing implementation before adding a parallel one, and resolves the Adaptive Rec vs Next Step overlap.
---

# One capability, one implementation

Continum currently has overlapping "what next" logic in three places:

- `continum/experimentation/analytical_reasoning.py` → `adaptive_recommendations()`
  (~line 284) — LLM-backed recommendations.
- `continum/askdata/flow.py` (~line 199–263) → `SUGGEST` / next-step planner,
  phase-ordered "Suggested next step" list.
- `continum/askdata/ask_engine.py` (~line 43) → `AskIntent.RECOMMENDATION`
  keyword intent ("what should", "next step", "run next").

These answer the same user question by different paths. That divergence is why
"Adaptive Rec" and "Next Step generation" feel redundant (issue #5).

## The rule

Before adding ANY new recommendation/next-step code, answer in the PR/commit:

1. Does one of the three paths above already produce this output?
2. If yes — **extend that one** and route the others to it. Do not add a fourth.
3. If two produce overlapping output, **merge to one canonical producer** and
   make the other a thin alias/caller.

## Decision for Adaptive Rec vs Next Step
They are not both needed as separate user-facing features:
- **Next-step** (`flow.py`) is *deterministic + phase-aware* — best for "where am
  I, what's the next step in the workflow."
- **Adaptive recommendations** (`analytical_reasoning.py`) is *LLM, data-driven* —
  best for "given these results, what should I investigate."

Pick `flow.py`'s phase-aware planner as the single entry point for the chat
"what next" chip, and have it call `adaptive_recommendations()` only to enrich
the list with data-driven items. One surface, one code path. Don't expose both
as separate buttons.

## Checklist
- [ ] Searched the three paths above before writing new code.
- [ ] New logic extends the canonical producer, not a parallel one.
- [ ] No two controls answer the identical question via different code.

# Continum Copilot guardrail skills

Project-local Claude Code skills that encode the conventions of the Continum /
PersistIQ Copilot so the *next* edit (by a human or by the Copilot's own LLM
harness) can't re-introduce a known failure class.

Each skill is a directory with a `SKILL.md`. Claude loads a skill automatically
when a request matches its `description`, so these act as guardrails at edit
time rather than as docs nobody reads.

| Skill | Prevents | Maps to issue |
|---|---|---|
| `module-registry`  | hardcoded module names/phases; "everything says Campaign Insights" | #7, #8 |
| `langgraph-routing`| unreachable graph nodes (viz path silently dropped) | #1 |
| `no-dead-features` | shipping no-op buttons / dead model variants | #2, #4 |
| `feature-dedup`    | two implementations of one capability | #5 |
| `output-rendering` | results rendering in the wrong place / not as text | #3, #6 |

All paths below are relative to the repo root on `feat/llm-tool-router`.

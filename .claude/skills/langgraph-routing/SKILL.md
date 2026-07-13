---
name: langgraph-routing
description: Use when editing the AskData LangGraph engine, its planner, node routing/branching, or the visualization path — files continum/askdata/graph_logic.py, engine.py, ask_engine.py. Enforces that every terminal node (especially viz) stays reachable, guarded, and covered by a routing test.
---

# Every graph node must be reachable, guarded, and tested

The AskData graph plans a sequence of steps and executes nodes in order. The
plan and nodes live in `continum/askdata/graph_logic.py`:

- The planner emits a `plan` list, default `["refine", "sql", "viz"]`
  (graph_logic.py ~line 124–150).
- `visualization_node` (graph_logic.py ~line 310) is the viz terminal. It has a
  **deterministic guard** that returns `{"visualizations": []}` when a chart
  wouldn't help (non-comparable rows / no numeric column), then an LLM step that
  may also return `[]`.

Issue #1 ("viz never shows") is almost always one of: the planner dropped `viz`
from the plan, the deterministic guard rejected the data, or the LLM returned an
empty chart. Diagnose in that order — don't assume it's the LLM.

## Rules

1. **No unreachable terminal.** Any node you add must be reachable by an explicit
   plan entry or edge condition. If a node can only be reached "sometimes",
   document the exact condition in a comment next to the planner.
2. **Every branch has a deterministic fallback.** An LLM step that can return
   empty/garbage must fall back to a defined alternative (text, table) — never a
   silent dead end.
3. **Log every routing decision.** Match the existing
   `logger.info("Entering visualization_node")` / guard-skip logging so a dropped
   viz is visible in `preview_logs`, not invisible.
4. **Add a routing assertion for the path you touched.** For viz: a test that a
   "plot/chart/trend/distribution over time" query produces a plan containing
   `viz` AND a non-empty `visualizations` payload for chartable data. A weak
   branch must fail a test, not degrade silently to text.

## When viz "doesn't show up" — triage order
1. Print the planner output — is `viz` in the plan?
2. Log the guard inputs (`rows`, `cols`, `numeric`) — did the deterministic guard skip?
3. Log the raw LLM viz response — empty list or unparseable?
4. Only then inspect the frontend render path in `dashboard.py`.

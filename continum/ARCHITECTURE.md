# Continum — Architecture & Layout

The package mirrors the **MatchView backend diagram**. Organising rule:
**a diagram node with more than one immediate child becomes a folder; otherwise it's a single file** (within practical size limits).

## Query flow

```
User UI ─▶ intentanalyser.py ─▶ orchestrator.py ─┬─▶ askdata/ ─▶ sql/viz/insight (graph_logic.py)
(userui/)   (classify + entities) (route decider)  └─▶ toolinterface.py ─▶ experimentation/
                                                                            insights/ ◀── post-run intelligence ──▶ User UI
```

## Layout

| Path | Diagram block | Role |
|---|---|---|
| `userui/` | User UI | Flask app, routes, dashboard templates, health |
| `contextmate/` | ContextMate | Clean raw data + generate/validate metadata (ingestion, contracts, synthetic, discovery) |
| `datastore/` | Data Store | Loader, stores, cross-exp memory, lineage, inspectors, `semantic_layer.py` (ontology+metrics+dimensions) |
| `intentanalyser.py` | Intent Analyser | Classify a query's intent + extract entities (single file → 0 children) |
| `orchestrator.py` | Orchestrator | Route decider: `detect_tool` / `execute_tool` (single file → 0 children) |
| `toolinterface.py` | Tool-Calling Interface | Module registry + `run_module` (single file) |
| `askdata/` | AskData (SQL/Viz/Insight agents) | LangGraph engine; the 3 agents are `sql_node`/`visualization_node`/`insight_node` sections in `graph_logic.py`; `ask_engine.py`, `flow.py`, `readout.py`, `narrative_runtime.py` |
| `experimentation/` | Experimentation Module Family | `analysis_dag`, `metric_planner`, `artifacts`, `enterprise`, `compare`, + `stats/ causal/ analytics/ monitoring/ post_analysis/` |
| `insights/` | (post-run intelligence) | `insight_bus`, `patterns`, `session` (dead `cognition` + `recommendations` modules removed 2026-06-27) |
| `crosscutting/` | (shared leaf utils) | `llm.py` (client+config+manager), `console.py`, `pdf.py`, `runtime_config.py` |
| `tests/` | — | pytest suite (142 tests) |

## Where did the old code go? (new ← old)

| New | Former location(s) |
|---|---|
| `intentanalyser.py` | `runtime/ask/copilot.py` (`Intent`, `detect_intent`, `extract_entities`) |
| `orchestrator.py` | `runtime/ask/tools.py` (+ `_summarise` from the old shell executor) |
| `toolinterface.py` | `api/dispatcher.py` |
| `contextmate/` | `api/bootstrap`, `core/ingestion/contracts`, `core/synthetic/generator`, `phases/discovery` |
| `datastore/` | `app/loader`, `core/intelligence/knowledge_graph`, `core/memory/stores`, `runtime/memory`, `core/orchestration/engine`→`lineage`, `runtime/inspect`, `core/semantic_layer/*`→`semantic_layer` |
| `userui/` | `ui/*`, `core/health` |
| `askdata/` | `runtime/ask/askdata/*`, `runtime/ask/flow`, `runtime/ask/readout`, `runtime/ask/intent`→`ask_engine`, `runtime/narrative`→`narrative_runtime` |
| `experimentation/stats/` | `core/experimentation/*` |
| `experimentation/causal/` | `core/causal/*` |
| `experimentation/analytics/` | `core/analytics/*` |
| `experimentation/monitoring/` | `core/monitoring/*`, `phases/monitoring/monitoring` |
| `experimentation/post_analysis/` | `phases/analysis/*`, `phases/intelligence/synthesis` |
| `experimentation/` (root) | `artifacts/types`→`artifacts`, `core/orchestration/dags/analysis_dag`, `core/intelligence/{metric_planner,analytical_reasoning,narrative}`, `runtime/{enterprise,compare}`, `phases/{planning,deployment}` |
| `insights/` | `runtime/{intelligence→insight_bus, cognition, patterns, recommendations, session}` |
| `crosscutting/` | `core/llm/*`→`llm`, `runtime/config`→`runtime_config`, `runtime/console`, `core/output/pdf` |

## Removed (legacy CLI/REPL, superseded by the web UI)

`cli.py`, `app/workflow.py`, `runtime/ask/copilot.py` (REPL loop), `runtime/shell/*`, and `dashboard.py.main.bak`.
`compare.py`'s shell-driven interactive functions were dropped; its `_extract_metrics`/`_synthesise` (used by the web) remain.

## Result

35 → 16 folders; 114 → 86 Python files (−2,211 net lines); 142/142 tests green.

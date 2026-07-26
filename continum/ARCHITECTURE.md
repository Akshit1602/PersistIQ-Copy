# Continum — Architecture & Layout

A lean module structure built entirely on **LangChain + LangGraph**. One secrets
source (repo-root `.env`); one DuckDB warehouse built from `sample_data/<Dataset>/`.

## Query flow

```
User UI ─▶ orchestration/ ─┬─▶ AskData/  (SQLGenerator → VisualGenerator → InsightGenerator)
(userui/)  (intent (chatbot│            = a LangGraph
 path only) + route        └─▶ ExpSuite/ (discovery/planning/monitoring/analysis/learnings)
 decider + LangGraph)            │           reached manually, or as a chat tool-call
                    ContextGraph/ ◀──────────┘   (tracks queries + module outputs; dataset-level KG)
                    mapMeta/ ─────────────▶ DuckDB + per-dataset metadata (feeds AskData + ContextGraph)
```

Manual experiment usage routes directly to an ExpSuite module. Chatbot usage is
classified by `orchestration.intent` and routed by the rest of `orchestration`.

## Layout

| Path | Role | AI? |
|---|---|---|
| `__init__.py` | Project-wide LLM init: `LLMClient` + credentials (`.env` only) + `get_chat_llm` + lifecycle manager | — |
| `orchestration/` | Intent breakdown (`intent.py`, chatbot path only), path decider + AskData LangGraph (`graph.py`), MatchView tool-calling (`matchview.py`), LLM router (`router.py`), guided flow (`flow.py`), document Q&A (`readout.py`); exposes `ContinumEngine` / `get_askdata_engine`, and every public function directly (`from continum.orchestration import locate, format_question, ...` — name a function, not a file) | AI |
| `AskData/` | 3 generators — `SQLGenerator` (NL→SQL on DuckDB), `VisualGenerator` (chart spec), `InsightGenerator` (insight from data or ContextGraph) | AI |
| `ExpSuite/` | Experimentation framework: 5 phase folders (`discovery`, `planning`, `monitoring`, `analysis`, `learnings_repository`) + shared `stats/` + `artifacts.py` + `registry.py` + `modules.py` + `enterprise.py` | mostly algorithmic |
| `ContextGraph/` | Knowledge graph + cross-experiment memory + session + insight bus + semantic layer + lineage | AI (emulated) |
| `mapMeta/` | Scans `sample_data/<Dataset>/`, loads all into one DuckDB (Xometry medallion gold view kept), emits per-dataset metadata (`scanner.py`) | — |
| `paths.py` | Where runtime state + generated outputs live: `RUNTIME_DATA_DIR`, `OUTPUTS_DIR`, `new_run_dir(module_key)` (segregated per-run output folders) | — |
| `userui/` | Flask web console (unchanged UI); rewired to the modules above; also holds `pdf.py` (report rendering — an output concern) | — |
| `tests/` | pytest suite | — |

There is no `crosscutting/` package: `llm.py` folded into `__init__.py`, `pdf.py` moved to `userui/` (it's an output generator), `runtime_config.py` became the top-level `paths.py`, and `console.py` (unused anywhere) was deleted outright.

## Where the old code went (new ← old)

| New | Former location |
|---|---|
| `__init__.py` (LLM) | `crosscutting/llm.py` (folded; `crosscutting/` no longer exists) |
| `paths.py` | `crosscutting/runtime_config.py` |
| `userui/pdf.py` | `crosscutting/pdf.py` |
| `orchestration/intent.py` | `intentAnalyser.py` (formerly `intentanalyser.py`) — folded into `orchestration/` |
| `orchestration/matchview.py` | `orchestrator.py` |
| `orchestration/router.py` | `askrouter.py` |
| `orchestration/graph.py` + `AskData/*` | `askdata/graph_logic.py` (split) + `askdata/engine.py` |
| `orchestration/flow.py`, `orchestration/readout.py` | `askdata/flow.py`, `askdata/readout.py` |
| `AskData/InsightGenerator.py` | `askdata/{insight_node, readme}` |
| `ExpSuite/` | `experimentation/` (re-segregated into phases) + `modules/new_modules.py` |
| `ExpSuite/registry.py` | `toolinterface.py` |
| `ExpSuite/analysis/ask_engine.py` | `askdata/ask_engine.py` |
| `ContextGraph/` | `datastore/` + `insights/` + `askdata/narrative_runtime.py` |
| `mapMeta/` | `contextmate/` + `datastore/loader.py` + `askdata/metadata.py` |

## Data

`mapMeta.setup_database("./sample_data")` builds one in-memory DuckDB:
Xometry (`Xometry/` 5 CSVs → Bronze→Silver→Gold `gold_experiment_analysis`, aliased `experiment_results`),
Shell (`Shell/` → `dim_station`, `fact_station`), Walmart (`Walmart/` → `campaign_data`).
DuckDB-native AskData queries whichever dataset `ACTIVE_DATASET` selects.

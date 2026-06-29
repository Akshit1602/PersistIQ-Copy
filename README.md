# Continum MatchView

**Continum MatchView** is a unified platform for experimentation intelligence, causal inference, and automated product analytics. It bridges the gap between raw experimental data and actionable business decisions by combining rigorous statistical methods with LLM-powered narrative intelligence — all driven through **Continum Copilot**, the conversational AI layer that sits on top of every module.

---

## 🚀 Overview

At the centre of the product is **Continum Copilot** — an AI-driven UI layer that lets you *talk to the platform*. Instead of hunting through menus, you ask a question or request an action in plain English and the Copilot:

- **answers data questions** by generating SQL, running it, and rendering the result as a table **and an interactive chart**;
- **explains the tool** from its own documentation;
- **drives the MatchView application modules for you** via tool calling — detecting intent, asking you to confirm, then executing the relevant module internally and reporting back inside the chat; and
- **guides you step-by-step through the experiment** — working out where you are in the lifecycle, suggesting the next step, then asking for that module's inputs one question at a time (see [Guided Flow](#-guided-flow-mvp2)).

Underneath the Copilot, Continum MatchView (also referred to as **Continum OS**) covers the entire experimentation lifecycle in five phases:

| Phase | Purpose |
|---|---|
| **Discovery** | Connect to source data, dynamic schema mapping, data validation |
| **Planning** | Brief generation, opportunity sizing, power calc, KPI/tracking plan, audience selection |
| **Monitoring** | Live health monitor + sequential testing (mSPRT) during the experiment |
| **Analysis** | A/B readout, causal inference (DiD, PSM, Synthetic Control, ITS, RDD), Simpson's, ROI |
| **Deployment** | Uplift modelling + decision engine for the action layer |

The platform is consumed via an **Interactive CLI**, a **Developer Shell**, or the **Visual Web Console** (where the Copilot lives in a collapsible right-hand pane).

---

## 🤖 Continum Copilot

The Copilot is a collapsible pane in the web console (toggled by the 🤖 floating button, bottom-right). It runs in three modes:

| Mode | What it does | Backed by |
|---|---|---|
| **✨ Auto** | Picks the best engine from your question, and intercepts MatchView module intents (see Tool Calling). | router + tools |
| **📖 Guide** | "How do I…?" / "What is…?" help, grounded in the README(s). | README reader + LLM |
| **📊 Data** | Natural-language → SQL over the dataset, returned as text + table + chart. | AskData LangGraph engine |

**Data answers** flow through the **AskData engine** (`continum/runtime/ask/askdata/`), a multi-node LangGraph workflow:

```
question → orchestrator → refine → sql (generate + execute) → visualization → insight
```

It builds its own in-memory SQLite from the bundled dataset, returns
`{response, sql, table, columns, visualizations}`, and the pane renders:

- the **insight** text,
- an **interactive Plotly chart** (bar / line / pie),
- the result **table**, and
- the generating **SQL**, tucked inside a collapsible **“View SQL”** dropdown.

### How the chat request flows

```
Copilot pane (dashboard.py JS)
   │  POST /api/copilot/ask  {question, mode, ui_context, history, [confirm_tool|decline]}
   ▼
copilot_ask()  (continum/ui/routes/api.py)
   ├─ confirm_tool? ───────────────► execute_tool()      → run a MatchView module / AskData
   ├─ module intent? ──────────────► confirmation prompt  (returns pending_tool)
   └─ otherwise ───────────────────► _auto_mode → Guide (README) | AskData (NL→SQL)
   ▼
JSON {response, sql, table, columns, visualizations, pending_tool, deploy_warning, next_steps, suggestions}
   ▼
cpAddBot() renders text + deploy-warning + collapsible SQL + table + Plotly chart
```

LLM credentials are optional. With Azure/OpenAI configured the Copilot uses GPT-4o-class models; otherwise it falls back to a local model where possible and remains usable for non-LLM features.

---

## 🧩 Tool Calling Architecture

The Copilot is a functional UI layer: when a question requires a MatchView module, it **calls that module for you** rather than just talking about it. This is implemented in **`continum/runtime/ask/tools.py`** and wired into `copilot_ask`.

**The protocol (intent → confirm → execute):**

1. **Detect** — `detect_tool(question)` matches the question against a curated set of `MatchViewTool` entries (keyword + regex triggers). How-to / "about the tool" phrasing is deliberately *not* intercepted (that's a Guide question, not an action).
2. **Confirm** — the Copilot returns a `pending_tool` and asks, explicitly:
   > *"Would you like to use the relevant MatchView **{Module}** module to {answer this / take this action}?"*
   The pane shows **Yes / No** chips (a typed "yes"/"no" works too). No module runs until you confirm.
3. **Execute** — on confirmation the frontend re-POSTs with `confirm_tool=<key>`; `execute_tool()` runs the real capability internally and the result renders in the chat.

**Module mapping** — the Copilot speaks the MatchView vocabulary while driving Continum's real modules from the dispatcher registry (`continum/api/dispatcher.py` → `run_module`):

| MatchView module (user-facing) | Kind | Real Continum capability |
|---|---|---|
| **Lead Lists** | analysis | `audience_selection` — propensity-scored audience selection |
| **Campaigns** | analysis | `experiment_analysis` — full A/B readout pipeline |
| **Campaign Insights** | analysis | `causal_analysis` — DiD / PSM / ITS attribution |
| **Sequence Monitoring** | analysis | `health_monitor` — SRM, guardrails, IOR trajectory |
| **Email Analytics** | data | AskData NL→SQL over the dataset (chartable) |
| **Deployment** | **deploy** | `uplift_modeller` + `decision_engine` — go-live / targeting |

Module execution is **best-effort and safe**: data look-ups go to the reliable AskData engine; analysis/deploy modules call `run_module`, and if a module needs more setup than the chat session can supply, the Copilot falls back to a data-grounded answer instead of surfacing an error.

---

## 🧭 Guided Flow (MVP2)

Tool calling above is **reactive** — you ask, and the question is mapped to one module. The **Guided Flow** is the **proactive** counterpart: you don't have to know which module to ask for. It treats **every module as a tool** and walks you through the experimentation lifecycle, one step at a time.

Tap the **🧭 Guide me** chip (or just say *"what's next?"* / *"guide me"*) in any mode, and the Copilot:

1. **Locates you** — reads your run history (`ExperimentSession.execution_history`) against the five-phase plan and shows a progress ledger (`✅ done · 🔵 in progress · ⚪ not started` per phase).
2. **Suggests the next step** — the next unrun module in your current phase, then the head of the next phase, as pickable chips.
3. **Fills the inputs** — once you pick a step, it asks **one question per input field**, pre-filled with smart, data-detected defaults. Accept a default ("ok" or the chip), type a value, or pick an option; numbers are validated and re-prompted on bad input.
4. **Confirms, then runs** — it echoes the gathered inputs for a final ✅, runs the module in the **console** (live stream + PDF/CSV outputs), and drops a result summary back into the chat with a **"What's next?"** chip to continue the loop.

**The protocol (locate → suggest → fill → confirm → run):**

```
🧭 Guide me ─► POST /api/copilot/flow  {message, flow_state, ui_context}
                   │
  locate ─► suggest ─► fill (one field / turn) ─► confirm ─► action:"run_module"
                   │                                              │
                   ▼                                              ▼
  JSON {response, stage, flow_state, chips, action, module_key, fields}
                                                                  │
                                    runModuleWithFields() ─► POST /api/execute (SSE console)
```

The engine lives in **`continum/runtime/ask/flow.py`** — pure and deterministic, so it works with or without an LLM loaded — and is wired into **`copilot_flow()`** in `continum/ui/routes/api.py`. Per-module questions reuse the **same `_get_module_config` field schema** the config form uses, so the chat and the form never drift. Conversation state is a small `{stage, module_key, idx, collected}` dict round-tripped to the client, keeping the endpoint stateless across turns. Execution is delegated to the existing `/api/execute` SSE console, so live logs, file links, and the stop button all work unchanged.

The five-phase plan (`PHASE_PLAN`):

| Phase | Modules offered as steps |
|---|---|
| **Discovery** | `schema_discovery` · `data_validation` · `dimension_setup` |
| **Planning** | `opportunity_sizing` · `power_calculator` · `metrics_and_tracking` · `audience_selection` · `brief_generator` |
| **Live Monitoring** | `health_monitor` · `sequential_testing` |
| **Analysis & Readout** | `experiment_analysis` · `causal_analysis` · `simpsons_paradox` · `roi_tracker` · `learnings_repository` |
| **Deployment** | `uplift_modeller` · `decision_engine` |

---

## 🧪 The Experimentation Flow (guardrails)

Because the Copilot can take real actions, it follows two experimentation guardrails on every tool interaction:

1. **Suggest next steps.** After answering or running a module, the Copilot offers **1–2 logical next steps** as clickable chips — e.g. after building a Lead List: *"Would you like to launch a sequence to this audience?"*. Each `MatchViewTool` carries its own `next_steps`.

2. **Warn before going live.** Any action that **deploys, activates, launches, or sends** a live campaign/sequence is a `KIND_DEPLOY` tool. Before/at execution the Copilot injects a prominent warning:

   > ⚠️ **Deploy / go-live warning** — This moves **{Module}** from an experimentation / draft state into a **LIVE** environment. Live actions affect real audiences, real sends, and real budget, and cannot be undone from this chat. Confirm your guardrails and approvals are in place before continuing.

   This complements the platform's statistical guardrail framework (`continum/core/experimentation/guardrails.py`: SRM, AOV no-harm, latency/error caps with `warning` / `breached` / `hard_stop` levels), which gates whether an experiment is safe to roll out in the first place.

The net effect: experimentation stays the default, and moving to a live/irreversible state always requires an explicit, well-signposted confirmation.

---

## 🛠️ Project Structure

```text
MatchView/
├── continum/                            # Core package (Continum OS)
│   ├── cli.py                           # CLI entry: `python -m continum.cli <cmd>`
│   │
│   ├── api/                             # Internal dispatch + bootstrap
│   │   ├── bootstrap.py                 # Wires DB, state, LLM at startup
│   │   └── dispatcher.py                # Module registry; run_module(name, …) → phase fn
│   │
│   ├── app/                             # CSV → DuckDB loader + demo workflow
│   │   ├── loader.py                    # bronze/silver/gold layer builders
│   │   └── workflow.py
│   │
│   ├── artifacts/types.py               # Typed result schemas (ExperimentResult, …)
│   │
│   ├── core/                            # Reusable engines (no phase/runtime imports)
│   │   ├── experimentation/             # stats, bayesian, cuped, sequential, srm, guardrails
│   │   ├── causal/                      # DoWhy + matching + IPW/TMLE + forecasting
│   │   ├── analytics/                   # opportunity sizing, ROI synthesis, segment slicing
│   │   ├── intelligence/                # reasoning, knowledge graph, metric planner, narrative
│   │   ├── semantic_layer/              # metric registry, dimension catalog, ontology
│   │   ├── monitoring/                  # drift / anomaly / SRM detectors + monitors
│   │   ├── orchestration/               # DAG execution (dags/analysis_dag.py)
│   │   ├── llm/                         # client.py, manager.py, config.py (OpenAI/Azure + fallback)
│   │   ├── memory/stores.py             # CrossExperimentMemory (DuckDB-backed)
│   │   ├── output/                      # JSON/CSV/PNG/PDF writers
│   │   ├── synthetic/generator.py       # Demo data generator
│   │   └── viz/charts.py                # Matplotlib dark-theme helpers
│   │
│   ├── phases/                          # The five lifecycle phases — each calls into core/
│   │   ├── discovery/  planning/  monitoring/  analysis/  deployment/  intelligence/
│   │
│   ├── runtime/                         # Interactive session layer
│   │   ├── session.py                   # ExperimentSession state-bag
│   │   ├── intelligence.py              # InsightBus (pub/sub) + WORKFLOW_CHAIN next-steps
│   │   ├── memory.py  enterprise.py  recommendations.py  …
│   │   │
│   │   ├── ask/                         # ── Continum Copilot ──
│   │   │   ├── copilot.py               # (legacy) turn-based reasoning + intent taxonomy
│   │   │   ├── intent.py                # intent classifier
│   │   │   ├── tools.py                 # ★ MatchView tool calling (detect/confirm/execute)
│   │   │   ├── flow.py                  # ★ Guided flow (locate → suggest → fill → run)
│   │   │   └── askdata/                 # ★ AskData NL→SQL LangGraph engine
│   │   │       ├── engine.py            # AskDataGraphEngine.ask() → response/sql/table/viz
│   │   │       ├── graph_logic.py       # orchestrator → refine → sql → visualization → insight
│   │   │       ├── metadata.py          # dataset schema → metadata
│   │   │       ├── llm.py               # provider-agnostic chat LLM factory
│   │   │       └── readme.py            # torch-free README reader (Guide mode)
│   │   │
│   │   └── shell/                       # Interactive CLI shell (menu, executor, renderer)
│   │
│   ├── ui/                              # Flask-based Visual Operator Console
│   │   ├── app.py                       # Flask factory; async boot of DB + medallion layers
│   │   ├── __main__.py                  # `python -m continum.ui` launcher
│   │   ├── routes/api.py                # JSON API — incl. /api/copilot/ask + /api/copilot/flow
│   │   └── templates/dashboard.py       # Dashboard + Copilot pane HTML/CSS/JS (Python string)
│   │
│   └── tests/                           # Pytest suite (conftest, statistics, calibration, routes)
│
├── .github/workflows/ci.yml             # tests · import smoke · pipeline integration
├── sample_data/                         # accounts / users / quotes / orders / experiments CSVs
├── runtime_data/                        # Generated artifacts (gitignored)
├── requirements.txt
└── README.md
```

---

## 🧭 Architecture & Data Flow

The package is layered so that **phases orchestrate, `core/` computes, `runtime/` holds session state, and `ui/` presents**. Nothing in `core/` imports from `phases/` or `runtime/` — dependencies only point inward.

```
            ┌─────────────────────────────────────────────────────────┐
  Entry     │  cli.py · ui/ (Flask + Copilot) · runtime/shell · demo   │
  points    └───────────────────────────┬─────────────────────────────┘
                                         │
                          ┌──────────────▼──────────────┐
  Dispatch                │  api/dispatcher  +  bootstrap │   run_module(name) → phase fn
                          └──────────────┬──────────────┘
                                         │
        ┌────────────────────────────────▼────────────────────────────────┐
  Phases │  discovery → planning → monitoring → analysis → deployment       │
        └────────────────────────────────┬────────────────────────────────┘
                                         │ call into
                          ┌──────────────▼──────────────┐
  Engines                 │  core/ (experimentation,     │
                          │  causal, analytics, llm, …)  │
                          └──────────────┬──────────────┘
                                         │ read/write
        ┌────────────────────────────────▼────────────────────────────────┐
  Data   │  app/loader → DuckDB medallion:  bronze → silver → gold          │
        └─────────────────────────────────────────────────────────────────┘
```

**Medallion data layers** (built by `app/loader.py`):
- **Bronze** — raw CSVs from `sample_data/` (or a Snowflake source) loaded verbatim into DuckDB.
- **Silver** — cleaned, typed, conformed tables (e.g. `silver_inquiries`).
- **Gold** — analysis-ready marts (e.g. `gold_experiment_analysis`) consumed by the phases.

**Session state** (`runtime/`) — an `ExperimentSession` plus an `InsightBus` thread through a run, so the CLI, shell, Copilot, and UI all see the same live state, recommendations, and audit trail.

---

## ⚙️ Installation

```bash
git clone <repository-url>
cd MatchView
pip install -r requirements.txt          # Python 3.10+, optimized for 3.12
```

**(Optional) LLM setup.** The Copilot's data + narrative features use an LLM. Configure Azure/OpenAI via environment variables or `.streamlit/secrets.toml`:

```bash
OPENAI_API_KEY=...            # OpenAI; or the Azure set below
OPENAI_API_TYPE=azure
OPENAI_API_BASE=...           # Azure endpoint
OPENAI_API_VERSION=...
OPENAI_DEPLOYMENT_NAME=...    # e.g. gpt-4o
```

With no key set, non-LLM features still work and the Copilot degrades gracefully.

---

## 📖 Usage

```bash
# Web UI + Continum Copilot  (open http://localhost:5050)
python -m continum.cli ui --port 5050
# (equivalently)  python -m continum.ui --port 5050 --data ./sample_data

# Full end-to-end interactive demo
python -m continum.cli demo

# Menu-driven interactive shell
python -m continum.cli shell

# Analyse a specific experiment / health check
python -m continum.cli analyse "experiment_name"
python -m continum.cli health

# Registry + introspection
python -m continum.cli list-experiments
python -m continum.cli list-modules
python -m continum.cli inspect session
python -m continum.cli audit --n 20

# Ask the Copilot from the CLI
python -m continum.cli ask "why did variant B win?"
```

**Try the Copilot (web console):** open the 🤖 pane and ask —
- *"conversion rate by account segment"* → chart + table + collapsible SQL
- *"who should I target?"* → confirm → **Lead Lists** module runs → next-step chips
- *"launch this campaign"* → confirm → ⚠️ **deploy warning** + **Deployment** module

---

## 🧪 Capabilities

### Causal Inference Engine
A/B analysis (with SRM + segment deep-dives), Difference-in-Differences, Synthetic Control, Propensity Score Matching, Interrupted Time Series, Regression Discontinuity.

### Counterfactual Forecasting
ARIMA / SARIMA, BSTS (Kalman filtering), Causal-Impact-style estimation with control covariates.

### Narrative & Decision Support
Automated decision memos, multi-section PDF reports, and **Continum Copilot** over experiment history, live runtime state, and the MatchView modules.

### Data Guardrails
Watchtower (dimensional anomaly + Simpson's Paradox), pipeline-health monitoring, SRM detector, and experiment guardrails (`warning` / `breached` / `hard_stop`).

---

## 🔧 Configuration

All configuration is via environment variables. None are required for the default synthetic/DuckDB demo — they only matter when wiring in a real LLM or Snowflake source.

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | `core/llm`, `runtime/ask/askdata` | _(unset)_ | Enables OpenAI/Azure for the Copilot. If unset, falls back to a local model. |
| `OPENAI_API_TYPE` | `core/llm/config` | _(unset)_ | Set to `azure` for Azure OpenAI. |
| `OPENAI_API_BASE` / `OPENAI_API_VERSION` / `OPENAI_DEPLOYMENT_NAME` | `core/llm`, `runtime/ask/askdata` | _(unset)_ | Azure endpoint / API version / deployment. |
| `OPENAI_MODEL` | `core/llm/config` | `gpt-4o-mini` | OpenAI model name. |
| `CONTINUM_OUTPUT_DIR` | `core/output/pipeline` | `~/continum_outputs` | Where generated artifacts are written. |
| `CONTINUM_SECRET` | `ui/app` | `continum-dev-key` | Flask session secret — **set this in any shared/hosted deployment.** |
| `SNOWFLAKE_ACCOUNT` / `_USER` / `_PASSWORD` / `_WAREHOUSE` / `_ROLE` | `data/synthetic` | _(unset)_ | Snowflake credentials (production-mode bootstrap). |

Runtime artifacts (session JSON, audit log, memory DB) are written under `runtime_data/` and are gitignored.

---

## 🩺 Troubleshooting

### Copilot charts not rendering
Charts are produced as a lightweight Plotly **spec** by the AskData engine and rendered **client-side**, so the data must survive a full round-trip. If charts stop appearing, check each link in the chain — this is exactly the bug that was fixed and the regression to watch for:

1. **Engine** — `askdata/engine.py:ask()` must return a non-empty `visualizations` list (spec keys `type`, `x`, `y`, `values`, `names`, `title`).
2. **Endpoint** — `copilot_ask()` in `ui/routes/api.py` must forward it: the `jsonify(...)` response **must include `"visualizations": viz`**. (The original bug: the endpoint dropped the field entirely.)
3. **Frontend wiring** — `sendCopilot`/`_cpFetch` must pass `visualizations:d.visualizations` into `cpAddBot`, which appends a `<div class="cp-chart">` and calls `cpRenderChart`.
4. **Renderer + library** — `cpRenderChart` translates the spec + row data into a Plotly figure (`bar`→bar, `line`→scatter, `pie`→pie) with `{responsive:true}`. It requires **Plotly.js**, loaded via CDN in the `<head>` (`https://cdn.plot.ly/plotly-2.35.2.min.js`). If the page can't reach the CDN, vendor the script locally.

A chart only renders when the query returns **rows**; a zero-row result shows a *"No rows matched that query."* note instead, and a malformed spec is caught (`try/catch`) so it never breaks the message. The generating SQL always lives in the collapsible **“View SQL”** `<details>` dropdown.

### Copilot replies "I need an OpenAI API key"
The data engine needs an LLM. Set the `OPENAI_*` variables (see Configuration) in `.env` or `.streamlit/secrets.toml`, then re-ask. Guide-mode (README) answers work without a key.

### A confirmed module says it "needs an active experiment"
Analysis/deploy modules run against the selected experiment. Pick one in the console (or pass it in `ui_context.active_experiment`); otherwise the Copilot falls back to a data-grounded answer.

---

## 🧰 Development & Testing

```bash
python -m pytest continum/tests/ -v                              # full suite
python -m pytest continum/tests/test_statistics.py -v            # inference primitives
python -m pytest continum/tests/test_routes.py -v                # Flask + Copilot routes
python -m pytest continum/tests/test_calibration.py -v -m "not slow"
```

| Test file | Covers |
|---|---|
| `test_statistics.py` | Core inference primitives (proportion/means tests, sample size, SRM, mSPRT) |
| `test_calibration.py` | Statistical calibration / false-positive-rate checks |
| `test_routes.py` | Flask UI + Copilot route smoke tests (incl. viz passthrough + tool confirmation) |

### Continuous Integration
`.github/workflows/ci.yml` runs on pushes/PRs across Python 3.10–3.12: unit + calibration tests (60% coverage floor on `core/`), a `py_compile` syntax check, an import smoke test, and a full synthetic A/B-readout pipeline integration.

---

## 📝 License
Proprietary / Internal Use Only.

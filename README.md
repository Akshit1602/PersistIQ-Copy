# Continum MatchView

**Continum MatchView** is a unified platform for experimentation intelligence, causal inference, and automated product analytics. It bridges the gap between raw experimental data and actionable business decisions by combining rigorous statistical methods with LLM-powered narrative intelligence — all driven through **Continum Copilot**, the conversational AI layer that sits on top of every module.

> **Layout note.** The codebase follows the MatchView backend diagram (see [`continum/ARCHITECTURE.md`](continum/ARCHITECTURE.md)). The legacy CLI/REPL/shell layout (`continum/cli.py`, `core/`, `phases/`, `runtime/`, `ui/`) has been **removed** — everything now runs through the web console (`continum/userui/`). This README reflects the current layout.

---

## 🚀 Overview

At the centre of the product is **Continum Copilot** — an AI-driven UI layer that lets you *talk to the platform*. Instead of hunting through menus, you ask a question or request an action in plain English and the Copilot:

- **answers data questions** by generating SQL, running it, and rendering the result as a table **and an interactive chart** (only when a chart actually helps);
- **explains the tool** from its own documentation;
- **drives the MatchView application modules for you** via tool calling — detecting intent, asking you to confirm, then running the relevant module (in the live execution console for analysis/deploy, or inline for data look-ups); and
- **guides you step-by-step through the experiment** — working out where you are in the lifecycle, suggesting the next step, then asking for that module's inputs one question at a time (see [Guided Flow](#-guided-flow)).

Underneath the Copilot, Continum MatchView covers the entire experimentation lifecycle in five phases:

| Phase | Purpose |
|---|---|
| **Discovery** (`phase_0`) | Connect to source data, dynamic schema mapping, data validation, pipeline health, anomaly watchtower |
| **Planning** (`phase_1`) | Brief generation, opportunity sizing, power calc, KPI/tracking plan, audience selection, balance diagnostics |
| **Monitoring** (`phase_2`) | Live health monitor + sequential testing (mSPRT) + the full A/B readout pipeline |
| **Analysis** (`phase_3`) | Causal inference (DiD, PSM, Synthetic Control, ITS, RDD), Simpson's, ROI, forecasting, learnings |
| **Deployment** (`phase_4`) | Uplift modelling + decision engine for the action layer |

Plus an **Intelligence layer** (`phase=intelligence`) of post-run synthesis tools (KPI synthesis, guardrail generation, anomaly synthesis, cross-experiment learning, root cause, …).

The platform is consumed via the **Visual Web Console** (Flask single-page app); the Copilot is reachable from the full-page **AI Copilot** view and the **Ask AI** tab of the right-hand panel.

---

## 🆕 Recent changes — MatchView Copilot UX pass (2026-06-29)

A round of UI/UX and reliability fixes to the web console (`continum/userui/`). Full
detail and verification notes live in [`docs/MV_FIXES.md`](docs/MV_FIXES.md); the
intelligence-layer / module-output investigation is in
[`docs/MV_INTELLIGENCE_LAYER.md`](docs/MV_INTELLIGENCE_LAYER.md).

**Right-panel tabs (Insights · Narrative · Ask AI · Evidence)**
- **Ask AI is the only chat-enabled tab** — the chat no longer leaks onto Insights/Narrative/Evidence.
- **Insights & Narrative** refresh the moment their tab is opened (previously only a 20 s poll).
- **Evidence** shows the grounding chain for the last answer — *Question → Resolution path → SQL executed → Data grounded on (table) → Answer*.
- **Ask AI parity:** quick-action chips + copilot-style bubbles/spacing.

**Chat answers**
- **Collapsible Result table / Visualization / SQL** (Snowflake-style `<details>`); charts render via a lazily-loaded Plotly.
- **No chart when one wouldn't help** — single values, yes/no answers, ID dumps, and "a table says it better" return no chart.
- **Tool confirmations describe what the module will do** before you confirm.
- **Experiment-not-selected callout** instead of a misleading "no data" answer for experiment-scoped modules.
- **60 s client timeout** with a friendly message instead of an endless spinner.
- **Every module shows a real description when clicked** (from the live registry).

**Running modules from chat → the Output folder**
- Confirming an **analysis / deploy** tool in chat runs it in the **execution console** (live logs + interactive `input()` via a modal — this fixed an `EOF when reading a line` crash on modules that prompt). **Data** look-ups answer inline.
- Every run saves its artifacts to a single **outputs folder** (`runtime_data/outputs`); the **Output** tab lists them with download links.

**Layout & routing**
- **Collapsible panes (Snowflake-style):** sidebar and right panel collapse/expand (state persisted); thin edge buttons reopen them.
- **Faster pathing:** the copilot skips the routing-LLM round-trip when an explicit keyword tool match already exists.

---

## 🤖 Continum Copilot

The Copilot is reachable two ways in the web console — the full-page **AI Copilot** view (left nav) and the **Ask AI** tab in the right-hand panel — both driving one shared conversation. It resolves each question into one of three modes server-side:

| Mode | What it does | Backed by |
|---|---|---|
| **✨ Auto** | Picks the best engine from your question, and intercepts MatchView module intents (see Tool Calling). | `askrouter.py` + `orchestrator.py` |
| **📖 Guide** | "How do I…?" / "What is…?" help, grounded in the README(s). | README reader + LLM |
| **📊 Data** | Natural-language → SQL over the dataset, returned as text + table + chart. | AskData LangGraph engine |

**Data answers** flow through the **AskData engine** (`continum/askdata/`), a multi-node LangGraph workflow:

```
question → orchestrator → refine → sql (generate + execute) → visualization → insight
```

It builds its own in-memory SQLite from the bundled dataset, returns
`{response, sql, table, columns, visualizations}`, and the chat renders the **insight** text plus, each in a **collapsible** block:

- the result **table**,
- an **interactive Plotly chart** (bar / line / pie) — only when the result is chartable, and
- the generating **SQL**.

### How the chat request flows

```
Copilot pane (continum/userui/templates/dashboard.py — JS)
   │  POST /api/copilot/ask  {question, mode, ui_context, [confirm_tool|decline]}
   ▼
copilot_ask()  (continum/userui/routes/api.py)
   ├─ confirm_tool? ───────────────► execute_tool()  → data inline, or analysis/deploy in the console
   ├─ keyword tool match? ─────────► confirmation prompt  (returns pending_tool)   ← fast path, no LLM
   ├─ else askrouter.llm_route ────► tool | module | guide | data | meta
   └─ data ────────────────────────► AskData (NL→SQL)
   ▼
JSON {response, sql, table, columns, visualizations, pending_tool, deploy_warning, next_steps, suggestions, error}
   ▼
_cpMsgHtml() renders text + confirm/callout + collapsible table/chart/SQL; renderPendingCharts() draws Plotly
```

LLM credentials are optional. With Azure/OpenAI configured the Copilot uses GPT-4o-class models; otherwise guide-mode (README) answers and all non-LLM features still work and the Copilot degrades gracefully.

---

## 🧩 Tool Calling Architecture

The Copilot is a functional UI layer: when a question requires a MatchView module, it **calls that module for you** rather than just talking about it. This lives in **`continum/orchestrator.py`** and is wired into `copilot_ask`.

**The protocol (detect → confirm → execute):**

1. **Detect** — `detect_tool(question)` matches the question against a curated set of `MatchViewTool` entries (keyword + regex triggers). How-to / "about the tool" phrasing is deliberately *not* intercepted (that's a Guide question). When a keyword match is found the routing LLM call is skipped entirely.
2. **Confirm** — the Copilot returns a `pending_tool` and asks, explicitly, **including a one-line description of what the module will do**:
   > *"That looks like a job for the MatchView **{Module}** module. It will **{description}**. Would you like to run **{Module}** to {answer this / take this action}?"*
   The pane shows **Yes / No** chips. No module runs until you confirm. For experiment-scoped modules with no experiment selected, you get a callout to pick one first.
3. **Execute** — on confirmation:
   - **Data** look-ups (`Email Analytics`) run the AskData engine and render inline (collapsible table + chart + SQL).
   - **Analysis / deploy** modules run through the live **execution console** (`/api/execute` + SSE): streamed logs, interactive `input()` via the modal, and generated artifacts captured into the **Output** folder.

**Module mapping** — the Copilot speaks the MatchView vocabulary while driving Continum's real modules from the registry (`continum/toolinterface.py` → `run_module`):

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

## 🧭 Guided Flow

Tool calling above is **reactive** — you ask, and the question is mapped to one module. The **Guided Flow** is the **proactive** counterpart: you don't have to know which module to ask for. It treats **every module as a tool** and walks you through the experimentation lifecycle, one step at a time.

Say *"what's next?"* / *"guide me"* and the Copilot:

1. **Locates you** — reads your run history against the five-phase plan and shows a progress ledger per phase.
2. **Suggests the next step** — the next unrun module in your current phase, then the head of the next phase, as pickable chips.
3. **Fills the inputs** — once you pick a step, it asks **one question per input field**, pre-filled with smart, data-detected defaults; numbers are validated and re-prompted on bad input.
4. **Confirms, then runs** — it echoes the gathered inputs for a final ✅, runs the module in the **console**, and drops a result summary back into the chat with a **"What's next?"** chip to continue the loop.

```
guide me ─► POST /api/copilot/flow  {message, flow_state, ui_context}
                   │
  locate ─► suggest ─► fill (one field / turn) ─► confirm ─► action:"run_module"
                   │                                              │
                   ▼                                              ▼
  JSON {response, stage, flow_state, chips, action, module_key, fields}
                                                                  │
                                            ─► POST /api/execute (SSE console)
```

The engine lives in **`continum/askdata/flow.py`** — pure and deterministic, so it works with or without an LLM loaded — wired into **`copilot_flow()`** in `continum/userui/routes/api.py`. Per-module questions reuse the **same `_get_module_config` field schema** the config form uses, so the chat and the form never drift. Conversation state is a small dict round-tripped to the client, keeping the endpoint stateless across turns.

---

## 🧪 The Experimentation Flow (guardrails)

Because the Copilot can take real actions, it follows two experimentation guardrails on every tool interaction:

1. **Suggest next steps.** After answering or running a module, the Copilot offers **1–2 logical next steps** as clickable chips. Each `MatchViewTool` carries its own `next_steps`.

2. **Warn before going live.** Any action that **deploys, activates, launches, or sends** a live campaign is a `KIND_DEPLOY` tool. Before execution the Copilot injects a prominent warning:

   > ⚠️ **Deploy / go-live warning** — This moves **{Module}** from an experimentation / draft state into a **LIVE** environment. Live actions affect real audiences, real sends, and real budget, and cannot be undone from this chat. Confirm your guardrails and approvals are in place before continuing.

   This complements the platform's statistical guardrail framework (SRM, AOV no-harm, latency/error caps with `warning` / `breached` / `hard_stop` levels) in `continum/experimentation/stats/`, which gates whether an experiment is safe to roll out.

---

## 🖥️ The Web Console

`python -m continum.userui` serves a single self-contained page (`continum/userui/templates/dashboard.py`) backed by the JSON/SSE API in `continum/userui/routes/api.py`.

- **Left sidebar** — Dashboard, the five phase sections, **Intelligence & tools**, **Data**, **AI Copilot**, **Output**, **Run history**. Collapsible.
- **Center** — phase module grids (click a card → config modal → run), the **execution console** (live SSE logs, interactive input modal, file links), the **Data** view, the **Output** view, and the full-page **AI Copilot**.
- **Right panel** — **Insights · Narrative · Ask AI · Evidence** tabs. Collapsible.
- **Output folder** — every module run writes its artifacts to `runtime_data/outputs` (override with `CONTINUM_OUTPUT_DIR`); the Output tab lists them via `GET /api/outputs`, downloadable through `GET /api/file`.

### Modules (live registry)

The registry (`continum/toolinterface.py`) is the single source of truth; query it live at `GET /api/modules`. Current set:

| Phase | Modules |
|---|---|
| **Discovery** | `schema_discovery` · `data_validation` · `dimension_setup` · `pipeline_health` · `watchtower` · `distribution_shift` |
| **Planning** | `opportunity_sizing` · `opportunity_sizing_v2` · `power_calculator` · `metrics_and_tracking` · `audience_selection` · `brief_generator` · `balance_diagnostics` |
| **Monitoring** | `experiment_analysis` · `health_monitor` · `sequential_testing` |
| **Analysis** | `causal_analysis` · `causal_analysis_full` · `forecasting` · `pre_post_analysis` · `simpsons_paradox` · `roi_tracker` · `roi_synthesis` · `learnings_repository` · `sequential_tester_core` |
| **Deployment** | `uplift_modeller` · `decision_engine` |
| **Intelligence** | `kpi_synthesis` · `guardrail_generation` · `tracking_plan` · `historical_learning` · `next_step_generation` · `anomaly_synthesis` · `cross_experiment_learning` · `adaptive_recommendations` · `ask_v2` · `open_questions` · `root_cause` |

Most modules are **pure deterministic algorithms** (scipy / statsmodels / sklearn / custom); only `schema_discovery`, `brief_generator`, and `metrics_and_tracking` require an LLM at their core. See [`docs/MV_INTELLIGENCE_LAYER.md`](docs/MV_INTELLIGENCE_LAYER.md) for the per-module breakdown.

---

## 🛠️ Project Structure

Mirrors the MatchView backend diagram (full detail in [`continum/ARCHITECTURE.md`](continum/ARCHITECTURE.md)). Organising rule: *a diagram node with more than one child becomes a folder, otherwise a single file.*

```text
PersistIQ/
├── continum/                       # Core package
│   ├── intentanalyser.py           # Intent Analyser — classify a query + extract entities
│   ├── orchestrator.py             # ★ Route decider + MatchView tool calling (detect/confirm/execute)
│   ├── askrouter.py                # LLM-first route selection over the full tool catalog
│   ├── toolinterface.py            # ★ Module registry + run_module / get_module / list_modules
│   │
│   ├── userui/                     # ── Visual Web Console (Flask) ──
│   │   ├── app.py                  # Flask factory; async boot of DB + medallion layers
│   │   ├── __main__.py             # `python -m continum.userui` launcher
│   │   ├── health.py               # /health + dependency checks
│   │   ├── routes/api.py           # JSON/SSE API — /api/copilot/ask, /api/execute, /api/outputs, …
│   │   └── templates/dashboard.py  # Dashboard + Copilot UI (HTML/CSS/JS as a Python string)
│   │
│   ├── askdata/                    # ── AskData (NL→SQL/Viz/Insight) ──
│   │   ├── engine.py               # AskDataGraphEngine.ask() → {response, sql, table, viz}
│   │   ├── graph_logic.py          # orchestrator → refine → sql → visualization → insight nodes
│   │   ├── ask_engine.py           # analytics-grounded ask engine
│   │   ├── flow.py                 # ★ Guided flow (locate → suggest → fill → run)
│   │   ├── readout.py              # post-analysis Q&A over saved outputs (uploaded + generated)
│   │   ├── narrative_runtime.py    # post-module narrative stream
│   │   ├── metadata.py · llm.py · readme.py
│   │   └── datasets/               # bundled demo datasets
│   │
│   ├── experimentation/            # Experimentation module family
│   │   ├── analysis_dag.py · metric_planner.py · artifacts.py · enterprise.py · compare.py
│   │   └── stats/ · causal/ · analytics/ · monitoring/ · post_analysis/
│   │
│   ├── insights/                   # post-run intelligence: insight_bus · patterns · session
│   ├── contextmate/                # clean raw data + generate/validate metadata, synthetic, discovery
│   ├── datastore/                  # loader (DuckDB medallion) · stores · memory · lineage · semantic_layer
│   ├── crosscutting/               # llm.py (client+config+manager) · console.py · pdf.py · runtime_config.py
│   └── tests/                      # pytest suite
│
├── docs/                           # MV_FIXES.md, MV_INTELLIGENCE_LAYER.md
├── sample_data/                    # accounts / users / quotes / orders / experiments CSVs
├── runtime_data/                   # generated artifacts incl. outputs/ (gitignored)
├── requirements.txt
└── README.md
```

---

## 🧭 Architecture & Data Flow

```
User UI ─▶ intentanalyser.py ─▶ orchestrator.py ─┬─▶ askdata/ ─▶ sql/viz/insight (graph_logic.py)
(userui/)   (classify+entities)  (route decider)  └─▶ toolinterface.py ─▶ experimentation/
                                                                          insights/ ◀─ post-run intelligence ─▶ User UI
```

**Medallion data layers** (built by `continum/datastore/loader.py`):
- **Bronze** — raw CSVs from `sample_data/` (or a Snowflake source) loaded verbatim into DuckDB.
- **Silver** — cleaned, typed, conformed tables (e.g. `silver_inquiries`).
- **Gold** — analysis-ready marts (e.g. `gold_experiment_analysis`) consumed by the modules.

**Session state** (`continum/insights/session.py`) — an experiment session plus an `InsightBus` thread through a run so the console, Copilot, and right-panel tabs all see the same live state, recommendations, and audit trail.

---

## ⚙️ Installation

```bash
git clone https://github.com/LatentView-Analytics-Ltd/PersistIQ.git
cd PersistIQ
python -m venv .venv && . .venv/Scripts/activate     # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt                       # Python 3.10+, optimized for 3.12
```

**(Optional) LLM setup.** The Copilot's data + narrative features use an LLM. Copy `.env.example` to `.env` (or use `.streamlit/secrets.toml`) and fill in **OpenAI** *or* **Azure OpenAI**:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# …or Azure OpenAI
OPENAI_API_TYPE=azure
OPENAI_API_KEY=your-azure-key
OPENAI_API_BASE=https://your-resource.openai.azure.com/
OPENAI_API_VERSION=2024-05-01-preview
OPENAI_DEPLOYMENT_NAME=gpt-4o
```

With no key set, guide-mode answers and non-LLM features still work; data questions require a key.

---

## 📖 Usage

```bash
# Web console + Continum Copilot  (open http://localhost:5050)
python -m continum.userui --port 5050 --data ./sample_data
```

> On Windows set `PYTHONIOENCODING=utf-8` first so console/emoji output doesn't error.

Everything is driven from the web console — there is no separate CLI/REPL (those were removed). Introspection that used to be CLI commands is now exposed as API routes, e.g. `GET /api/modules`, `GET /api/experiments`, `GET /api/session`, `GET /api/outputs`, `GET /api/health/detail`.

**Try the Copilot (Ask AI tab or AI Copilot page):**
- *"conversion rate by account segment"* → chart + table + collapsible SQL
- *"is the experiment healthy?"* → confirm → **Sequence Monitoring** runs in the console → Output tab
- *"launch this campaign"* → confirm → ⚠️ **deploy warning** + **Deployment** module

---

## 🧪 Capabilities

### Causal Inference Engine
A/B analysis (with SRM + segment deep-dives), Difference-in-Differences, Synthetic Control, Propensity Score Matching, Interrupted Time Series, Regression Discontinuity. (`continum/experimentation/causal/`)

### Counterfactual Forecasting
ARIMA / SARIMA, BSTS, Causal-Impact-style estimation with control covariates. (`continum/experimentation/causal/` + `post_analysis/`)

### Narrative & Decision Support
Automated decision memos, multi-section PDF reports, and **Continum Copilot** over experiment history, live runtime state, and the MatchView modules.

### Data Guardrails
Watchtower (dimensional anomaly + Simpson's Paradox), pipeline-health monitoring, SRM detector, distribution-shift checks, and experiment guardrails (`warning` / `breached` / `hard_stop`). (`continum/experimentation/monitoring/` + `stats/`)

---

## 🔧 Configuration

All configuration is via environment variables (or `.env` / `.streamlit/secrets.toml`). None are required for the default synthetic/DuckDB demo — they only matter when wiring in a real LLM or Snowflake source.

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | `crosscutting/llm`, `askdata` | _(unset)_ | Enables OpenAI/Azure for the Copilot. Without it, data questions are disabled but guide-mode works. |
| `OPENAI_API_TYPE` | `crosscutting/llm` | _(unset)_ | Set to `azure` for Azure OpenAI. |
| `OPENAI_API_BASE` / `OPENAI_API_VERSION` / `OPENAI_DEPLOYMENT_NAME` | `crosscutting/llm`, `askdata` | _(unset)_ | Azure endpoint / API version / deployment. |
| `OPENAI_MODEL` | `crosscutting/llm` | `gpt-4o-mini` | OpenAI model name. |
| `ACTIVE_DATASET` | `askdata` | `sample` | Which bundled dataset the assistant queries (`sample` \| `shell`). |
| `CONTINUM_OUTPUT_DIR` | `crosscutting/runtime_config` | `runtime_data/outputs` | Where module-generated output files are collected (the Output tab reads this). |
| `CONTINUM_SECRET` | `userui/app` | `continum-dev-key` | Flask session secret — **set this in any shared/hosted deployment.** |
| `SNOWFLAKE_ACCOUNT` / `_USER` / `_PASSWORD` / `_WAREHOUSE` / `_ROLE` | `contextmate` | _(unset)_ | Snowflake credentials (production-mode bootstrap). |

Runtime artifacts (session JSON, audit log, memory DB, the `outputs/` folder) are written under `runtime_data/` and are gitignored.

---

## 🩺 Troubleshooting

### Copilot charts not rendering
Charts are produced as a lightweight Plotly **spec** by the AskData engine and rendered **client-side**, so the data must survive a full round-trip:

1. **Engine** — `askdata/graph_logic.py:visualization_node` returns a `visualizations` list (spec keys `type`, `x`, `y`, `values`, `names`, `color`, `title`). It deliberately returns `[]` for non-chartable results (single value/row, no numeric column).
2. **Endpoint** — `copilot_ask()` in `userui/routes/api.py` forwards it: the response **must include `"visualizations": viz`**.
3. **Frontend** — `_cpMsgHtml()` appends a `<div class="cp-chart" data-cid=…>` inside a collapsible, and `renderPendingCharts()` draws it.
4. **Renderer** — `_renderOneChart()` translates the spec + row data into a Plotly figure (`bar`→bar, `line`→scatter+lines, `pie`→pie; `color` splits into multiple series). Plotly is **lazily loaded** from the CDN (`https://cdn.plot.ly/plotly-2.27.0.min.js`) by `ensurePlotly()`. If the page can't reach the CDN, the collapsible still shows but the chart won't draw — vendor the script locally.

### Copilot replies "I need an OpenAI API key"
The data engine needs an LLM. Set the `OPENAI_*` variables (see Configuration) in `.env` or `.streamlit/secrets.toml`, then re-ask. Guide-mode (README) answers work without a key.

### A confirmed module says it "needs an experiment"
Analysis/deploy modules run against the selected experiment. Pick one from the **experiment dropdown** in the top bar (or pass it in `ui_context.active_experiment`); the Copilot calls this out rather than returning a misleading "no data" answer.

### Output files / downloads 404
Generated files live in the outputs folder (`runtime_data/outputs`, or `CONTINUM_OUTPUT_DIR`). `GET /api/file` only serves files inside that whitelisted folder; `GET /api/outputs` lists the folder.

---

## 🧰 Development & Testing

```bash
python -m pytest continum/tests/ -v                              # full suite
python -m pytest continum/tests/test_statistics.py -v            # inference primitives
python -m pytest continum/tests/test_routes.py -v                # Flask + Copilot routes
python -m pytest continum/tests/test_mv_copilot_ui.py -v         # Copilot UI/UX regression guards
python -m pytest continum/tests/test_calibration.py -v -m "not slow"
```

| Test file | Covers |
|---|---|
| `test_statistics.py` | Core inference primitives (proportion/means tests, sample size, SRM, mSPRT) |
| `test_calibration.py` | Statistical calibration / false-positive-rate checks |
| `test_routes.py` | Flask UI + Copilot route smoke tests (incl. viz passthrough + tool confirmation + LLM routing) |
| `test_mv_copilot_ui.py` | Tab isolation, tool-confirmation description, needs-experiment callout, module descriptions, Evidence/collapsible helpers |

### Continuous Integration
`.github/workflows/ci.yml` runs on pushes/PRs across Python 3.10–3.12: unit + calibration tests, a `py_compile` syntax check, an import smoke test, and a full synthetic A/B-readout pipeline integration.

---

## 📝 License
Proprietary / Internal Use Only.

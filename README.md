Here are the complete `requirements.txt`, `.env.example`, and `README.md` files for the repository. Place `requirements.txt` and `.env.example` in the project root alongside `continum/` and `frontend/`.

---

### 1. `requirements.txt`

```text
# Web Framework & Async Server
fastapi>=0.111.0
starlette>=0.37.2
uvicorn[standard]>=0.30.0

# Configuration & Data Validation
pydantic>=2.7.0
pydantic-settings>=2.2.0
python-dotenv>=1.0.1

# Agent Orchestration & LLM
langchain>=0.2.0
langchain-core>=0.2.0
langchain-openai>=0.1.7
langgraph>=0.1.0

# Math, Statistics & Causal Engine
numpy>=1.26.0
scipy>=1.13.0

# Database & Visuals
sqlalchemy>=2.0.0
plotly>=5.20.0

# External Telemetry & MCP
requests>=2.31.0
mcp>=1.0.0

```

---

### 2. `.env.example`

Create a file named `.env.example` (and copy it to `.env` for local execution):

```env
# Application Settings
APP_NAME="Continum Retail Experimentation Engine"
ENVIRONMENT="development"

# LLM Configuration
OPENAI_API_KEY="sk-proj-your-openai-api-key-here"
LLM_MODEL="gpt-4o"
LLM_TEMPERATURE=0.0

# Database Connection
DATABASE_URL="sqlite:///./continum_warehouse.db"

# StatSig Telemetry Integration (Optional for live pulse data)
STATSIG_API_KEY=""
STATSIG_BASE_URL="https://statsigapi.net/v1"

```

---

### 3. `README.md`

```markdown
# Continum: AI Retail Experimentation Co-Pilot & MatchView Hub

Continum is an enterprise-grade A/B testing co-pilot and statistical experimentation platform designed specifically for retail environments. It pairs a **deterministic statistical computing engine** with a **LangGraph agentic orchestrator** and streams real-time insights to the **MatchView** interactive frontend dashboard.

---

## 🏗️ Architecture Overview

The system is built on a clean, layered architecture that strictly separates pure mathematical calculations from LLM synthesis to eliminate statistical hallucinations:

```text
  [ MatchView React Frontend ]
              │ (SSE / REST)
              ▼
    [ continum.userui ] ──▶ FastAPI SSE Chat Stream & Experiment Hub Endpoints
              │
              ▼
  [ continum.orchestration ] ──▶ LangGraph ReAct Supervisor + Domain Subgraphs
              │
       ┌──────┴────────────────────────┬────────────────────────┐
       ▼                               ▼                        ▼
[ continum.ExpSuite ]       [ continum.mapMeta ]      [ continum.AskData ]
 ├── stats_inference/        ├── scanner.py            ├── sql_engine.py
 ├── planning/               ├── metadata_store.py     ├── visual_generator.py
 └── causal/                 └── statsig_connector.py  └── growth_simulator.py
       │
       ▼
 [ continum.mcp ] ──▶ Model Context Protocol (MCP) Tool Server

```

### Core Layers

1. **`continum/ExpSuite/` (Pure Statistical Core)**: Pure, zero-LLM Python modules for Sample Ratio Mismatch (SRM) detection, CUPED variance reduction, Welch/Z-test hypothesis testing, Sequential Probability Ratio Tests (SPRT), Bayesian Beta-Binomial testing, Difference-in-Differences (DiD), and Monte Carlo growth forecasting.
2. **`continum/mapMeta/`**: Database schema introspector, live StatSig REST API telemetry connector, and the baseline profiler that derives MatchView's auto-populated input suggestions from an experiment's own data.
3. **`continum/askdata/`**: Read-only Text-to-SQL execution engine and renderer-neutral chart generator (`chart_spec.py`) for metric lift, traffic split, growth projection, and ad-hoc query-result charts. A `derive_chart_spec` call auto-charts any SQL result that has a chartable shape, so a question that implies a picture gets one without the model having to remember to ask for it.
4. **`continum/orchestration/`**: LangGraph agent supervisor with subgraphs for Ingestion, Planning, Health Monitoring, Analysis, and Data Querying.
5. **`continum/userui/`**: FastAPI serving layer streaming text token chunks, tool-execution status indicators, and pre-formatted UI cards over Server-Sent Events (SSE).
6. **`continum/mcp/`**: FastMCP server exposing all A/B testing tools to external agentic clients (Cursor, Claude Desktop, etc.).

---

## 🚀 Getting Started

### Prerequisites

* **Python**: 3.11 or higher
* **Node.js**: v18 or higher (for MatchView UI)
* **OpenAI API Key**: Required for conversational copilot functions

---

### Backend Setup (`continum`)

1. **Clone the repository and navigate to root**:
```bash
git clone [https://github.com/your-org/continum.git](https://github.com/your-org/continum.git)
cd continum

```


2. **Create and activate a Python virtual environment**:
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

```


3. **Install dependencies**:
```bash
pip install -r requirements.txt

```


4. **Configure environment variables**:
```bash
cp .env.example .env

```


Open `.env` and set your `OPENAI_API_KEY`.
5. **Start the FastAPI serving server**:
```bash
python -m continum.userui.app

```


The API will be available at `http://localhost:8000`. You can inspect endpoints at `http://localhost:8000/docs`.
6. **(Optional) Run the FastMCP server for IDE / Claude Desktop integration**:
```bash
python -m continum.mcp.server

```



---

### Frontend Setup (`MatchView App`)

1. **Navigate to the MatchView frontend folder**:
```bash
cd "MatchView App"

```


2. **Install Node dependencies**:
```bash
npm install

```


3. **Launch the Vite development server**:
```bash
npm run dev

```


Open your browser to `http://localhost:5173` to access the MatchView Copilot Workspace.

---

## 📡 Key API Routes

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/chat/stream` | Server-Sent Events stream for real-time Copilot responses, tool status, and UI cards |
| `GET` | `/api/experiments` | Retrieves cataloged running and historical experiments for the top dropdown and hub |
| `GET` | `/api/experiments/{id}/health` | Fetches live StatSig exposure counts and pulse metrics |
| `GET` | `/api/suggestions/inputs` | Baseline input values derived from the data behind an experiment (auto-populate) |
| `POST` | `/api/approval/resume` | Resumes an interrupted LangGraph workflow after Human-in-the-Loop (HITL) confirmation |
| `GET` | `/health` | Server health check endpoint |

---

## ✨ Auto-Populated Experiment Inputs

MatchView's forms (Analytics Lab modules, the digital and store hypothesis wizards, and the
chat interview) pre-fill their inputs from the selected experiment's own data instead of
starting blank or trusting hardcoded placeholders.

Resolution order per field, highest confidence first — a field the user has already edited is
never overwritten:

1. **Dataset** — `GET /api/suggestions/inputs?experiment=<name>&channel=<digital|store>` profiles
   the configured warehouse first, falling back to the bundled sample datasets under
   `sample_data/` (`continum/mapMeta/baseline_profiler.py`). An unmatched experiment returns an
   empty field map rather than an error, so the UI degrades gracefully.
2. **Prior run / project history** — values already locked in another module of this experiment,
   or a sibling experiment in the same project.
3. **Hypothesis-derived** — funnel stage and metric suggestions classified from the experiment's
   own hypothesis and goal text.
4. **Industry benchmark** — offered as a click-to-apply suggestion, never pre-filled.

Every suggested value carries its source, a plain-language rationale, and (where applicable) the
period of data it covers — visible via the info icon next to each pre-filled field. See
`frontend/src/data/inputSuggestions.ts` for the client-side engine that assembles and ranks these
suggestions.

---

## 🧪 Statistical Tooling Summary

| Category | Available Tools |
| --- | --- |
| **Inference & Health** | `check_srm`, `apply_cuped_variance_reduction`, `run_hypothesis_test`, `run_sprt_sequential_test`, `run_bayesian_ab_test`, `check_guardrail_degradation` |
| **Planning & Sizing** | `calculate_power_and_sample_size`, `calculate_opportunity_size`, `plan_experiment_metrics`, `balance_traffic_allocation` |
| **Causal & Growth** | `calculate_diff_in_diff`, `run_monte_carlo_growth_forecast`, `run_causal_engine` |
| **Data & Visuals** | `execute_sql_query`, `generate_plotly_visualization`, `simulate_and_visualize_growth` |

---

## 📊 Copilot Visualization & Reports Sync

The chat Copilot now generates a chart card whenever a request implies one:

* **Auto-chart on SQL results** — `ask_data_sql` charts its own rows automatically when they hold a chartable shape (no separate chart tool call needed); pass `visualize=False` to suppress it.
* **Explicit chart requests** — `ask_data_visualize` covers named experiment charts (`metric_lift`, `srm_distribution`, `growth_forecast`) plus generic shapes (`bar`, `grouped_bar`, `line`, `area`, `pie`, `scatter`, or `auto` to infer from raw rows).
* **Renderer-neutral spec** — every chart is built as a `ChartSpec` (`continum/AskData/chart_spec.py`) and streamed to MatchView as a `UIArtifact`; the frontend draws its own SVG from the spec (`ArtifactChart.tsx`) rather than embedding a Plotly figure.
* **Reports tab sync** — any chart or stat card a chat turn produces is filed into the Reports tab alongside Analytics Lab module runs, tagged under a **Copilot** bucket when it maps to no module.

```

```
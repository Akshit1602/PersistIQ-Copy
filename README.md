# Continum MatchView

**Continum MatchView** is a platform for experimentation intelligence, causal inference, and automated product analytics. It pairs rigorous statistics with LLM-powered narrative intelligence, driven through **Continum Copilot** — the conversational layer over every module.

The whole architecture runs on **LangChain + LangGraph** (OpenAI / Azure OpenAI). All secrets live in a single repo-root **`.env`** — there is no `.streamlit/secrets.toml`.

---

## 🧭 Architecture

```
User UI ─▶ orchestration/ ─┬─▶ AskData/  ─▶ SQLGenerator → VisualGenerator → InsightGenerator
(userui/)  (intent (chatbot│            (NL→SQL / chart / insight — a LangGraph)
 path only) + route        └─▶ ExpSuite/ (tool-call: discovery/planning/monitoring/analysis/learnings)
 decider + LangGraph)            │
                    ContextGraph/  ◀────┘   (tracks queries + module outputs; dataset-level knowledge graph)
                    mapMeta/  ─────────▶ DuckDB + per-dataset metadata (feeds AskData + ContextGraph)
```

- **Manual experiment usage** routes straight to the relevant **ExpSuite** module (skips intent analysis).
- **Chatbot usage** goes through `orchestration`'s intent analysis → routing, which picks AskData (SQL/Viz/Insight) or an ExpSuite tool-call. ExpSuite modules that need input from the user are driven as a **tool-call interaction** (guided flow).
- **AskData** is AI-powered (LangGraph NL→SQL on the dataset's DuckDB schema). **ContextGraph** is AI-powered (knowledge graph + memory). **ExpSuite** is mostly algorithmic (stats / causal / sklearn) with optional LLM narration.

### Package layout

```text
PersistIQ/
├── .env / .env.example              # ALL secrets (single source; .env is gitignored)
├── continum/
│   ├── __init__.py                  # project-wide LLM init (client + creds + get_chat_llm)
│   ├── orchestration/               # intent analysis + path decider + AskData LangGraph + tool-calling
│   │   ├── __init__.py              #   ContinumEngine + get_askdata_engine; flattens every function below
│   │   ├── intent.py                #   LLM intent breakdown + entities (chatbot path only)
│   │   ├── graph.py                 #   the AskData LangGraph (refine→sql→viz→insight→summarize)
│   │   ├── matchview.py             #   MatchView tools: detect / confirm / execute
│   │   ├── router.py                #   LLM-first route classifier (tool|module|data|guide|meta)
│   │   ├── flow.py                  #   guided flow (locate→suggest→fill→run)
│   │   └── readout.py               #   Q&A over uploaded / generated documents
│   ├── AskData/                     # AI-powered NL→SQL / Viz / Insight (exactly 3 generators)
│   │   ├── SQLGenerator.py          #   refine/breakdown + NL→SQL on the DuckDB schema
│   │   ├── VisualGenerator.py       #   Plotly chart spec (with deterministic fallback)
│   │   └── InsightGenerator.py      #   short insight from data or ContextGraph context
│   ├── ExpSuite/                    # experimentation framework (5 phases + shared kernel)
│   │   ├── registry.py              #   module registry + run_module / list_modules
│   │   ├── artifacts.py · stats/    #   shared pydantic contracts + stats kernel
│   │   ├── discovery/ · planning/ · monitoring/ · analysis/ · learnings_repository/
│   │   └── modules.py               #   additional analytics modules
│   ├── ContextGraph/                # AI-powered knowledge graph + memory + session + insight bus
│   ├── mapMeta/                     # scan sample_data/ → DuckDB (medallion) + per-dataset metadata
│   ├── paths.py                     # runtime state + output paths; new_run_dir() segregates per run
│   └── userui/                      # Flask web console (unchanged UI); also holds pdf.py (report rendering)
├── sample_data/
│   ├── Shell/     Shell__dim_station__preview_.csv, Shell__fact_station_day_product__preview_.csv
│   ├── Xometry/   accounts.csv, experiments.csv, orders.csv, quotes.csv, users.csv
│   └── Walmart/   Sample Dataset.xlsx
├── requirements.txt
└── README.md
```

---

## 🤖 Continum Copilot

Reachable as the full-page **AI Copilot** and the **Ask AI** right-panel tab. Each message resolves server-side to one of:

| Mode | What it does | Backed by |
|---|---|---|
| **✨ Auto** | Picks the best engine + intercepts MatchView module intents (tool calling). | `orchestration` (`router` + `matchview`) |
| **📖 Guide** | "How do I…?" / "What is…?" help, grounded in the README. | `AskData.InsightGenerator.about` |
| **📊 Data** | NL → SQL over the dataset, returned as insight + table + chart. | `AskData` LangGraph via `orchestration` |

**Data answers** flow through the AskData LangGraph:

```
question → orchestration(plan) → refine → sql (generate + execute on DuckDB) → visualization → insight → summarize
```

returning `{response, sql, table, columns, visualizations}`. The chat renders the **insight** text plus collapsible **table**, **Plotly chart** (only when chartable), and **SQL**.

### Tool calling (detect → confirm → execute)

When a request maps to a MatchView module, `orchestration.detect_tool` matches it, the Copilot returns a `pending_tool` with a one-line description and **Yes/No** chips, and on confirm `orchestration.execute_tool` runs the real module from `ExpSuite.registry` (or the AskData engine for data look-ups). Deploy / go-live actions carry a prominent warning.

### Datasets

`mapMeta` builds one DuckDB from `sample_data/<Dataset>/` and emits per-dataset metadata:

| Dataset (`ACTIVE_DATASET`) | Folder | Tables |
|---|---|---|
| `experiments` (default) | `Xometry/` | `experiment_results` (medallion `gold_experiment_analysis`) |
| `shell` | `Shell/` | `dim_station`, `fact_station` |
| `sample` | `Walmart/` | `campaign_data` |

---

## ⚙️ Installation

```bash
git clone https://github.com/LatentView-Analytics-Ltd/PersistIQ.git
cd PersistIQ
python -m venv .venv && . .venv/Scripts/activate     # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt                       # Python 3.10+, optimized for 3.12
```

**LLM setup (optional but recommended).** Copy `.env.example` to `.env` and fill in **OpenAI** *or* **Azure OpenAI**:

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

With no key set, guide-mode answers and all non-LLM features still work; data questions require a key. **Credentials are read only from `.env` (or real environment variables) — nothing else.**

---

## 📖 Usage

```bash
python -m continum.userui --port 5050 --data ./sample_data     # open http://localhost:5050
```

> On Windows set `PYTHONIOENCODING=utf-8` first so console/emoji output doesn't error.

**Try the Copilot:**
- *"conversion rate by variant for mobile_nav_redesign"* → insight + table + collapsible chart & SQL
- *"is the experiment healthy?"* → confirm → **Health Monitor** runs → result in chat
- *"what's next?"* → guided flow suggests the next module and collects its inputs

---

## 🔧 Configuration

All configuration is via environment variables (or `.env`). None are required for the default DuckDB demo — they only matter for a real LLM or a Snowflake source.

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | `continum` (LLM init), AskData | _(unset)_ | Enables OpenAI/Azure. Without it, data questions are disabled; guide-mode works. |
| `OPENAI_API_TYPE` | LLM init | _(unset)_ | Set to `azure` for Azure OpenAI. |
| `OPENAI_API_BASE` / `OPENAI_API_VERSION` / `OPENAI_DEPLOYMENT_NAME` | LLM init | _(unset)_ | Azure endpoint / API version / deployment. |
| `OPENAI_MODEL` | LLM init | `gpt-4o-mini` | OpenAI model name. |
| `ACTIVE_DATASET` | `mapMeta` | `experiments` | Active dataset (`experiments` \| `shell` \| `sample`). |
| `CONTINUM_OUTPUT_DIR` | `paths.py` | `runtime_data/outputs` | Where module output files are collected (segregated per run — `outputs/<module_key>/<run_id>/`). |
| `CONTINUM_SECRET` | `userui/app` | `continum-dev-key` | Flask session secret — **set this in any shared deployment.** |
| `SNOWFLAKE_*` | `mapMeta` | _(unset)_ | Optional Snowflake credentials (production bootstrap). |

Runtime artifacts (session JSON, memory DB, `outputs/`) are written under `runtime_data/` and are gitignored.

---

## 🧰 Development & Testing

```bash
python -m pytest continum/tests/ -m "not slow" -q       # full suite (fast)
python -m pytest continum/tests/test_statistics.py -v   # inference primitives
python -m pytest continum/tests/test_routes.py -v        # Flask + Copilot routes
```

CI (`.github/workflows/`) runs the unit + calibration tests, a `py_compile` syntax check, and an import smoke test across Python 3.10–3.12.

---

## 📝 License
Proprietary / Internal Use Only.

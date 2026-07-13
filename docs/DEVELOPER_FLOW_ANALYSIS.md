# Continum PersistIQ — Codebase Flow & Architectural Analysis

This document provides a highly detailed developer-friendly architectural analysis mapping the **Continum PersistIQ (Continum OS)** codebase to the system flow diagram (`image.png`). It details how the codebase is structured, how the data and execution flow, and how our newly-added nested subdirectory outputs integrate into this architecture.

---

## 1. High-Level Architectural Mapping

The diagram describes a beautifully segmented, data-driven, and model-driven experimentation intelligence framework. The table below maps each block from the diagram directly to the package structure and key files in the codebase.

| Diagram Block | Codebase Package / File Path | Architectural Role & Developer Guidance |
| :--- | :--- | :--- |
| **Bronze Ingestion Contract** | `continum/contextmate/contracts.py` | Defines data schemas and serialization formats (via Pydantic) for bronze layer ingestion (Databricks, Snowflake, CSVs). |
| **SourceReader (Abstract)** | `continum/contextmate/contracts.py` | The base class interface for data source connectors. |
| **CSV / Databricks Reader** | `continum/contextmate/contracts.py` | Concrete sub-classes handling standard CSV parsing or Databricks connections. |
| **Bronze / Silver / Gold Layers** | `continum/datastore/loader.py` | Orchestrates the progressive schema-loading and transformation pipeline inside DuckDB. |
| **ContextMate - Generate Metadata** | `continum/contextmate/discovery.py` | Scans the data catalog, automatically maps schema constraints, and outputs metadata JSON configurations. |
| **Tagged Metadata Files** | `runtime_data/` | Artifacts such as `client_schema_demo.json` that specify table structures and semantic layer mapping. |
| **Data Store (DB)** | `continum/datastore/stores.py`<br>`continum/datastore/knowledge_graph.py` | Persistently stores transactional records, experiment logs, metadata registry, and knowledge graphs (using DuckDB and JSON stores). |
| **Session State + Data Interface** | `continum/insights/session.py`<br>`continum/userui/routes/api.py` | Tracks active session variables (selected experiment, active dataset/company) and exposes unified REST APIs to the UI. |
| **User UI Chatbot** | `continum/userui/` | Flask-based interactive visual operator console and streaming SSE endpoint. |
| **Intent Analyser** | `continum/intentanalyser.py` | Parses natural language queries to classify user intent (e.g. SRM check, segment deep dive, next step recommendations) and extracts entities. |
| **Orchestrator** | `continum/orchestrator.py`<br>`continum/askrouter.py` | Performs routing decisions: detects the matching module/tool to run or hands off complex queries to `AskData`. |
| **AskData Engine** | `continum/askdata/ask_engine.py`<br>`continum/askdata/graph_logic.py` | A multi-agent LangGraph orchestrator containing **SQL**, **Visualization**, and **Insight** agents. Translates NL into SQL, renders Plotly visual charts, and returns deep narrative insights. |
| **Experimentation Module Family** | `continum/experimentation/`<br>`continum/modules/new_modules.py` | The complete suite of analytical modules grouped into subfamilies as described in Section 2 below. |

---

## 2. Experimentation Module Family — Subfamily Categorization

To make the codebase significantly more **developer-friendly**, we have aligned and categorized our experimentation modules in the registry (`continum/toolinterface.py`) according to the three distinct lifecycles displayed on the diagram's right side:

### A. Pre-Experiment Planning
These modules assist product teams with scoping, sizing, hypothesis generation, and experimental design prior to deploying any code.
* **Sizing & Feasibility:**
  * `opportunity_sizing` / `opportunity_sizing_v2` (measures potential upside from closing IOR/conversion gap)
  * `power_calculator` (determines sample sizes, duration, and MDE curves)
  * `opportunity_ranking` (scores and ranks feature opportunities)
  * `funnel_analysis` & `cohort_analysis` (pinpoints high-leverage drop-off points)
* **Design & Alignment:**
  * `brief_generator` (automates formal experiment briefs)
  * `hypothesis_generation` (generates testable hypotheses with counter-hypotheses and risks)
  * `experiment_design` (recommends optimal statistical methods: randomized A/B, DiD, ITS, etc.)
  * `metrics_and_tracking` (specifies tracking events, KPIs, and guardrail requirements)
  * `audience_selection` (assigns groups using propensity score matching or causal ML)

### B. Run & Log (Live Experiment Monitoring)
These modules track experimental telemetry, validation, and early stopping criteria in real-time as data streams in.
* **Telemetry & Pipeline Audits:**
  * `pipeline_health` & `watchtower` (scans silver tables for dimensional/time anomalies)
  * `distribution_shift` (compares baseline vs treatment period covariate stability)
* **Real-time Statsig Monitoring:**
  * `health_monitor` (performs sample ratio mismatch (SRM) checks, guardrail violation checks, and ETA projections)
  * `sequential_testing` (computes mSPRT always-valid p-values allowing safe peeking)

### C. Post-Experiment Analysis & Readout
These modules operate once data collection completes, applying rigorous causal inference and producing executive summaries.
* **Core Readouts:**
  * `experiment_analysis` (full automated z-test/t-test A/B readout pipeline)
  * `bayesian_analysis` (calculates posterior probabilities and credible intervals)
  * `readout_generator` & `executive_summary` (generates narrative summaries)
* **Causal Inference & Attribution:**
  * `causal_analysis` & `causal_analysis_full` (runs DiD event-studies, propensity matching, synthetic controls, RDD, mediation)
  * `pre_post_analysis` (provides fallback analysis for 100% rollouts)
  * `simpsons_paradox` (flags conflicting subgroup treatment effects)
  * `roi_tracker` & `roi_synthesis` (measures post-ship incremental revenue)
* **Segmentation & Rollout Targeting:**
  * `segment_deep_dive` & `driver_discovery` (identifies high-performing user clusters)
  * `uplift_modeller` (trains treatment-effect meta-learners to predict individual CATE scores)
  * `decision_engine` (applies knapsack optimization to targeting under budget constraints)
* **Organizational Memory:**
  * `learnings_repository` (enables storage and semantic querying of historical test findings)

---

## 3. Concrete Code & Architecture Optimizations

To support the above diagram flow and make the codebase highly developer-friendly, the following architectural and file-system optimizations have been successfully implemented:

### 1. Structured & Context-Rich Output Folders
* **Before:** Output files were written as flat files in the root folder or copied directly to a single `outputs` directory. Filenames carried short UUIDs or random hashes, stripping them of context.
* **Optimization:** Generated files are now organized within a structured folder hierarchy: `runtime_data/outputs/<company_dataset>/<experiment_name>/`.
* **File Naming Convention:** File names are automatically formatted to carry complete context:
  `{original_base_name}_{company}_{experiment}_{timestamp_YYYYMMDD_HHMMSS}{extension}`
  This ensures developers and analysts can immediately identify where each file originated and when it was produced.
* **Robust Collection:** In `continum/userui/routes/api.py`, the system is now extremely robust. It inspects module return dictionaries for multiple common keys (`_outputs`, `output_file`, `result_file`, `csv_path`), capturing any and all files generated by both standard and newer analytical modules.

### 2. Recursive & Contextual Listing APIs
* **Before:** The `/api/outputs` route scanned only flat files directly under `runtime_data/outputs` and ignored subdirectories.
* **Optimization:** The route now recursively traverses the directory tree using `os.walk`. It presents files with relative-path display names (e.g., `experiments / pricing_display_4way / brief_experiments_pricing_display_4way_20261105_123456.pdf`), providing deep visual context within the UI's Output tab.

### 3. Unified Security Access Validation
* **Optimization:** Since nested output files are saved within subdirectories of the authorized `OUTPUTS_DIR`, the file server route (`/api/file`) securely authorizes them using `os.path.commonpath`, allowing nested downloads without exposing sensitive system files outside of `runtime_data/outputs/`.

---

## 4. Operational Walkthrough for Developers

For developers extending or working with this codebase:
1. **To Register a New Module:** Add its execution function to `continum/modules/new_modules.py` and register it inside `continum/toolinterface.py`'s registry lists. Specify its phase and category clearly to align with the Planning, Monitoring, or Post-Analysis diagram blocks.
2. **File Generation:** Ensure your new module returns the path of any generated files (PDFs, CSVs, JSON) under the `output_file`, `result_file`, `csv_path`, or `_outputs` keys in its returned dictionary.
3. **Execution & Copying:** The web runner will automatically intercept these file paths, sanitize active metadata context (company & experiment), create the correct nested directories under `runtime_data/outputs/`, copy the files, and assign a beautiful timestamped filename.

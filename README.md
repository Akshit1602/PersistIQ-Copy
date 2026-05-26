# Continum PersistIQ

**Continum PersistIQ** is a unified platform for experimentation intelligence, causal inference, and automated product analytics. It bridges the gap between raw experimental data and actionable business decisions by combining rigorous statistical methods with LLM-powered narrative intelligence.

---

## 🚀 Overview

Continum PersistIQ (also referred to as **Continum OS**) provides a comprehensive suite of tools for the entire experimentation lifecycle:
- **Foundation**: Schema discovery, pipeline health monitoring, and data quality guardrails.
- **Planning**: Power calculators, opportunity sizing, and automated experiment briefs.
- **Live Monitoring**: Sequential testing (mSPRT) and real-time health checks.
- **Analysis**: Advanced causal inference (A/B, DiD, PSM, Synthetic Control) and counterfactual forecasting.
- **Narrative**: Automated synthesis of findings into decision memos and PDF reports.

The platform can be consumed via an **Interactive CLI**, a **Developer Shell**, or a **Visual Web Console**.

---

## 🛠️ Project Structure

```text
.
├── continum/               # Core package (Continum OS)
│   ├── api/                # Internal API dispatcher and bootstrap
│   ├── app/                # Workflow orchestration and data loaders
│   ├── core/               # Deep logic: Monitoring, LLM Manager, Orchestration
│   ├── runtime/            # Runtime state: Session, Bus, Memory, Copilot
│   ├── ui/                 # Flask-based Visual Operator Console
│   └── cli.py              # Unified CLI entry point (`continum` command)
├── core/                   # Root-level core logic (Back-compat)
├── data/                   # Data ingestion and synthetic generation
├── modules/                # Specialized analysis modules (Causal, Forecasting, etc.)
├── utils/                  # Shared stats and reporting utilities
├── main.py                 # Interactive guided dispatcher
├── sample_data/            # Default datasets for demos
└── requirements.txt        # Project dependencies
```

---

## ⚙️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd continum-persistiq
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Requires Python 3.3+. Optimized for Python 3.12.*

3. **(Optional) LLM Setup**:
   The platform defaults to a local **Qwen2.5-1.5B-Instruct** model via `transformers`. Ensure you have enough memory (or a GPU) if you plan to use the narrative features.

---

## 📖 Usage

### 1. Interactive Guided Mode (`main.py`)
The easiest way to explore the platform's capabilities. It provides a menu-driven interface for all analysis phases.
```bash
python main.py
```

### 2. Continum OS CLI (`continum/cli.py`)
A powerful, command-based interface for developers and automated workflows.
```bash
# Launch the full interactive demo
python -m continum.cli demo

# Start the Continum OS Shell
python -m continum.cli shell

# Launch the Web UI
python -m continum.cli ui --port 5050

# Analyse a specific experiment
python -m continum.cli analyse "experiment_name"

# Check pipeline health
python -m continum.cli health
```

### 3. Visual Operator Console (Web UI)
A Flask-based dashboard for visual exploration of experiments and causal reports.
```bash
python -m continum.cli ui
```
Navigate to `http://localhost:5050` to view the console.

---

## 🧪 Core Intelligence Modules

### Causal Inference Engine
Go beyond simple A/B tests with specialized estimators for every scenario:
- **A/B Test Analysis**: Standard randomized trial analysis with SRM checks and segment deep-dives.
- **Difference-in-Differences (DiD)**: Enhanced 2x2 and Two-Way Fixed Effects (TWFE) for quasi-experiments.
- **Synthetic Control**: Counterfactual construction from weighted donor units.
- **Propensity Score Matching (PSM)**: Removal of selection bias in observational data.
- **Interrupted Time Series (ITS)**: Detection of level and slope shifts at intervention points.
- **Regression Discontinuity (RDD)**: Exploitation of sharp threshold rules for causal identification.

### Counterfactual Forecasting
Model "what would have happened" without an intervention using time-series methods:
- **ARIMA / SARIMA**: Autoregressive models with seasonal components.
- **BSTS**: Bayesian Structural Time Series with Kalman filtering.
- **Causal Impact**: Google-style BSTS incorporating external control covariates.

### Narrative & Decision Support
- **Automated Decision Memos**: LLM-synthesized summaries of statistical findings.
- **PDF Report Generation**: Professional-grade reports including charts, insights, and recommendations.
- **Continum Copilot**: An interactive AI assistant to query experiment history and runtime state.

---

## 📊 Data Guardrails
- **Watchtower**: Automated detection of dimensional anomalies and Simpson's Paradox.
- **Pipeline Health**: Real-time monitoring of data ingestion and transformation quality.
- **SRM Detector**: Early warning system for Sample Ratio Mismatch in experiments.

---

## 📝 License
Proprietary / Internal Use Only.

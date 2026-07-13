# Intelligence Layer & Algorithmic Tools — Investigation (B1/B2)

_Investigated 2026-06-29 by tracing `continum/toolinterface.py` registry → impl functions._

## TL;DR
- **19 modules** are registered in the live dispatcher (`_build_registry`). The dashboard's
  `MOD_META` is a cosmetic superset; only registry modules actually run.
- **All 11 "intelligence layer" modules are WIRED** (real implementations) — they have a
  **deterministic core** and only use the LLM for optional narrative enhancement. None are stubs.
- **13 "algorithmic" tools are pure deterministic** (scipy/statsmodels/sklearn/custom); only
  3 modules **require** the LLM at their core (`schema_discovery`, `brief_generator`, `metrics_and_tracking`).

## Intelligence layer (phase=intelligence) — all WIRED
| Module | Type | How it works |
|--------|------|--------------|
| kpi_synthesis | deterministic (+opt LLM) | METRICS_KB lookup by experiment type; LLM only narrates |
| guardrail_generation | deterministic | baseline mean ± z·stddev thresholds from SQL |
| tracking_plan | deterministic (+opt LLM) | event names from METRICS_KB + property mapping |
| historical_learning | deterministic + LLM synth | keyword-ranked search over `experiment_learnings`; LLM summarizes |
| next_step_generation | deterministic FSM (+opt LLM) | `_PHASE_TRANSITIONS` routing + live signals |
| anomaly_synthesis | deterministic (z-score) | IOR/volume/variant-balance z-checks (warn z>2.5, crit z>4) |
| cross_experiment_learning | deterministic | per-exp Δ-IOR, win-rate, effect size aggregation |
| adaptive_recommendations | rule-based (+opt LLM) | `_RECOMMENDATION_RULES` dict |
| ask_v2 | hybrid | intent detect + live DB retrieval + LLM synth (deterministic fallback) |
| open_questions | rule-based (+opt LLM) | SRM/Simpson/time-decay rules |
| root_cause | template + LLM | rule-based candidates; LLM for detailed diagnosis |

## Algorithmic (deterministic, no LLM) tools — libraries used
power_calculator (scipy/statsmodels), opportunity_sizing (custom chain), causal_analysis(_full)
(DiD/ITS via statsmodels, PSM via sklearn, Synthetic Control / Mediation / RDD / ARIMA-BSTS custom),
sequential_testing (mSPRT), pre_post_analysis (OLS+time FE), simpsons_paradox (stratified),
roi_tracker (OLS counterfactual+DiD), forecasting (ARIMA/SARIMA/BSTS/ETS), distribution_shift (KS+chi²),
learnings_repository (DuckDB+keyword rank), audience_selection (propensity rules),
balance_diagnostics (covariate balance + Love plot).

## LLM-core modules (need LLM)
schema_discovery, brief_generator (5 LLM calls → PDF), metrics_and_tracking (5 LLM calls → PDF).

## Module output / "copilot library" (B2)
- **Where output goes:** `execute()` worker (api.py ~504-544). If the module result carries
  `_outputs` (file paths) they are registered into the **readout library** via
  `askdata.readout.add_generated()`; otherwise the result text is captured via
  `result_to_text()` and stored with `add_generated_text()`. Downloadable files are served by
  `/api/file` (whitelisted dirs) and listed by `/api/outputs/<run_id>`.
- **The "copilot library" = the readout store**, an **in-memory** list on the Flask app
  (`app._readouts`, `askdata/readout.py:get_store`). It is **per-process, not persisted to disk**.
  The Copilot answers readout questions grounded ONLY in this store (`readout.answer`).
- **runtime_data/** holds platform artifacts: `.continum_audit.ndjson` (audit log),
  `.continum_snapshots/`, governance JSON, the memory DuckDB, the session JSON, and any
  module-written files (e.g. `data_validation_122026/`, PDFs).
- **PDF/TXT/MD** outputs are auto-registered to the library; **PNG/CSV/JSON** are kept for
  download but NOT added to the library (`readout.py`).

### Gaps surfaced (→ feed the fix list)
1. The readout library is **in-memory only** — outputs vanish on restart. (candidate: persist to runtime_data/)
2. Module-run output is **not surfaced as a dedicated UI tab** — only as downloadable file chips
   in the execution console + as readout-library grounding for chat. (→ bug B4 "output tab")
3. Chat-invoked tools (`execute_tool`) run **silently inside the request**; they do not stream to
   the execution console. (→ bug B4 "make any tool call run, open the console")

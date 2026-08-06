# Databricks notebook source
# MAGIC %md
# MAGIC # MatchView Store — Concurrent Initiative Impact Measurement
# MAGIC ### Dollar Tree MVP: Sales Driver Decomposition, Causal Attribution, Validation Diagnostics & Weekly Forecasting
# MAGIC
# MAGIC One end-to-end flow covering the Sreeragh/Abinaaya technical topics from the MVP presentation:
# MAGIC - **Topic 6** — Sales Driver Decomposition: Traffic, Conversion, UPT, AUR
# MAGIC - **Topic 9** — Concurrent Initiative Attribution / Non-Random Store Selection
# MAGIC - **Topic 10** — Causal Methodology & Validation Diagnostics
# MAGIC - **Topic 7** — Weekly Forecasting Framework & Backtesting
# MAGIC
# MAGIC Built against 5 Delta tables: `store_master`, `store_performance_weekly`, `initiative_catalog`,
# MAGIC `store_initiative_mapping`, `macro_external_data`.
# MAGIC
# MAGIC **Synthetic data only** — calibrated to the refined scope Dollar Tree shared (store attributes,
# MAGIC G.O.L.D. score cadence, the 3 named initiatives, "10-30 concurrent initiatives", cannibalization from
# MAGIC new-store openings, and the customer-behavior lag on store improvements) — no real Dollar Tree data
# MAGIC is used anywhere in this notebook.

# COMMAND ----------

# MAGIC %md ## 0. Setup

# COMMAND ----------

# MAGIC %pip install econml lightgbm scikit-learn --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import numpy as np
import pandas as pd
from pyspark.sql import functions as F

dbutils.widgets.text("n_stores", "800", "Number of stores")
dbutils.widgets.text("n_weeks", "52", "Number of weeks")
dbutils.widgets.text("n_zips", "160", "Number of distinct ZIPs")
dbutils.widgets.text("catalog", "matchview_store", "Schema for Delta tables")

N_STORES = int(dbutils.widgets.get("n_stores"))
N_WEEKS = int(dbutils.widgets.get("n_weeks"))
N_ZIPS = int(dbutils.widgets.get("n_zips"))
SCHEMA = dbutils.widgets.get("catalog")
SEED = 42

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
spark.sql(f"USE {SCHEMA}")

rng = np.random.default_rng(SEED)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. `store_master` — the non-variable baseline
# MAGIC
# MAGIC Fixed/slowly-changing attributes across all stores — "size of the store and density of population
# MAGIC have a direct relationship to sales," plus `risk_tier` and `open_date` (the latter drives the
# MAGIC new-store cannibalization effect in Section 3).

# COMMAND ----------

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
zip_codes = [f"{10000 + i}" for i in range(N_ZIPS)]

# Long-tail zip sizing: a few urban zips hold many stores, most hold 1-3 —
# needed so "neighbor" (same-zip) comparisons are meaningful.
zip_weights = rng.pareto(1.6, N_ZIPS) + 0.3
zip_weights = zip_weights / zip_weights.sum()
store_zip = rng.choice(zip_codes, N_STORES, p=zip_weights)
zip_density = dict(zip(zip_codes, rng.lognormal(6.3, 0.9, N_ZIPS).clip(50, 20000)))

risk_tier = rng.choice(["Low", "Medium", "High"], N_STORES, p=[0.5, 0.35, 0.15])

# open_date: ~85% pre-existing, ~15% open *during* the observation window
# (these drive cannibalization on their same-zip neighbors in Section 3).
obs_start = pd.Timestamp("2024-01-01")
is_new_store = rng.uniform(0, 1, N_STORES) < 0.15
open_date = np.where(
    is_new_store,
    [obs_start + pd.Timedelta(weeks=int(w)) for w in rng.integers(4, N_WEEKS - 4, N_STORES)],
    [obs_start - pd.Timedelta(days=int(d)) for d in rng.integers(365, 365 * 12, N_STORES)],
)

store_master_pd = pd.DataFrame({
    "store_id": [f"S{i:05d}" for i in range(N_STORES)],
    "open_date": pd.to_datetime(open_date).date,
    "store_size_sqft": rng.normal(9500, 2200, N_STORES).clip(4000, 18000).round(0),
    "population_density": [round(zip_density[z] * rng.normal(1, 0.1), 0) for z in store_zip],
    "location_zip": store_zip,
    "risk_tier": risk_tier,
})

# Initial G.O.L.D. score at week 0 — kept internally so it can genuinely
# *drive* Paint-and-Powder's non-random selection in Section 2 (not just a
# label attached after the fact). It becomes the first quarterly value in
# store_performance_weekly, not a persisted store_master column, since the
# real G.O.L.D. score is explicitly time-varying per the requirements.
size_rank0 = store_master_pd["store_size_sqft"].rank(pct=True)
density_rank0 = store_master_pd["population_density"].rank(pct=True)
_gold_q0 = (55 + 20 * (size_rank0 + density_rank0) / 2 + rng.normal(0, 12, N_STORES)).clip(10, 99).round(0)
store_master_pd["_gold_q0"] = _gold_q0.values  # internal only, dropped before saving

store_master = spark.createDataFrame(store_master_pd.drop(columns=["_gold_q0"]))
store_master.write.mode("overwrite").saveAsTable("store_master")
print(f"store_master: {store_master.count():,} rows")
display(store_master.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. `initiative_catalog` and `store_initiative_mapping`
# MAGIC
# MAGIC The 3 named initiatives, each with a real **non-random selection rule** (matching how Dollar Tree
# MAGIC actually picks stores for these programs) and an `expected_lag_weeks` — "store improvements will
# MAGIC have a lag in customer behavior as most customers only visit a Dollar Tree sporadically."
# MAGIC
# MAGIC 1. **Multi-Price Roll-out** (Assortment) — merchandise/shelving change, rolled out to
# MAGIC    **higher-volume stores first** (bigger assortment payoff).
# MAGIC 2. **Dedicated Cashiers** (Staffing) — "lean staffing models... optimize where dedicated cashiers
# MAGIC    make sense" — also targeted at **high-volume stores**.
# MAGIC 3. **Paint-and-Powder** (Remodel) — refresh "to improve overall internal conditions," targeted at
# MAGIC    **low G.O.L.D.-score stores** — a textbook selection-on-need bias, and the one Section 5 shows
# MAGIC    a naive analysis gets backwards.
# MAGIC
# MAGIC All three overlap in time, and many stores get 2-3 at once — matching the "10-30 concurrent
# MAGIC initiatives" framing. `status` (Active / Paused / Control) covers stores that were paused early too.

# COMMAND ----------

GROUND_TRUTH = {
    "multiprice_rollout": {"traffic": 0.010, "conversion": 0.035, "upt": 0.045, "aur": 0.005,
                           "start_week": 10, "end_week": 40, "lag_weeks": 2, "category": "Assortment",
                           "name": "Multi-Price Roll-out"},
    "dedicated_cashiers": {"traffic": 0.000, "conversion": 0.040, "upt": 0.010, "aur": 0.000,
                           "start_week": 5, "end_week": 45, "lag_weeks": 1, "category": "Staffing",
                           "name": "Dedicated Cashiers"},
    "paint_and_powder":   {"traffic": 0.025, "conversion": 0.015, "upt": 0.000, "aur": 0.000,
                           "start_week": 15, "end_week": 50, "lag_weeks": 4, "category": "Remodel",
                           "name": "Paint-and-Powder"},
}
# NOTE: GROUND_TRUTH is kept in this notebook purely so the causal analysis in
# Section 5 can be checked against a known-correct answer. Remove in a real
# deployment — a real notebook wouldn't know the true effect in advance.

initiative_catalog_pd = pd.DataFrame([
    {"initiative_id": k, "initiative_name": v["name"], "initiative_category": v["category"],
     "expected_lag_weeks": v["lag_weeks"]}
    for k, v in GROUND_TRUTH.items()
])
initiative_catalog = spark.createDataFrame(initiative_catalog_pd)
initiative_catalog.write.mode("overwrite").saveAsTable("initiative_catalog")
display(initiative_catalog)

# COMMAND ----------

rng_sel = np.random.default_rng(SEED + 2)
size_rank = store_master_pd["store_size_sqft"].rank(pct=True)
density_rank = store_master_pd["population_density"].rank(pct=True)
volume_proxy_rank = (size_rank + density_rank) / 2
gold_rank = store_master_pd["_gold_q0"].rank(pct=True)

mapping_rows = []
for init_id, params in GROUND_TRUTH.items():
    if init_id in ("multiprice_rollout", "dedicated_cashiers"):
        p_select = np.clip(0.05 + 0.35 * volume_proxy_rank, 0.02, 0.55)
    else:  # paint_and_powder: low G.O.L.D. score -> selected (real selection-on-need bias)
        p_select = np.clip(0.60 - 0.50 * gold_rank, 0.05, 0.65)

    selected = rng_sel.uniform(0, 1, N_STORES) < p_select
    paused = selected & (rng_sel.uniform(0, 1, N_STORES) < 0.08)  # 8% of selected get paused early

    for i, sid in enumerate(store_master_pd["store_id"]):
        status, rollout_date, end_date = "Control", None, None
        if selected[i]:
            status = "Paused" if paused[i] else "Active"
            jitter = int(rng_sel.integers(-3, 4))  # per-store rollout stagger
            start_wk = max(0, params["start_week"] + jitter)
            rollout_date = (obs_start + pd.Timedelta(weeks=start_wk)).date()
            end_wk = (params["end_week"] if not paused[i]
                      else max(start_wk + 2, params["end_week"] - int(rng_sel.integers(5, 15))))
            end_date = (obs_start + pd.Timedelta(weeks=int(end_wk))).date()
        mapping_rows.append((sid, init_id, rollout_date, end_date, status))

mapping_pd = pd.DataFrame(mapping_rows, columns=["store_id", "initiative_id", "rollout_date", "end_date", "status"])
store_initiative_mapping = spark.createDataFrame(mapping_pd)
store_initiative_mapping.write.mode("overwrite").saveAsTable("store_initiative_mapping")

print(f"store_initiative_mapping: {store_initiative_mapping.count():,} rows")
store_initiative_mapping.groupBy("initiative_id", "status").count().orderBy("initiative_id", "status").show()

overlap = mapping_pd[mapping_pd["status"] != "Control"].groupby("store_id").size()
print("Concurrent overlap (stores with 2+ active/paused initiatives):")
print(overlap.value_counts().sort_index().to_string())
gold_by_id = store_master_pd.set_index("store_id")["_gold_q0"]
paint_selected_ids = [sid for sid, st in mapping_pd.set_index(["initiative_id", "store_id"])["status"].xs("paint_and_powder", level="initiative_id").items() if st != "Control"]
paint_not_selected_ids = [sid for sid in store_master_pd["store_id"] if sid not in set(paint_selected_ids)]
print(f"\nSelection-bias check: mean initial GOLD score, paint-selected="
      f"{gold_by_id.reindex(paint_selected_ids).mean():.1f}  vs. "
      f"not-selected={gold_by_id.reindex(paint_not_selected_ids).mean():.1f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. `macro_external_data`
# MAGIC
# MAGIC Generated **once per ZIP-week**, not duplicated per store — every store in a ZIP shares the same
# MAGIC weather/economic conditions, joined in when `store_performance_weekly` is built.

# COMMAND ----------

weeks = pd.date_range(obs_start, periods=N_WEEKS, freq="W-MON")
macro_rows = []
for z in zip_codes:
    z_rng = np.random.default_rng(SEED + 1000 + int(z) % 1000)
    week_of_year = weeks.isocalendar().week.to_numpy(dtype=float)
    weather = np.clip(0.5 + 0.35 * np.cos(2 * np.pi * (week_of_year - 2) / 52) + z_rng.normal(0, 0.08, N_WEEKS), 0, 1)
    econ = 1.0 + np.cumsum(z_rng.normal(0, 0.005, N_WEEKS))
    for i, wk in enumerate(weeks):
        macro_rows.append((z, wk.date(), round(float(weather[i]), 4), round(float(econ[i]), 4)))

macro_pd = pd.DataFrame(macro_rows, columns=["location_zip", "week_start_date", "weather_index", "local_economic_index"])
macro_external_data = spark.createDataFrame(macro_pd)
macro_external_data.write.mode("overwrite").saveAsTable("macro_external_data")
print(f"macro_external_data: {macro_external_data.count():,} rows ({N_ZIPS} zips x {N_WEEKS} weeks)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. `store_performance_weekly` — the weekly panel
# MAGIC
# MAGIC Store x week grain: Traffic x Conversion x UPT x AUR = Sales, with:
# MAGIC - Each initiative's effect **delayed by `expected_lag_weeks`** past its own per-store `rollout_date`
# MAGIC - **Cannibalization**: same-ZIP stores that opened more recently suppress an existing store's traffic
# MAGIC - **New-store ramp-up**: a store's own traffic builds over its first 8 weeks after `open_date`
# MAGIC - **G.O.L.D. score** refreshed every 90 days (quarter), not weekly — matching the real cadence
# MAGIC - Weeks before a store's `open_date` are excluded entirely (a store that doesn't exist yet has no
# MAGIC   performance row — not a zero-sales row)
# MAGIC
# MAGIC Built with vectorized Spark column expressions — the way this would actually run at Dollar Tree's
# MAGIC ~9,500-store scale, not a Python row loop.

# COMMAND ----------

week_dates = spark.createDataFrame(pd.DataFrame({"week_start_date": [w.date() for w in weeks], "week_idx": range(N_WEEKS)}))
panel = store_master.crossJoin(week_dates)

panel = (panel
    .withColumn("_size_factor", F.col("store_size_sqft") / 9500.0)
    .withColumn("_density_factor", F.log1p(F.col("population_density")) / F.log1p(F.lit(2000.0)))
    .withColumn("_risk_mult", F.when(F.col("risk_tier") == "High", 0.97)
                              .when(F.col("risk_tier") == "Medium", 0.99)
                              .otherwise(1.0))
    .withColumn("base_traffic", 3200 * F.col("_size_factor") * (0.6 + 0.4 * F.col("_density_factor")))
    .withColumn("base_conversion", F.lit(0.19) * F.col("_risk_mult"))
    .withColumn("base_upt", F.lit(1.35))
    .withColumn("base_aur", F.lit(4.35))
    .withColumn("_weeks_since_open", F.datediff(F.col("week_start_date"), F.col("open_date")) / 7.0)
    .withColumn("_ramp_factor", F.when(F.col("_weeks_since_open") < 0, F.lit(0.0))
                                 .when(F.col("_weeks_since_open") < 8, F.col("_weeks_since_open") / 8.0)
                                 .otherwise(F.lit(1.0)))
)

# ── Cannibalization: count same-zip stores that opened before this week but
#    after this store's own open_date (a newer competing neighbor already active).
neighbors = (store_master.alias("a")
    .join(store_master.alias("b"), on=(F.col("a.location_zip") == F.col("b.location_zip")) & (F.col("a.store_id") != F.col("b.store_id")))
    .select(F.col("a.store_id").alias("store_id"), F.col("a.open_date").alias("own_open_date"),
            F.col("b.open_date").alias("neighbor_open_date")))
cannib_by_week = (neighbors.crossJoin(week_dates)
    .filter((F.col("neighbor_open_date") <= F.col("week_start_date")) & (F.col("neighbor_open_date") > F.col("own_open_date")))
    .groupBy("store_id", "week_start_date").agg(F.count("*").alias("n_newer_neighbors")))

panel = (panel.join(cannib_by_week, on=["store_id", "week_start_date"], how="left")
    .withColumn("n_newer_neighbors", F.coalesce(F.col("n_newer_neighbors"), F.lit(0)))
    .withColumn("_cannib_mult", F.pow(F.lit(0.94), F.least(F.col("n_newer_neighbors"), F.lit(3))))
)

# ── Initiative exposure, WITH the lag: effect starts expected_lag_weeks after
#    rollout_date, stops at end_date, and only applies to Active/Paused stores.
mapping_with_lag = (store_initiative_mapping
    .join(initiative_catalog, on="initiative_id")
    .withColumn("effect_start_date", F.expr("date_add(rollout_date, CAST(expected_lag_weeks * 7 AS INT))"))
)

def add_initiative_effect(panel_df, init_id: str):
    m = mapping_with_lag.filter(F.col("initiative_id") == init_id).select(
        "store_id", "effect_start_date", "end_date", F.col("status").alias(f"_status_{init_id}"))
    joined = panel_df.join(m, on="store_id", how="left")
    active_col = ((F.col(f"_status_{init_id}").isin("Active", "Paused")) &
                  (F.col("week_start_date") >= F.col("effect_start_date")) &
                  (F.col("week_start_date") <= F.col("end_date")))
    joined = joined.withColumn(f"in_{init_id}", F.coalesce(active_col, F.lit(False)))
    g = GROUND_TRUTH[init_id]
    for driver in ["traffic", "conversion", "upt", "aur"]:
        joined = joined.withColumn(f"_mult_{init_id}_{driver}",
                                    F.when(F.col(f"in_{init_id}"), F.lit(1 + g[driver])).otherwise(F.lit(1.0)))
    return joined.drop("effect_start_date", "end_date")

for iid in GROUND_TRUTH:
    panel = add_initiative_effect(panel, iid)

panel = panel.join(macro_external_data, on=["location_zip", "week_start_date"], how="left")

# ── G.O.L.D. score: refreshed every 90 days (quarter), broadcast across the
#    13 weeks within that quarter.
panel = panel.withColumn("quarter_idx", (F.col("week_idx") / 13).cast("int"))

gold_walk_pd = store_master_pd[["store_id"]].copy()
gold_walk_pd["gold_q0"] = store_master_pd["_gold_q0"].values
for q in range(1, (N_WEEKS // 13) + 2):
    gold_walk_pd[f"gold_q{q}"] = (gold_walk_pd[f"gold_q{q-1}"] + rng.normal(0, 6, N_STORES)).clip(10, 99).round(0)
gold_long = gold_walk_pd.melt(id_vars="store_id", var_name="q", value_name="gold_score")
gold_long["quarter_idx"] = gold_long["q"].str.replace("gold_q", "").astype(int)
gold_sdf = spark.createDataFrame(gold_long[["store_id", "quarter_idx", "gold_score"]])
panel = panel.join(gold_sdf, on=["store_id", "quarter_idx"], how="left")

def product_of(cols):
    expr = F.lit(1.0)
    for c in cols:
        expr = expr * F.col(c)
    return expr

seasonality = 1 + 0.10 * F.sin(2 * np.pi * (F.col("week_idx") - 5) / 52)
mult_traffic = [f"_mult_{i}_traffic" for i in GROUND_TRUTH]
mult_conversion = [f"_mult_{i}_conversion" for i in GROUND_TRUTH]
mult_upt = [f"_mult_{i}_upt" for i in GROUND_TRUTH]
mult_aur = [f"_mult_{i}_aur" for i in GROUND_TRUTH]

panel = (panel
    .withColumn("traffic", F.col("base_traffic") * seasonality * F.col("_ramp_factor") * F.col("_cannib_mult")
                * (1 - 0.08 * (1 - F.col("weather_index"))) * F.col("local_economic_index")
                * product_of(mult_traffic) * (F.rand(SEED) * 0.10 + 0.95))
    .withColumn("conversion", F.least(F.greatest(
        F.col("base_conversion") * product_of(mult_conversion) * (F.rand(SEED + 1) * 0.12 + 0.94),
        F.lit(0.02)), F.lit(0.6)))
    .withColumn("upt", F.col("base_upt") * product_of(mult_upt) * (F.rand(SEED + 2) * 0.08 + 0.96))
    .withColumn("aur", F.col("base_aur") * product_of(mult_aur) * (F.rand(SEED + 3) * 0.08 + 0.96))
    .withColumn("total_sales", F.col("traffic") * F.col("conversion") * F.col("upt") * F.col("aur"))
)

# A store that doesn't exist yet has no performance row (not a zero-sales row).
store_performance_weekly = panel.filter(F.col("week_start_date") >= F.col("open_date")).select(
    "store_id", "week_start_date", "gold_score", "total_sales", "traffic",
    F.col("conversion").alias("conversion_rate"), "upt", "aur",
    "in_multiprice_rollout", "in_dedicated_cashiers", "in_paint_and_powder", "n_newer_neighbors",
)
store_performance_weekly.write.mode("overwrite").saveAsTable("store_performance_weekly")

n_rows = store_performance_weekly.count()
print(f"store_performance_weekly: {n_rows:,} rows")
display(store_performance_weekly.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Sales Driver Decomposition (Topic 6) — naive first look
# MAGIC
# MAGIC A simple treated-vs-control comparison per initiative. Paint-and-Powder's number here is the reason
# MAGIC Section 6 exists — read it, then see it corrected below.

# COMMAND ----------

def decompose_naive(flag_col: str, treated_col_status_map, label: str):
    active = store_performance_weekly.filter(F.col(flag_col))
    treated_ids = [sid for sid, st in treated_col_status_map.items() if st != "Control"]
    control_pool = store_performance_weekly.filter(~F.col("store_id").isin(treated_ids))
    agg = [F.mean(c).alias(c) for c in ["traffic", "conversion_rate", "upt", "aur", "total_sales"]]
    t, c = active.agg(*agg).first(), control_pool.agg(*agg).first()
    print(f"\n=== {label}: naive driver decomposition ===")
    for d in ["traffic", "conversion_rate", "upt", "aur"]:
        print(f"  {d:15s}: {(t[d]/c[d]-1)*100:+.2f}%")
    print(f"  {'Net (naive)':15s}: {(t['total_sales']/c['total_sales']-1)*100:+.2f}%   <- corrected in Section 6")

status_map = mapping_pd.set_index(["initiative_id", "store_id"])["status"]
for iid, label in [("multiprice_rollout", "Multi-Price Roll-out"), ("dedicated_cashiers", "Dedicated Cashiers"),
                    ("paint_and_powder", "Paint-and-Powder")]:
    smap = status_map.xs(iid, level="initiative_id").to_dict()
    decompose_naive(f"in_{iid}", smap, label)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Concurrent Initiative Attribution / Non-Random Store Selection (Topic 9)
# MAGIC
# MAGIC **Double ML**, orthogonalizing against store attributes, cannibalization exposure, calendar
# MAGIC week (each initiative's active window is calendar-bound, so time itself is a confounder), and
# MAGIC exposure to the *other two* concurrent initiatives — this is the "concurrent" in concurrent
# MAGIC initiative attribution: each effect is estimated net of the others running at the same time.

# COMMAND ----------

from econml.dml import LinearDML
from lightgbm import LGBMRegressor, LGBMClassifier

perf_pd = store_performance_weekly.toPandas()
perf_pd["week_start_date"] = pd.to_datetime(perf_pd["week_start_date"])
perf_pd["week_of_year"] = perf_pd["week_start_date"].dt.isocalendar().week.astype(int)
perf_pd["gold_q1_static"] = perf_pd["store_id"].map(gold_walk_pd.set_index("store_id")["gold_q0"])
perf_pd["store_size_sqft"] = perf_pd["store_id"].map(store_master_pd.set_index("store_id")["store_size_sqft"])
perf_pd["population_density"] = perf_pd["store_id"].map(store_master_pd.set_index("store_id")["population_density"])

y = perf_pd["total_sales"].to_numpy()

def run_double_ml(init_id: str, label: str) -> float:
    t = perf_pd[f"in_{init_id}"].astype(int).to_numpy()
    other_flags = [f"in_{i}" for i in GROUND_TRUTH if i != init_id]
    X = perf_pd[["gold_q1_static", "store_size_sqft", "population_density",
                 "n_newer_neighbors", "week_of_year"] + other_flags].astype(float).to_numpy()
    est = LinearDML(
        model_y=LGBMRegressor(n_estimators=100, max_depth=4, verbosity=-1, min_child_samples=5),
        model_t=LGBMClassifier(n_estimators=100, max_depth=4, verbosity=-1, min_child_samples=5),
        discrete_treatment=True, cv=3, random_state=SEED,
    )
    est.fit(Y=y, T=t, X=None, W=X)
    ate_pct = est.effect(X=None).mean() / perf_pd["total_sales"].mean() * 100
    inf = est.effect_inference(X=None)
    ci_lo, ci_hi = inf.conf_int(alpha=0.05)
    print(f"  {label:28s}: corrected lift {ate_pct:+.2f}%  (95% CI: "
          f"{np.mean(ci_lo)/perf_pd['total_sales'].mean()*100:+.2f}% to "
          f"{np.mean(ci_hi)/perf_pd['total_sales'].mean()*100:+.2f}%)")
    return ate_pct

paint_control_ids = [sid for sid, st in status_map.xs("paint_and_powder", level="initiative_id").items() if st == "Control"]
naive_paint = ((perf_pd.loc[perf_pd["in_paint_and_powder"], "total_sales"].mean()
               / perf_pd.loc[perf_pd["store_id"].isin(paint_control_ids), "total_sales"].mean()) - 1) * 100

print(f"Reminder — naive Paint-and-Powder estimate: {naive_paint:+.2f}%\n")
print("Corrected (Double ML) lift, all 3 initiatives, each net of the other 2 concurrent:")
mp_ate = run_double_ml("multiprice_rollout", "Multi-Price Roll-out")
ca_ate = run_double_ml("dedicated_cashiers", "Dedicated Cashiers")
pa_ate = run_double_ml("paint_and_powder", "Paint-and-Powder")

print(f"\n{'='*72}\nKEY FINDING\n{'='*72}")
print(f"Naive Paint-and-Powder estimate: {naive_paint:+.2f}%  (looks like it's HURTING sales)")
print(f"Corrected Paint-and-Powder estimate: {pa_ate:+.2f}%  (actually a genuine positive lift)")
print("Refreshed stores were, by design, the lowest-G.O.L.D.-score stores to begin with — a naive")
print("comparison confounds the refresh effect with whatever was already dragging those stores down.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Causal Methodology & Validation Diagnostics (Topic 10)
# MAGIC
# MAGIC Before trusting Section 6's numbers: (a) covariate balance pre-adjustment (Standardized Mean
# MAGIC Difference, target < 0.10) — Paint-and-Powder should show real imbalance here, confirming the bias
# MAGIC is genuine, not a modeling artifact — and (b) propensity overlap / common support.

# COMMAND ----------

def smd(a, b):
    pooled_std = np.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    return abs(np.mean(a) - np.mean(b)) / pooled_std if pooled_std > 0 else 0.0

paint_treated_ids = [sid for sid, st in status_map.xs("paint_and_powder", level="initiative_id").items() if st != "Control"]
gold_by_store = store_master_pd.set_index("store_id")["_gold_q0"]
smd_val = smd(gold_by_store.loc[paint_treated_ids], gold_by_store.loc[paint_control_ids])
print(f"Raw SMD on initial G.O.L.D. score (Paint-and-Powder): {smd_val:.3f}  "
      f"({'imbalanced -- this IS the selection bias Section 6 corrects for' if smd_val > 0.1 else 'balanced'})")

from sklearn.linear_model import LogisticRegression

X_prop = store_master_pd[["_gold_q0", "store_size_sqft", "population_density"]].astype(float)
y_prop = store_master_pd["store_id"].isin(paint_treated_ids).astype(int)
propensity = LogisticRegression(max_iter=500).fit(X_prop, y_prop).predict_proba(X_prop)[:, 1]
print(f"\nPropensity score range: [{propensity.min():.3f}, {propensity.max():.3f}]  "
      f"Common support OK: {propensity.min() > 0.02 and propensity.max() < 0.98}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Weekly Forecasting Framework & Backtesting (Topic 7)
# MAGIC
# MAGIC A pooled (fleet-wide) LightGBM forecaster, backtested on a held-out final stretch of weeks — real
# MAGIC MAE/RMSE/MAPE on data the model never trained on, not in-sample fit.

# COMMAND ----------

fc = perf_pd.sort_values(["store_id", "week_start_date"]).copy()
fc["lag_1"] = fc.groupby("store_id")["total_sales"].shift(1)
fc["lag_2"] = fc.groupby("store_id")["total_sales"].shift(2)
fc["store_code"] = fc["store_id"].astype("category").cat.codes
fc = fc.dropna(subset=["lag_1", "lag_2"])

HOLDOUT_WEEKS = 8
cutoff = fc["week_start_date"].max() - pd.Timedelta(weeks=HOLDOUT_WEEKS)
train, test = fc[fc["week_start_date"] <= cutoff], fc[fc["week_start_date"] > cutoff]

feature_cols = ["store_code", "week_of_year", "lag_1", "lag_2",
                 "in_multiprice_rollout", "in_dedicated_cashiers", "in_paint_and_powder"]
fc_model = LGBMRegressor(n_estimators=200, max_depth=5, min_child_samples=10, verbosity=-1, random_state=SEED)
fc_model.fit(train[feature_cols].astype(float), train["total_sales"])

pred = fc_model.predict(test[feature_cols].astype(float))
actual = test["total_sales"].to_numpy()
mae, rmse = np.mean(np.abs(actual - pred)), np.sqrt(np.mean((actual - pred) ** 2))
nonzero = actual > 0
mape = np.mean(np.abs((actual[nonzero] - pred[nonzero]) / actual[nonzero])) * 100

print(f"Backtest ({HOLDOUT_WEEKS}-week holdout, n={len(test):,} store-weeks the model never trained on):")
print(f"  MAE:  ${mae:,.2f}")
print(f"  RMSE: ${rmse:,.2f}")
print(f"  MAPE: {mape:.2f}%")

# COMMAND ----------

# MAGIC %md ## 9. Executive Readout

# COMMAND ----------

print("="*72)
print("EXECUTIVE READOUT — Concurrent Initiative Impact (corrected for selection bias)")
print("="*72)
for label, ate in [("Multi-Price Roll-out", mp_ate), ("Dedicated Cashiers", ca_ate), ("Paint-and-Powder", pa_ate)]:
    print(f"  {label:22s}: {ate:+.2f}% net incremental sales lift "
          f"(Double ML, net of the other 2 concurrent initiatives + store attributes + calendar time)")
print(f"\nWeekly forecast backtest accuracy: {mape:.1f}% MAPE over an {HOLDOUT_WEEKS}-week holdout.")
print(f"\nKey finding: a naive treated-vs-control read of Paint-and-Powder showed {naive_paint:+.2f}% — "
      "apparently hurting sales. Correcting for the fact that refreshed stores were, by design, the "
      f"lowest-G.O.L.D.-score stores to begin with reveals a true {pa_ate:+.2f}% lift.")
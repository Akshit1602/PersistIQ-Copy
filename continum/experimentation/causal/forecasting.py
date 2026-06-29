from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger("continum.causal.forecasting")


# ─────────────────────────────────────────────────────────────────────────────
# RESULT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

def _forecast_result(
    method:        str,
    metric:        str,
    horizon:       int,
    forecast:      List[float],
    ci_lo:         List[float],
    ci_hi:         List[float],
    dates:         List[str],
    in_sample_mae: float = 0.0,
    in_sample_rmse: float = 0.0,
    model_info:    Dict = None,
    causal_impact: Dict = None,
) -> Dict:
    return {
        "method":          method,
        "metric":          metric,
        "horizon":         horizon,
        "forecast":        forecast,
        "ci_lo":           ci_lo,
        "ci_hi":           ci_hi,
        "dates":           dates,
        "in_sample_mae":   round(in_sample_mae, 6),
        "in_sample_rmse":  round(in_sample_rmse, 6),
        "model_info":      model_info or {},
        "causal_impact":   causal_impact,
    }


def _date_range(last_date: Any, horizon: int, freq: str = "D") -> List[str]:
    last = pd.Timestamp(last_date)
    return [str((last + pd.tseries.frequencies.to_offset(freq) * (i + 1)).date())
            for i in range(horizon)]


def _mae_rmse(actual: np.ndarray, predicted: np.ndarray) -> Tuple[float, float]:
    residuals = actual - predicted
    mae  = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    return mae, rmse


def _to_series(data) -> pd.Series:
    if isinstance(data, pd.Series):
        s = data.dropna().astype(float)
    elif isinstance(data, pd.DataFrame):
        date_col   = next((c for c in data.columns if "date" in c.lower()), data.columns[0])
        metric_col = next((c for c in data.columns if c != date_col), data.columns[-1])
        s = data.set_index(date_col)[metric_col].dropna().astype(float)
        if not isinstance(s.index, pd.DatetimeIndex):
            s.index = pd.to_datetime(s.index)
    else:
        s = pd.Series(data, dtype=float).dropna()
    return s


# ─────────────────────────────────────────────────────────────────────────────
# ARIMA
# ─────────────────────────────────────────────────────────────────────────────

def run_arima_forecast(
    data,
    horizon:    int  = 30,
    metric:     str  = "metric",
    max_p:      int  = 3,
    max_d:      int  = 2,
    max_q:      int  = 3,
    auto_order: bool = True,
) -> Optional[Dict]:
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError:
        logger.warning("statsmodels required for ARIMA — pip install statsmodels")
        return None

    s = _to_series(data)
    if len(s) < 10:
        return None

    best_aic   = np.inf
    best_order = (1, 1, 1)

    if auto_order:
        for p in range(max_p + 1):
            for d in range(max_d + 1):
                for q in range(max_q + 1):
                    try:
                        m = ARIMA(s, order=(p, d, q)).fit()
                        if m.aic < best_aic:
                            best_aic   = m.aic
                            best_order = (p, d, q)
                    except Exception:
                        continue

    try:
        fitted    = ARIMA(s, order=best_order).fit()
        fc_obj    = fitted.get_forecast(steps=horizon)
        fc_mean   = fc_obj.predicted_mean.tolist()
        fc_ci     = fc_obj.conf_int(alpha=0.05)
        ci_lo     = fc_ci.iloc[:, 0].tolist()
        ci_hi     = fc_ci.iloc[:, 1].tolist()
        in_sample = fitted.fittedvalues
        mae, rmse = _mae_rmse(s.values[-len(in_sample):], in_sample.values)
        dates     = _date_range(s.index[-1] if hasattr(s.index, "freq") else len(s), horizon)

        return _forecast_result(
            method="arima", metric=metric, horizon=horizon,
            forecast=fc_mean, ci_lo=ci_lo, ci_hi=ci_hi, dates=dates,
            in_sample_mae=mae, in_sample_rmse=rmse,
            model_info={"order": best_order, "aic": round(best_aic, 2)},
        )
    except Exception as e:
        logger.warning("ARIMA fit failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SEASONAL ARIMA (SARIMA)
# ─────────────────────────────────────────────────────────────────────────────

def run_sarima_forecast(
    data,
    horizon:       int = 30,
    metric:        str = "metric",
    order:         tuple = (1, 1, 1),
    seasonal_order: tuple = (1, 1, 0, 7),   # weekly seasonality default
) -> Optional[Dict]:
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except ImportError:
        return None

    s = _to_series(data)
    if len(s) < max(30, seasonal_order[-1] * 2):
        return None

    try:
        fitted  = SARIMAX(s, order=order, seasonal_order=seasonal_order,
                          enforce_stationarity=False,
                          enforce_invertibility=False).fit(disp=False)
        fc_obj  = fitted.get_forecast(steps=horizon)
        fc_mean = fc_obj.predicted_mean.tolist()
        fc_ci   = fc_obj.conf_int(alpha=0.05)
        ci_lo   = fc_ci.iloc[:, 0].tolist()
        ci_hi   = fc_ci.iloc[:, 1].tolist()
        in_s    = fitted.fittedvalues
        mae, rmse = _mae_rmse(s.values[-len(in_s):], in_s.values)
        dates   = _date_range(s.index[-1] if hasattr(s.index, "freq") else len(s), horizon)

        return _forecast_result(
            method="sarima", metric=metric, horizon=horizon,
            forecast=fc_mean, ci_lo=ci_lo, ci_hi=ci_hi, dates=dates,
            in_sample_mae=mae, in_sample_rmse=rmse,
            model_info={"order": order, "seasonal_order": seasonal_order,
                        "aic": round(fitted.aic, 2)},
        )
    except Exception as e:
        logger.warning("SARIMA fit failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# BSTS — Bayesian Structural Time Series (via statsmodels UnobservedComponents)
# ─────────────────────────────────────────────────────────────────────────────

def run_bsts_forecast(
    data,
    horizon: int = 30,
    metric:  str = "metric",
    level:   bool = True,
    trend:   bool = True,
    seasonal: Optional[int] = 7,   # None to disable
) -> Optional[Dict]:
    try:
        from statsmodels.tsa.statespace.structural import UnobservedComponents
    except ImportError:
        return None

    s = _to_series(data)
    if len(s) < 20:
        return None

    spec = {}
    if level:  spec["level"]  = True
    if trend:  spec["trend"]  = True
    if seasonal and seasonal > 1:
        spec["freq_seasonal"] = [{"period": seasonal, "harmonics": 2}]

    try:
        fitted  = UnobservedComponents(s, **spec).fit(disp=False, maxiter=200)
        fc_obj  = fitted.get_forecast(steps=horizon)
        fc_mean = fc_obj.predicted_mean.tolist()
        fc_ci   = fc_obj.conf_int(alpha=0.05)
        ci_lo   = fc_ci.iloc[:, 0].tolist()
        ci_hi   = fc_ci.iloc[:, 1].tolist()
        in_s    = fitted.fittedvalues
        mae, rmse = _mae_rmse(s.values[-len(in_s):], in_s.values)
        dates   = _date_range(s.index[-1] if hasattr(s.index, "freq") else len(s), horizon)

        return _forecast_result(
            method="bsts", metric=metric, horizon=horizon,
            forecast=fc_mean, ci_lo=ci_lo, ci_hi=ci_hi, dates=dates,
            in_sample_mae=mae, in_sample_rmse=rmse,
            model_info={"spec": spec, "aic": round(fitted.aic, 2)},
        )
    except Exception as e:
        logger.warning("BSTS fit failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ETS — Exponential Smoothing (Holt-Winters)
# ─────────────────────────────────────────────────────────────────────────────

def run_ets_forecast(
    data,
    horizon:  int  = 30,
    metric:   str  = "metric",
    seasonal: Optional[int] = None,    # e.g. 7 for weekly
    trend:    str  = "add",
) -> Optional[Dict]:
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError:
        return _naive_ets_forecast(data, horizon, metric)

    s = _to_series(data)
    if len(s) < 10:
        return None

    kw = {"trend": trend}
    if seasonal and len(s) >= seasonal * 2:
        kw["seasonal"] = "add"
        kw["seasonal_periods"] = seasonal

    try:
        fitted    = ExponentialSmoothing(s, **kw).fit(optimized=True)
        fc_mean   = fitted.forecast(horizon).tolist()
        std_err   = float(np.std(fitted.resid))
        z95       = 1.96
        ci_lo     = [v - z95 * std_err for v in fc_mean]
        ci_hi     = [v + z95 * std_err for v in fc_mean]
        mae, rmse = _mae_rmse(s.values, fitted.fittedvalues.values)
        dates     = _date_range(s.index[-1] if hasattr(s.index, "freq") else len(s), horizon)

        return _forecast_result(
            method="ets", metric=metric, horizon=horizon,
            forecast=fc_mean, ci_lo=ci_lo, ci_hi=ci_hi, dates=dates,
            in_sample_mae=mae, in_sample_rmse=rmse,
            model_info={"seasonal": seasonal, "trend": trend},
        )
    except Exception as e:
        logger.warning("ETS fit failed: %s — using naive", e)
        return _naive_ets_forecast(data, horizon, metric)


def _naive_ets_forecast(data, horizon: int, metric: str) -> Optional[Dict]:
    s = _to_series(data)
    if len(s) < 2:
        return None
    alpha  = 0.3
    level  = float(s.iloc[0])
    for v in s.iloc[1:]:
        level = alpha * v + (1 - alpha) * level
    std_err   = float(s.std())
    fc_mean   = [level] * horizon
    ci_lo     = [level - 1.96 * std_err] * horizon
    ci_hi     = [level + 1.96 * std_err] * horizon
    dates     = _date_range(len(s), horizon)
    return _forecast_result(
        method="naive_ets", metric=metric, horizon=horizon,
        forecast=fc_mean, ci_lo=ci_lo, ci_hi=ci_hi, dates=dates,
        model_info={"alpha": alpha},
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENSEMBLE
# ─────────────────────────────────────────────────────────────────────────────

def run_forecast_ensemble(
    data,
    horizon:     int   = 30,
    metric:      str   = "metric",
    methods:     Optional[List[str]] = None,
) -> Optional[Dict]:
    available = methods or ["arima", "ets", "bsts"]
    fn_map = {
        "arima":  run_arima_forecast,
        "sarima": run_sarima_forecast,
        "bsts":   run_bsts_forecast,
        "ets":    run_ets_forecast,
    }

    results = {}
    for m in available:
        if m in fn_map:
            r = fn_map[m](data, horizon=horizon, metric=metric)
            if r is not None:
                results[m] = r

    if not results:
        return run_ets_forecast(data, horizon, metric)  # last-resort

    # Weight by inverse (1 + RMSE)
    weights = {}
    for m, r in results.items():
        rmse = r["in_sample_rmse"] or 1.0
        weights[m] = 1.0 / (1.0 + rmse)
    total_w = sum(weights.values())
    weights = {m: w / total_w for m, w in weights.items()}

    fc_mean = [
        sum(results[m]["forecast"][i] * weights[m] for m in results)
        for i in range(horizon)
    ]
    ci_lo = [
        sum(results[m]["ci_lo"][i] * weights[m] for m in results)
        for i in range(horizon)
    ]
    ci_hi = [
        sum(results[m]["ci_hi"][i] * weights[m] for m in results)
        for i in range(horizon)
    ]
    dates = list(results.values())[0]["dates"]

    return _forecast_result(
        method="ensemble", metric=metric, horizon=horizon,
        forecast=fc_mean, ci_lo=ci_lo, ci_hi=ci_hi, dates=dates,
        model_info={"methods": list(results), "weights": {m: round(w, 3) for m, w in weights.items()}},
    )


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL IMPACT (BSTS counterfactual)
# ─────────────────────────────────────────────────────────────────────────────

def run_causal_impact(
    pre_series:  pd.Series,
    post_series: pd.Series,
    metric:      str = "metric",
    method:      str = "bsts",
) -> Optional[Dict]:
    if len(pre_series) < 10 or len(post_series) < 3:
        return None

    horizon  = len(post_series)
    fc_fn    = {"bsts": run_bsts_forecast, "arima": run_arima_forecast,
                "ets":  run_ets_forecast}.get(method, run_ets_forecast)

    fc = fc_fn(pre_series, horizon=horizon, metric=metric)
    if fc is None:
        fc = _naive_ets_forecast(pre_series, horizon, metric)
    if fc is None:
        return None

    predicted = np.array(fc["forecast"])
    actual    = post_series.values.astype(float)
    effect    = actual - predicted
    cumeff    = float(np.sum(effect))

    # One-sample t-test: are residuals significantly different from 0?
    t_stat, p_val = stats.ttest_1samp(effect, 0.0)

    return {
        "method":            method,
        "metric":            metric,
        "predicted":         predicted.tolist(),
        "actual":            actual.tolist(),
        "ci_lo":             fc["ci_lo"],
        "ci_hi":             fc["ci_hi"],
        "point_effect":      effect.tolist(),
        "cumulative_effect": round(cumeff, 6),
        "mean_effect":       round(float(np.mean(effect)), 6),
        "p_value":           round(float(p_val), 6),
        "is_significant":    bool(p_val < 0.05),
        "t_stat":            round(float(t_stat), 4),
        "pre_n":             len(pre_series),
        "post_n":            len(post_series),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROI FORECASTING — project shipped lift forward N months
# ─────────────────────────────────────────────────────────────────────────────

def run_roi_forecasting(
    delta_ior:          float,          # observed lift in IOR (pp, e.g. 0.02)
    baseline_ior:       float,          # pre-experiment IOR
    monthly_inquiries:  float,          # traffic volume
    aov:                float,          # average order value ($)
    gross_margin:       float = 0.30,   # fraction
    horizon_months:     int   = 12,
    confidence:         float = 0.95,   # CI to propagate
    delta_ci_lo:        float = None,   # experiment CI lower bound
    delta_ci_hi:        float = None,   # experiment CI upper bound
) -> Dict:
    months   = list(range(1, horizon_months + 1))
    inc_orders_per_month = monthly_inquiries * delta_ior

    # Central estimate
    inc_gmv_monthly   = inc_orders_per_month * aov
    inc_margin_monthly = inc_gmv_monthly * gross_margin

    cumulative_gmv    = [inc_gmv_monthly * m for m in months]
    cumulative_margin  = [inc_margin_monthly * m for m in months]

    # CI propagation (if experiment CI supplied)
    if delta_ci_lo is not None and delta_ci_hi is not None:
        inc_gmv_lo = monthly_inquiries * delta_ci_lo * aov
        inc_gmv_hi = monthly_inquiries * delta_ci_hi * aov
        cum_gmv_lo = [inc_gmv_lo * m for m in months]
        cum_gmv_hi = [inc_gmv_hi * m for m in months]
    else:
        # Assume 20% uncertainty on the estimate
        uncertainty = 0.20
        cum_gmv_lo  = [v * (1 - uncertainty) for v in cumulative_gmv]
        cum_gmv_hi  = [v * (1 + uncertainty) for v in cumulative_gmv]

    return {
        "horizon_months":       horizon_months,
        "delta_ior":            delta_ior,
        "baseline_ior":         baseline_ior,
        "monthly_inquiries":    monthly_inquiries,
        "aov":                  aov,
        "gross_margin":         gross_margin,
        "inc_orders_monthly":   round(inc_orders_per_month, 1),
        "inc_gmv_monthly":      round(inc_gmv_monthly, 2),
        "inc_margin_monthly":   round(inc_margin_monthly, 2),
        "cumulative_gmv":       [round(v, 2) for v in cumulative_gmv],
        "cumulative_gmv_lo":    [round(v, 2) for v in cum_gmv_lo],
        "cumulative_gmv_hi":    [round(v, 2) for v in cum_gmv_hi],
        "cumulative_margin":    [round(v, 2) for v in cumulative_margin],
        "months":               months,
        "12m_gmv":              round(cumulative_gmv[-1], 2),
        "12m_margin":           round(cumulative_margin[-1], 2),
    }


__all__ = [
    "run_arima_forecast",
    "run_sarima_forecast",
    "run_bsts_forecast",
    "run_ets_forecast",
    "run_forecast_ensemble",
    "run_causal_impact",
    "run_roi_forecasting",
]

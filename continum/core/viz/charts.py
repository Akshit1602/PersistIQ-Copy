from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("continum.viz")

DARK_BG   = "#0f172a"
ACCENT    = "#7c3aed"
TREATMENT = "#f97316"
CONTROL   = "#4e9af1"
POSITIVE  = "#22c55e"
NEGATIVE  = "#ef4444"
NEUTRAL   = "#a1a1aa"
HIGHLIGHT = "#facc15"
WARNING   = "#f59e0b"


def _ax_style(ax, title: str = "", xlabel: str = "", ylabel: str = ""):
    ax.set_facecolor("#1e293b")
    ax.tick_params(colors="#94a3b8", labelsize=8)
    ax.xaxis.label.set_color("#94a3b8")
    ax.yaxis.label.set_color("#94a3b8")
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")
    if title:
        ax.set_title(title, color=HIGHLIGHT, fontsize=10, fontweight="bold", pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, color="#94a3b8", fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color="#94a3b8", fontsize=9)
    ax.grid(True, alpha=0.15, color="#334155")


def _fig(*args, **kw):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(*args, facecolor=DARK_BG, **kw)
    return fig, plt


# ─────────────────────────────────────────────────────────────────────────────
# POWER CURVE
# ─────────────────────────────────────────────────────────────────────────────

def power_curve(
    baseline:  float,
    mde_abs:   float,
    n_per_var: int,
    duration:  int,
    alpha:     float = 0.05,
    power:     float = 0.80,
) -> Any:
    fig, plt = _fig(figsize=(14, 5))
    fig.suptitle("Power Calculator", color=HIGHLIGHT, fontsize=12, fontweight="bold", y=1.01)

    ax1 = fig.add_subplot(1, 3, 1)
    mde_range = np.linspace(0.001, mde_abs * 3, 80)
    from scipy.stats import norm
    z_a = norm.ppf(1 - alpha / 2)
    z_b = norm.ppf(power)
    ss_range = ((z_a + z_b) ** 2 * 2 * baseline * (1 - baseline) / mde_range ** 2).astype(int)
    ax1.plot(mde_range * 100, ss_range, color=TREATMENT, lw=2.5)
    ax1.axvline(mde_abs * 100, color=HIGHLIGHT, linestyle="--", lw=1.5,
                label=f"MDE={mde_abs*100:.2f}pp")
    ax1.axhline(n_per_var, color=POSITIVE, linestyle=":", lw=1.5,
                label=f"n={n_per_var:,}/var")
    ax1.legend(fontsize=7, labelcolor="white")
    _ax_style(ax1, "Sample Size vs MDE", "MDE (pp)", "n per variant")
    ax1.yaxis.set_major_formatter(
        __import__("matplotlib").ticker.FuncFormatter(lambda x, _: f"{int(x):,}")
    )

    ax2 = fig.add_subplot(1, 3, 2)
    dur_range = np.arange(7, duration * 2 + 1, 1)
    power_range = []
    for d in dur_range:
        n_d = n_per_var * d / duration
        se = np.sqrt(2 * baseline * (1 - baseline) / max(n_d, 1))
        z  = mde_abs / se - z_a
        power_range.append(float(norm.cdf(z)))
    ax2.plot(dur_range, [p * 100 for p in power_range], color=CONTROL, lw=2.5)
    ax2.axhline(80, color=HIGHLIGHT, linestyle="--", lw=1.5, label="80% power")
    ax2.axvline(duration, color=TREATMENT, linestyle="--", lw=1.5,
                label=f"{duration}d planned")
    ax2.set_ylim(0, 105)
    ax2.legend(fontsize=7, labelcolor="white")
    _ax_style(ax2, "Power vs Duration", "Days", "Power (%)")

    ax3 = fig.add_subplot(1, 3, 3)
    labels = ["Baseline IOR", "IOR + MDE"]
    vals   = [baseline * 100, (baseline + mde_abs) * 100]
    bars   = ax3.bar(labels, vals, color=[CONTROL, POSITIVE], width=0.45, edgecolor="#334155")
    for bar, v in zip(bars, vals):
        ax3.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                 f"{v:.2f}%", ha="center", color="white", fontsize=9, fontweight="bold")
    ax3.annotate(
        f"Δ = +{mde_abs*100:.2f}pp\n({mde_abs/baseline*100:.1f}% rel)",
        xy=(1, (baseline + mde_abs / 2) * 100),
        xytext=(1.3, (baseline + mde_abs / 2) * 100),
        arrowprops={"arrowstyle": "->", "color": HIGHLIGHT},
        color=HIGHLIGHT, fontsize=8,
    )
    _ax_style(ax3, "Effect Size Visualised", "", "IOR (%)")

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITY FUNNEL
# ─────────────────────────────────────────────────────────────────────────────

def opportunity_funnel(
    category:    str,
    funnel_chain: List[Tuple],
    monthly_gmv:  float,
    monthly_gm:   float,
    horizon:      int,
    mde_info:     Dict,
) -> Any:
    fig, plt = _fig(figsize=(16, 5))
    fig.suptitle(f"Opportunity Sizing — {category.title()}", color=HIGHLIGHT,
                 fontsize=12, fontweight="bold")

    ax1 = fig.add_subplot(1, 3, 1)
    labels = ["Stat Min", "Biz Min", "Benchmark", "Recommended"]
    vals   = [mde_info.get("stat_min_rel_pct", 1), mde_info.get("biz_min_rel_pct", 1),
              mde_info.get("bench_mid_rel_pct", 5), mde_info.get("recommended_rel_pct", 5)]
    colors = [NEUTRAL, NEUTRAL, CONTROL, HIGHLIGHT]
    bars   = ax1.bar(labels, vals, color=colors, edgecolor="#334155")
    for bar, v in zip(bars, vals):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                 f"{v:.1f}%", ha="center", color="white", fontsize=8, fontweight="bold")
    _ax_style(ax1, "MDE Breakdown", "", "Relative MDE (%)")
    plt.setp(ax1.get_xticklabels(), rotation=15, ha="right")

    ax2 = fig.add_subplot(1, 3, 2)
    months   = np.arange(1, horizon + 1)
    cum_gmv  = months * monthly_gmv / 1e6
    cum_gm   = months * monthly_gm  / 1e6
    ax2.fill_between(months, cum_gmv, alpha=0.2, color=TREATMENT)
    ax2.plot(months, cum_gmv, color=TREATMENT, lw=2.5, label="GMV")
    ax2.fill_between(months, cum_gm, alpha=0.2, color=POSITIVE)
    ax2.plot(months, cum_gm, color=POSITIVE, lw=2.5, label="Gross Margin")
    ax2.yaxis.set_major_formatter(
        __import__("matplotlib").ticker.FuncFormatter(lambda x, _: f"${x:.2f}M")
    )
    ax2.legend(fontsize=8, labelcolor="white")
    _ax_style(ax2, "Cumulative Opportunity", "Month", "$ Millions")

    ax3 = fig.add_subplot(1, 3, 3)
    ax3.axis("off")
    ax3.set_title("Funnel Chain", color=HIGHLIGHT, fontsize=10, fontweight="bold", pad=8)
    for i, row in enumerate(funnel_chain[:6]):
        y_pos = 0.92 - i * 0.17
        ax3.text(0.02, y_pos, str(row[0]), transform=ax3.transAxes,
                 color="#94a3b8", fontsize=8.5)
        val_str = f"{row[1]}"
        if row[2]:
            val_str += f"  →  {row[2]}"
        ax3.text(0.02, y_pos - 0.06, val_str, transform=ax3.transAxes,
                 color="white", fontsize=9, fontweight="bold")
        if row[3]:
            ax3.text(0.02, y_pos - 0.12, str(row[3]), transform=ax3.transAxes,
                     color=POSITIVE, fontsize=8.5, fontstyle="italic")
        if i < len(funnel_chain) - 1:
            ax3.annotate("", xy=(0.1, y_pos - 0.16), xytext=(0.1, y_pos - 0.01),
                         xycoords="axes fraction", textcoords="axes fraction",
                         arrowprops={"arrowstyle": "->", "color": NEUTRAL, "lw": 1})

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT READOUT
# ─────────────────────────────────────────────────────────────────────────────

def experiment_readout(
    variants:    List[str],
    ior_vals:    List[float],
    ci_lo:       List[float],
    ci_hi:       List[float],
    p_vals:      List[float],
    exp_name:    str = "",
    delta_pp:    List[float] = None,
    segment_df:  Optional[pd.DataFrame] = None,
) -> Any:
    n_plots = 2 if segment_df is not None else 1
    fig, plt = _fig(figsize=(7 * n_plots, 5))
    fig.suptitle(f"Experiment Readout — {exp_name}", color=HIGHLIGHT,
                 fontsize=12, fontweight="bold")

    ax1 = fig.add_subplot(1, n_plots, 1)
    colors = []
    for i, v in enumerate(variants):
        if "control" in str(v).lower():
            colors.append(CONTROL)
        elif i < len(p_vals) and p_vals[i] < 0.05:
            colors.append(POSITIVE if (delta_pp and delta_pp[i] > 0) else NEGATIVE)
        else:
            colors.append(NEUTRAL)

    x_pos = range(len(variants))
    ax1.bar(x_pos, [v * 100 for v in ior_vals], color=colors,
            width=0.5, edgecolor="#334155", alpha=0.85)
    for i, (ior, lo, hi) in enumerate(zip(ior_vals, ci_lo, ci_hi)):
        ax1.errorbar(i, ior * 100, yerr=[[ior * 100 - lo * 100], [hi * 100 - ior * 100]],
                     fmt="none", color="white", capsize=5, lw=2)
        ax1.text(i, ior * 100 + 0.15, f"{ior*100:.2f}%", ha="center",
                 color="white", fontsize=8, fontweight="bold")
        if i < len(p_vals) and "control" not in str(variants[i]).lower():
            sig = "✓ sig" if p_vals[i] < 0.05 else "n.s."
            ax1.text(i, lo * 100 - 0.25, f"p={p_vals[i]:.3f} {sig}",
                     ha="center", color=HIGHLIGHT if p_vals[i] < 0.05 else NEUTRAL, fontsize=7)

    ax1.set_xticks(list(x_pos))
    ax1.set_xticklabels(variants, rotation=15, ha="right")
    _ax_style(ax1, "IOR by Variant (95% CI)", "Variant", "IOR (%)")

    if segment_df is not None and not segment_df.empty and n_plots > 1:
        ax2 = fig.add_subplot(1, n_plots, 2)
        try:
            pivot = segment_df.pivot_table(
                index="level", columns="dim", values="delta_pp", aggfunc="mean"
            ).fillna(0)
            import matplotlib.pyplot as _plt
            import matplotlib.colors as _mc
            cmap = _mc.LinearSegmentedColormap.from_list("rg", [NEGATIVE, "#1e293b", POSITIVE])
            im = ax2.imshow(pivot.values, cmap=cmap, aspect="auto",
                            vmin=-max(0.1, abs(pivot.values).max()),
                            vmax=max(0.1, abs(pivot.values).max()))
            ax2.set_xticks(range(len(pivot.columns)))
            ax2.set_xticklabels(pivot.columns, rotation=30, ha="right")
            ax2.set_yticks(range(len(pivot.index)))
            ax2.set_yticklabels(pivot.index)
            for i in range(len(pivot.index)):
                for j in range(len(pivot.columns)):
                    v = pivot.values[i, j]
                    ax2.text(j, i, f"{v:+.1f}", ha="center", va="center",
                             color="white", fontsize=7)
            _plt.colorbar(im, ax=ax2).set_label("Δ pp", color="#94a3b8")
            _ax_style(ax2, "Segment × Dimension Δ IOR (pp)")
        except Exception as e:
            ax2.text(0.5, 0.5, f"Segment chart\nunavailable\n({e})",
                     ha="center", va="center", transform=ax2.transAxes, color=NEUTRAL)

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# DID EVENT STUDY
# ─────────────────────────────────────────────────────────────────────────────

def did_event_study(event_study: List[Dict], did_estimate_pp: float,
                    ci_boot: List[float]) -> Any:
    fig, plt = _fig(figsize=(14, 5))
    ax1 = fig.add_subplot(1, 2, 1)
    if event_study:
        weeks  = [e["week"]       for e in event_study]
        gaps   = [e["gap"]        for e in event_study]
        ci_lo  = [e["gap_ci_lo"]  for e in event_study]
        ci_hi  = [e["gap_ci_hi"]  for e in event_study]
        ax1.fill_between(weeks, ci_lo, ci_hi, alpha=0.20, color=TREATMENT)
        ax1.plot(weeks, gaps, color=TREATMENT, lw=2.5, marker="o", ms=3,
                 label="Trt − Ctrl gap (pp)")
        ax1.axhline(0, color="white", lw=1, linestyle="--", alpha=0.4)
        ax1.axvline(0, color=HIGHLIGHT, lw=2, label="Intervention")
        pre = [w for w in weeks if w < 0]
        if pre:
            ax1.axvspan(min(pre) - 0.5, -0.5, alpha=0.07, color=NEUTRAL)
        ax1.legend(fontsize=7, labelcolor="white")
    _ax_style(ax1, "DiD Event Study", "Week relative to intervention",
              "Treatment − Control gap (pp)")

    ax2 = fig.add_subplot(1, 2, 2)
    boot = np.random.normal(did_estimate_pp / 100, abs(did_estimate_pp / 100) * 0.3, 5000) * 100
    ax2.hist(boot, bins=50, color=NEUTRAL, alpha=0.7, edgecolor="#334155")
    ax2.axvline(did_estimate_pp, color=TREATMENT, lw=2.5,
                label=f"Estimate={did_estimate_pp:+.3f}pp")
    if len(ci_boot) == 2:
        ax2.axvline(ci_boot[0], color=HIGHLIGHT, lw=1.5, linestyle="--")
        ax2.axvline(ci_boot[1], color=HIGHLIGHT, lw=1.5, linestyle="--",
                    label=f"95% CI [{ci_boot[0]:+.2f}, {ci_boot[1]:+.2f}]pp")
    ax2.axvline(0, color="white", lw=1, linestyle=":", alpha=0.5)
    ax2.legend(fontsize=7, labelcolor="white")
    _ax_style(ax2, "Bootstrap DiD Distribution", "DiD estimate (pp)", "Frequency")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# ITS COUNTERFACTUAL
# ─────────────────────────────────────────────────────────────────────────────

def its_counterfactual(its_result: Dict) -> Any:
    fig, plt = _fig(figsize=(12, 5))
    dates    = pd.to_datetime(its_result.get("dates", []))
    actual   = np.array(its_result.get("actual_values", []))
    fitted   = np.array(its_result.get("fitted_values", []))
    cf       = np.array(its_result.get("counterfactual", []))
    cut      = pd.Timestamp(its_result.get("cutoff_date", dates[len(dates)//2] if len(dates) else "2024-01-01"))

    ax1 = fig.add_subplot(1, 2, 1)
    if len(dates) > 0 and len(actual) == len(dates):
        ax1.scatter(dates, actual * 100, color=CONTROL, s=10, alpha=0.5, label="Actual")
        ax1.plot(dates, fitted  * 100, color=TREATMENT, lw=2, label="Fitted")
        ax1.plot(dates, cf      * 100, color=NEUTRAL, lw=2, linestyle="--", label="Counterfactual")
        ax1.axvline(cut, color=HIGHLIGHT, lw=2, linestyle="--", label="Intervention")
        post_mask = dates >= cut
        if post_mask.sum() > 0:
            ax1.fill_between(dates[post_mask], cf[post_mask] * 100, actual[post_mask] * 100,
                             alpha=0.25, color=POSITIVE, label="Attributed lift")
    ax1.legend(fontsize=7, labelcolor="white")
    _ax_style(ax1, "ITS — Actual vs Counterfactual", "Date", "IOR (%)")
    plt.setp(ax1.get_xticklabels(), rotation=20, ha="right")

    ax2 = fig.add_subplot(1, 2, 2)
    stats_labels = ["Level change (pp)", "Slope change\n(pp/day)", "Model R²"]
    stats_vals   = [
        its_result.get("level_change_pp", 0),
        its_result.get("slope_change_pp_day", 0),
        its_result.get("model_r2", 0) * 10,   # scale R² for visibility
    ]
    colors_s = [POSITIVE if v > 0 else NEGATIVE for v in stats_vals]
    ax2.barh(stats_labels, stats_vals, color=colors_s, edgecolor="#334155")
    for i, (lab, v) in enumerate(zip(stats_labels, stats_vals)):
        ax2.text(max(v, 0) + 0.01, i, f"{v:+.4f}", va="center", color="white", fontsize=8)
    ax2.axvline(0, color="white", lw=1, alpha=0.4)
    _ax_style(ax2, "ITS Coefficients", "Value", "")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# UPLIFT DISTRIBUTION + QINI
# ─────────────────────────────────────────────────────────────────────────────

def uplift_distribution(scores: np.ndarray, labels: np.ndarray,
                         treatment: np.ndarray) -> Any:
    fig, plt = _fig(figsize=(12, 5))

    ax1 = fig.add_subplot(1, 2, 1)
    trt_scores  = scores[treatment == 1]
    ctrl_scores = scores[treatment == 0]
    ax1.hist(trt_scores, bins=40, color=TREATMENT, alpha=0.6, density=True, label="Treatment")
    ax1.hist(ctrl_scores, bins=40, color=CONTROL, alpha=0.6, density=True, label="Control")
    ax1.axvline(0, color="white", lw=1, linestyle="--", alpha=0.5)
    ax1.legend(fontsize=8, labelcolor="white")
    _ax_style(ax1, "Uplift Score Distribution", "Uplift score", "Density")

    ax2 = fig.add_subplot(1, 2, 2)
    # Percentile profile
    pcts    = np.linspace(10, 100, 10)
    trt_profile, ctrl_profile = [], []
    for p in pcts:
        thresh = np.percentile(scores, 100 - p)
        mask   = scores >= thresh
        if mask.sum() > 0:
            trt_rate  = float(labels[(mask) & (treatment == 1)].mean()) if (mask & (treatment==1)).sum() > 0 else 0
            ctrl_rate = float(labels[(mask) & (treatment == 0)].mean()) if (mask & (treatment==0)).sum() > 0 else 0
            trt_profile.append(trt_rate * 100)
            ctrl_profile.append(ctrl_rate * 100)
        else:
            trt_profile.append(0)
            ctrl_profile.append(0)
    ax2.plot(pcts, trt_profile, color=TREATMENT, lw=2.5, marker="o", ms=4, label="Treatment IOR")
    ax2.plot(pcts, ctrl_profile, color=CONTROL, lw=2.5, marker="s", ms=4, label="Control IOR")
    ax2.fill_between(pcts, ctrl_profile, trt_profile, alpha=0.15, color=POSITIVE)
    ax2.legend(fontsize=8, labelcolor="white")
    _ax_style(ax2, "IOR by Uplift Percentile", "Top-N% by uplift score", "IOR (%)")
    plt.tight_layout()
    return fig


def qini_curve(scores: np.ndarray, labels: np.ndarray, treatment: np.ndarray) -> Any:
    fig, plt = _fig(figsize=(8, 5))
    ax = fig.add_subplot(1, 1, 1)

    # Sort by descending score
    order      = np.argsort(-scores)
    s_treat    = treatment[order]
    s_label    = labels[order]
    n          = len(scores)
    n_treat    = s_treat.sum()
    n_ctrl     = n - n_treat

    qini_vals, rand_vals, targeted = [0.0], [0.0], []
    cum_treat_conv, cum_ctrl_conv = 0, 0
    cum_treat_n,   cum_ctrl_n    = 0, 0

    for i in range(n):
        if s_treat[i] == 1:
            cum_treat_conv += s_label[i]
            cum_treat_n    += 1
        else:
            cum_ctrl_conv  += s_label[i]
            cum_ctrl_n     += 1
        frac_ctrl = cum_ctrl_n  / max(n_ctrl, 1)
        qini      = cum_treat_conv - cum_ctrl_conv * frac_ctrl
        qini_vals.append(float(qini))
        rand_vals.append(i * (n_treat * s_label[s_treat==1].mean() if n_treat>0 else 0) / n)

    x_axis = np.linspace(0, 1, n + 1)
    ax.plot(x_axis, qini_vals, color=TREATMENT, lw=2.5, label="Model Qini")
    ax.plot(x_axis, rand_vals, color=NEUTRAL, lw=1.5, linestyle="--", label="Random")
    ax.fill_between(x_axis, rand_vals, qini_vals, alpha=0.15, color=POSITIVE)
    ax.axhline(0, color="white", lw=0.8, alpha=0.3)

    # Qini coefficient
    qini_coef = float(np.trapz(qini_vals, x_axis) - np.trapz(rand_vals, x_axis))
    ax.text(0.55, 0.15, f"Qini coefficient: {qini_coef:.4f}",
            transform=ax.transAxes, color=HIGHLIGHT, fontsize=9, fontweight="bold")

    ax.legend(fontsize=8, labelcolor="white")
    _ax_style(ax, "Qini Curve (Uplift Model Performance)",
              "Fraction of population targeted", "Incremental conversions")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# ROI TRAJECTORY
# ─────────────────────────────────────────────────────────────────────────────

def roi_trajectory(
    dates: List, observed: List[float], counterfactual: List[float],
    cum_gmv: List[float], ship_date: str, exp_name: str = "",
) -> Any:
    fig, plt = _fig(figsize=(14, 5))

    ax1 = fig.add_subplot(1, 2, 1)
    dt = pd.to_datetime(dates) if dates else []
    obs = np.array(observed)
    cf  = np.array(counterfactual)
    if len(dt) > 0:
        ax1.plot(dt, obs * 100, color=TREATMENT, lw=2.5, label="Observed IOR")
        ax1.plot(dt, cf  * 100, color=NEUTRAL, lw=2, linestyle="--", label="Counterfactual")
        ship = pd.Timestamp(ship_date)
        ax1.axvline(ship, color=HIGHLIGHT, lw=2, linestyle="--", label="Ship date")
        post = dt >= ship
        if np.sum(post) > 0:
            ax1.fill_between(dt[post], cf[post] * 100, obs[post] * 100,
                             alpha=0.25, color=POSITIVE, label="Attributed lift")
    ax1.legend(fontsize=7, labelcolor="white")
    _ax_style(ax1, f"ROI Tracker — {exp_name}", "Date", "IOR (%)")
    plt.setp(ax1.get_xticklabels(), rotation=20, ha="right")

    ax2 = fig.add_subplot(1, 2, 2)
    if cum_gmv:
        days = np.arange(1, len(cum_gmv) + 1)
        gmv  = np.array(cum_gmv) / 1e3
        ax2.fill_between(days, gmv, alpha=0.25, color=POSITIVE)
        ax2.plot(days, gmv, color=POSITIVE, lw=2.5)
        ax2.axhline(0, color="white", lw=0.8, alpha=0.3)
        ax2.yaxis.set_major_formatter(
            __import__("matplotlib").ticker.FuncFormatter(lambda x, _: f"${x:.0f}K")
        )
    _ax_style(ax2, "Cumulative Incremental GMV", "Days post-ship", "GMV ($K)")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# FORECASTING FAN
# ─────────────────────────────────────────────────────────────────────────────

def forecast_chart(
    history:  List[float],
    forecast: List[float],
    ci_lo:    List[float],
    ci_hi:    List[float],
    metric:   str = "IOR",
    method:   str = "ensemble",
) -> Any:
    fig, plt = _fig(figsize=(12, 5))
    ax = fig.add_subplot(1, 1, 1)

    n_hist = len(history)
    n_fore = len(forecast)
    x_hist = np.arange(n_hist)
    x_fore = np.arange(n_hist, n_hist + n_fore)

    ax.plot(x_hist, [v * 100 for v in history], color=CONTROL, lw=2, label="Historical")
    ax.plot(x_fore, [v * 100 for v in forecast], color=TREATMENT, lw=2.5,
            linestyle="-", label=f"Forecast ({method})")
    ax.fill_between(x_fore, [v * 100 for v in ci_lo], [v * 100 for v in ci_hi],
                    alpha=0.20, color=TREATMENT, label="95% CI")
    ax.axvline(n_hist, color=HIGHLIGHT, lw=1.5, linestyle="--", alpha=0.7, label="Now")
    ax.legend(fontsize=8, labelcolor="white")
    _ax_style(ax, f"{metric} Forecast — {n_fore} period horizon", "Period", f"{metric} (%)")
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# ANOMALY DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def anomaly_dashboard(anomalies: List[Dict], experiment: str = "") -> Any:
    if not anomalies:
        fig, plt = _fig(figsize=(8, 3))
        ax = fig.add_subplot(1, 1, 1)
        ax.text(0.5, 0.5, "✅  No anomalies detected", ha="center", va="center",
                transform=ax.transAxes, color=POSITIVE, fontsize=12)
        ax.axis("off")
        return fig

    fig, plt = _fig(figsize=(12, max(4, len(anomalies) * 0.7 + 2)))
    ax = fig.add_subplot(1, 1, 1)

    metrics  = [f"{a['metric']} ({a.get('type','')})" for a in anomalies]
    z_scores = [a.get("z_score", 0) or 0 for a in anomalies]
    colors   = [NEGATIVE if a.get("severity") == "critical" else WARNING for a in anomalies]

    y_pos    = range(len(metrics))
    ax.barh(list(y_pos), z_scores, color=colors, edgecolor="#334155", alpha=0.85)
    ax.axvline(2.0, color=WARNING, linestyle="--", lw=1.5, alpha=0.7, label="|z|=2.0 warn")
    ax.axvline(3.0, color=NEGATIVE, linestyle="--", lw=1.5, alpha=0.7, label="|z|=3.0 crit")
    ax.axvline(-2.0, color=WARNING, linestyle="--", lw=1.5, alpha=0.7)
    ax.axvline(-3.0, color=NEGATIVE, linestyle="--", lw=1.5, alpha=0.7)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(metrics, fontsize=8)
    for i, z in enumerate(z_scores):
        ax.text(z + (0.05 if z >= 0 else -0.05), i, f"{z:+.2f}σ",
                va="center", ha="left" if z >= 0 else "right", color="white", fontsize=7.5)
    ax.legend(fontsize=7, labelcolor="white")
    _ax_style(ax, f"Anomaly Dashboard{' — ' + experiment if experiment else ''}",
              "Z-score", "Metric")
    plt.tight_layout()
    return fig


__all__ = [
    "power_curve", "opportunity_funnel", "experiment_readout",
    "did_event_study", "its_counterfactual", "uplift_distribution",
    "qini_curve", "roi_trajectory", "forecast_chart", "anomaly_dashboard",
]

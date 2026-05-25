from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("continum.visualization.charts")

# ── Colour palette (matches notebook COLORS dict) ────────────────────────────
COLORS = {
    "control":    "#3498DB",
    "treatment":  "#E74C3C",
    "positive":   "#2ECC71",
    "negative":   "#E74C3C",
    "neutral":    "#95A5A6",
    "highlight":  "#F39C12",
    "accent":     "#9B59B6",
    "background": "#0f0f0f",
    "text":       "#ECF0F1",
}
SMD_THRESHOLD = 0.10


def _mpl():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError as e:
        raise ImportError(
            "matplotlib is required for visualizations: pip install matplotlib"
        ) from e


def _apply_dark_style(fig, ax_list):
    fig.patch.set_facecolor(COLORS["background"])
    for ax in ax_list:
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors=COLORS["text"])
        ax.xaxis.label.set_color(COLORS["text"])
        ax.yaxis.label.set_color(COLORS["text"])
        ax.title.set_color(COLORS["highlight"])
        for spine in ax.spines.values():
            spine.set_edgecolor("#2d2d44")


# ─────────────────────────────────────────────────────────────────────────────
# LOVE PLOT — COVARIATE BALANCE
# ─────────────────────────────────────────────────────────────────────────────

def plot_love_plot(
    balance_results: Dict[str, Dict],
    exp_name: str = "",
    output_path: str = "balance_love_plot.png",
) -> str:
    plt = _mpl()
    import matplotlib.patches as mpatches

    if not balance_results:
        logger.warning("plot_love_plot: empty balance_results")
        return ""

    cov_list = list(balance_results.keys())
    smds     = [float(v.get("smd", 0)) if isinstance(v.get("smd"), (int, float)) else 0.0
                for v in balance_results.values()]
    flags    = [bool(v.get("flag", False)) for v in balance_results.values()]

    fig, ax = plt.subplots(figsize=(9, max(3, len(cov_list) * 0.55)))
    colors  = [COLORS["negative"] if f else COLORS["positive"] for f in flags]
    y_pos   = range(len(cov_list))

    ax.barh(list(y_pos), smds, color=colors, alpha=0.82, edgecolor="white", height=0.65)
    ax.axvline(x=SMD_THRESHOLD, color=COLORS["negative"], linestyle="--", linewidth=1.4,
               label=f"Threshold (SMD={SMD_THRESHOLD})", alpha=0.75)
    ax.axvline(x=0, color="grey", linewidth=0.5, alpha=0.4)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(cov_list, fontsize=10, color=COLORS["text"])
    ax.set_xlabel("Standardised Mean Difference (SMD)", color=COLORS["text"])
    title = f"Love Plot — Covariate Balance{' · ' + exp_name if exp_name else ''}"
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlim(left=0)

    pass_p  = mpatches.Patch(color=COLORS["positive"], alpha=0.8, label="Balanced (SMD ≤ 0.10)")
    fail_p  = mpatches.Patch(color=COLORS["negative"], alpha=0.8, label="Imbalanced (SMD > 0.10)")
    thresh  = plt.Line2D([0], [0], color=COLORS["negative"], linestyle="--",
                          label=f"Threshold ({SMD_THRESHOLD})")
    ax.legend(handles=[pass_p, fail_p, thresh], fontsize=9, loc="lower right")
    _apply_dark_style(fig, [ax])
    plt.tight_layout()
    plt.savefig(output_path, dpi=130, bbox_inches="tight", facecolor=COLORS["background"])
    plt.close()
    logger.info("Love plot saved → %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITY SIZING CHART
# ─────────────────────────────────────────────────────────────────────────────

def plot_opportunity(
    opportunity_result: Dict,
    desc: str = "",
    output_path: str = "opportunity_sizing.png",
) -> str:
    plt = _mpl()
    r   = opportunity_result

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.patch.set_facecolor(COLORS["background"])
    title = f"Opportunity Sizing: {desc[:55]}" if desc else "Opportunity Sizing"
    fig.suptitle(title, fontsize=13, color=COLORS["highlight"], fontweight="bold")

    # Panel 1: MDE breakdown
    ax = axes[0]
    mde_info = r.get("mde_info", {})
    stat_min = mde_info.get("stat_min_rel_pct",   r.get("ior_gap_pp", 1) * 0.5)
    biz_min  = mde_info.get("biz_min_rel_pct",    r.get("ior_gap_pp", 1))
    bench    = mde_info.get("bench_mid_rel_pct",  r.get("ior_gap_pp", 1) * 1.5)
    recommended = mde_info.get("recommended_rel_pct", r.get("ior_gap_pp", 1) * 1.2)
    labels   = ["Statistical\nMinimum", "Business\nMinimum", "Industry\nBenchmark", "Recommended\nMDE"]
    values   = [stat_min, biz_min, bench, recommended]
    bar_cols = [COLORS["neutral"], COLORS["neutral"], COLORS["control"], COLORS["highlight"]]
    bars     = ax.bar(labels, values, color=bar_cols, width=0.55)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{v:.1f}%", ha="center", fontsize=10, fontweight="bold", color="white")
    ax.set_title("MDE Breakdown\n(relative %)")
    ax.set_ylabel("Relative MDE (%)", color=COLORS["text"])

    # Panel 2: Cumulative GMV over horizon
    ax = axes[1]
    months  = np.arange(1, int(r.get("time_horizon_months", 12)) + 1)
    gm_mo   = float(r.get("incremental_gm_monthly",     r.get("incremental_revenue_monthly", 0) * 0.3))
    gmv_mo  = float(r.get("incremental_revenue_monthly", 0))
    cum_gmv = months * gmv_mo / 1e6
    cum_gm  = months * gm_mo  / 1e6
    ax.fill_between(months, cum_gmv, alpha=0.2, color=COLORS["treatment"])
    ax.plot(months, cum_gmv, color=COLORS["treatment"], lw=2.5, label="GMV ($M)")
    ax.fill_between(months, cum_gm,  alpha=0.2, color=COLORS["positive"])
    ax.plot(months, cum_gm,  color=COLORS["positive"],  lw=2.5, label="Gross Margin ($M)")
    ax.set_xlabel("Month", color=COLORS["text"])
    ax.set_ylabel("Cumulative ($M)", color=COLORS["text"])
    ax.set_title("Cumulative Opportunity")
    ax.legend(fontsize=9)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.2f}M"))

    # Panel 3: Summary text
    ax = axes[2]
    ax.axis("off")
    ax.set_title("Key Numbers")
    lines = [
        ("IOR gap",         f"{r.get('ior_gap_pp', 0):+.2f}pp"),
        ("Monthly inq.",    f"{r.get('monthly_inquiries', 0):,.0f}"),
        ("Incr. orders/mo", f"{r.get('incremental_orders_monthly', 0):,.1f}"),
        ("Incr. GMV/mo",    f"${r.get('incremental_revenue_monthly', 0):,.0f}"),
        ("Incr. GM/mo",     f"${gm_mo:,.0f}"),
        ("12-mo GMV upside",f"${gmv_mo * 12:,.0f}"),
        ("12-mo GM upside", f"${gm_mo * 12:,.0f}"),
    ]
    for i, (label, val) in enumerate(lines):
        ax.text(0.03, 0.95 - i * 0.13, label, transform=ax.transAxes,
                fontsize=9, color=COLORS["neutral"], va="top")
        ax.text(0.03, 0.88 - i * 0.13, val, transform=ax.transAxes,
                fontsize=10, color="white", va="top", fontweight="bold")

    _apply_dark_style(fig, list(axes))
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=COLORS["background"])
    plt.close()
    logger.info("Opportunity chart saved → %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-VARIANT POST-EXPERIMENT CHART
# ─────────────────────────────────────────────────────────────────────────────

def plot_multivariant(
    df,
    pairwise_df,
    variants:    List[str],
    control:     str,
    exp_name:    str = "",
    alpha:       float = 0.05,
    output_path: str = "post_experiment_analysis.png",
) -> str:
    import pandas as pd
    plt = _mpl()
    from matplotlib.gridspec import GridSpec

    treatments = [v for v in variants if v != control]
    bar_colors = [COLORS["treatment"], COLORS["accent"], COLORS["positive"], COLORS["highlight"]]

    n_rows = 2 + (1 if len(treatments) > 0 else 0)
    fig    = plt.figure(figsize=(20, 7 * n_rows))
    fig.patch.set_facecolor(COLORS["background"])
    gs     = GridSpec(n_rows, 3, figure=fig, hspace=0.55, wspace=0.38)

    all_axes = []

    # ── Row 1a: IOR per variant ───────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    all_axes.append(ax1)
    all_vars = [control] + treatments
    all_cols = [COLORS["control"]] + bar_colors[:len(treatments)]
    ior_vals = [float(df[df["variant"] == v]["converted_to_order"].mean() * 100)
                for v in all_vars]
    bars = ax1.bar(all_vars, ior_vals, color=all_cols, width=0.55)
    for bar, v in zip(bars, ior_vals):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03,
                 f"{v:.3f}%", ha="center", fontsize=9, fontweight="bold", color="white")
    ax1.set_title("IOR per Variant")
    ax1.set_ylabel("IOR (%)", color=COLORS["text"])
    plt.setp(ax1.get_xticklabels(), rotation=20, ha="right", fontsize=8)

    # ── Row 1b: CI forest plot ────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    all_axes.append(ax2)
    primary = pairwise_df[pairwise_df["is_primary"] == True].reset_index(drop=True) \
              if not pairwise_df.empty and "is_primary" in pairwise_df.columns \
              else pairwise_df.reset_index(drop=True)
    for i, row in primary.iterrows():
        col = (COLORS["positive"] if row.get("significant") and row.get("direction") == "positive"
               else COLORS["negative"] if row.get("significant") and row.get("direction") == "negative"
               else COLORS["neutral"])
        ax2.plot([row["ci_lo_pp"], row["ci_hi_pp"]], [i, i],
                 color=col, lw=3, solid_capstyle="round")
        ax2.scatter([row["delta_pp"]], [i], color=col, s=80, zorder=5)
    ax2.axvline(0, color="white", lw=1, linestyle="--", alpha=0.6)
    ax2.set_yticks(range(len(primary)))
    if not primary.empty:
        ax2.set_yticklabels([r.get("variant", str(i)) for i, r in primary.iterrows()],
                            fontsize=9, color=COLORS["text"])
    ax2.set_xlabel("IOR delta (pp)", color=COLORS["text"])
    ax2.set_title(f"IOR Δ vs {control}\n(95% CI, Bonferroni-adj)")

    # ── Row 1c: p-values ─────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    all_axes.append(ax3)
    if not primary.empty:
        pvals  = [row["p_value"]  for _, row in primary.iterrows()]
        labels = [row.get("variant", f"V{i}")[:15]  for i, row in primary.iterrows()]
        pcols  = [COLORS["positive"] if p < alpha else COLORS["negative"] for p in pvals]
        ax3.barh(labels, pvals, color=pcols)
        ax3.axvline(alpha, color=COLORS["highlight"], lw=2, linestyle="--",
                    label=f"α={alpha}")
        for i, p in enumerate(pvals):
            ax3.text(p + 0.005, i, f"{p:.4f}", va="center", fontsize=9, color="white")
        ax3.legend(fontsize=9)
    ax3.set_xlabel("p-value", color=COLORS["text"])
    ax3.set_title("P-values per Variant")

    # ── Row 2: Segment heatmap ────────────────────────────────────────────────
    if not pairwise_df.empty and "account_segment" in df.columns:
        ax4 = fig.add_subplot(gs[1, :])
        all_axes.append(ax4)
        segs  = sorted(df["account_segment"].dropna().unique())
        heat  = np.full((len(treatments), len(segs)), np.nan)
        for ti, trt in enumerate(treatments):
            trt_rows = pairwise_df[pairwise_df.get("variant", pairwise_df.columns[0]) == trt] \
                       if "variant" in pairwise_df.columns else pd.DataFrame()
            for si, seg in enumerate(segs):
                ctrl_seg  = df[(df["variant"] == control)  & (df["account_segment"] == seg)]
                treat_seg = df[(df["variant"] == trt) & (df["account_segment"] == seg)]
                if len(ctrl_seg) > 10 and len(treat_seg) > 10:
                    heat[ti, si] = float(treat_seg["converted_to_order"].mean() * 100
                                         - ctrl_seg["converted_to_order"].mean() * 100)
        vmax = float(np.nanmax(np.abs(heat))) if not np.all(np.isnan(heat)) else 1.0
        im = ax4.imshow(heat, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)
        plt.colorbar(im, ax=ax4, label="IOR delta (pp)")
        ax4.set_xticks(range(len(segs)));  ax4.set_xticklabels(segs, color=COLORS["text"])
        ax4.set_yticks(range(len(treatments))); ax4.set_yticklabels(treatments, color=COLORS["text"])
        for ti in range(len(treatments)):
            for si in range(len(segs)):
                v = heat[ti, si]
                if not np.isnan(v):
                    ax4.text(si, ti, f"{v:+.2f}pp", ha="center", va="center",
                             fontsize=10, color="white", fontweight="bold")
        ax4.set_title("IOR Delta Heatmap: Variant × Segment")

    _apply_dark_style(fig, all_axes)
    fig.suptitle(f"Post-Experiment: {exp_name}  |  {len(variants)} variants",
                 fontsize=13, color=COLORS["highlight"], fontweight="bold", y=1.01)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=COLORS["background"])
    plt.close()
    logger.info("Multivariant chart saved → %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT WATERFALL
# ─────────────────────────────────────────────────────────────────────────────

def plot_segment_waterfall(
    slice_findings,
    exp_name: str = "",
    dimension: str = "account_segment",
    output_path: str = "segment_waterfall.png",
) -> str:
    plt = _mpl()

    slices = [s for s in slice_findings
              if getattr(s, "dimension_name", "") == dimension]
    if not slices:
        logger.warning("plot_segment_waterfall: no slices for dimension=%s", dimension)
        return ""

    slices = sorted(slices, key=lambda s: s.delta.delta_pp, reverse=True)
    labels = [s.dimension_value for s in slices]
    deltas = [s.delta.delta_pp for s in slices]
    colors = [COLORS["positive"] if d > 0 else COLORS["negative"] for d in deltas]
    sigs   = [s.is_heterogeneous for s in slices]

    fig, ax = plt.subplots(figsize=(10, max(4, len(slices) * 0.8)))
    bars = ax.barh(labels, deltas, color=colors, alpha=0.85, edgecolor="white")
    ax.axvline(0, color="white", lw=1.2, alpha=0.5)
    for bar, delta, sig in zip(bars, deltas, sigs):
        label_x = delta + (0.01 if delta >= 0 else -0.01)
        ha = "left" if delta >= 0 else "right"
        marker = "✅" if sig else ""
        ax.text(label_x, bar.get_y() + bar.get_height() / 2,
                f"{delta:+.3f}pp {marker}", va="center", ha=ha,
                fontsize=9, color="white")
    ax.set_xlabel("IOR Δ vs control (pp)", color=COLORS["text"])
    ax.set_title(f"Segment Waterfall: {exp_name or dimension}", fontweight="bold")
    ax.set_yticklabels(labels, fontsize=10, color=COLORS["text"])
    _apply_dark_style(fig, [ax])
    plt.tight_layout()
    plt.savefig(output_path, dpi=130, bbox_inches="tight", facecolor=COLORS["background"])
    plt.close()
    logger.info("Segment waterfall saved → %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# SEQUENTIAL TRAJECTORY
# ─────────────────────────────────────────────────────────────────────────────

def plot_sequential_trajectory(
    n_history:   List[int],
    e_history:   List[float],
    delta_history: Optional[List[float]] = None,
    alpha: float = 0.05,
    exp_name: str = "",
    output_path: str = "sequential_trajectory.png",
) -> str:
    plt = _mpl()

    n_panels = 2 if delta_history else 1
    fig, axes = plt.subplots(1, n_panels, figsize=(14 if n_panels == 2 else 8, 5))
    if n_panels == 1:
        axes = [axes]
    fig.patch.set_facecolor(COLORS["background"])
    threshold = 1.0 / alpha

    # Panel 1: e-value
    ax = axes[0]
    ax.plot(n_history, e_history, color=COLORS["treatment"], lw=2, label="E-value")
    ax.axhline(threshold, color=COLORS["highlight"], lw=1.5, linestyle="--",
               label=f"Boundary (1/α = {threshold:.0f})")
    ax.fill_between(n_history, 0, e_history,
                    where=[e >= threshold for e in e_history],
                    color=COLORS["positive"], alpha=0.25, label="Significant region")
    ax.set_xlabel("N observations", color=COLORS["text"])
    ax.set_ylabel("mSPRT E-value", color=COLORS["text"])
    ax.set_title(f"Sequential E-value Trajectory{' · ' + exp_name if exp_name else ''}")
    ax.legend(fontsize=9)

    # Panel 2: delta trajectory
    if delta_history and len(axes) > 1:
        ax2 = axes[1]
        ax2.plot(n_history, delta_history, color=COLORS["control"], lw=2, label="Δ (pp)")
        ax2.axhline(0, color="white", lw=1, linestyle="--", alpha=0.5)
        ax2.fill_between(n_history, 0, delta_history,
                         where=[d > 0 for d in delta_history],
                         color=COLORS["positive"], alpha=0.2)
        ax2.fill_between(n_history, 0, delta_history,
                         where=[d <= 0 for d in delta_history],
                         color=COLORS["negative"], alpha=0.2)
        ax2.set_xlabel("N observations", color=COLORS["text"])
        ax2.set_ylabel("IOR Δ (pp)", color=COLORS["text"])
        ax2.set_title("Effect Estimate over Time")

    _apply_dark_style(fig, axes)
    plt.tight_layout()
    plt.savefig(output_path, dpi=130, bbox_inches="tight", facecolor=COLORS["background"])
    plt.close()
    logger.info("Sequential trajectory saved → %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# POWER CURVE
# ─────────────────────────────────────────────────────────────────────────────

def plot_power_curve(
    baseline_rate: float,
    alpha: float = 0.05,
    power_target: float = 0.80,
    output_path: str = "power_curve.png",
) -> str:
    from continum.core.experimentation.statistics import compute_sample_size
    plt = _mpl()

    mde_pcts = np.linspace(2, 30, 50)
    n_80 = [compute_sample_size(baseline_rate, baseline_rate * pct / 100, alpha, 0.80)["n_per_variant"]
            for pct in mde_pcts]
    n_90 = [compute_sample_size(baseline_rate, baseline_rate * pct / 100, alpha, 0.90)["n_per_variant"]
            for pct in mde_pcts]

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(COLORS["background"])
    ax.plot(mde_pcts, n_80, color=COLORS["treatment"], lw=2.5, label="80% power")
    ax.plot(mde_pcts, n_90, color=COLORS["positive"],  lw=2.5, label="90% power")
    ax.fill_between(mde_pcts, n_80, n_90, alpha=0.15, color=COLORS["highlight"],
                    label="80%→90% range")
    ax.set_xlabel("MDE (% relative to baseline)", color=COLORS["text"])
    ax.set_ylabel("Sample size per variant", color=COLORS["text"])
    ax.set_title(f"Power Curve  ·  Baseline={baseline_rate:.1%}  α={alpha}",
                 fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
    _apply_dark_style(fig, [ax])
    plt.tight_layout()
    plt.savefig(output_path, dpi=130, bbox_inches="tight", facecolor=COLORS["background"])
    plt.close()
    logger.info("Power curve saved → %s", output_path)
    return output_path


__all__ = [
    "COLORS", "SMD_THRESHOLD",
    "plot_love_plot",
    "plot_opportunity",
    "plot_multivariant",
    "plot_segment_waterfall",
    "plot_sequential_trajectory",
    "plot_power_curve",
]

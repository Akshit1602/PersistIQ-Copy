from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ttest_ind

logger = logging.getLogger("continum.causal.balance")

SMD_THRESHOLD = 0.10
BALANCE_MAX_ITER = 10


# ─────────────────────────────────────────────────────────────────────────────
# SMD HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def compute_smd(a: pd.Series, b: pd.Series) -> float:
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 5 or len(b) < 5:
        return float("nan")
    mu_a, mu_b = a.mean(), b.mean()
    sd_a, sd_b = a.std(), b.std()
    pooled = np.sqrt(((len(a) - 1) * sd_a**2 + (len(b) - 1) * sd_b**2) / (len(a) + len(b) - 2))
    return float(abs(mu_a - mu_b) / pooled) if pooled > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# BALANCE BATTERY
# ─────────────────────────────────────────────────────────────────────────────

BALANCE_COVARIATES = [
    ("account_segment", "categorical"),
    ("platform", "categorical"),
    ("country", "categorical"),
    ("lifetime_orders", "continuous"),
    ("personal_ior", "continuous"),
    ("avg_order_value", "continuous"),
    ("days_since_last", "continuous"),
    ("n_inquiries", "continuous"),
    ("has_billing_profile", "categorical"),
]


def run_balance_battery(
    assignments: pd.DataFrame,
    control_col: str = "group",
    control_label: str = "control",
    covariate_spec: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Dict]:
    spec = covariate_spec or BALANCE_COVARIATES
    groups = sorted(assignments[control_col].unique())
    ctrl = assignments[assignments[control_col] == control_label]
    treatments = [g for g in groups if g != control_label]

    results: Dict[str, Dict] = {}
    for cov_name, ctype in spec:
        if cov_name not in assignments.columns:
            continue
        for trt in treatments:
            trt_df = assignments[assignments[control_col] == trt]
            key = cov_name if len(treatments) == 1 else f"{cov_name}__{trt}"
            row = {"covariate": cov_name, "treatment": trt, "type": ctype}

            if ctype == "continuous":
                a = pd.to_numeric(ctrl[cov_name], errors="coerce").dropna()
                b = pd.to_numeric(trt_df[cov_name], errors="coerce").dropna()
                if len(a) < 5 or len(b) < 5:
                    continue
                smd = compute_smd(a, b)
                _, pv = ttest_ind(a.values, b.values, equal_var=False)
                row.update(
                    {
                        "smd": round(smd, 4),
                        "p_value": round(float(pv), 4),
                        "mean_ctrl": round(float(a.mean()), 4),
                        "mean_trt": round(float(b.mean()), 4),
                        "flag": smd > SMD_THRESHOLD,
                    }
                )
            else:
                ctrl_cnt = ctrl[cov_name].value_counts()
                trt_cnt = trt_df[cov_name].value_counts()
                cats = sorted(set(ctrl_cnt.index) | set(trt_cnt.index))
                contingency = np.array(
                    [
                        [ctrl_cnt.get(c, 0) for c in cats],
                        [trt_cnt.get(c, 0) for c in cats],
                    ]
                )
                try:
                    _, pv, _, _ = chi2_contingency(contingency)
                except Exception:
                    pv = 1.0
                cp = ctrl_cnt / ctrl_cnt.sum() if ctrl_cnt.sum() > 0 else ctrl_cnt
                tp = trt_cnt / trt_cnt.sum() if trt_cnt.sum() > 0 else trt_cnt
                max_diff = float((cp - tp).abs().max()) if not tp.empty else 0.0
                row.update(
                    {
                        "smd": round(max_diff, 4),
                        "p_value": round(float(pv), 4),
                        "mean_ctrl": str(ctrl_cnt.idxmax()) if not ctrl_cnt.empty else "—",
                        "mean_trt": str(trt_cnt.idxmax()) if not trt_cnt.empty else "—",
                        "flag": bool(pv < 0.05),
                    }
                )
            results[key] = row

    return results


def print_balance_report(
    results: Dict,
    n_ctrl: int,
    n_trt: int,
) -> bool:
    n_flags = sum(1 for r in results.values() if r.get("flag"))
    print("\n  ── Covariate Balance Report ──────────────────────────────────────")
    print(
        f"  {'Covariate':<26} {'Ctrl mean':<16} {'Trt mean':<16} {'SMD':>6}  {'p-val':>6}  Status"
    )
    print("  " + "─" * 80)
    for r in results.values():
        icon = "⚠️  " if r.get("flag") else "✅ "
        smd = f"{r['smd']:.4f}" if isinstance(r["smd"], float) else "—"
        pv = f"{r['p_value']:.4f}"
        mc = f"{r['mean_ctrl']:.4f}" if isinstance(r["mean_ctrl"], float) else str(r["mean_ctrl"])
        mt = f"{r['mean_trt']:.4f}" if isinstance(r["mean_trt"], float) else str(r["mean_trt"])
        print(f"  {r['covariate']:<26} {mc:<16} {mt:<16} {smd:>6}  {pv:>6}  {icon}")
    print("  " + "─" * 80)
    print(f"  n(control)={n_ctrl:,}  n(treatment)={n_trt:,}")
    print(
        f"  SMD threshold: {SMD_THRESHOLD}  (flag if SMD > {SMD_THRESHOLD} or p < 0.05 for categoricals)"
    )
    if n_flags == 0:
        print("\n  ✅ Balance: PASS — all covariates within acceptable bounds.")
    else:
        print(f"\n  ⚠️  Balance: FAIL — {n_flags} covariate(s) flagged.")
    return n_flags == 0


# ─────────────────────────────────────────────────────────────────────────────
# LOVE PLOT
# ─────────────────────────────────────────────────────────────────────────────


def plot_love_plot(
    balance_results: Dict,
    exp_name: str = "",
    output_path: str = "love_plot.png",
) -> Optional[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available — Love plot skipped")
        return None

    cov_list = [r["covariate"] for r in balance_results.values()]
    smds = [r["smd"] if isinstance(r["smd"], float) else 0.0 for r in balance_results.values()]
    flags = [r.get("flag", False) for r in balance_results.values()]

    if not cov_list:
        return None

    fig, ax = plt.subplots(figsize=(8, max(3, len(cov_list) * 0.55)))
    colors = ["#E74C3C" if f else "#2ECC71" for f in flags]
    y_pos = list(range(len(cov_list)))

    ax.barh(y_pos, smds, color=colors, alpha=0.80, edgecolor="white", height=0.65)
    ax.axvline(
        SMD_THRESHOLD,
        color="#E74C3C",
        linestyle="--",
        lw=1.4,
        label=f"Threshold (SMD={SMD_THRESHOLD})",
        alpha=0.7,
    )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cov_list, fontsize=10)
    ax.set_xlabel("Standardised Mean Difference (SMD)", fontsize=10)
    title = f"Love Plot — Covariate Balance{' · ' + exp_name if exp_name else ''}"
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.axvline(0, color="grey", lw=0.5, alpha=0.4)
    ax.set_xlim(left=0)
    pass_patch = mpatches.Patch(color="#2ECC71", alpha=0.8, label="Balanced (SMD ≤ 0.10)")
    fail_patch = mpatches.Patch(color="#E74C3C", alpha=0.8, label="Imbalanced (SMD > 0.10)")
    ax.legend(handles=[pass_patch, fail_patch], fontsize=9, loc="lower right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close()
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# RE-RANDOMISATION
# ─────────────────────────────────────────────────────────────────────────────


def rerandomise_until_balanced(
    features_df: pd.DataFrame,
    n_per_group: int,
    n_groups: int,
    exp_name: str,
    max_iter: int = BALANCE_MAX_ITER,
    group_col: str = "group",
) -> Tuple[pd.DataFrame, Dict, bool]:
    group_names = ["control"] + [
        f"treatment_{i}" if n_groups > 2 else "treatment" for i in range(1, n_groups)
    ]
    n_total = n_per_group * n_groups
    eligible = features_df.sample(min(n_total, len(features_df)), random_state=None).reset_index(
        drop=True
    )

    for attempt in range(1, max_iter + 1):
        shuffled = eligible.sample(frac=1, random_state=attempt * 17).reset_index(drop=True)
        # Assign in round-robin order
        assignments_per = [
            len(shuffled) // n_groups + (1 if i < len(shuffled) % n_groups else 0)
            for i in range(n_groups)
        ]
        group_labels = []
        for g, cnt in zip(group_names, assignments_per):
            group_labels.extend([g] * cnt)
        shuffled[group_col] = group_labels[: len(shuffled)]
        shuffled["experiment_name"] = exp_name
        shuffled["selection_mode"] = "propensity_balanced"

        balance = run_balance_battery(shuffled, control_col=group_col)
        passed = all(not r.get("flag", False) for r in balance.values())

        if passed:
            print(f"     ✅ Balance achieved on attempt {attempt}/{max_iter}")
            return shuffled, balance, True

        n_flags = sum(1 for r in balance.values() if r.get("flag"))
        if attempt < max_iter:
            print(f"     ↩️  Attempt {attempt}: {n_flags} flag(s) — re-drawing…")

    print(f"     ⚠️  Balance not achieved after {max_iter} attempts.")
    return shuffled, balance, False


__all__ = [
    "compute_smd",
    "run_balance_battery",
    "print_balance_report",
    "plot_love_plot",
    "rerandomise_until_balanced",
    "SMD_THRESHOLD",
    "BALANCE_COVARIATES",
]

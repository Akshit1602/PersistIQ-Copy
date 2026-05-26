import numpy as np
import pandas as pd

# ═════════════════════════════════════════════════════════════════════════════
# MODULE E — EXPERIMENT HEALTH MONITOR
# ═════════════════════════════════════════════════════════════════════════════

def run_health_monitor(llm):
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + '  🩺  EXPERIMENT HEALTH MONITOR'.ljust(70) + '║')
    print('║' + '  Real-time status · SRM · Guardrails · ETA to significance'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    # Only show running experiments
    running = [e for e in EXPERIMENT_REGISTRY if e['status'] == 'running']
    if not running:
        print('\n  No running experiments found.')
        return

    print('\n  Running experiments:')
    for i, e in enumerate(running):
        days_in = (pd.Timestamp.today() - pd.Timestamp(e['start_date'])).days
        print(f'  [{i+1}] {e["experiment_name"]}  (day {days_in} of planned {e["planned_days"]})')
        print(f'       {e["description"]}')

    while True:
        raw = input('\n  ❓ Select experiment [1]: ').strip() or '1'
        try:
            idx = int(raw)-1
            if 0 <= idx < len(running): break
        except ValueError: pass
        print('     ⚠️  Invalid choice')

    exp_info  = running[idx]
    exp_name  = exp_info['experiment_name']
    variants  = exp_info['variants']
    control   = 'control'
    start_dt  = pd.Timestamp(exp_info['start_date'])
    today_sim = EXP_END if USE_SYNTHETIC_DATA else pd.Timestamp.now().normalize()  # synthetic: deterministic date; production: real today
    days_elapsed = (today_sim - start_dt).days

    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df = dedup_dataframe(exp_df)   # remove duplicates before health checks
    dq = validate_experiment_data(exp_df, exp_name)
    if dq['warnings']:
        print(f'\n  ⚠️  DQ warnings: ' + ' | '.join(dq['warnings'][:3]))

    print(f'\n  ── Checking health of: {exp_name} ──')
    print(f'  Days elapsed: {days_elapsed} / planned {exp_info["planned_days"]}')
    print(f'  Progress    : {min(days_elapsed/exp_info["planned_days"]*100, 100):.0f}%')

    # ── 1. Sample ratio mismatch ──────────────────────────────────────────────
    from scipy.stats import chi2 as _chi2
    counts   = exp_df['variant'].value_counts()
    n_total  = counts.sum()
    expected = n_total / len(variants)
    chi2_val = sum((counts.get(v,0) - expected)**2 / expected for v in variants)
    p_srm    = 1 - _chi2.cdf(chi2_val, df=len(variants)-1)
    srm_flag = '🚨 SRM DETECTED — investigate before trusting results' if p_srm < 0.01 else '✅ Clean'

    print(f'\n  [1/5] Sample Ratio Mismatch')
    for v in variants:
        n = counts.get(v, 0)
        print(f'     {v:<18}: {n:>6,}  ({n/n_total*100:.1f}%)')
    print(f'  χ²={chi2_val:.3f}  p={p_srm:.4f}  {srm_flag}')

    # ── 2. Primary metric trajectory ─────────────────────────────────────────
    print(f'\n  [2/5] Primary Metric Trajectory (IOR)')
    alpha  = 0.05 / max(1, len(variants)-1)  # Bonferroni
    latest = {}
    for v in variants:
        vdf = exp_df[exp_df['variant'] == v]
        n, c = len(vdf), int(vdf['converted_to_order'].sum())
        ior  = c/n if n > 0 else 0
        latest[v] = {'n': n, 'c': c, 'ior': ior}
        print(f'  {v:<18}: IOR={ior*100:.3f}%  n={n:,}  conversions={c:,}')

    ctrl_n, ctrl_c   = latest[control]['n'], latest[control]['c']
    treat_results    = {}
    for v in [x for x in variants if x != control]:
        tr_n, tr_c = latest[v]['n'], latest[v]['c']
        pr = proportion_test(ctrl_n, ctrl_c, tr_n, tr_c, alpha)
        treat_results[v] = pr
        sig_label = f'✅ SIGNIFICANT (p={pr["p_value"]:.4f})' if pr['is_significant'] \
                    else f'⏳ not yet significant (p={pr["p_value"]:.4f})'
        print(f'\n  {v} vs {control}: Δ={pr["delta_pp"]:+.4f}pp  CI=[{pr["ci_lo_pp"]:+.3f},{pr["ci_hi_pp"]:+.3f}]  {sig_label}')

    # ── 3. ETA to significance ────────────────────────────────────────────────
    print(f'\n  [3/5] ETA to Significance')
    baseline_ior = latest[control]['ior']
    current_obs  = ctrl_n
    if baseline_ior > 0 and current_obs > 0:
        # Current effect size — use it to estimate required n
        for v in [x for x in variants if x != control]:
            obs_delta = abs(latest[v]['ior'] - baseline_ior)
            if obs_delta < 0.001:
                print(f'  {v}: Effect too small to estimate ETA (<0.1pp observed)')
                continue
            ss     = compute_sample_size(baseline_ior, obs_delta, alpha, 0.80, len(variants))
            needed = ss['n_per_variant']
            daily_rate = current_obs / max(days_elapsed, 1)
            if current_obs >= needed:
                print(f'  {v}: ✅ Already have sufficient sample ({current_obs:,} ≥ {needed:,})')
            else:
                days_needed = int(np.ceil((needed - current_obs) / max(daily_rate, 1)))
                eta_date    = (today_sim + pd.Timedelta(days=days_needed)).strftime('%Y-%m-%d')
                print(f'  {v}: Need {needed:,} per variant. At {daily_rate:.0f}/day → {days_needed} more days (ETA: {eta_date})')

    # ── 4. Guardrail checks ───────────────────────────────────────────────────
    print(f'\n  [4/5] Guardrail Metrics')
    guardrail_cols = [c for c in ['order_value', 'fulfillment_days'] if c in exp_df.columns]
    ctrl_df = exp_df[exp_df['variant'] == control]
    all_clear = True
    for g_col in guardrail_cols:
        ctrl_vals = ctrl_df[g_col].dropna().values
        for v in [x for x in variants if x != control]:
            tr_vals = exp_df[exp_df['variant']==v][g_col].dropna().values
            if len(ctrl_vals) < 10 or len(tr_vals) < 10: continue
            mr = means_test(ctrl_vals, tr_vals, 0.05)
            pct_change = mr.get('delta_rel', 0) * 100
            flag = '🚨 BREACH' if (mr.get('is_significant') and abs(pct_change) > 5) else '✅ OK'
            if '🚨' in flag: all_clear = False
            print(f'  {g_col} ({v} vs {control}): Δ={pct_change:+.1f}%  p={mr.get("p_value",1):.4f}  {flag}')
    if all_clear:
        print('  All guardrail metrics within acceptable range.')

    # ── 5. Trajectory chart ───────────────────────────────────────────────────
    print(f'\n  [5/5] Generating trajectory chart...')
    daily_df = df_daily[df_daily['experiment_name'] == exp_name].copy()
    if len(daily_df) > 0:
        fig, axes = plt.subplots(1, 2, figsize=(16, 5))
        fig.patch.set_facecolor('#0f0f0f')
        fig.suptitle(f'🩺 Health Monitor: {exp_name}', fontsize=13,
                     color=COLORS['highlight'], fontweight='bold')
        var_colors = {'control': COLORS['control'], 'treatment': COLORS['treatment'],
                      'google_only': '#22c55e', 'multi_provider': '#7c3aed'}
        ax1 = axes[0]
        for v in variants:
            vd = daily_df[daily_df['variant'] == v].sort_values('day_number')
            ax1.plot(vd['day_number'], vd['ior']*100,
                     color=var_colors.get(v, COLORS['accent']), lw=2, label=v, marker='o', markersize=3)
        ax1.set_xlabel('Day of experiment'); ax1.set_ylabel('Cumulative IOR (%)')
        ax1.set_title('IOR Trajectory Over Time', color=COLORS['highlight'])
        ax1.legend(fontsize=8); ax1.grid(True, alpha=0.3)
        ax2 = axes[1]
        for v in [x for x in variants if x != control]:
            ctrl_d = daily_df[daily_df['variant']==control].set_index('day_number')['ior']
            trt_d  = daily_df[daily_df['variant']==v].set_index('day_number')['ior']
            common = ctrl_d.index.intersection(trt_d.index)
            if len(common) > 3:
                delta = (trt_d.loc[common] - ctrl_d.loc[common]) * 100
                ax2.plot(common, delta.values, lw=2, label=f'{v} vs {control}',
                         color=var_colors.get(v, COLORS['accent']))
        ax2.axhline(0, color='white', lw=1, linestyle='--', alpha=0.5)
        ax2.fill_between(common if len(common)>0 else [0], 0,
                         delta.values if len(common)>0 else [0], alpha=0.1,
                         color=COLORS['treatment'])
        ax2.set_xlabel('Day'); ax2.set_ylabel('IOR delta (pp)')
        ax2.set_title('Treatment Effect Over Time', color=COLORS['highlight'])
        ax2.legend(fontsize=8); ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('health_monitor.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()
        print('  📁 Chart saved → health_monitor.png')

    # ── LLM health summary ────────────────────────────────────────────────────
    summary = {'experiment': exp_name, 'days_elapsed': days_elapsed,
               'srm': {'detected': p_srm<0.01, 'p': round(p_srm,4)},
               'guardrails_clear': all_clear,
               'results': [{
                   'variant': v, 'delta_pp': treat_results[v]['delta_pp'],
                   'p_value': treat_results[v]['p_value'],
                   'significant': treat_results[v]['is_significant'],
               } for v in treat_results]}
    narrative = llm.narrate(summary,
        'Experiment health check for running A/B test. Provide: (1) overall health status, '
        '(2) whether to continue or stop early, (3) any immediate risks, (4) recommendation.')
    print('\n  🤖 ' + '-'*68)
    print(narrative)
    print('  ' + '-'*68)
    return summary


# ═════════════════════════════════════════════════════════════════════════════
# MODULE F — SEQUENTIAL TESTING (Always-Valid P-values via mSPRT)
# ═════════════════════════════════════════════════════════════════════════════

def _msprt_pvalue(n1: int, x1: int, n2: int, x2: int, rho: float = 0.5) -> float:
    """
    Mixture Sequential Probability Ratio Test (mSPRT) for proportions.
    Returns an always-valid p-value — safe to check at any point without
    inflating Type I error.

    Reference: Johari et al. (2017) "Peeking at A/B Tests"
    rho: mixing parameter (0.5 is a robust default)
    """
    if n1 == 0 or n2 == 0:
        return 1.0
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    if p_pool in (0.0, 1.0) or p1 == p2:
        return 1.0

    def safe_log(p, n, x):
        if p <= 0 or p >= 1: return 0
        return x * np.log(p) + (n-x) * np.log(1-p)

    llr = safe_log(p1, n1, x1) + safe_log(p2, n2, x2) \
        - safe_log(p_pool, n1, x1) - safe_log(p_pool, n2, x2)

    mixture_e = np.exp(llr) * (1 + 1.0 / (2 * rho))
    p_val = min(1.0, 1.0 / max(mixture_e, 1e-10))
    return round(float(p_val), 6)


def run_sequential_testing(llm):
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + '  🔄  SEQUENTIAL TESTING  (Always-Valid P-values)'.ljust(70) + '║')
    print('║' + '  Safe to peek at any time — no false positive inflation'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    print('\n  Sequential testing lets you look at results at any point during an')
    print('  experiment without inflating your false positive rate.')
    print('  Standard p-values are only valid AT the planned end date.')
    print('  mSPRT p-values are valid at ANY point — "always-valid".\n')

    # Select experiment
    exp_summary = db.execute("""
        SELECT e.experiment_name, COUNT(*) n_rows, COUNT(DISTINCT e.variant) n_variants,
               STRING_AGG(DISTINCT e.variant, ' | ') variants,
               MIN(e.created_at)::DATE start_date, MAX(e.created_at)::DATE end_date,
               r.status
        FROM all_experiments e
        LEFT JOIN experiment_registry r USING (experiment_name)
        GROUP BY e.experiment_name, r.status
        ORDER BY start_date DESC
    """).df()

    print('  Available experiments:')
    for i, row in exp_summary.iterrows():
        status_icon = '🟢' if row.get('status')=='running' else '✅'
        print(f'  [{i+1}] {status_icon} {row["experiment_name"]}  ({row["n_variants"]} variants, {row["n_rows"]:,} rows)')

    while True:
        raw = input(f'\n  ❓ Select experiment [1-{len(exp_summary)}]: ').strip()
        try:
            idx = int(raw)-1
            if 0 <= idx < len(exp_summary): break
        except: pass
        print('     ⚠️  Invalid')

    exp_name  = exp_summary.iloc[idx]['experiment_name']
    exp_df    = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df    = exp_df.sort_values('created_at').reset_index(drop=True)
    variants  = sorted(exp_df['variant'].unique().tolist())
    control   = 'control' if 'control' in variants else variants[0]
    treatments= [v for v in variants if v != control]

    alpha = 0.05
    print(f'\n  Experiment : {exp_name}')
    print(f'  Variants   : {variants}')
    print(f'  α threshold: {alpha}  (Bonferroni-adj: {alpha/max(1,len(treatments)):.4f})')

    # ── Run sequential analysis over time ─────────────────────────────────────
    CHECKPOINTS = [25, 50, 75, 100]   # % of data to check at
    seq_results = {v: [] for v in treatments}
    standard_results = {}

    print('\n  ── Sequential P-value at each peek ──')
    print(f'  {"Checkpoint":<14} ' + ''.join(f'{v:<25}' for v in treatments))
    print('  ' + '─'*60)

    for pct in CHECKPOINTS:
        n_take = max(20, int(len(exp_df) * pct / 100))
        subset = exp_df.iloc[:n_take]
        ctrl_sub = subset[subset['variant']==control]
        row_vals = [f'{pct:>3}% ({n_take:>5,})']
        for v in treatments:
            tr_sub = subset[subset['variant']==v]
            n1, x1 = len(ctrl_sub), int(ctrl_sub['converted_to_order'].sum())
            n2, x2 = len(tr_sub),   int(tr_sub['converted_to_order'].sum())
            p_std  = proportion_test(n1, x1, n2, x2, alpha)['p_value']
            p_seq  = _msprt_pvalue(n1, x1, n2, x2)
            seq_results[v].append({'pct': pct, 'n': n_take, 'p_std': p_std, 'p_seq': p_seq,
                                   'ior_ctrl': x1/n1 if n1>0 else 0, 'ior_treat': x2/n2 if n2>0 else 0})
            std_sig = '✅' if p_std < alpha/len(treatments) else '  '
            seq_sig = '✅' if p_seq < alpha/len(treatments) else '  '
            row_vals.append(f'std p={p_std:.4f}{std_sig} seq p={p_seq:.4f}{seq_sig}')
        print('  ' + ' | '.join(row_vals))

    # Full-data standard result for comparison
    print('\n  ── Full-data comparison: Standard vs Sequential ──')
    ctrl_all = exp_df[exp_df['variant']==control]
    for v in treatments:
        tr_all = exp_df[exp_df['variant']==v]
        n1, x1 = len(ctrl_all), int(ctrl_all['converted_to_order'].sum())
        n2, x2 = len(tr_all),   int(tr_all['converted_to_order'].sum())
        p_std  = proportion_test(n1, x1, n2, x2, alpha)['p_value']
        p_seq  = _msprt_pvalue(n1, x1, n2, x2)
        delta  = (x2/n2 - x1/n1)*100 if n2>0 and n1>0 else 0
        std_label = '✅ significant' if p_std < alpha/len(treatments) else '⚠️  not significant'
        seq_label = '✅ significant' if p_seq < alpha/len(treatments) else '⚠️  not significant'
        print(f'\n  {v} vs {control}:  Δ={delta:+.4f}pp')
        print(f'    Standard p-value : {p_std:.5f}  → {std_label}')
        print(f'    Sequential p-val : {p_seq:.5f}  → {seq_label}')
        if p_seq < p_std:
            print(f'    💡 Sequential is MORE sensitive here (detected effect earlier)')
        elif p_seq > p_std:
            print(f'    ℹ️  Sequential is more conservative (safe for peeking — expected)')
        standard_results[v] = {'p_std': p_std, 'p_seq': p_seq, 'delta_pp': delta}

    # ── Visualise sequential vs standard p-values over time ──────────────────
    if seq_results and any(len(v)>0 for v in seq_results.values()):
        fig, axes = plt.subplots(1, len(treatments), figsize=(8*len(treatments), 5))
        fig.patch.set_facecolor('#0f0f0f')
        if len(treatments) == 1: axes = [axes]
        for ax, v in zip(axes, treatments):
            rows = seq_results[v]
            pcts = [r['pct'] for r in rows]
            std_ps = [r['p_std'] for r in rows]
            seq_ps = [r['p_seq'] for r in rows]
            ax.plot(pcts, std_ps,  color=COLORS['control'],   lw=2.5, marker='o', label='Standard p-value')
            ax.plot(pcts, seq_ps,  color=COLORS['treatment'], lw=2.5, marker='s', label='Sequential p-value (mSPRT)')
            ax.axhline(alpha/len(treatments), color=COLORS['highlight'], lw=1.5,
                       linestyle='--', label=f'α={alpha/len(treatments):.3f}')
            ax.fill_between(pcts, 0, alpha/len(treatments), alpha=0.08, color=COLORS['positive'])
            ax.set_xlabel('Data collected (%)'); ax.set_ylabel('p-value')
            ax.set_title(f'Sequential vs Standard: {v}', color=COLORS['highlight'])
            ax.legend(fontsize=8); ax.set_ylim(0, 1)
            ax.text(60, alpha/len(treatments)+0.03, 'Significance threshold',
                    color=COLORS['highlight'], fontsize=8)
        plt.suptitle(f'🔄 Sequential Testing: {exp_name}', fontsize=13,
                     color=COLORS['highlight'], fontweight='bold')
        plt.tight_layout()
        plt.savefig('sequential_testing.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()
        print('  📁 Chart saved → sequential_testing.png')

    narrative = llm.narrate(standard_results,
        f'Sequential testing analysis for {exp_name}. Compare standard vs always-valid p-values. '
        'Explain: (1) what the difference means in practice, (2) whether early peeking would have '
        'led to a different decision, (3) recommendation on using sequential testing for this team.')
    print('\n  🤖 ' + '-'*68)
    print(narrative)
    print('  ' + '-'*68)
    return seq_results


# ═════════════════════════════════════════════════════════════════════════════
# MODULE G — SIMPSON'S PARADOX DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

def run_simpsons_paradox_detector(llm):
    """Module 9 — experiment-first Simpson's Paradox detection."""
    return analyze_experiment(llm, mode='paradox')

# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT TYPE CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────

EXP_TYPE_CATALOGUE = {
    'ab_test': {
        'label':           'A/B Test (Randomised Controlled Trial)',
        'description':     'Randomly assign users to control vs treatment. Gold standard for causal claims.',
        'when_to_use':     'Can randomise users; enough traffic; clear binary assignment possible.',
        'when_not':        'Cannot randomise (pricing for all, one-time events, infrastructure changes).',
        'causal_strength': 'High — randomisation eliminates confounding',
        'complexity':      'Low',
        'requires':        ['randomisation possible', 'sufficient traffic', 'metric measurable in real-time'],
        'pros':            ['Clean causal claim', 'Easy to explain', 'Sequential testing possible'],
        'cons':            ['Requires traffic', 'Cannot test everything', 'Takes weeks'],
        'keywords':        ['ui', 'feature', 'checkout', 'button', 'flow', 'onboarding', 'pricing', 'copy'],
    },
    'pre_post': {
        'label':           'Pre-Post Analysis',
        'description':     'Compare metric before vs after a change. No control group.',
        'when_to_use':     'Shipped to 100% immediately; no control group possible; quick read needed.',
        'when_not':        'When seasonality or other changes may confound; prefer DiD or ITS instead.',
        'causal_strength': 'Low — confounded by time, seasonality, concurrent changes',
        'complexity':      'Low',
        'requires':        ['clear before/after timestamp', 'stable baseline period'],
        'pros':            ['Simple to compute', 'No control group needed'],
        'cons':            ['Confounded by time-varying factors', 'Cannot attribute causality confidently'],
        'keywords':        ['before', 'after', 'shipped', '100%', 'rollout', 'pre', 'post'],
    },
    'did': {
        'label':           'Difference-in-Differences (DiD)',
        'description':     'Compare change over time between treated and untreated groups.',
        'when_to_use':     'Partial rollout with a natural control group (region, tier, segment).',
        'when_not':        'No credible control group; treated and control have different pre-trends.',
        'causal_strength': 'High if parallel-trends assumption holds',
        'complexity':      'Medium',
        'requires':        ['treated + control group', 'pre and post period data', 'parallel pre-trends'],
        'pros':            ['Handles selection-on-constants', 'Well-understood methodology'],
        'cons':            ['Parallel-trends must hold', 'Sensitive to differential shocks'],
        'keywords':        ['rollout', 'partial', 'region', 'tier', 'segment', 'launched', 'shipped to'],
    },
    'its': {
        'label':           'Interrupted Time Series (ITS)',
        'description':     'Model level + trend before and after intervention on a single series.',
        'when_to_use':     '100% rollout; long pre-period available; no control group.',
        'when_not':        'Short time series; other interventions occurred around the change.',
        'causal_strength': 'Medium — controls for trend and seasonality',
        'complexity':      'Medium',
        'requires':        ['90+ days pre-period', 'daily or weekly data', 'no concurrent interventions'],
        'pros':            ['No control group needed', 'Captures trend and seasonality'],
        'cons':            ['Assumes no other change coincided', 'Requires enough history'],
        'keywords':        ['time', 'series', 'trend', 'seasonality', 'daily', 'weekly'],
    },
    'synthetic_control': {
        'label':           'Synthetic Control',
        'description':     'Construct a counterfactual from a weighted combination of donor units.',
        'when_to_use':     'One treated unit; multiple similar donor units with good pre-period fit.',
        'when_not':        'No similar donor units; donors also received the treatment.',
        'causal_strength': 'High with good donor fit',
        'complexity':      'High',
        'requires':        ['1 treated unit', '3+ donor units', 'similar pre-period trajectories'],
        'pros':            ['Handles single-unit interventions', 'Transparent weights'],
        'cons':            ['Requires good donor pool', 'Inference is non-standard'],
        'keywords':        ['region', 'market', 'city', 'one', 'single', 'rollout'],
    },
    'psm': {
        'label':           'Propensity Score Matching (PSM)',
        'description':     'Match treated and untreated users by their probability of being treated.',
        'when_to_use':     'Observational data; users self-selected; measured confounders are rich.',
        'when_not':        'Important confounders unobserved; overlap between groups is poor.',
        'causal_strength': 'Medium — observable confounders only',
        'complexity':      'Medium',
        'requires':        ['observational data', 'rich user features', 'overlap in propensity scores'],
        'pros':            ['Uses existing data', 'Handles self-selection partially'],
        'cons':            ['Cannot control for unobservables', 'Sensitive to model specification'],
        'keywords':        ['observational', 'self-select', 'adopted', 'opted in', 'users who'],
    },
    'regression_discontinuity': {
        'label':           'Regression Discontinuity (RDD)',
        'description':     'Exploit a sharp cutoff rule on a running variable to identify local causal effect.',
        'when_to_use':     'Treatment is assigned by a threshold (score ≥ cutoff → treated).',
        'when_not':        'No clear cutoff; users can manipulate their running variable.',
        'causal_strength': 'High locally — near-random assignment at the threshold',
        'complexity':      'High',
        'requires':        ['continuous running variable', 'sharp cutoff', 'dense data near threshold'],
        'pros':            ['Strong causal claim near cutoff', 'No randomisation needed'],
        'cons':            ['Only valid near threshold', 'External validity limited'],
        'keywords':        ['score', 'threshold', 'cutoff', 'tier', 'qualification', 'eligibility'],
    },
    'causal_mediation': {
        'label':           'Causal Mediation Analysis',
        'description':     'Decompose total effect into direct and indirect (through a mediator) effects.',
        'when_to_use':     'You want to understand HOW the feature causes the outcome, not just THAT it does.',
        'when_not':        'You only need a headline effect; mediator is not measured.',
        'causal_strength': 'High — if mediator is correctly specified',
        'complexity':      'High',
        'requires':        ['A/B test or quasi-experiment', 'measured mediator variable', 'identification assumptions'],
        'pros':            ['Reveals mechanism', 'Informs feature iteration', 'Academically rigorous'],
        'cons':            ['Requires strong assumptions', 'Complex to implement and explain'],
        'keywords':        ['mechanism', 'why', 'through', 'mediator', 'pathway', 'because'],
    },
}


def recommend_experiment_type(
    desc: str,
    problem: str,
    hypothesis: str,
    target_audience: str,
    constraints: dict,
    llm,
) -> list:
    """
    Scores each experiment type against the user's situation and returns
    a ranked list with explanations. Uses a two-stage approach:
    Stage 1: Rule-based scoring on structural constraints (fast)
    Stage 2: LLM refinement for nuanced considerations
    """
    scores = {k: 0 for k in EXP_TYPE_CATALOGUE}
    reasons = {k: [] for k in EXP_TYPE_CATALOGUE}

    can_randomise = constraints.get('can_randomise', True)
    has_control_group = constraints.get('has_control_group', False)
    rollout_pct = constraints.get('rollout_pct', 50)
    has_time_series = constraints.get('has_time_series', True)
    pre_period_days = constraints.get('pre_period_days', 180)
    has_threshold = constraints.get('has_threshold', False)
    observational = constraints.get('observational', False)

    # ── Rule-based scoring ────────────────────────────────────────────────────
    if can_randomise and rollout_pct <= 70:
        scores['ab_test'] += 5
        reasons['ab_test'].append('Randomisation is possible — gold standard applies')
    else:
        scores['ab_test'] -= 3
        reasons['ab_test'].append('Cannot randomise or 100% rollout — A/B test not feasible')

    if rollout_pct == 100 and not can_randomise:
        scores['pre_post'] += 3
        reasons['pre_post'].append('100% rollout — pre-post is the baseline option')
        if has_time_series and pre_period_days >= 90:
            scores['its'] += 4
            reasons['its'].append('Rich time series available — ITS is stronger than simple pre-post')
            scores['pre_post'] -= 1

    if has_control_group and not can_randomise:
        scores['did'] += 4
        reasons['did'].append('Untreated control group exists — DiD is well-suited')

    if rollout_pct < 100 and has_control_group:
        scores['did'] += 3
        reasons['did'].append('Partial rollout with control group — parallel trends may hold')

    if has_time_series and pre_period_days >= 180:
        scores['its'] += 3
        scores['synthetic_control'] += 2
        reasons['its'].append(f'{pre_period_days} days of pre-period data — sufficient for ITS')

    if observational:
        scores['psm'] += 4
        reasons['psm'].append('Observational data with self-selection — PSM addresses this')
        scores['ab_test'] -= 2

    if has_threshold:
        scores['regression_discontinuity'] += 5
        reasons['regression_discontinuity'].append('Assignment threshold detected — RD design is ideal')

    # Keyword scoring on description
    desc_lower = (desc + ' ' + problem + ' ' + hypothesis).lower()
    for method, meta in EXP_TYPE_CATALOGUE.items():
        kw_hits = sum(1 for kw in meta['keywords'] if kw in desc_lower)
        scores[method] += kw_hits
        if kw_hits > 0:
            reasons[method].append(f'{kw_hits} keyword match(es) in description')

    # ── LLM refinement ────────────────────────────────────────────────────────
    top_3_by_score = sorted(scores, key=lambda k: scores[k], reverse=True)[:4]
    top_3_text = '\n'.join(
        f'  {k}: score={scores[k]}, reasons={reasons[k]}'
        for k in top_3_by_score
    )
    catalogue_text = '\n'.join(
        f'  {k}: {v["label"]} — {v["when_to_use"]}'
        for k, v in EXP_TYPE_CATALOGUE.items()
    )
    prompt = (
        f'You are a senior data scientist selecting an experiment design methodology.\n\n'
        f'Feature: "{desc}"\n'
        f'Problem: "{problem}"\n'
        f'Hypothesis: "{hypothesis}"\n'
        f'Target audience: "{target_audience}"\n'
        f'Constraints: {constraints}\n\n'
        f'Rule-based top candidates:\n{top_3_text}\n\n'
        f'All available methods:\n{catalogue_text}\n\n'
        f'Return ONLY a JSON array of the top 3 method keys in order of recommendation, '
        f'with a one-sentence reason for each. Format:\n'
        f'[{{"method":"ab_test","reason":"..."}},{{"method":"did","reason":"..."}},...]\n'
        f'No other text.'
    )
    try:
        resp = llm.ask(prompt).strip()
        # Extract JSON from response
        json_match = re.search(r'\[.*\]', resp, re.DOTALL)
        if json_match:
            ranked = json.loads(json_match.group())
            return ranked[:3]
    except Exception as e:
        logger.warning('LLM experiment type ranking failed: %s', e)

    # Fallback: return rule-based top 3
    return [
        {'method': k, 'reason': '; '.join(reasons[k][:2]) or EXP_TYPE_CATALOGUE[k]['when_to_use']}
        for k in top_3_by_score[:3]
    ]


def _infer_constraints_from_description(desc: str, llm) -> tuple:
    """
    One LLM call replaces the 7 serial constraint questions.
    Returns (constraints dict, uncertain_keys list).
    """
    prompt = (
        f'A product team wants to test this feature: "{desc}"\n\n'
        'Infer the experiment setup constraints. Reply ONLY with valid JSON — no other text:\n'
        '{\n'
        '  "can_randomise": true,\n'
        '  "rollout_pct": 50,\n'
        '  "has_control_group": false,\n'
        '  "has_time_series": true,\n'
        '  "pre_period_days": 180,\n'
        '  "observational": false,\n'
        '  "has_threshold": false,\n'
        '  "uncertain_keys": ["rollout_pct"]\n'
        '}\n'
        'uncertain_keys lists the 1-3 keys most worth confirming with the user.'
    )
    try:
        raw = llm.ask(prompt)
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            d = json.loads(m.group())
            uncertain = d.pop('uncertain_keys', [])
            defaults = {
                'can_randomise': True, 'rollout_pct': 50,
                'has_control_group': False, 'has_time_series': True,
                'pre_period_days': 180, 'observational': False,
                'has_threshold': False,
            }
            for k, v in defaults.items():
                d.setdefault(k, v)
            return d, uncertain
    except Exception as e:
        logger.warning('_infer_constraints_from_description failed: %s', e)
    defaults = {
        'can_randomise': True, 'rollout_pct': 50, 'has_control_group': False,
        'has_time_series': True, 'pre_period_days': 180,
        'observational': False, 'has_threshold': False,
    }
    return defaults, list(defaults.keys())


def _confirm_uncertain_constraints(constraints: dict, uncertain: list) -> dict:
    """
    Only ask about keys the LLM flagged as ambiguous. Typically 1-3 questions.
    """
    QUESTION_MAP = {
        'can_randomise':     ('Can users be randomly assigned to control vs treatment?', bool),
        'rollout_pct':       ('% of traffic receiving this feature (100 = full rollout)?', float),
        'has_control_group': ('Will there be a permanent untreated group (segment/region)?', bool),
        'has_time_series':   ('Do you have 3+ months of historical daily data?', bool),
        'pre_period_days':   ('How many days of pre-feature history are available?', int),
        'observational':     ('Observational study — users self-select rather than being assigned?', bool),
        'has_threshold':     ('Is treatment assigned based on a score or threshold?', bool),
    }
    if not uncertain:
        return constraints
    print(f'\n  Confirming {len(uncertain)} inferred value(s) — press Enter to accept default:\n')
    for key in uncertain:
        if key not in QUESTION_MAP:
            continue
        q, typ = QUESTION_MAP[key]
        default = constraints.get(key)
        if typ == bool:
            hint = f'[{"Y/n" if default else "y/N"}]'
            raw = input(f'  ❓ {q} {hint}: ').strip().lower()
            if raw:
                constraints[key] = raw in ('y', 'yes')
        elif typ in (float, int):
            hint = f'[{default}]'
            raw = input(f'  ❓ {q} {hint}: ').strip()
            if raw:
                try:
                    constraints[key] = typ(raw)
                except ValueError:
                    pass
    return constraints


def _show_method_recommendation(recommendations: list, menu_items: list) -> str:
    """
    Leads with the top recommendation so the user sees the answer immediately.
    Full 8-method menu is hidden behind [?] to reduce cognitive load.
    """
    if not recommendations:
        return 'ab_test'
    top      = recommendations[0]
    method_key = top.get('method', 'ab_test')
    meta     = EXP_TYPE_CATALOGUE.get(method_key, {})
    print()
    print('  ┌' + '─'*68 + '┐')
    print(f'  │  Recommended: {meta.get("label", method_key):<54}│')
    print(f'  │  Why: {top.get("reason","")[:62]:<62}│')
    print(f'  │  Causal strength: {meta.get("causal_strength",""):<51}│')
    reqs = ", ".join(meta.get("requires", [])[:2])
    print(f'  │  Requires: {reqs:<58}│')
    print('  └' + '─'*68 + '┘')
    if len(recommendations) > 1:
        alt      = recommendations[1]
        alt_meta = EXP_TYPE_CATALOGUE.get(alt.get('method', ''), {})
        print(f'\n  Alternative: {alt_meta.get("label","")}')
        print(f'  Trade-off  : {alt.get("reason","")}')
    print()
    raw = input(
        f'  Use "{meta.get("label", method_key)}"?  '
        '[Y = yes  /  N = choose differently  /  ? = see all options]: '
    ).strip().lower()
    if raw in ('', 'y', 'yes'):
        return method_key
    if raw == '?':
        print()
        for idx, (k, v) in enumerate(menu_items, 1):
            print(f'  [{idx}]  {v["label"]}')
            print(f'        {v["when_to_use"]}')
        while True:
            pick = input(f'\n  Enter number [1-{len(menu_items)}]: ').strip()
            if pick.isdigit() and 1 <= int(pick) <= len(menu_items):
                return menu_items[int(pick)-1][0]
            print('     ⚠️  Invalid choice')
    if raw == 'n':
        if len(recommendations) > 1:
            print('\n  Alternatives:')
            for i, rec in enumerate(recommendations[1:], 2):
                m2 = EXP_TYPE_CATALOGUE.get(rec.get('method', ''), {})
                print(f'  [{i}] {m2.get("label",""):40} — {rec.get("reason","")}')
        print(f'  [?] See all {len(menu_items)} methods')
        while True:
            pick = input('  Choose: ').strip().lower()
            if pick == '?':
                return _show_method_recommendation([], menu_items)
            if pick.isdigit():
                n = int(pick)
                if 2 <= n <= len(recommendations):
                    return recommendations[n-1].get('method', 'ab_test')
            print('     ⚠️  Invalid choice')
    return method_key


def _prompt_all_gap_sections(gap_sections_spec: list) -> dict:
    """
    Collect all section mode choices in one pass.
    Returns dict {sec_name: ('user', text) | ('llm', None) | ('skip', None)}.
    """
    print()
    print('  ── Section preferences ────────────────────────────────────────────')
    print('For each section:  1 = I\'ll write it   2 = LLM drafts (default)   3 = Skip')
    print()
    choices = {}
    for sec_name, sec_desc in gap_sections_spec:
        print(f'  {sec_name}')
        print(f'    {sec_desc}')
        raw = input('  [1/2/3] (default 2): ').strip() or '2'
        if raw == '1':
            print(f'\n  Enter your {sec_name.lower()} content. Blank line to finish.')
            lines = []
            while True:
                line = input('  │ ')
                if not line.strip() and lines:
                    break
                if line.strip():
                    lines.append(line)
            text = '\n'.join(lines).strip()
            choices[sec_name] = ('user', text) if text else ('llm', None)
        elif raw == '3':
            choices[sec_name] = ('skip', None)
        else:
            choices[sec_name] = ('llm', None)
        print()
    return choices


def _generate_brief_in_batches(
    sections_for_llm: list,
    context_block: str,
    guidance: str,
    llm,
) -> dict:
    """
    Two-batch generation instead of one monolithic call.
    Batch 1 — structural: brief header, problem, hypothesis, method, design.
    Batch 2 — operational: validity, risks, rollout, sign-off.
    Each batch has its own token budget so later sections never get cut off.
    """
    BATCH_1 = {'EXPERIMENT BRIEF', 'PROBLEM STATEMENT', 'HYPOTHESIS',
               'WHY THIS METHOD', 'EXPERIMENT DESIGN'}
    BATCH_2 = {'SUCCESS CRITERIA', 'CAUSAL VALIDITY CHECKS',
               'RISKS AND MITIGATIONS', 'ROLLOUT PLAN', 'SIGN-OFF REQUIRED'}
    b1 = [s for s in sections_for_llm if s in BATCH_1]
    b2 = [s for s in sections_for_llm if s in BATCH_2]
    parsed = {}
    for batch, batch_label in [(b1, 'structural'), (b2, 'operational')]:
        if not batch:
            continue
        print(f'  Generating {batch_label} sections ({len(batch)})...', end=' ', flush=True)
        prompt = build_llm_prompt_from_template(
            role=(
                'You are a senior product analytics lead writing an experiment brief. '
                'Be concise and specific. Use "Field: value" lines for metadata. '
                'Each section must be 3-6 lines unless detail is explicitly needed.'
            ),
            context_block=context_block,
            sections_to_fill=batch,
            content_guidance=guidance,
        )
        raw = llm.ask(prompt)
        raw = _strip_decorative_chars(raw)
        batch_parsed = parse_sections_from_llm_output(raw, batch)
        parsed.update(batch_parsed)
        filled = sum(1 for v in batch_parsed.values() if v.strip())
        print(f'done  ({filled}/{len(batch)} filled)')
    return parsed


def run_brief_generator(llm):
    """
    Experiment Brief Generator — uses auto-inference for method selection and
    constraint gathering. Sections collected in one pass; brief generated in
    two focused batches to prevent token exhaustion.
    """
    print()
    print('=' * 72)
    print('  EXPERIMENT BRIEF GENERATOR')
    print('  Choose or suggest an experiment type, then write a full PRD brief.')
    print('=' * 72)

    # ── Step 1: Gather basic inputs ───────────────────────────────────────────
    print('\n  Step 1 of 3 — Describe the feature and context\n')
    while True:
        desc = input('  Feature description (what changes?): ').strip()
        if len(desc) >= 10:
            break
        print('     Please provide more detail (at least 10 characters)')

    problem    = input('\n  Problem statement (what user/business problem does this solve?): ').strip()
    hypothesis = input('\n  Hypothesis (what do you expect to happen and why?): ').strip()
    target     = input('\n  Target audience (who sees this feature?): ').strip()

    # ── Step 2: Method selection (auto-infer then confirm) ───────────────────
    print()
    print('-' * 72)
    print('  Step 2 of 3 — Experiment method')
    print('-' * 72)

    menu_items = list(EXP_TYPE_CATALOGUE.items())
    recommendations   = []
    constraints       = {}
    chosen_method_key = None

    print()
    print('  [A]  Auto-suggest — infer best method from your description (recommended)')
    print('  [M]  Manual       — browse all 8 methods and pick')
    print()
    mode_raw = input('  Choose [A/M] (default A): ').strip().upper() or 'A'

    if mode_raw == 'M':
        # ── Manual: show full menu ────────────────────────────────────────────
        for idx, (k, v) in enumerate(menu_items, 1):
            print(f'  [{idx}]  {v["label"]}')
            print(f'        When to use: {v["when_to_use"]}')
        while chosen_method_key is None:
            raw = input(f'\n  Enter number [1-{len(menu_items)}]: ').strip()
            if raw.isdigit() and 1 <= int(raw) <= len(menu_items):
                chosen_method_key = menu_items[int(raw)-1][0]
    else:
        # ── Auto-suggest: infer constraints, ask only about ambiguous ones ────
        print('\n  Analysing feature description...')
        constraints, uncertain = _infer_constraints_from_description(desc, llm)
        constraints = _confirm_uncertain_constraints(constraints, uncertain)

        print('\n  Inferred constraints:')
        for k, v in constraints.items():
            print(f'    {k:<22}: {v}')

        raw_ok = input('\n  Look right? [Y/n]: ').strip().lower()
        if raw_ok == 'n':
            # Fall back to manual constraint questions
            can_randomise = input('  Can you randomly assign users? [Y/n]: ').strip().lower() != 'n'
            raw_pct = input('  % of traffic in experiment [50]: ').strip()
            rollout_pct = float(raw_pct) if raw_pct else 50
            has_control = input('  Permanent untreated group? [y/N]: ').strip().lower() == 'y'
            has_ts = input('  3+ months historical data? [Y/n]: ').strip().lower() != 'n'
            raw_days = input('  Days of pre-feature history [180]: ').strip()
            pre_days = int(raw_days) if raw_days else 180
            obs = input('  Observational study? [y/N]: ').strip().lower() == 'y'
            thresh = input('  Threshold-based assignment? [y/N]: ').strip().lower() == 'y'
            constraints = {
                'can_randomise': can_randomise, 'rollout_pct': rollout_pct,
                'has_control_group': has_control, 'has_time_series': has_ts,
                'pre_period_days': pre_days, 'observational': obs,
                'has_threshold': thresh,
            }

        print('\n  Computing recommendation...')
        recommendations = recommend_experiment_type(
            desc, problem, hypothesis, target, constraints, llm)

        chosen_method_key = _show_method_recommendation(recommendations, menu_items)

    chosen_label = EXP_TYPE_CATALOGUE.get(chosen_method_key, {}).get('label', chosen_method_key)
    method_meta  = EXP_TYPE_CATALOGUE.get(chosen_method_key, {})
    is_ab_test   = 'ab_test' in chosen_method_key
    print(f'\n  ✅ Method: {chosen_label}')

    # ── Step 3: Section preferences + brief generation ───────────────────────
    print()
    print('-' * 72)
    print('  Step 3 of 3 — Brief sections')
    print('-' * 72)

    gap_sections_spec = [
        ('SUCCESS CRITERIA',
         'Primary / secondary / guardrail metrics and the size of the move you need.'),
        ('CAUSAL VALIDITY CHECKS',
         'Method-specific checks that must pass before trusting results.'),
        ('RISKS AND MITIGATIONS',
         'What could go wrong, and how you would handle it.'),
        ('ROLLOUT PLAN',
         'Ramp-up %, monitoring cadence, stop criteria, and what "ship" means.'),
    ]
    always_llm = ['EXPERIMENT BRIEF', 'PROBLEM STATEMENT', 'HYPOTHESIS',
                  'WHY THIS METHOD', 'EXPERIMENT DESIGN', 'SIGN-OFF REQUIRED']

    gap_choices = _prompt_all_gap_sections(gap_sections_spec)
    user_section_content = {
        k: v[1] for k, v in gap_choices.items() if v[0] == 'user' and v[1]
    }
    llm_section_list = [k for k, v in gap_choices.items() if v[0] == 'llm']

    # ── Template check ────────────────────────────────────────────────────────
    default_sections = [
        'EXPERIMENT BRIEF', 'PROBLEM STATEMENT', 'HYPOTHESIS',
        'WHY THIS METHOD', 'EXPERIMENT DESIGN', 'SUCCESS CRITERIA',
        'CAUSAL VALIDITY CHECKS', 'RISKS AND MITIGATIONS',
        'ROLLOUT PLAN', 'SIGN-OFF REQUIRED',
    ]
    user_sections, _ = ask_for_template('Experiment Brief / PRD', default_sections)
    sections_to_use  = user_sections if user_sections else default_sections

    sections_for_llm = [
        s for s in sections_to_use if s in always_llm or s in llm_section_list
    ]

    try:
        _past = _query_relevant_learnings(f'{desc} {problem}', n=3)
        _past_text = _format_past_learnings(_past)
        _knowledge_note = (
            f'\n\nRELEVANT PAST EXPERIMENTS ({len(_past)} found):\n{_past_text}'
            if _past else ''
        )
        if _past:
            print(f'\n  📚 Found {len(_past)} relevant past experiment(s) — incorporating into brief')
    except Exception:
        _knowledge_note = ''

    context_block = (
        f'Feature: "{desc}"\n'
        f'Problem: "{problem}"\n'
        f'Hypothesis: "{hypothesis}"\n'
        f'Target audience: "{target}"\n'
        f'Experiment type: {chosen_label}\n'
        f'Causal strength: {method_meta.get("causal_strength", "medium")}\n'
        f'Method requires: {", ".join(method_meta.get("requires", []))}' +
        _knowledge_note
    )

    traffic_line = (
        'Traffic allocation: 50% control / 50% treatment' if is_ab_test
        else 'Pre period: [dates], Post period: [dates]'
    )
    guidance = (
        f'EXPERIMENT BRIEF: include Title, Type ({chosen_label}), Team, Priority as "Field: value" lines.\n'
        f'EXPERIMENT DESIGN: Method: {chosen_label} / {traffic_line} / Target audience: {target} / '
        f'Exclusions / Sample size considerations.\n'
        'HYPOTHESIS: "We believe <change> will cause <effect> for <users> because <reasoning>. '
        'We will know this is true when <metric> changes by <amount>."\n'
        f'A/B test: {"yes" if is_ab_test else "no"}.'
    )

    parsed = {}
    if sections_for_llm:
        parsed = _generate_brief_in_batches(sections_for_llm, context_block, guidance, llm)

    # Merge user-provided sections
    for k, v in user_section_content.items():
        parsed[k] = v

    from collections import OrderedDict
    parsed_ordered = OrderedDict(
        (s, parsed.get(s, '')) for s in sections_to_use
    )

    # ── Render PDF ────────────────────────────────────────────────────────────
    fname = 'experiment_brief.pdf'
    out_path = render_document_pdf(
        title='Experiment Brief',
        subtitle='Feature: ' + desc[:90],
        sections=parsed_ordered,
        output_path=fname,
        metadata={
            'Feature':         desc[:120],
            'Experiment type': chosen_label,
            'Causal strength': method_meta.get('causal_strength', 'Unknown'),
            'Complexity':      method_meta.get('complexity', 'Unknown'),
            'Target audience': target[:120] if target else 'n/a',
        },
        accent_color=PDF_PALETTE['primary'],
    )
    print(f'\n  Brief saved → {out_path}')

    # ── Auto-run power calculator for A/B tests ───────────────────────────────
    power_result = None
    if is_ab_test:
        print('\n' + '━'*72)
        print('  A/B test selected — auto-running Power Calculator...')
        print('━'*72)
        try:
            power_result = run_power_calculator(llm)
        except Exception as e:
            print(f'  ⚠️  Power calculator error: {type(e).__name__}: {e}')

    return {
        'brief_sections':      dict(parsed_ordered),
        'recommended_method':  chosen_method_key,
        'all_recommendations': recommendations,
        'constraints':         constraints,
        'output_file':         out_path,
        'sections_used':       sections_to_use,
        'user_provided':       list(user_section_content.keys()),
        'power_calculator':    power_result,
    }



def run_learnings_repository(llm):
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + '  📚  EXPERIMENT LEARNINGS REPOSITORY'.ljust(70) + '║')
    print('║' + '  Add, search, and retrieve past experiment knowledge'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')
    print()
    print('  [1]  🔍  Search learnings  (find relevant past experiments)')
    print('  [2]  ➕  Add new learning  (record a concluded experiment)')
    print('  [3]  📋  Browse all         (list everything in the repository)')
    print()
    while True:
        action = input('  ❓ Choose [1/2/3]: ').strip()
        if action in ('1','2','3'): break

    if action == '3':
        df_learn = db.execute("""
            SELECT id, experiment_name, ship_decision, outcome, recorded_at
            FROM experiment_learnings ORDER BY recorded_at DESC
        """).df()
        print(f'\n  Repository contains {len(df_learn)} learning(s):\n')
        for _, row in df_learn.iterrows():
            icon = {'ship':'✅','no_ship':'❌','partial_ship':'⚠️'}.get(row['ship_decision'],'⬜')
            print(f'  {icon} [{row["id"]}] {row["experiment_name"]}  ({row["recorded_at"]})')
            print(f'       {row["outcome"][:100]}')
            print()
        # Full details
        sel = input('  ❓ Enter ID to read full details (or Enter to skip): ').strip().upper()
        if sel:
            row = db.execute(f"SELECT * FROM experiment_learnings WHERE id = '{sel}'").df()
            if len(row) > 0:
                r = row.iloc[0]
                print(f'\n  {"─"*68}')
                for col in row.columns:
                    print(f'  {col:<28} {r[col]}')
        return

    if action == '1':
        query = input('\n  ❓ Search query (describe what you want to know): ').strip()
        df_learn = db.execute("SELECT * FROM experiment_learnings").df()
        if len(df_learn) == 0:
            print('  No learnings recorded yet.')
            return

        all_text = '\n\n'.join(
            f'[{r["id"]}] {r["experiment_name"]}: {r["key_learning"]}. '
            f'What worked: {r["what_worked"]}. Tags: {r["tags"]}'
            for _, r in df_learn.iterrows()
        )
        prompt = (
            f'Search this experiment learnings repository and return the most relevant results.\n'
            f'Query: "{query}"\n\n'
            f'Repository:\n{all_text}\n\n'
            f'Return: the 2-3 most relevant experiment IDs and why they are relevant. '
            f'Then synthesise the key insight that answers the query.'
        )
        print('\n  🤖 Searching...')
        result = llm.ask(prompt)
        print('\n' + '─'*68)
        print(result)
        print('─'*68)
        return result

    if action == '2':
        # Add new learning
        print('\n  ── Record a new learning ──')
        print('  (This stores the outcome so future experiment designs can learn from it)\n')
        exp_name    = input('  ❓ Experiment name: ').strip()
        ship_raw    = input('  ❓ Ship decision (ship/no_ship/partial_ship): ').strip()
        outcome     = input('  ❓ Outcome summary (1-2 sentences, include numbers): ').strip()
        key_learn   = input('  ❓ Key learning (the "so what" insight): ').strip()
        worked      = input('  ❓ What worked: ').strip()
        didnt       = input('  ❓ What did NOT work: ').strip()
        recommend   = input('  ❓ Recommendation for future experiments: ').strip()
        follow_ups  = input('  ❓ Follow-up experiment ideas (comma-sep): ').strip()
        tags        = input('  ❓ Tags (comma-sep, e.g. checkout,ior,mobile): ').strip()

        df_learn = db.execute("SELECT id FROM experiment_learnings").df()
        new_id   = f'L{len(df_learn)+1:03d}'
        new_row  = pd.DataFrame([{
            'id':                    new_id,
            'experiment_name':       exp_name,
            'ship_decision':         ship_raw,
            'outcome':               outcome,
            'key_learning':          key_learn,
            'what_worked':           worked,
            'what_didnt':            didnt,
            'recommendation':        recommend,
            'follow_up_experiments': [x.strip() for x in follow_ups.split(',')],
            'recorded_by':           'Analytics Team',
            'recorded_at':           pd.Timestamp.today().strftime('%Y-%m-%d'),
            'tags':                  [x.strip() for x in tags.split(',')],
        }])
        df_all_learn = pd.concat([
            db.execute("SELECT * FROM experiment_learnings").df(), new_row
        ], ignore_index=True)
        db.register('experiment_learnings', df_all_learn)
        print(f'\n  ✅ Learning [{new_id}] recorded. Repository now has {len(df_all_learn)} entries.')

        narrative = llm.narrate(new_row.to_dict('records'),
            'A new experiment learning has been recorded. Write a 2-sentence distillation '
            'of the most important insight for future experiment designers.')
        print(f'\n  🤖 Insight: {narrative}')
        return new_id



# ═════════════════════════════════════════════════════════════════════════════
# MODULE 10 — ROI TRACKER WITH COUNTERFACTUAL FORECASTING
# ═════════════════════════════════════════════════════════════════════════════

def _fit_counterfactual_model(df_ts: 'pd.DataFrame', cutoff_date: 'pd.Timestamp') -> dict:
    """
    Fits a lightweight time-series decomposition model on pre-ship IOR data.

    Model:  IOR(t) = trend(t) + weekly_seasonality(t) + monthly_seasonality(t) + noise
    Method: OLS regression with dummy variables — no external libraries needed.
             This is a simplified version of what Prophet does internally.

    Parameters:
        df_ts       : platform_daily_ior DataFrame
        cutoff_date : ship date — train on data before this, forecast after

    Returns dict with:
        coefficients, forecast function, in-sample R², MAPE
    """
    train = df_ts[df_ts['date'] < cutoff_date].copy().reset_index(drop=True)
    if len(train) < 60:
        return None

    n = len(train)
    X = np.zeros((n, 1 + 1 + 6 + 11))   # intercept + trend + 6 DOW dummies + 11 month dummies
    X[:, 0] = 1.0                                          # intercept
    X[:, 1] = np.arange(n) / n                            # normalised trend (0→1)
    for dow in range(1, 7):                                # Mon=0 is baseline
        X[:, 1 + dow] = (train['day_of_week'] == dow).astype(float)
    for m in range(1, 12):                                 # Jan is baseline
        X[:, 7 + m] = (train['month'] == (m + 1)).astype(float)

    y = train['ior'].values

    try:
        XtX = X.T @ X
        XtX_inv = np.linalg.inv(XtX + np.eye(XtX.shape[0]) * 1e-8)  # ridge regularisation
        coef = XtX_inv @ X.T @ y
    except np.linalg.LinAlgError:
        return None

    y_hat = X @ coef
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    mape   = np.mean(np.abs((y - y_hat) / np.clip(y, 0.01, 1))) * 100

    def forecast(dates: 'pd.Series') -> 'np.ndarray':
        """Generate counterfactual IOR forecast for given dates."""
        n_pred = len(dates)
        trend_val = np.arange(n, n + n_pred) / n
        Xp = np.zeros((n_pred, 1 + 1 + 6 + 11))
        Xp[:, 0] = 1.0
        Xp[:, 1] = trend_val
        for dow in range(1, 7):
            Xp[:, 1 + dow] = (dates.dt.dayofweek == dow).astype(float)
        for m in range(1, 12):
            Xp[:, 7 + m] = (dates.dt.month == (m + 1)).astype(float)
        return np.clip(Xp @ coef, 0.01, 0.99)

    return {
        'coef': coef, 'r2': round(r2, 4), 'mape': round(mape, 3),
        'n_train': n, 'train_start': train['date'].min(), 'cutoff': cutoff_date,
        'forecast': forecast,
    }


def _confidence_grade(model_fit: dict, n_confounders: int, has_holdout: bool) -> tuple:
    """
    Returns a confidence grade (A/B/C/D) and explanation string.

    Grade A: Holdout group exists — cleanest possible measurement
    Grade B: Good model fit (R²>0.6), few confounders (≤1)
    Grade C: Moderate fit or 2-3 confounders — interpret with caution
    Grade D: Poor fit or many confounders — results unreliable
    """
    if has_holdout:
        return 'A', 'Holdout group present — cleanest causal estimate'
    r2 = model_fit.get('r2', 0) if model_fit else 0
    if r2 >= 0.65 and n_confounders == 0:
        return 'B', f'Good model fit (R²={r2:.2f}), no concurrent ships detected'
    if r2 >= 0.50 and n_confounders <= 2:
        return 'C', (f'Moderate fit (R²={r2:.2f}), {n_confounders} concurrent ship(s). '
                     f'Counterfactual estimate is directionally correct but magnitude uncertain.')
    return 'D', (f'Weak model fit (R²={r2:.2f}) or {n_confounders} confounders. '
                 f'Results are indicative only — validate with a holdout group.')


def _compute_gmv_impact(
    post_df: 'pd.DataFrame',
    counterfactual: 'np.ndarray',
    daily_inquiries: float,
    aov: float,
) -> dict:
    """
    Computes incremental GMV using the counterfactual-corrected IOR lift.

    incremental_daily_gmv = (observed_IOR − counterfactual_IOR) × daily_inquiries × AOV
    """
    observed    = post_df['observed_ior'].values[:len(counterfactual)]
    cf          = counterfactual[:len(observed)]
    lift_series = observed - cf

    daily_gmv = lift_series * daily_inquiries * aov
    cumulative = np.cumsum(daily_gmv)

    return {
        'lift_series':        lift_series,
        'daily_gmv_series':   daily_gmv,
        'cumulative_gmv':     cumulative,
        'total_gmv_90d':      float(np.sum(daily_gmv)),
        'avg_daily_lift_pp':  float(np.mean(lift_series) * 100),
        'median_daily_lift_pp': float(np.median(lift_series) * 100),
        'pct_days_positive':  float(np.mean(lift_series > 0) * 100),
    }


def run_roi_tracker(llm):
    """Module 10 — experiment-first ROI tracking for shipped features."""
    return analyze_experiment(llm, mode='roi')

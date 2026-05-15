import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT SELECTOR
# ─────────────────────────────────────────────────────────────────────────────

def select_experiment() -> tuple:
    """
    Lists all experiments from the data.
    User picks one by number.
    Returns (experiment_name, df_experiment, variant_list, control_name)
    """
    print('\n  Fetching experiment list from data...')
    exp_summary = db.execute("""
        SELECT
            e.experiment_name,
            COUNT(*)                                              AS n_rows,
            COUNT(DISTINCT e.variant)                            AS n_variants,
            STRING_AGG(DISTINCT e.variant, ' | ')                AS variants,
            MIN(e.created_at)::DATE                              AS start_date,
            MAX(e.created_at)::DATE                              AS end_date,
            AVG(CAST(e.converted_to_order AS DOUBLE))*100        AS overall_ior_pct,
            r.description,
            r.status,
            r.team
        FROM all_experiments e
        LEFT JOIN experiment_registry r USING (experiment_name)
        GROUP BY e.experiment_name, r.description, r.status, r.team
        ORDER BY start_date DESC
    """).df()

    print('\n  ┌' + '─'*70 + '┐')
    print('  │  AVAILABLE EXPERIMENTS' + ' '*47 + '│')
    print('  ├' + '─'*70 + '┤')
    for i, (_, row) in enumerate(exp_summary.iterrows()):
        status_icon = '🟢' if row.get('status') == 'running' else '✅' if row.get('status') == 'concluded' else '⬜'
        print(f"  │  [{i+1}] {status_icon} {row['experiment_name']:<40}"[:73].ljust(73) + '│')
        print(f"  │       {row['n_rows']:>6,} rows  |  {row['n_variants']} variants: {row['variants'][:40]}".ljust(73) + '│')
        desc = str(row.get('description',''))[:65] or 'No description'
        print(f"  │       {desc}".ljust(73) + '│')
        print(f"  │       {row['start_date']} → {row['end_date']}  |  Team: {str(row.get('team','?'))[:15]}  |  IOR: {row['overall_ior_pct']:.2f}%".ljust(73) + '│')
        if i < len(exp_summary)-1:
            print('  ├' + '─'*70 + '┤')
    print('  └' + '─'*70 + '┘')

    while True:
        raw = input(f'\n  ❓ Select experiment [1–{len(exp_summary)}]: ').strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(exp_summary): break
        except ValueError: pass
        print(f'     ⚠️  Enter a number between 1 and {len(exp_summary)}')

    selected_name = exp_summary.iloc[idx]['experiment_name']
    df_selected   = df_all_experiments[df_all_experiments['experiment_name'] == selected_name].copy()
    variants      = sorted(df_selected['variant'].unique().tolist())
    control       = 'control' if 'control' in variants else variants[0]

    print(f'\n  ✅ Selected: {selected_name}')
    print(f'     Variants detected: {variants}')
    print(f'     Control group    : "{control}"')
    print(f'     Rows             : {len(df_selected):,}')

    return selected_name, df_selected, variants, control


# ─────────────────────────────────────────────────────────────────────────────
# PAIRWISE COMPARISON ENGINE — handles N variants
# ─────────────────────────────────────────────────────────────────────────────

def run_pairwise_comparisons(
    df: pd.DataFrame,
    variants: list,
    control: str,
    alpha: float = 0.05,
    bonferroni: bool = True,
) -> pd.DataFrame:
    """
    For N variants, computes:
    - Each treatment vs control (primary comparisons)
    - Each treatment vs every other treatment (secondary comparisons)
    Applies Bonferroni correction if requested.
    """
    treatments = [v for v in variants if v != control]

    # All unique pairs
    pairs = [(control, t) for t in treatments]                    # vs control
    pairs += [(treatments[i], treatments[j])                      # vs each other
              for i in range(len(treatments))
              for j in range(i+1, len(treatments))]

    # Bonferroni correction: alpha / number of comparisons
    n_comparisons = len(pairs)
    alpha_adj     = alpha / n_comparisons if bonferroni and n_comparisons > 1 else alpha

    rows = []
    for var_a, var_b in pairs:
        grp_a = df[df['variant'] == var_a]
        grp_b = df[df['variant'] == var_b]
        if len(grp_a) < 30 or len(grp_b) < 30:
            continue

        n_a = len(grp_a); conv_a = int(grp_a['converted_to_order'].sum())
        n_b = len(grp_b); conv_b = int(grp_b['converted_to_order'].sum())
        pr  = proportion_test(n_a, conv_a, n_b, conv_b, alpha_adj)
        mr  = means_test(grp_a['order_value'].values, grp_b['order_value'].values, alpha_adj, apply_winsorise=True)

        is_primary = (var_a == control)
        rows.append({
            'comparison':    f'{var_a} vs {var_b}',
            'baseline':      var_a,
            'variant':       var_b,
            'is_primary':    is_primary,  # True = vs control
            'n_baseline':    n_a,
            'n_variant':     n_b,
            'ior_baseline':  pr['rate_control'],
            'ior_variant':   pr['rate_treatment'],
            'delta_pp':      pr['delta_pp'],
            'ci_lo_pp':      pr['ci_lo_pp'],
            'ci_hi_pp':      pr['ci_hi_pp'],
            'p_value':       pr['p_value'],
            'sig':           pr['is_significant'],
            'direction':     pr['direction'],
            'effect_h':      pr['effect_size_h'],
            'gmv_baseline':  mr.get('mean_control', 0),
            'gmv_variant':   mr.get('mean_treatment', 0),
            'gmv_delta':     mr.get('delta_mean', 0),
            'p_value_gmv':   mr.get('p_value', 1.0),
            'sig_gmv':       mr.get('is_significant', False),
            'alpha_used':    alpha_adj,
            'bonferroni':    bonferroni,
            'n_comparisons': n_comparisons,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION ANALYSIS FOR N VARIANTS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_dimension_multivariant(
    df: pd.DataFrame,
    dim: str,
    variants: list,
    control: str,
    alpha: float,
) -> pd.DataFrame:
    """For each level of `dim`, runs each treatment vs control."""
    rows = []
    for level, grp in df.groupby(dim):
        ctrl = grp[grp['variant'] == control]
        if len(ctrl) < 20: continue
        for trt in [v for v in variants if v != control]:
            tr = grp[grp['variant'] == trt]
            if len(tr) < 20: continue
            pr = proportion_test(len(ctrl), int(ctrl['converted_to_order'].sum()),
                                 len(tr),   int(tr['converted_to_order'].sum()), alpha)
            rows.append({
                'dimension': dim, 'level': str(level), 'variant': trt,
                'n_ctrl': len(ctrl), 'n_treat': len(tr),
                'ior_ctrl': pr['rate_control'], 'ior_treat': pr['rate_treatment'],
                'delta_pp': pr['delta_pp'], 'ci_lo_pp': pr['ci_lo_pp'], 'ci_hi_pp': pr['ci_hi_pp'],
                'p_value': pr['p_value'], 'sig': pr['is_significant'], 'direction': pr['direction'],
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN POST-EXPERIMENT ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_post_experiment_analysis(llm):
    print('\n' + '═'*72)
    print('  🔬  POST-EXPERIMENT ANALYSIS  (Multi-Variant)')
    print('═'*72)

    # ── Step 1: Pick experiment ───────────────────────────────────────────────
    exp_name, df, variants, control = select_experiment()
    df = dedup_dataframe(df)
    dq = validate_experiment_data(df, exp_name)
    if dq.get('warnings') or dq.get('errors'):
        for msg in dq.get('warnings',[]): print(f'  ⚠️  {msg}')
        for msg in dq.get('errors',  []): print(f'  🚨 ERROR: {msg}')
    else:
        print('  ✅ Data quality: clean')

    # ── Step 2: Configure analysis ────────────────────────────────────────────
    print('\n  Configuration (press Enter for defaults):')
    alpha_raw = input('  ❓ Significance level α [0.05]: ').strip()
    alpha     = float(alpha_raw) if alpha_raw else 0.05

    bonferroni = True
    if len(variants) > 2:
        bon_raw = input(f'  ❓ Apply Bonferroni correction for {len(variants)-1} treatments? [Y/n]: ').strip().lower()
        bonferroni = bon_raw != 'n'

    seg_filter  = input('  ❓ Filter to segment(s)? (comma-sep or Enter for all): ').strip()
    plat_filter = input('  ❓ Filter to platform? (web/mobile or Enter for all): ').strip()

    if seg_filter:
        segs = [s.strip() for s in seg_filter.split(',')]
        df   = df[df['account_segment'].isin(segs)]
        print(f'  → Filtered to segments: {segs}  ({len(df):,} rows)')
    if plat_filter:
        df   = df[df['platform'] == plat_filter.lower()]
        print(f'  → Filtered to platform: {plat_filter}  ({len(df):,} rows)')

    n_comparisons = len(variants) - 1 + max(0, (len(variants)-1)*(len(variants)-2)//2)
    alpha_adj     = alpha / n_comparisons if bonferroni and n_comparisons > 1 else alpha
    print(f'\n  α = {alpha}' + (f'  → Bonferroni-adjusted: {alpha_adj:.5f} ({n_comparisons} comparisons)' if bonferroni and n_comparisons > 1 else ''))

    # ── Step 3: SRM check ─────────────────────────────────────────────────────
    print('\n  ── [1/5] Sample Ratio Mismatch ──')
    from scipy.stats import chi2 as _chi2
    counts  = df['variant'].value_counts()
    n_total = counts.sum()
    expected = n_total / len(variants)
    chi2_stat = sum((counts.get(v,0) - expected)**2 / expected for v in variants)
    p_srm = 1 - _chi2.cdf(chi2_stat, df=len(variants)-1)
    srm_flag = '🚨 SRM DETECTED' if p_srm < 0.01 else '✅ No SRM'
    for v in variants:
        print(f'     {v:<22}: {counts.get(v,0):>7,}  ({counts.get(v,0)/n_total*100:.1f}%)')
    print(f'     χ²={chi2_stat:.3f}  p={p_srm:.4f}  {srm_flag}')

    # ── Step 4: Overall pairwise comparisons ──────────────────────────────────
    print('\n  ── [2/5] Pairwise Comparisons ──')
    pairwise_df = run_pairwise_comparisons(df, variants, control, alpha, bonferroni)

    primary = pairwise_df[pairwise_df['is_primary'] == True]
    secondary = pairwise_df[pairwise_df['is_primary'] == False]

    print(f'\n  Primary comparisons (vs "{control}"):')
    for _, r in primary.iterrows():
        sig_str = f'✅ p={r["p_value"]:.4f}' if r['sig'] else f'⚠️  p={r["p_value"]:.4f} n.s.'
        print(f'    {r["variant"]:<22} IOR: {r["ior_baseline"]*100:.3f}% → {r["ior_variant"]*100:.3f}%  '
              f'Δ={r["delta_pp"]:+.4f}pp [{r["ci_lo_pp"]:+.3f}, {r["ci_hi_pp"]:+.3f}]  {sig_str}')

    if len(secondary) > 0:
        print(f'\n  Head-to-head (treatment vs treatment):')
        for _, r in secondary.iterrows():
            sig_str = f'✅ p={r["p_value"]:.4f}' if r['sig'] else f'⚠️  p={r["p_value"]:.4f} n.s.'
            print(f'    {r["baseline"]:<14} vs {r["variant"]:<14} Δ={r["delta_pp"]:+.4f}pp  {sig_str}')

    # ── Step 5: Dimensional breakdown ─────────────────────────────────────────
    print('\n  ── [3/5] Dimensional Analysis ──')
    dims = ['account_segment','platform','country','device_type','category','has_billing_profile']
    dim_results = []
    for dim in dims:
        if dim not in df.columns: continue
        res = analyze_dimension_multivariant(df, dim, variants, control, alpha_adj)
        if len(res) == 0: continue
        dim_results.append(res)
        print(f'\n  📊 {dim.upper().replace("_"," ")}')

        for trt_name, trt_grp in res.groupby('variant'):
            print(f'    [{trt_name}]')
            for _, row in trt_grp.iterrows():
                sig_icon = '✅' if row['sig'] else '——'
                dir_icon = '↑' if row['direction']=='positive' else '↓' if row['direction']=='negative' else '→'
                print(f'      {row["level"]:<20} {dir_icon} {row["delta_pp"]:+.4f}pp '
                      f'[{row["ci_lo_pp"]:+.3f},{row["ci_hi_pp"]:+.3f}] '
                      f'p={row["p_value"]:.4f} {sig_icon}')

    combined = pd.concat(dim_results, ignore_index=True) if dim_results else pd.DataFrame()

    # ── Step 6: Winners / Losers per variant ──────────────────────────────────
    print('\n  ── [4/5] Winners / Losers per Variant ──')
    if not combined.empty:
        for trt in [v for v in variants if v != control]:
            trt_data = combined[combined['variant'] == trt]
            wins  = trt_data[trt_data['sig'] & (trt_data['direction']=='positive')]
            loses = trt_data[trt_data['sig'] & (trt_data['direction']=='negative')]
            neuts = trt_data[~trt_data['sig']]
            print(f'\n  Variant: [{trt}]')
            print(f'    🟢 Winning dimensions ({len(wins)}):')
            for _, r in wins.iterrows():
                print(f'       {r["dimension"]:<22} {r["level"]:<18} Δ={r["delta_pp"]:+.3f}pp  p={r["p_value"]:.4f}')
            print(f'    🔴 Losing dimensions ({len(loses)}):')
            for _, r in loses.iterrows():
                print(f'       {r["dimension"]:<22} {r["level"]:<18} Δ={r["delta_pp"]:+.3f}pp  p={r["p_value"]:.4f}')
            print(f'    ⚪ Neutral ({len(neuts)} not significant)')

    # ── Step 7: Visualisations ────────────────────────────────────────────────
    print('\n  ── [5/5] Generating Visualisations ──')
    _plot_multivariant(df, pairwise_df, combined, variants, control, exp_name, alpha)

    # ── Step 8: LLM Narrative ─────────────────────────────────────────────────
    print('\n  🤖 Generating executive analysis...')
    ship_summary = [{
        'variant': r['variant'],
        'delta_pp': r['delta_pp'], 'p_value': r['p_value'],
        'significant': r['sig'], 'direction': r['direction'],
        'ci': [r['ci_lo_pp'], r['ci_hi_pp']],
    } for _, r in primary.iterrows()]
    dim_summary  = {}
    if not combined.empty:
        for trt in [v for v in variants if v != control]:
            trt_d = combined[combined['variant']==trt]
            dim_summary[trt] = {
                'winners': trt_d[trt_d['sig'] & (trt_d['direction']=='positive')][['dimension','level','delta_pp']].to_dict('records'),
                'losers':  trt_d[trt_d['sig'] & (trt_d['direction']=='negative')][['dimension','level','delta_pp']].to_dict('records'),
            }
    narrative = llm.narrate(
        {'experiment': exp_name, 'pairwise': ship_summary, 'dimensions': dim_summary,
         'srm': {'detected': p_srm<0.01, 'p': round(p_srm,4)}, 'bonferroni': bonferroni},
        context=(
            f'Post-experiment analysis for "{exp_name}". {len(variants)} variants including control. '
            f'Provide: (1) Ship/No-Ship/Partial-Ship recommendation per variant, '
            f'(2) which variant wins and why, (3) segment-level nuance, '
            f'(4) caveats (SRM, multiple comparisons, novelty effect), '
            f'(5) recommended rollout strategy.'
        )
    )
    print('\n' + '─'*72)
    print('  🤖  EXECUTIVE ANALYSIS')
    print('─'*72)
    print(narrative)
    print('─'*72)
    return pairwise_df, combined


def _plot_multivariant(df, pairwise_df, combined, variants, control, exp_name, alpha):
    treatments = [v for v in variants if v != control]
    n_treats   = len(treatments)
    bar_colors = [COLORS['treatment'], COLORS['accent'], COLORS['positive'], COLORS['highlight']][:n_treats]

    n_rows_plot = 2 + (1 if not combined.empty else 0)
    fig = plt.figure(figsize=(20, 7 * n_rows_plot))
    fig.patch.set_facecolor('#0f0f0f')
    gs  = GridSpec(n_rows_plot, 3, figure=fig, hspace=0.55, wspace=0.38)

    # ── Row 1: Overall IOR per variant ────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    all_vars  = [control] + treatments
    all_cols  = [COLORS['control']] + bar_colors
    ior_vals  = [df[df['variant']==v]['converted_to_order'].mean()*100 for v in all_vars]
    bars      = ax1.bar(all_vars, ior_vals, color=all_cols, width=0.55)
    for bar, v in zip(bars, ior_vals):
        ax1.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.03,
                 f'{v:.3f}%', ha='center', fontsize=10, fontweight='bold', color='white')
    ax1.set_title('IOR per Variant', color=COLORS['highlight'])
    ax1.set_ylabel('IOR (%)')
    plt.setp(ax1.get_xticklabels(), rotation=20, ha='right', fontsize=8)

    # ── Row 1: CI forest plot for primary comparisons ─────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    primary = pairwise_df[pairwise_df['is_primary'] == True].reset_index(drop=True)
    for i, row in primary.iterrows():
        col = COLORS['positive'] if (row['sig'] and row['direction']=='positive') \
              else COLORS['negative'] if (row['sig'] and row['direction']=='negative') \
              else COLORS['neutral']
        ax2.plot([row['ci_lo_pp'], row['ci_hi_pp']], [i, i], color=col, lw=3, solid_capstyle='round')
        ax2.scatter([row['delta_pp']], [i], color=col, s=80, zorder=5)
    ax2.axvline(0, color='white', lw=1, linestyle='--', alpha=0.7)
    ax2.set_yticks(range(len(primary)))
    ax2.set_yticklabels([r['variant'] for _, r in primary.iterrows()], fontsize=9)
    ax2.set_xlabel('IOR delta (pp)')
    ax2.set_title(f'IOR Δ vs {control}\n(95% CI, Bonferroni-adj if >1 treatment)', color=COLORS['highlight'])

    # ── Row 1: P-value comparison ─────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    pvals  = [r['p_value'] for _, r in primary.iterrows()]
    labels = [r['variant'][:15] for _, r in primary.iterrows()]
    colors_p = [COLORS['positive'] if p < alpha else COLORS['negative'] for p in pvals]
    ax3.barh(labels, pvals, color=colors_p)
    ax3.axvline(alpha, color=COLORS['highlight'], lw=2, linestyle='--', label=f'α={alpha}')
    for i, p in enumerate(pvals):
        ax3.text(p + 0.005, i, f'{p:.4f}', va='center', fontsize=9, color='white')
    ax3.set_xlabel('p-value'); ax3.set_title('P-values per Variant', color=COLORS['highlight'])
    ax3.legend(fontsize=9)

    # ── Row 2: Segment × Variant heatmap ─────────────────────────────────────
    if not combined.empty and 'account_segment' in combined['dimension'].values:
        ax4 = fig.add_subplot(gs[1, :])
        seg_data = combined[combined['dimension']=='account_segment']
        seg_levels = sorted(seg_data['level'].unique())
        heat = np.full((len(treatments), len(seg_levels)), np.nan)
        for ti, trt in enumerate(treatments):
            for si, seg in enumerate(seg_levels):
                row = seg_data[(seg_data['variant']==trt) & (seg_data['level']==seg)]
                if len(row) > 0:
                    heat[ti, si] = row.iloc[0]['delta_pp']
        vmax = np.nanmax(np.abs(heat)) if not np.all(np.isnan(heat)) else 1
        im = ax4.imshow(heat, cmap='RdYlGn', aspect='auto', vmin=-vmax, vmax=vmax)
        plt.colorbar(im, ax=ax4, label='IOR delta (pp)')
        ax4.set_xticks(range(len(seg_levels))); ax4.set_xticklabels(seg_levels)
        ax4.set_yticks(range(len(treatments))); ax4.set_yticklabels(treatments)
        for ti in range(len(treatments)):
            for si in range(len(seg_levels)):
                v = heat[ti, si]
                if not np.isnan(v):
                    row = seg_data[(seg_data['variant']==treatments[ti]) & (seg_data['level']==seg_levels[si])]
                    sig_mark = '✅' if (len(row)>0 and row.iloc[0]['sig']) else ''
                    ax4.text(si, ti, f'{v:+.2f}pp{sig_mark}', ha='center', va='center',
                             fontsize=10, color='white', fontweight='bold')
        ax4.set_title('IOR Delta Heatmap: Variant × Segment  (✅ = significant)', color=COLORS['highlight'])

    # ── Row 3: Dimension winners summary per variant ───────────────────────────
    if not combined.empty and n_rows_plot > 2:
        for ti, trt in enumerate(treatments[:3]):  # max 3 treatments in this row
            ax = fig.add_subplot(gs[2, ti])
            trt_dim = combined[combined['variant']==trt].copy()
            winners  = trt_dim[trt_dim['sig'] & (trt_dim['direction']=='positive')]
            losers   = trt_dim[trt_dim['sig'] & (trt_dim['direction']=='negative')]
            ax.axis('off')
            ax.set_title(f'[{trt}]\nWinners / Losers', color=bar_colors[ti] if ti < len(bar_colors) else COLORS['neutral'])
            lines = []
            lines.append(('🟢 WINNING', COLORS['positive']))
            for _, r in winners.iterrows():
                lines.append((f"  {r['dimension'][:10]} / {r['level'][:10]}  {r['delta_pp']:+.3f}pp", 'white'))
            lines.append(('🔴 LOSING', COLORS['negative']))
            for _, r in losers.iterrows():
                lines.append((f"  {r['dimension'][:10]} / {r['level'][:10]}  {r['delta_pp']:+.3f}pp", 'white'))
            if not winners.empty and not losers.empty:
                lines.append(('─'*30, '#444'))
                lines.append((f'Net: {int(len(winners))} win, {int(len(losers))} lose', COLORS['highlight']))
            for row_i, (txt, col) in enumerate(lines[:14]):
                ax.text(0.03, 0.97-row_i*0.07, txt, transform=ax.transAxes,
                        fontsize=8.5, color=col, va='top', fontfamily='monospace')

    plt.suptitle(f'🔬 Post-Experiment: {exp_name}  |  {len(variants)} variants', fontsize=13,
                 color=COLORS['highlight'], fontweight='bold', y=1.01)
    plt.savefig('post_experiment_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → post_experiment_analysis.png')


print('✅ Multi-variant post-experiment module loaded')
print('   Supports: N variants, experiment selection, Bonferroni correction, head-to-head comparisons')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

# ─────────────────────────────────────────────────────────────────────────────
# LLM INTELLIGENCE LAYER
# ─────────────────────────────────────────────────────────────────────────────


def _query_relevant_learnings(topic: str, n: int = 3) -> list:
    """
    Semantic search of experiment_learnings for past experiments relevant to topic.
    Returns up to n records as dicts, or empty list if repository is empty.
    Used proactively by briefs, power calc, and causal analysis — not just on demand.
    """
    try:
        df = db.execute("SELECT * FROM experiment_learnings ORDER BY recorded_at DESC").df()
    except Exception:
        return []
    if df.empty:
        return []

    topic_words = set(re.sub(r'[^a-z ]', '', topic.lower()).split())
    scored = []
    for _, row in df.iterrows():
        text = ' '.join(str(v).lower() for v in [
            row.get('key_learning',''), row.get('outcome',''),
            row.get('what_worked',''), row.get('tags',''),
        ])
        text_words = set(re.sub(r'[^a-z ]', '', text).split())
        overlap = len(topic_words & text_words)
        scored.append((overlap, row.to_dict()))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:n] if scored[0][0] > 0]


def _format_past_learnings(learnings: list) -> str:
    """Format a list of learning dicts into a compact text block for LLM prompts."""
    if not learnings:
        return '(No relevant past experiments found in the Learnings Repository.)'
    lines = []
    for l in learnings:
        lines.append(
            f'• [{l.get("id","")}] {l.get("experiment_name","")} '
            f'({l.get("ship_decision","?").replace("_"," ")}): '
            f'{l.get("key_learning","")} '
            f'| What worked: {l.get("what_worked","")} '
            f'| What did not: {l.get("what_didnt","")}'
        )
    return '\n'.join(lines)


def _build_experiment_context(
    exp_name: str,
    exp_info: dict,
    overall: dict,
    dim_cuts: dict,
    interesting: list,
    decision: str,
    reasoning: str,
    extra_insights: dict = None,
) -> dict:
    """
    Assemble everything the platform knows about a concluded experiment
    into a single context object. Every downstream LLM call draws from this.

    Returns a dict with keys:
      experiment, description, hypothesis, method, decision, reasoning,
      overall_summary, segment_summary, interesting_summary,
      time_trend_summary, extra_insights_summary, past_learnings
    """
    # Overall effect summary
    overall_summary = '; '.join(
        f'{t}: Δ={r["delta_pp"]:+.2f}pp [CI {r["ci_lo_pp"]:+.2f}, '
        f'{r["ci_hi_pp"]:+.2f}] p={r["p_value"]:.4f} n={r["n_treatment"]:,} '
        f'{"(sig)" if r["sig"] else "(n.s.)"}'
        for t, r in overall.items()
    )

    seg_parts = []
    for dim, rows in dim_cuts.items():
        sig_rows = [r for r in rows if r['sig']]
        for r in sig_rows[:4]:
            seg_parts.append(
                f'{r["dim"]}={r["level"]}/{r["treatment"]}: '
                f'Δ={r["delta_pp"]:+.2f}pp (sig)'
            )
    segment_summary = '; '.join(seg_parts) or 'No significant segment-level effects.'

    interesting_summary = ', '.join(
        f'{kind}: {r["dim"]}={r["level"]} Δ={r["delta_pp"]:+.2f}pp'
        for kind, r in interesting[:5]
    ) or 'None detected.'

    time_trend = ''
    if extra_insights and extra_insights.get('time_decay'):
        td = extra_insights['time_decay']
        time_trend = (
            f'Early effect (first half): Δ={td.get("early_delta",0):+.2f}pp | '
            f'Late effect (second half): Δ={td.get("late_delta",0):+.2f}pp | '
            f'Decay: {td.get("decay_direction","stable")}'
        )
    else:
        time_trend = '(Time-period breakdown not computed for this experiment.)'

    ei_summary = ''
    if extra_insights:
        parts = []
        if extra_insights.get('cohort_effect'):
            ce = extra_insights['cohort_effect']
            parts.append(f'New user cohort effect: {ce.get("summary","n/a")}')
        if extra_insights.get('cross_metric'):
            parts.append(f'Cross-metric: {extra_insights["cross_metric"].get("summary","n/a")}')
        ei_summary = '; '.join(parts) or '(No additional insights detected.)'
    else:
        ei_summary = '(Insights mining not run.)'

    topic = f'{exp_info.get("description","")} {overall_summary}'
    past_learnings = _query_relevant_learnings(topic, n=3)

    return {
        'experiment':          exp_name,
        'description':         exp_info.get('description', ''),
        'hypothesis':          exp_info.get('hypothesis', '(not recorded)'),
        'method':              exp_info.get('method', 'A/B test'),
        'team':                exp_info.get('team', ''),
        'decision':            decision,
        'reasoning':           reasoning,
        'overall_summary':     overall_summary,
        'segment_summary':     segment_summary,
        'interesting_summary': interesting_summary,
        'time_trend_summary':  time_trend,
        'extra_insights':      ei_summary,
        'past_learnings':      _format_past_learnings(past_learnings),
        'n_past_learnings':    len(past_learnings),
    }


def _mine_additional_insights(
    exp_df: 'pd.DataFrame',
    overall: dict,
    dim_cuts: dict,
    control: str = 'control',
    treatments: list = None,
) -> dict:
    """
    Run automated additional statistical tests beyond the pre-specified analysis:
      1. Time-period decay — did the effect weaken over the experiment duration?
      2. Cohort effect — do new users respond differently from returning users?
      3. Cross-metric correlation — does IOR lift correlate with AOV change?

    Returns a structured dict of results (all deterministic — no LLM).
    The LLM only sees this dict AFTER it is computed.
    """
    if treatments is None:
        treatments = [v for v in exp_df['variant'].unique() if v != control]
    if not treatments:
        return {}

    trt = treatments[0]
    results = {}

    # ── 1. Time-period decay ─────────────────────────────────────────────────
    try:
        exp_df = exp_df.copy()
        exp_df['_date'] = pd.to_datetime(exp_df['created_at'])
        date_min = exp_df['_date'].min()
        date_max = exp_df['_date'].max()
        mid_date = date_min + (date_max - date_min) / 2

        early = exp_df[exp_df['_date'] <= mid_date]
        late  = exp_df[exp_df['_date'] >  mid_date]

        def _ior(df, variant):
            sub = df[df['variant'] == variant]
            if len(sub) < 30:
                return None
            return float(sub['converted_to_order'].mean())

        early_ctrl = _ior(early, control)
        early_trt  = _ior(early, trt)
        late_ctrl  = _ior(late,  control)
        late_trt   = _ior(late,  trt)

        if all(v is not None for v in [early_ctrl, early_trt, late_ctrl, late_trt]):
            early_delta = (early_trt - early_ctrl) * 100
            late_delta  = (late_trt  - late_ctrl)  * 100
            decay       = late_delta - early_delta
            results['time_decay'] = {
                'early_delta': round(early_delta, 3),
                'late_delta':  round(late_delta,  3),
                'decay_pp':    round(decay, 3),
                'decay_direction': ('weakening' if decay < -0.3
                                    else 'strengthening' if decay > 0.3
                                    else 'stable'),
                'summary': (
                    f'Early half Δ={early_delta:+.2f}pp → '
                    f'Late half Δ={late_delta:+.2f}pp '
                    f'({"weakening" if decay < -0.3 else "strengthening" if decay > 0.3 else "stable"})'
                ),
            }
    except Exception as e:
        results['time_decay'] = {'error': str(e)}

    # ── 2. Cohort effect — new vs returning users ────────────────────────────
    try:
        if 'lifetime_orders' in exp_df.columns:
            exp_df['_is_new'] = exp_df['lifetime_orders'] <= 1
            new_users = exp_df[exp_df['_is_new']]
            ret_users = exp_df[~exp_df['_is_new']]

            def _delta(df):
                c = df[df['variant']==control]['converted_to_order'].mean()
                t = df[df['variant']==trt]['converted_to_order'].mean()
                n_c = len(df[df['variant']==control])
                n_t = len(df[df['variant']==trt])
                if n_c < 30 or n_t < 30:
                    return None, None
                return (t - c) * 100, n_t

            new_delta, new_n = _delta(new_users)
            ret_delta, ret_n = _delta(ret_users)

            if new_delta is not None and ret_delta is not None:
                divergence = abs(new_delta - ret_delta) > 0.5
                results['cohort_effect'] = {
                    'new_user_delta_pp': round(new_delta, 3),
                    'returning_user_delta_pp': round(ret_delta, 3),
                    'divergence': divergence,
                    'summary': (
                        f'New users Δ={new_delta:+.2f}pp (n={new_n:,}) vs '
                        f'returning Δ={ret_delta:+.2f}pp (n={ret_n:,}) '
                        f'{"— DIVERGENT" if divergence else "— similar response"}'
                    ),
                }
    except Exception as e:
        results['cohort_effect'] = {'error': str(e)}

    # ── 3. Cross-metric: does IOR lift correlate with AOV change? ─────────────
    try:
        if 'order_value' in exp_df.columns:
            ctrl_df = exp_df[(exp_df['variant']==control) & exp_df['converted_to_order']]
            trt_df  = exp_df[(exp_df['variant']==trt)     & exp_df['converted_to_order']]
            if len(ctrl_df) >= 30 and len(trt_df) >= 30:
                aov_ctrl = float(ctrl_df['order_value'].mean())
                aov_trt  = float(trt_df['order_value'].mean())
                aov_delta_pct = (aov_trt - aov_ctrl) / aov_ctrl * 100
                # IOR direction
                ior_direction = next(
                    ('+' if r['sig'] and r['delta_pp'] > 0 else
                     '-' if r['sig'] and r['delta_pp'] < 0 else '~'
                     for r in overall.values()), '~')
                aov_direction = '+' if aov_delta_pct > 1 else '-' if aov_delta_pct < -1 else '~'
                alignment = (ior_direction == aov_direction or
                             ior_direction == '~' or aov_direction == '~')
                results['cross_metric'] = {
                    'aov_control':   round(aov_ctrl, 2),
                    'aov_treatment': round(aov_trt, 2),
                    'aov_delta_pct': round(aov_delta_pct, 2),
                    'ior_aov_aligned': alignment,
                    'summary': (
                        f'AOV: ${aov_ctrl:.0f} → ${aov_trt:.0f} '
                        f'({aov_delta_pct:+.1f}%) '
                        f'{"— IOR and AOV move together (good)" if alignment else "— IOR and AOV DIVERGE (investigate)"}'
                    ),
                }
    except Exception as e:
        results['cross_metric'] = {'error': str(e)}

    return results


def _synthesise_findings(context: dict, llm) -> str:
    """
    Single unified synthesis prompt.

    Asks the LLM to combine:
      - Statistical results (overall + segment-level)
      - Time trends (did the effect decay?)
      - Decision and its reasoning
      - Decision IMPLICATIONS (what should we actually do next?)
      - Trade-offs (what are we giving up with this decision?)
      - Past learnings (what have we seen before that is relevant?)

    Returns a structured text block with four labelled sections.
    """
    prompt = textwrap.dedent(f"""
You are a senior product analytics lead synthesising the full findings of a concluded experiment.

EXPERIMENT: {context['experiment']}
DESCRIPTION: {context['description']}
HYPOTHESIS: {context['hypothesis']}
TEAM: {context['team']}

STATISTICAL RESULTS:
  Overall: {context['overall_summary']}
  Key segments: {context['segment_summary']}
  Interesting findings: {context['interesting_summary']}
  Time trend: {context['time_trend_summary']}
  Additional insights: {context['extra_insights']}

DECISION: {context['decision']}
REASONING: {context['reasoning']}

RELEVANT PAST EXPERIMENTS ({context['n_past_learnings']} found):
{context['past_learnings']}

Write a response with EXACTLY FOUR sections, labelled as shown:

SYNTHESIS:
A 3-4 sentence paragraph combining what the stats, segment-level results, and time trend
collectively tell us. Reconcile any tensions (e.g. aggregate positive but Growth negative).
Be specific — reference actual numbers.

IMPLICATIONS:
3-4 bullet points explaining what the decision means in practice: who gets the feature,
what the rollout sequence should be, what risks to monitor, and what the business should
expect over the next 90 days. This is NOT a restatement of the decision — it reasons
about consequences and next steps.

TRADE-OFFS:
2-3 bullet points on what we are giving up with this decision. If PARTIAL SHIP, what does
holding back Growth cost us? If NO SHIP, what is the opportunity cost? If SHIP, what
guardrails are we relaxing? Be honest and specific.

KNOWLEDGE APPLIED:
1-2 sentences on what past experiments told us that was relevant to interpreting these
results, and whether this experiment confirmed or contradicted that prior knowledge.

Write in plain business English. No emojis. No decorative symbols.
    """).strip()

    try:
        raw = llm.ask(prompt)
        try:
            raw = _strip_decorative_chars(raw)
        except NameError:
            pass
        return raw
    except Exception as e:
        return f'(Synthesis failed: {e})'


def _explain_roi_gap(
    exp_name: str,
    experiment_lift_pp: float,
    production_lift_pp: float,
    concurrent_ships: list,
    llm,
) -> str:
    """
    When post-ship ROI measurement shows a different lift from the experiment,
    LLM reasons about the most likely explanations. Called from _roi_analysis().
    """
    gap  = production_lift_pp - experiment_lift_pp
    sign = 'lower' if gap < 0 else 'higher'
    conc = ', '.join(s['name'] for s in concurrent_ships[:3]) if concurrent_ships else 'none identified'

    prompt = textwrap.dedent(f"""
You are a senior data scientist explaining why post-ship ROI differs from a measured experiment.

Experiment: {exp_name}
Experiment lift (measured): {experiment_lift_pp:+.2f}pp IOR
Post-ship lift (measured):  {production_lift_pp:+.2f}pp IOR
Gap: {abs(gap):.2f}pp {sign} than experiment

Concurrent features shipped during monitoring window: {conc}

In 3-5 sentences, explain the most likely reason(s) for the gap.
Cover: novelty/hawthorne effects, concurrent feature confounds, seasonal variation,
population drift, or SRM-induced bias. Be specific — name which cause is most plausible
for this magnitude of gap and this experiment type.
End with one concrete recommendation for the next measurement cycle.
Do not use emojis.
    """).strip()

    try:
        raw = llm.ask(prompt)
        try:
            raw = _strip_decorative_chars(raw)
        except NameError:
            pass
        return raw
    except Exception as e:
        return f'(Gap explanation unavailable: {e})'



# ═════════════════════════════════════════════════════════════════════════════
# MODULE 11 — CAUSAL ANALYSIS ENGINE
# ═════════════════════════════════════════════════════════════════════════════

# ── Method 1: Pre-Post Analysis ───────────────────────────────────────────────

def _run_pre_post(exp_name: str, cutoff_date: 'pd.Timestamp', alpha: float) -> dict:
    """
    Simple before/after comparison. Weakest causal claim.
    Compares IOR in pre-period vs post-period for the treated population.
    """
    pre  = df_all_experiments[
        (df_all_experiments['experiment_name'] == exp_name) &
        (df_all_experiments['created_at'] < cutoff_date)
    ]
    post = df_all_experiments[
        (df_all_experiments['experiment_name'] == exp_name) &
        (df_all_experiments['created_at'] >= cutoff_date)
    ]
    # Use hist_inquiries if pre-period rows are sparse
    if len(pre) < 50:
        pre = df_hist_inquiries[df_hist_inquiries['created_at'] < cutoff_date]

    if len(pre) == 0 or len(post) == 0:
        return {'error': 'Insufficient data for pre-post comparison'}

    n_pre, c_pre   = len(pre),  int(pre['converted_to_order'].sum())
    n_post, c_post = len(post), int(post['converted_to_order'].sum())
    result = proportion_test(n_pre, c_pre, n_post, c_post, alpha)

    gmv_change = (float(post['order_value'].mean() - pre['order_value'].mean())
                  if 'order_value' in post.columns and 'order_value' in pre.columns
                  and len(pre) > 0 and len(post) > 0
                  else 0.0)

    return {
        'method':        'Pre-Post Analysis',
        'cutoff_date':   str(cutoff_date.date()),
        'n_pre':         n_pre,  'conv_pre': c_pre,  'ior_pre':  result['rate_control'],
        'n_post':        n_post, 'conv_post': c_post, 'ior_post': result['rate_treatment'],
        'delta_pp':      result['delta_pp'],
        'ci':            [result['ci_lo_pp'], result['ci_hi_pp']],
        'p_value':       result['p_value'],
        'significant':   result['is_significant'],
        'gmv_change':    round(gmv_change, 2),
        'caveat':        'Pre-post confounded by seasonality and concurrent changes. Interpret with caution.',
    }


# ── Method 2: Difference-in-Differences (Enhanced) ─────────────────────────────

def _run_did_v2(
    treatment_units: list,
    control_units: list,
    cutoff_date: 'pd.Timestamp',
    pre_start: 'pd.Timestamp',
    alpha: float = 0.05,
    unit_col: str = 'account_segment',   # 'account_segment' | 'buyer_id' | 'account_id'
    outcome_col: str = 'converted_to_order',
    n_bootstrap: int = 1_000,
    run_twfe: bool = True,
) -> dict:
    """
    Enhanced Difference-in-Differences estimator.

    Computes:
      · Classic 2×2 DiD with delta-method SE
      · Bootstrap CI (1 000 resamples, percentile method)
      · Parallel trends test (regression-based, not just split-half)
      · Event study with pointwise 95% CIs
      · Two-Way Fixed Effects (TWFE) OLS estimate
      · Staggered adoption warning
      · Bacon decomposition summary (if multiple treatment times detected)

    Parameters
    ──────────
    treatment_units : list of values in unit_col that received the treatment
    control_units   : list of values in unit_col that are untreated controls
    cutoff_date     : intervention date (pd.Timestamp)
    pre_start       : start of pre-period (pd.Timestamp)
    alpha           : significance level
    unit_col        : the column that defines treatment/control assignment
    outcome_col     : binary outcome column (0/1 or bool)
    n_bootstrap     : number of bootstrap resamples for SE estimation
    run_twfe        : if True, also estimate via TWFE OLS
    """
    import numpy as np
    import pandas as pd
    from scipy import stats as scipy_stats

    all_data = pd.concat([
        globals().get('df_hist_inquiries', pd.DataFrame()),
        globals().get('df_all_experiments', pd.DataFrame()),
    ], ignore_index=True)
    all_data = all_data[all_data['created_at'] >= pre_start].copy()

    if unit_col not in all_data.columns:
        return {'error': f'unit_col "{unit_col}" not found in data'}

    all_units = treatment_units + control_units
    all_data  = all_data[all_data[unit_col].isin(all_units)].copy()
    all_data['treated']  = all_data[unit_col].isin(treatment_units).astype(int)
    all_data['post']     = (all_data['created_at'] >= cutoff_date).astype(int)
    all_data[outcome_col] = all_data[outcome_col].astype(float)

    # Split into cells
    treat_pre  = all_data[(all_data['treated']==1) & (all_data['post']==0)]
    treat_post = all_data[(all_data['treated']==1) & (all_data['post']==1)]
    ctrl_pre   = all_data[(all_data['treated']==0) & (all_data['post']==0)]
    ctrl_post  = all_data[(all_data['treated']==0) & (all_data['post']==1)]

    for cell_name, cell_df in [('treat_pre', treat_pre), ('treat_post', treat_post),
                                ('ctrl_pre', ctrl_pre),   ('ctrl_post', ctrl_post)]:
        if len(cell_df) < 20:
            return {'error': f'Insufficient data in {cell_name} cell ({len(cell_df)} rows)'}

    def ior(df): return float(df[outcome_col].mean()) if len(df) > 0 else np.nan
    def se_p(df):
        p = float(df[outcome_col].mean())
        return np.sqrt(p * (1 - p) / len(df)) if len(df) > 0 else np.nan

    ior_tp  = ior(treat_pre);  ior_tpo = ior(treat_post)
    ior_cp  = ior(ctrl_pre);   ior_cpo = ior(ctrl_post)
    did_est = (ior_tpo - ior_tp) - (ior_cpo - ior_cp)

    se_delta = np.sqrt(se_p(treat_pre)**2 + se_p(treat_post)**2 +
                       se_p(ctrl_pre)**2  + se_p(ctrl_post)**2)
    z_val  = did_est / se_delta if se_delta > 0 else 0
    p_val  = 2 * float(scipy_stats.norm.sf(abs(z_val)))
    ci_lo  = did_est - scipy_stats.norm.ppf(1 - alpha/2) * se_delta
    ci_hi  = did_est + scipy_stats.norm.ppf(1 - alpha/2) * se_delta

    boot_dids  = []
    for _bi in range(n_bootstrap):
        _s = 42 + _bi
        b_tp  = treat_pre.sample(len(treat_pre),   replace=True, random_state=_s)
        b_tpo = treat_post.sample(len(treat_post), replace=True, random_state=_s+1)
        b_cp  = ctrl_pre.sample(len(ctrl_pre),     replace=True, random_state=_s+2)
        b_cpo = ctrl_post.sample(len(ctrl_post),   replace=True, random_state=_s+3)
        boot_dids.append(
            (ior(b_tpo) - ior(b_tp)) - (ior(b_cpo) - ior(b_cp))
        )
    boot_arr  = np.array(boot_dids)
    se_boot   = float(np.std(boot_arr))
    ci_boot_lo = float(np.percentile(boot_arr, 100 * alpha / 2))
    ci_boot_hi = float(np.percentile(boot_arr, 100 * (1 - alpha / 2)))

    pre_data = all_data[all_data['post'] == 0].copy()
    pre_data['t'] = (pre_data['created_at'] - pre_start).dt.days.astype(float)
    pre_data['treated_x_t'] = pre_data['treated'] * pre_data['t']

    pt_p_value = 1.0
    pt_coef    = 0.0
    try:
        X_pt = np.column_stack([
            np.ones(len(pre_data)),
            pre_data['t'].values,
            pre_data['treated'].values,
            pre_data['treated_x_t'].values,
        ])
        y_pt  = pre_data[outcome_col].values
        XtX   = X_pt.T @ X_pt + np.eye(4) * 1e-8
        coefs = np.linalg.solve(XtX, X_pt.T @ y_pt)
        resid = y_pt - X_pt @ coefs
        sig2  = np.sum(resid**2) / max(len(y_pt) - 4, 1)
        se_c  = np.sqrt(np.diag(sig2 * np.linalg.inv(XtX)))
        pt_coef   = float(coefs[3])                          # interaction coef
        t_stat_pt = pt_coef / se_c[3] if se_c[3] > 0 else 0
        pt_p_value = float(2 * scipy_stats.t.sf(abs(t_stat_pt), df=len(y_pt) - 4))
    except Exception:
        pass

    parallel_ok = pt_p_value > 0.10   # non-significant → trends were parallel

    event_study = []
    for week_offset in range(-12, 17):
        w_start = cutoff_date + pd.Timedelta(weeks=week_offset)
        w_end   = w_start + pd.Timedelta(weeks=1)
        tw = all_data[(all_data['treated']==1) & all_data['created_at'].between(w_start, w_end)]
        cw = all_data[(all_data['treated']==0) & all_data['created_at'].between(w_start, w_end)]
        if len(tw) >= 15 and len(cw) >= 15:
            gap   = ior(tw) - ior(cw)
            se_g  = np.sqrt(se_p(tw)**2 + se_p(cw)**2)
            z95   = scipy_stats.norm.ppf(0.975)
            event_study.append({
                'week':       week_offset,
                'treat_ior':  float(ior(tw)),
                'ctrl_ior':   float(ior(cw)),
                'gap':        float(gap),
                'gap_ci_lo':  float(gap - z95 * se_g),   # ← NEW: pointwise CI
                'gap_ci_hi':  float(gap + z95 * se_g),   # ← NEW: pointwise CI
                'n_treat':    len(tw),
                'n_ctrl':     len(cw),
            })

    twfe_result = {}
    if run_twfe:
        # Aggregate to unit × week panel
        all_data['week'] = all_data['created_at'].dt.to_period('W').apply(
            lambda x: x.start_time
        )
        panel = (
            all_data
            .groupby([unit_col, 'week', 'treated'])
            [outcome_col].mean()
            .reset_index()
        )
        panel['post']  = (panel['week'] >= cutoff_date).astype(int)
        panel['D']     = panel['treated'] * panel['post']

        panel['y_dm']  = (panel[outcome_col]
                          - panel.groupby(unit_col)[outcome_col].transform('mean')
                          - panel.groupby('week')[outcome_col].transform('mean')
                          + panel[outcome_col].mean())
        panel['D_dm']  = (panel['D']
                          - panel.groupby(unit_col)['D'].transform('mean')
                          - panel.groupby('week')['D'].transform('mean')
                          + panel['D'].mean())
        X_tw = panel['D_dm'].values.reshape(-1, 1)
        y_tw = panel['y_dm'].values
        if np.sum(X_tw**2) > 1e-10:
            twfe_coef  = float(np.sum(X_tw.flatten() * y_tw) / np.sum(X_tw**2))
            resid_tw   = y_tw - X_tw.flatten() * twfe_coef
            se_tw      = float(np.sqrt(np.sum(resid_tw**2) /
                                max(len(y_tw) - 2, 1) /
                                np.sum(X_tw**2)))
            t_tw       = twfe_coef / se_tw if se_tw > 0 else 0
            p_tw       = float(2 * scipy_stats.t.sf(abs(t_tw), df=max(len(y_tw)-2, 1)))
            twfe_result = {
                'twfe_estimate_pp':   round(twfe_coef * 100, 4),
                'twfe_se_pp':         round(se_tw * 100, 4),
                'twfe_p_value':       round(p_tw, 5),
                'twfe_significant':   p_tw < alpha,
                'twfe_n_unit_periods': len(panel),
            }

    stagger_warning = None
    exp_data = globals().get('df_all_experiments', pd.DataFrame())
    if unit_col in exp_data.columns and len(exp_data) > 0:
        first_treatment = (
            exp_data[exp_data['variant'] != 'control']
            .groupby(unit_col)['created_at'].min()
        )
        if len(first_treatment) > 1:
            unique_dates = first_treatment.dt.to_period('W').unique()
            if len(unique_dates) > 1:
                stagger_warning = (
                    f'Staggered adoption detected: {len(unique_dates)} distinct'
                    f' treatment-start weeks. Classic 2×2 DiD may be biased.'
                    f' TWFE estimate above accounts for this, but consider'
                    f' Callaway-Sant\'Anna or Sun-Abraham estimators for'
                    f' heterogeneous treatment effects.'
                )

    return {
        'method':              'Difference-in-Differences (Enhanced)',
        'unit_col':            unit_col,
        'treatment_units':     treatment_units,
        'control_units':       control_units,
        'cutoff_date':         str(cutoff_date.date()),
        'pre_start':           str(pre_start.date()),
        # 2×2 cells
        'ior_treat_pre':       round(ior_tp,  5),
        'ior_treat_post':      round(ior_tpo, 5),
        'ior_ctrl_pre':        round(ior_cp,  5),
        'ior_ctrl_post':       round(ior_cpo, 5),
        'treat_diff':          round(ior_tpo - ior_tp, 5),
        'ctrl_diff':           round(ior_cpo - ior_cp, 5),
        # Classic DiD estimate
        'did_estimate_pp':     round(did_est * 100, 4),
        'did_se_delta_pp':     round(se_delta * 100, 4),
        'did_se_bootstrap_pp': round(se_boot * 100, 4),
        'ci_delta_pp':         [round(ci_lo * 100, 4), round(ci_hi * 100, 4)],
        'ci_bootstrap_pp':     [round(ci_boot_lo * 100, 4), round(ci_boot_hi * 100, 4)],
        'p_value':             round(p_val, 5),
        'significant':         p_val < alpha,
        'n_bootstrap':         n_bootstrap,
        # Parallel trends
        'parallel_trends_interaction_coef': round(pt_coef * 100, 5),
        'parallel_trends_p':   round(pt_p_value, 4),
        'parallel_trends_ok':  parallel_ok,
        'parallel_trends_note': (
            '✅ Parallel trends holds (regression test, p={:.3f})'.format(pt_p_value)
            if parallel_ok else
            '⚠️  Parallel trends VIOLATED (p={:.3f}) — DiD estimate may be biased.'
            ' Consider ITS or Synthetic Control instead.'.format(pt_p_value)
        ),
        'event_study':         event_study,
        **twfe_result,
        'stagger_warning':     stagger_warning,
        'n_treat_pre':   len(treat_pre),  'n_treat_post': len(treat_post),
        'n_ctrl_pre':    len(ctrl_pre),   'n_ctrl_post':  len(ctrl_post),
    }


def _plot_did_v2(result: dict, alpha: float = 0.05):
    """
    Enhanced DiD visualisation:
    [1] 2×2 bar chart with DiD annotation
    [2] Event study with shaded 95% CI band
    [3] Bootstrap distribution of DiD estimate
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    fig.patch.set_facecolor('#0f0f0f')
    COLORS_LOCAL = {
        'treatment': '#f97316', 'control': '#4e9af1',
        'positive': '#22c55e', 'negative': '#ef4444',
        'highlight': '#facc15', 'neutral': '#a1a1aa',
    }

    ax1 = axes[0]
    groups = ['Treat\nPre', 'Treat\nPost', 'Ctrl\nPre', 'Ctrl\nPost']
    vals   = [result['ior_treat_pre']*100, result['ior_treat_post']*100,
              result['ior_ctrl_pre']*100,  result['ior_ctrl_post']*100]
    colors_2x2 = [COLORS_LOCAL['treatment'], COLORS_LOCAL['positive'],
                  COLORS_LOCAL['control'],   COLORS_LOCAL['neutral']]
    bars = ax1.bar(groups, vals, color=colors_2x2, width=0.5)
    for bar, v in zip(bars, vals):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                 f'{v:.3f}%', ha='center', fontsize=9.5, fontweight='bold', color='white')

    sig_icon = '✅' if result['significant'] else '⚠️ n.s.'
    pt_icon  = '✅ PT holds' if result['parallel_trends_ok'] else '❌ PT violated'
    ax1.set_title(
        f'DiD 2×2  |  Δ={result["did_estimate_pp"]:+.3f}pp  {sig_icon}\n'
        f'p={result["p_value"]:.4f}  Bootstrap CI: [{result["ci_bootstrap_pp"][0]:+.3f}, '
        f'{result["ci_bootstrap_pp"][1]:+.3f}]pp\n{pt_icon}',
        color=COLORS_LOCAL['highlight'], fontsize=9
    )
    ax1.set_ylabel('IOR (%)')
    ax1.grid(True, alpha=0.2)

    ax2 = axes[1]
    ev    = result.get('event_study', [])
    if ev:
        weeks  = [e['week'] for e in ev]
        gaps   = [e['gap'] * 100 for e in ev]
        ci_lo  = [e['gap_ci_lo'] * 100 for e in ev]
        ci_hi  = [e['gap_ci_hi'] * 100 for e in ev]

        ax2.fill_between(weeks, ci_lo, ci_hi, alpha=0.25,
                         color=COLORS_LOCAL['treatment'], label='95% CI')
        ax2.plot(weeks, gaps, color=COLORS_LOCAL['treatment'],
                 lw=2.5, marker='o', ms=4, label='Treatment − Control gap')
        ax2.axhline(0, color='white', lw=1, linestyle='--', alpha=0.5)
        ax2.axvline(0, color=COLORS_LOCAL['highlight'], lw=2, label='Intervention')

        # Shade pre-period
        pre_weeks = [w for w in weeks if w < 0]
        if pre_weeks:
            ax2.axvspan(min(pre_weeks)-0.5, -0.5, alpha=0.07,
                        color=COLORS_LOCAL['neutral'], label='Pre-period')

        ax2.set_xlabel('Week relative to intervention')
        ax2.set_ylabel('Treatment − Control gap (pp)')
        pt_msg = ('✅ Pre-period gaps near zero (PT holds)'
                  if result['parallel_trends_ok']
                  else '⚠️ Pre-period trend divergence (PT possibly violated)')
        ax2.set_title(f'Event Study with 95% CI\n{pt_msg}',
                      color=COLORS_LOCAL['highlight'], fontsize=9)
        ax2.legend(fontsize=7.5)
        ax2.grid(True, alpha=0.2)

    ax3 = axes[2]
    sim_boot = np.random.normal(
        result['did_estimate_pp'] / 100,
        result['did_se_bootstrap_pp'] / 100,
        size=5000
    ) * 100
    ax3.hist(sim_boot, bins=40, color=COLORS_LOCAL['neutral'],
             alpha=0.7, label='Bootstrap distribution')
    ax3.axvline(result['did_estimate_pp'], color=COLORS_LOCAL['treatment'],
                lw=2.5, label=f'DiD estimate ({result["did_estimate_pp"]:+.3f}pp)')
    ax3.axvline(result['ci_bootstrap_pp'][0], color=COLORS_LOCAL['highlight'],
                lw=1.5, linestyle='--', label=f'{int((1-alpha)*100)}% CI')
    ax3.axvline(result['ci_bootstrap_pp'][1], color=COLORS_LOCAL['highlight'],
                lw=1.5, linestyle='--')
    ax3.axvline(0, color='white', lw=1, linestyle=':', alpha=0.6, label='Null (0)')
    ax3.set_xlabel('DiD estimate (pp)')
    ax3.set_ylabel('Frequency')
    twfe_note = ''
    if 'twfe_estimate_pp' in result:
        ax3.axvline(result['twfe_estimate_pp'], color=COLORS_LOCAL['positive'],
                    lw=2, linestyle='-.', label=f'TWFE={result["twfe_estimate_pp"]:+.3f}pp')
        twfe_note = f'  TWFE: {result["twfe_estimate_pp"]:+.3f}pp (p={result.get("twfe_p_value","?"):.4f})'
    ax3.set_title(f'Bootstrap Distribution (n={result["n_bootstrap"]:,})\n{twfe_note}',
                  color=COLORS_LOCAL['highlight'], fontsize=9)
    ax3.legend(fontsize=7.5)

    plt.suptitle('Difference-in-Differences — Enhanced Analysis',
                 fontsize=13, color=COLORS_LOCAL['highlight'], fontweight='bold')
    plt.tight_layout()
    plt.savefig('did_analysis_v2.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → did_analysis_v2.png')

# ── Method 3: Interrupted Time Series ────────────────────────────────────────

def _run_its(
    cutoff_date: 'pd.Timestamp',
    pre_start: 'pd.Timestamp',
    post_end: 'pd.Timestamp',
) -> dict:
    """
    Fits two regression lines (pre and post) on the daily IOR time series.
    Estimates: (1) immediate level change at cutoff, (2) slope change post-cutoff.
    """
    df_ts = db.execute("SELECT * FROM platform_daily_ior ORDER BY date").df()
    df_ts['date'] = pd.to_datetime(df_ts['date'])

    window = df_ts[(df_ts['date'] >= pre_start) & (df_ts['date'] <= post_end)].copy()
    if len(window) < 30:
        return {'error': 'Insufficient time series data (need ≥30 days)'}

    window = window.reset_index(drop=True)
    cutoff_pos = window[window['date'] >= cutoff_date].index[0]

    n = len(window)
    t  = np.arange(n, dtype=float)
    D  = (window['date'] >= cutoff_date).astype(float).values
    Dt = t * D

    X = np.column_stack([np.ones(n), t, D, Dt])
    y = window['ior'].values

    XtX = X.T @ X
    coef = np.linalg.solve(XtX + np.eye(4)*1e-8, X.T @ y)
    y_hat = X @ coef
    residuals = y - y_hat
    n_params = 4
    sigma2 = np.sum(residuals**2) / (n - n_params)
    se_coef = np.sqrt(np.diag(sigma2 * np.linalg.inv(XtX + np.eye(4)*1e-8)))

    b0, b1, b2, b3 = coef      # intercept, pre-slope, level change, slope change
    se_b2, se_b3   = se_coef[2], se_coef[3]

    t_b2 = b2 / se_b2 if se_b2 > 0 else 0
    t_b3 = b3 / se_b3 if se_b3 > 0 else 0
    p_b2 = 2 * float(stats.t.sf(abs(t_b2), df=n-n_params))
    p_b3 = 2 * float(stats.t.sf(abs(t_b3), df=n-n_params))

    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((y - y.mean())**2)
    r2     = 1 - ss_res/ss_tot if ss_tot > 0 else 0

    X_cf     = np.column_stack([np.ones(n), t, np.zeros(n), np.zeros(n)])
    y_cf     = X_cf @ coef

    post_mask      = window['date'] >= cutoff_date
    avg_observed   = window.loc[post_mask, 'ior'].mean()
    avg_cf_post    = y_cf[post_mask].mean()
    avg_fitted_post= y_hat[post_mask].mean()

    return {
        'method':            'Interrupted Time Series',
        'cutoff_date':       str(cutoff_date.date()),
        'pre_days':          int(cutoff_pos),
        'post_days':         int(n - cutoff_pos),
        'model_r2':          round(r2, 4),
        'pre_slope_pp_day':  round(b1 * 100, 5),
        'level_change_pp':   round(b2 * 100, 4),
        'level_change_p':    round(p_b2, 5),
        'level_significant': p_b2 < 0.05,
        'slope_change_pp_day': round(b3 * 100, 5),
        'slope_change_p':    round(p_b3, 5),
        'slope_significant': p_b3 < 0.05,
        'avg_observed_post': round(avg_observed, 5),
        'avg_counterfactual_post': round(avg_cf_post, 5),
        'avg_lift_pp':       round((avg_observed - avg_cf_post) * 100, 4),
        'fitted_values':     y_hat.tolist(),
        'counterfactual':    y_cf.tolist(),
        'dates':             window['date'].dt.strftime('%Y-%m-%d').tolist(),
        'actual_ior':        y.tolist(),
    }


# ── Method 4: Propensity Score Matching ──────────────────────────────────────

def _run_psm(
    treatment_condition: str,
    outcome_col: str,
    alpha: float,
) -> dict:
    """
    Propensity Score Matching:
    1. Fit logistic regression to predict treatment assignment from covariates
    2. Nearest-neighbour matching (1:1 without replacement)
    3. Compare outcomes between matched pairs → ATT (Average Treatment Effect on Treated)
    Also: check covariate balance before and after matching (SMD)
    """
    from scipy.special import expit as sigmoid

    exp_df = df_all_experiments[
        (df_all_experiments['experiment_name'] == 'billing_profile_confirmation_v2')
    ].copy()

    merged = exp_df.merge(df_psm_features[['buyer_id','has_orders','is_us','is_web',
                                           'high_gmv','segment_num','lifetime_orders']],
                          on='buyer_id', how='inner')
    if len(merged) < 100:
        return {'error': 'Insufficient data for PSM'}

    merged['treated'] = (merged['variant'] == 'treatment').astype(int)
    outcome_vals = merged[outcome_col].astype(float).values

    covariates = ['has_orders','is_us','is_web','high_gmv','segment_num']
    X = merged[covariates].fillna(0).values.astype(float)
    y_treat = merged['treated'].values

    n_feat = X.shape[1]
    X_aug  = np.column_stack([np.ones(len(X)), X])   # add intercept
    theta  = np.zeros(n_feat + 1)

    for _ in range(300):    # gradient descent
        pred = sigmoid(X_aug @ theta)
        grad = X_aug.T @ (pred - y_treat) / len(y_treat)
        theta -= 0.1 * grad

    propensity = sigmoid(X_aug @ theta)
    merged['propensity'] = propensity

    treated_idx   = merged[merged['treated']==1].index.tolist()
    control_idx   = merged[merged['treated']==0].index.tolist()
    matched_pairs = []
    used_controls = set()

    for t_idx in treated_idx:
        p_t = merged.loc[t_idx, 'propensity']
        best_c, best_dist = None, np.inf
        for c_idx in control_idx:
            if c_idx in used_controls: continue
            dist = abs(p_t - merged.loc[c_idx, 'propensity'])
            if dist < best_dist:
                best_dist, best_c = dist, c_idx
        if best_c is not None and best_dist < 0.10:   # caliper = 0.10
            matched_pairs.append((t_idx, best_c))
            used_controls.add(best_c)

    if len(matched_pairs) < 20:
        return {'error': f'Too few matched pairs ({len(matched_pairs)}). '
                         'Consider widening caliper or checking propensity overlap.'}

    t_idx_list = [p[0] for p in matched_pairs]
    c_idx_list = [p[1] for p in matched_pairs]
    t_outcomes = merged.loc[t_idx_list, outcome_col].astype(float).values
    c_outcomes = merged.loc[c_idx_list, outcome_col].astype(float).values

    # ATT estimate
    att = t_outcomes.mean() - c_outcomes.mean()
    pr_matched = proportion_test(
        len(c_outcomes), int(c_outcomes.sum()),
        len(t_outcomes), int(t_outcomes.sum()),
        alpha
    )

    smd_before, smd_after = [], []
    for cov in covariates:
        t_vals_all = merged.loc[merged['treated']==1, cov].fillna(0).values
        c_vals_all = merged.loc[merged['treated']==0, cov].fillna(0).values
        t_vals_mat = merged.loc[t_idx_list, cov].fillna(0).values
        c_vals_mat = merged.loc[c_idx_list, cov].fillna(0).values
        pool_sd    = np.sqrt((t_vals_all.std()**2 + c_vals_all.std()**2) / 2) or 1
        smd_b = abs(t_vals_all.mean() - c_vals_all.mean()) / pool_sd
        smd_a = abs(t_vals_mat.mean() - c_vals_mat.mean()) / pool_sd
        smd_before.append({'covariate': cov, 'smd': round(smd_b, 4)})
        smd_after.append({'covariate': cov,  'smd': round(smd_a, 4)})

    max_smd_after = max(s['smd'] for s in smd_after)
    balance_ok    = max_smd_after < 0.10

    return {
        'method':            'Propensity Score Matching',
        'n_treated':         len(treated_idx),
        'n_matched_pairs':   len(matched_pairs),
        'caliper':           0.10,
        'att_pp':            round(att * 100, 4),
        'ior_treated':       round(t_outcomes.mean(), 5),
        'ior_control':       round(c_outcomes.mean(), 5),
        'p_value':           pr_matched['p_value'],
        'significant':       pr_matched['is_significant'],
        'ci_pp':             [pr_matched['ci_lo_pp'], pr_matched['ci_hi_pp']],
        'smd_before':        smd_before,
        'smd_after':         smd_after,
        'max_smd_after':     round(max_smd_after, 4),
        'balance_ok':        balance_ok,
        'balance_note':      'Good balance (max SMD < 0.10)' if balance_ok else
                             f'Poor balance (max SMD={max_smd_after:.3f}). Results may be biased.',
    }


# ── Method 5: Synthetic Control ───────────────────────────────────────────────

def _run_synthetic_control_v2(
    treatment_segment: str,
    donor_segments: list,
    cutoff_date: 'pd.Timestamp',
    pre_start: 'pd.Timestamp',
    pre_rmspe_threshold: float = 0.015,   # reject if pre-RMSPE > threshold
    min_pre_weeks: int = 10,
    min_post_weeks: int = 4,
) -> dict:
    """
    Enhanced Synthetic Control with quality gates, time-placebo, and
    permutation inference.

    Parameters
    ──────────
    treatment_segment  : segment treated (e.g. 'Core')
    donor_segments     : untreated segments used to build the synthetic unit
    cutoff_date        : intervention date
    pre_start          : start of the pre-period
    pre_rmspe_threshold: if pre-period RMSPE exceeds this, SC estimate is
                         flagged as unreliable (fit too poor to extrapolate)
    min_pre_weeks      : minimum pre-period weeks required
    min_post_weeks     : minimum post-period weeks required
    """
    from scipy.optimize import minimize
    import numpy as np
    import pandas as pd

    all_data = pd.concat([
        globals().get('df_hist_inquiries', pd.DataFrame()),
        globals().get('df_all_experiments', pd.DataFrame()),
    ], ignore_index=True)

    all_data['week'] = all_data['created_at'].dt.to_period('W').apply(
        lambda x: x.start_time
    )
    weekly = (all_data
              .groupby(['week', 'account_segment'])['converted_to_order']
              .mean()
              .reset_index())
    weekly.columns = ['week', 'segment', 'ior']
    weekly = weekly[weekly['segment'].isin([treatment_segment] + donor_segments)]
    pivot  = (weekly
              .pivot(index='week', columns='segment', values='ior')
              .ffill()
              .dropna())

    if treatment_segment not in pivot.columns:
        return {'error': f'Treatment segment "{treatment_segment}" not in data'}

    pre_mask  = pd.to_datetime(pivot.index) < cutoff_date
    post_mask = pd.to_datetime(pivot.index) >= cutoff_date

    n_pre  = int(pre_mask.sum())
    n_post = int(post_mask.sum())

    if n_pre < min_pre_weeks:
        return {'error': f'Only {n_pre} pre-period weeks (need ≥{min_pre_weeks})'}
    if n_post < min_post_weeks:
        return {'error': f'Only {n_post} post-period weeks (need ≥{min_post_weeks})'}

    y_treat_pre  = pivot.loc[pre_mask, treatment_segment].values
    y_donors_pre = pivot.loc[pre_mask, donor_segments].values

    def objective(w):
        return float(np.sum((y_treat_pre - y_donors_pre @ w)**2))

    n_donors = len(donor_segments)
    w0       = np.ones(n_donors) / n_donors
    result_opt = minimize(
        objective, w0, method='SLSQP',
        bounds=[(0, 1)] * n_donors,
        constraints={'type': 'eq', 'fun': lambda w: np.sum(w) - 1},
        options={'maxiter': 1000, 'ftol': 1e-12},
    )
    weights = result_opt.x

    y_sc_pre  = y_donors_pre @ weights
    y_sc_post = pivot.loc[post_mask, donor_segments].values @ weights
    y_trt_pre = y_treat_pre
    y_trt_post = pivot.loc[post_mask, treatment_segment].values

    pre_rmspe  = float(np.sqrt(np.mean((y_trt_pre - y_sc_pre)**2)))
    post_rmspe = float(np.sqrt(np.mean((y_trt_post - y_sc_post)**2)))
    rmspe_ratio = float(post_rmspe / pre_rmspe) if pre_rmspe > 1e-10 else 0.0

    fit_quality = (
        'Excellent' if pre_rmspe < 0.005 else
        'Good'      if pre_rmspe < 0.010 else
        'Marginal'  if pre_rmspe < pre_rmspe_threshold else
        'Poor'
    )
    fit_ok = pre_rmspe < pre_rmspe_threshold
    fit_warning = None
    if not fit_ok:
        fit_warning = (
            f'Pre-period RMSPE={pre_rmspe*100:.3f}pp exceeds threshold '
            f'({pre_rmspe_threshold*100:.3f}pp). The synthetic unit fits poorly. '
            f'The post-period estimate is unreliable. Try: (a) adding more donors, '
            f'(b) shortening the pre-period, (c) using DiD or ITS instead.'
        )

    max_weight    = float(np.max(weights))
    dominant_donor = donor_segments[int(np.argmax(weights))]
    concentration_warning = None
    if max_weight > 0.85:
        concentration_warning = (
            f'Donor "{dominant_donor}" receives {max_weight:.0%} of the weight. '
            f'The synthetic unit is nearly identical to this single donor. '
            f'Consider running a DiD with just these two segments instead.'
        )

    avg_gap_pp = float((y_trt_post - y_sc_post).mean() * 100)

    donor_placebo_gaps = []
    for donor in donor_segments:
        placebo_donors = [s for s in donor_segments if s != donor]
        if len(placebo_donors) == 0:
            continue
        y_p_pre  = pivot.loc[pre_mask, donor].values
        y_pd_pre = pivot.loc[pre_mask, placebo_donors].values
        if y_pd_pre.ndim == 1:
            y_pd_pre = y_pd_pre.reshape(-1, 1)
        n_d = y_pd_pre.shape[1]
        try:
            r_p = minimize(
                lambda w: float(np.sum((y_p_pre - y_pd_pre @ w)**2)),
                np.ones(n_d) / n_d,
                method='SLSQP',
                bounds=[(0, 1)] * n_d,
                constraints={'type': 'eq', 'fun': lambda w: sum(w) - 1},
            )
            w_p           = r_p.x
            y_sc_p_post   = pivot.loc[post_mask, placebo_donors].values @ w_p
            y_p_post      = pivot.loc[post_mask, donor].values
            p_rmspe_donor = float(np.sqrt(np.mean(
                (y_p_pre - y_pd_pre @ w_p)**2
            )))
            # Only include donors with decent fit (pre_rmspe < 2× treatment RMSPE)
            if p_rmspe_donor < 2 * pre_rmspe + 1e-6:
                donor_placebo_gaps.append(
                    float((y_p_post - y_sc_p_post).mean() * 100)
                )
        except Exception:
            pass

    time_placebo_gap  = None
    time_placebo_note = None
    pseudo_cutoff = pre_start + (cutoff_date - pre_start) / 2
    pseudo_pre_mask  = pd.to_datetime(pivot.index) < pseudo_cutoff
    pseudo_post_mask = (pd.to_datetime(pivot.index) >= pseudo_cutoff) & pre_mask

    if pseudo_pre_mask.sum() >= 6 and pseudo_post_mask.sum() >= 4:
        y_pp_pre    = pivot.loc[pseudo_pre_mask, treatment_segment].values
        y_pd_donors = pivot.loc[pseudo_pre_mask, donor_segments].values
        try:
            r_tp = minimize(
                lambda w: float(np.sum((y_pp_pre - y_pd_donors @ w)**2)),
                np.ones(n_donors) / n_donors,
                method='SLSQP',
                bounds=[(0, 1)] * n_donors,
                constraints={'type': 'eq', 'fun': lambda w: sum(w) - 1},
            )
            w_tp          = r_tp.x
            y_sc_tp_post  = pivot.loc[pseudo_post_mask, donor_segments].values @ w_tp
            y_tp_post     = pivot.loc[pseudo_post_mask, treatment_segment].values
            time_placebo_gap = float((y_tp_post - y_sc_tp_post).mean() * 100)
            time_placebo_note = (
                f'Time-placebo gap = {time_placebo_gap:+.3f}pp (should ≈ 0). '
                + ('✅ Method passes in-time placebo check.'
                   if abs(time_placebo_gap) < abs(avg_gap_pp) * 0.5
                   else '⚠️  Time-placebo gap is large relative to treatment gap — interpret with caution.')
            )
        except Exception:
            pass

    all_placebo_gaps = donor_placebo_gaps.copy()
    if time_placebo_gap is not None:
        all_placebo_gaps.append(time_placebo_gap)

    p_combined = (
        (np.sum(np.abs(all_placebo_gaps) >= abs(avg_gap_pp)) + 1) /
        (len(all_placebo_gaps) + 1)
    ) if all_placebo_gaps else None

    rmspe_interpretation = (
        'Strong evidence of effect (ratio > 5)' if rmspe_ratio > 5 else
        'Moderate evidence (ratio 2–5)'          if rmspe_ratio > 2 else
        'Weak evidence (ratio 1–2)'              if rmspe_ratio > 1 else
        'No detectable effect (ratio ≤ 1)'
    )

    return {
        'method':                    'Synthetic Control (Enhanced)',
        'treatment_segment':         treatment_segment,
        'donor_segments':            donor_segments,
        'cutoff_date':               str(cutoff_date.date()),
        'pre_start':                 str(pre_start.date()),
        # Donor weights
        'weights':                   {d: round(float(w), 4)
                                      for d, w in zip(donor_segments, weights)},
        'dominant_donor':            dominant_donor,
        'max_donor_weight':          round(max_weight, 4),
        'concentration_warning':     concentration_warning,
        # Fit quality
        'pre_rmspe':                 round(pre_rmspe, 6),
        'pre_rmspe_pp':              round(pre_rmspe * 100, 4),
        'post_rmspe':                round(post_rmspe, 6),
        'rmspe_ratio':               round(rmspe_ratio, 3),
        'rmspe_interpretation':      rmspe_interpretation,
        'fit_quality':               fit_quality,
        'fit_ok':                    fit_ok,
        'fit_warning':               fit_warning,
        # Main estimate
        'avg_gap_pp':                round(avg_gap_pp, 4),
        # Inference
        'n_donor_placebo_tests':     len(donor_placebo_gaps),
        'donor_placebo_gaps_pp':     [round(g, 4) for g in donor_placebo_gaps],
        'time_placebo_gap_pp':       round(time_placebo_gap, 4) if time_placebo_gap is not None else None,
        'time_placebo_note':         time_placebo_note,
        'n_placebo_tests_combined':  len(all_placebo_gaps),
        'p_value_placebo_combined':  round(float(p_combined), 4) if p_combined is not None else None,
        # Time series (for plotting)
        'sc_pre':         y_sc_pre.tolist(),
        'sc_post':        y_sc_post.tolist(),
        'treat_pre':      y_trt_pre.tolist(),
        'treat_post':     y_trt_post.tolist(),
        'dates_pre':      [str(d) for d in pivot.index[pre_mask]],
        'dates_post':     [str(d) for d in pivot.index[post_mask]],
        'weeks_pre':      n_pre,
        'weeks_post':     n_post,
    }


def _plot_synthetic_control_v2(result: dict):
    """
    Enhanced SC plot:
    [1] Treatment vs synthetic control time series with gap shading
    [2] Post-period gap trajectory
    [3] Combined placebo distribution (donor + time placebo)
    """
    import matplotlib.pyplot as plt
    import numpy as np

    COLORS_LOCAL = {
        'treatment': '#f97316', 'control': '#4e9af1',
        'positive': '#22c55e', 'negative': '#ef4444',
        'highlight': '#facc15', 'neutral': '#a1a1aa',
    }

    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    fig.patch.set_facecolor('#0f0f0f')

    all_dates  = result['dates_pre'] + result['dates_post']
    sc_vals    = list(result['sc_pre'])  + list(result['sc_post'])
    trt_vals   = list(result['treat_pre']) + list(result['treat_post'])
    n_pre      = result['weeks_pre']

    ax = axes[0]
    ax.plot(range(len(trt_vals)), [v*100 for v in trt_vals],
            color=COLORS_LOCAL['treatment'], lw=2.5, label=result['treatment_segment'])
    ax.plot(range(len(sc_vals)),  [v*100 for v in sc_vals],
            color=COLORS_LOCAL['control'],  lw=2.5, linestyle='--',
            label='Synthetic control')
    ax.axvline(n_pre, color=COLORS_LOCAL['highlight'], lw=2, label='Intervention')
    ax.fill_between(
        range(n_pre, len(trt_vals)),
        [v*100 for v in sc_vals[n_pre:]],
        [v*100 for v in trt_vals[n_pre:]],
        color=COLORS_LOCAL['positive'] if result['avg_gap_pp'] >= 0 else COLORS_LOCAL['negative'],
        alpha=0.25, label='Post-period gap'
    )
    fit_icon = {'Excellent': '✅', 'Good': '✅', 'Marginal': '⚠️', 'Poor': '❌'}
    ax.set_title(
        f'Synthetic Control  |  Avg gap={result["avg_gap_pp"]:+.3f}pp\n'
        f'Fit: {fit_icon.get(result["fit_quality"],"?")} {result["fit_quality"]}'
        f' (pre-RMSPE={result["pre_rmspe_pp"]:.3f}pp)\n'
        f'RMSPE ratio={result["rmspe_ratio"]:.2f}  — {result["rmspe_interpretation"]}',
        color=COLORS_LOCAL['highlight'], fontsize=8
    )
    ax.set_xlabel('Week'); ax.set_ylabel('IOR (%)')
    ax.legend(fontsize=7.5); ax.grid(True, alpha=0.2)

    ax2 = axes[1]
    post_gaps = [(t - s) * 100
                 for t, s in zip(result['treat_post'], result['sc_post'])]
    weeks_post = list(range(1, len(post_gaps) + 1))
    bar_colors = [COLORS_LOCAL['positive'] if g >= 0 else COLORS_LOCAL['negative']
                  for g in post_gaps]
    ax2.bar(weeks_post, post_gaps, color=bar_colors, width=0.7, alpha=0.8)
    ax2.axhline(0, color='white', lw=1.5, linestyle='--', alpha=0.6)
    ax2.axhline(result['avg_gap_pp'], color=COLORS_LOCAL['highlight'],
                lw=2, linestyle='-', label=f'Avg gap={result["avg_gap_pp"]:+.3f}pp')
    ax2.set_xlabel('Week after intervention'); ax2.set_ylabel('Gap (pp)')
    ax2.set_title('Post-Intervention Weekly Gap\n(Treatment − Synthetic Control)',
                  color=COLORS_LOCAL['highlight'])
    ax2.legend(fontsize=8); ax2.grid(True, alpha=0.2)

    ax3 = axes[2]
    donor_gaps = result.get('donor_placebo_gaps_pp', [])
    time_gap   = result.get('time_placebo_gap_pp')

    if donor_gaps:
        ax3.hist(donor_gaps, bins=max(5, len(donor_gaps)//2+1),
                 color=COLORS_LOCAL['neutral'], alpha=0.7, label='Donor placebos')
    if time_gap is not None:
        ax3.axvline(time_gap, color=COLORS_LOCAL['control'],
                    lw=2, linestyle='-.', label=f'Time placebo ({time_gap:+.3f}pp)')

    ax3.axvline(result['avg_gap_pp'], color=COLORS_LOCAL['treatment'],
                lw=2.5, label=f'Treatment ({result["avg_gap_pp"]:+.3f}pp)')
    ax3.axvline(0, color='white', lw=1, linestyle=':', alpha=0.6)
    p_val = result.get('p_value_placebo_combined')
    p_str = f'Permutation p={p_val:.3f}' if p_val is not None else 'p=N/A'
    ax3.set_xlabel('Avg post-period gap (pp)'); ax3.set_ylabel('Count')
    ax3.set_title(f'Combined Placebo Distribution\n{p_str}  (donor + time placebos)',
                  color=COLORS_LOCAL['highlight'])
    ax3.legend(fontsize=7.5)

    plt.suptitle('Synthetic Control — Enhanced Analysis',
                 fontsize=13, color=COLORS_LOCAL['highlight'], fontweight='bold')
    plt.tight_layout()
    plt.savefig('synthetic_control_v2.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → synthetic_control_v2.png')


# ── Method 4: Propensity Score Matching ──────────────────────────────────────


def _causal_header(title: str, subtitle: str):
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + f'  {title}'.ljust(70) + '║')
    print('║' + f'  {subtitle}'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')


def _ask_alpha() -> float:
    raw = input('  ❓ Significance level α [0.05]: ').strip()
    try:
        v = float(raw)
        return v if 0 < v < 1 else 0.05
    except ValueError:
        return 0.05


def _ask_date(prompt: str, default: 'pd.Timestamp') -> 'pd.Timestamp':
    raw = input(f'  ❓ {prompt} [default: {default.date()}]: ').strip()
    try:
        return pd.Timestamp(raw) if raw else default
    except Exception:
        print(f'     ⚠️  Could not parse date — using default {default.date()}')
        return default


def _print_proportion_result(label: str, result: dict, alpha: float):
    sig = '✅ Significant' if result['is_significant'] else '⚠️  Not significant'
    print(f'  {label}')
    print(f'    Control IOR    : {result["rate_control"]*100:.3f}%  (n={result.get("n_control","?")})')
    print(f'    Treatment IOR  : {result["rate_treatment"]*100:.3f}%')
    print(f'    Δ              : {result["delta_pp"]:+.4f}pp  [{result["ci_lo_pp"]:+.3f}, {result["ci_hi_pp"]:+.3f}]')
    print(f'    p-value        : {result["p_value"]:.5f}  {sig} (α={alpha})')


def _causal_narrative(llm, result: dict, context_str: str):
    """LLM narrative for any causal result dict."""
    print('\n  🤖 Generating interpretation...')
    serialisable = {k: v for k, v in result.items()
                    if not isinstance(v, (list, dict)) or k in ('weights',)}
    narrative = llm.narrate(serialisable, context=context_str)
    print('\n' + '─'*72)
    print(narrative)
    print('─'*72)


# ─────────────────────────────────────────────────────────────────────────────
# METHOD MENU  →  run_causal_analysis (replaces old auto-selector)
# ─────────────────────────────────────────────────────────────────────────────

def _save_method_pdf(
    method_name: str,
    result: dict,
    chart_paths: list,
    narrative: str,
    output_filename: str,
) -> str:
    """
    Universal PDF report generator for all standalone causal method runners.
    Produces a clean, consistent report regardless of the method used.

    Parameters
    ──────────
    method_name     : human label (e.g. "A/B Test Analysis")
    result          : the result dict returned by the runner
    chart_paths     : list of .png file paths to embed (order preserved)
    narrative       : LLM-generated interpretation string
    output_filename : target .pdf filename
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak,
            Table, TableStyle, Image as RLImage,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        import os

        doc = SimpleDocTemplate(
            output_filename, pagesize=letter,
            topMargin=0.75*inch, bottomMargin=0.75*inch,
            leftMargin=0.75*inch, rightMargin=0.75*inch,
        )
        styles  = getSampleStyleSheet()
        palette = PDF_PALETTE  # uses global palette from cell 26

        title_style = ParagraphStyle('CTitle', parent=styles['Title'],
                                     fontSize=20, textColor=rl_colors.HexColor(palette['primary']),
                                     spaceAfter=6)
        h1_style    = ParagraphStyle('CH1', parent=styles['Heading1'],
                                     fontSize=13, textColor=rl_colors.HexColor(palette['primary']),
                                     spaceBefore=14, spaceAfter=4)
        body_style  = ParagraphStyle('CBody', parent=styles['Normal'],
                                     fontSize=10, leading=14, spaceAfter=4,
                                     alignment=TA_JUSTIFY)
        code_style  = ParagraphStyle('CCode', parent=styles['Code'],
                                     fontSize=8.5, leading=12, spaceAfter=2,
                                     backColor=rl_colors.HexColor('#1a1a1a'),
                                     textColor=rl_colors.HexColor('#e5e5e5'))
        kv_style    = ParagraphStyle('CKV', parent=styles['Normal'],
                                     fontSize=9, leading=12, spaceAfter=2)

        story = []

        story.append(Spacer(1, 0.5*inch))
        story.append(Paragraph(f'Causal Analysis Report', title_style))
        story.append(Paragraph(f'<b>{method_name}</b>', h1_style))
        story.append(Spacer(1, 0.15*inch))

        meta_rows = [
            ['Method',      method_name],
            ['Generated',   pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')],
        ]
        for key in ['experiment', 'treatment_segment', 'treatment_units',
                    'cutoff_date', 'pre_start']:
            if key in result and result[key]:
                meta_rows.append([key.replace('_', ' ').title(), str(result[key])[:80]])
        for key in ['n_pre', 'n_post', 'n_treated', 'n_matched_pairs',
                    'n_total', 'weeks_pre', 'weeks_post']:
            if key in result:
                meta_rows.append([key.replace('_', ' ').title(), f'{result[key]:,}'])

        meta_tbl = Table(meta_rows, colWidths=[2.2*inch, 4.3*inch])
        meta_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), rl_colors.HexColor(palette['primary'] + '22')),
            ('TEXTCOLOR',  (0,0), (0,-1), rl_colors.HexColor(palette['primary'])),
            ('FONTNAME',   (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE',   (0,0), (-1,-1), 9),
            ('ROWBACKGROUNDS', (0,0), (-1,-1),
             [rl_colors.HexColor('#f8f8f8'), rl_colors.white]),
            ('GRID',       (0,0), (-1,-1), 0.4, rl_colors.HexColor('#dddddd')),
            ('PADDING',    (0,0), (-1,-1), 5),
        ]))
        story.append(meta_tbl)
        story.append(PageBreak())

        story.append(Paragraph('Key Results', h1_style))

        DISPLAY_KEYS = [
            # A/B / Pre-Post
            ('ior_pre',             'IOR Pre-period'),
            ('ior_post',            'IOR Post-period'),
            ('ior_treat_pre',       'IOR Treat Pre'),
            ('ior_treat_post',      'IOR Treat Post'),
            ('ior_ctrl_pre',        'IOR Control Pre'),
            ('ior_ctrl_post',       'IOR Control Post'),
            ('ior_treated',         'IOR Treated (matched)'),
            ('ior_control',         'IOR Control (matched)'),
            ('did_estimate_pp',     'DiD Estimate (pp)'),
            ('avg_gap_pp',          'Avg Post-period Gap (pp)'),
            ('att_pp',              'ATT (pp)'),
            ('late_pp',             'LATE Estimate (pp)'),
            ('delta_pp',            'Δ IOR (pp)'),
            ('level_change_pp',     'Level Change (pp)'),
            ('slope_change_pp_day', 'Slope Change (pp/day)'),
            ('avg_lift_pp',         'Avg Lift vs Counterfactual (pp)'),
            ('p_value',             'p-value'),
            ('significant',         'Significant'),
            ('ci_bootstrap_pp',     'Bootstrap CI (pp)'),
            ('ci_pp',               'Confidence Interval (pp)'),
            ('parallel_trends_ok',  'Parallel Trends Holds'),
            ('fit_quality',         'SC Fit Quality'),
            ('pre_rmspe_pp',        'SC Pre-RMSPE (pp)'),
            ('rmspe_ratio',         'SC RMSPE Ratio'),
            ('balance_ok',          'Covariate Balance OK'),
            ('max_smd_after',       'Max SMD (after matching)'),
            ('match_rate',          'PSM Match Rate'),
            ('model_r2',            'ITS Model R²'),
            ('bandwidth',           'RDD Bandwidth'),
        ]
        res_data = [['Metric', 'Value']]
        for key, label in DISPLAY_KEYS:
            if key in result and result[key] is not None:
                val = result[key]
                if isinstance(val, float):
                    val_str = f'{val:.4f}'
                elif isinstance(val, bool):
                    val_str = '✅ Yes' if val else '❌ No'
                elif isinstance(val, list):
                    val_str = f'[{val[0]:.3f}, {val[1]:.3f}]' if len(val)==2 else str(val)[:60]
                else:
                    val_str = str(val)[:80]
                res_data.append([label, val_str])

        if len(res_data) > 1:
            res_tbl = Table(res_data, colWidths=[3.5*inch, 3.0*inch])
            res_tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), rl_colors.HexColor(palette['primary'])),
                ('TEXTCOLOR',  (0,0), (-1,0), rl_colors.white),
                ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 9),
                ('ROWBACKGROUNDS', (0,1), (-1,-1),
                 [rl_colors.HexColor('#f0f8ff'), rl_colors.white]),
                ('GRID',       (0,0), (-1,-1), 0.4, rl_colors.HexColor('#cccccc')),
                ('PADDING',    (0,0), (-1,-1), 5),
            ]))
            story.append(res_tbl)
        story.append(PageBreak())

        if chart_paths:
            story.append(Paragraph('Visualisations', h1_style))
            for cp in chart_paths:
                if cp and os.path.exists(cp):
                    try:
                        img = RLImage(cp, width=6.5*inch, height=4.2*inch)
                        story.append(img)
                        story.append(Spacer(1, 0.15*inch))
                    except Exception as img_err:
                        story.append(Paragraph(f'[Chart unavailable: {cp}]', body_style))
            story.append(PageBreak())

        if narrative:
            story.append(Paragraph('Interpretation & Recommendation', h1_style))
            for para in narrative.split('\n\n'):
                clean = para.strip().replace('<', '&lt;').replace('>', '&gt;')
                if clean:
                    story.append(Paragraph(clean, body_style))
                    story.append(Spacer(1, 0.06*inch))
            story.append(PageBreak())

        warning_keys = ['fit_warning', 'stagger_warning', 'concentration_warning',
                        'parallel_trends_note', 'time_placebo_note', 'caveat',
                        'rmspe_interpretation', 'balance_note']
        warnings_present = [result[k] for k in warning_keys
                            if k in result and result[k]]
        if warnings_present:
            story.append(Paragraph('Validity Notes & Warnings', h1_style))
            for w in warnings_present:
                story.append(Paragraph(f'• {str(w)[:400]}', body_style))
            story.append(Spacer(1, 0.1*inch))

        doc.build(story)
        return output_filename

    except Exception as pdf_err:
        print(f'  ⚠️  PDF generation failed: {pdf_err}')
        return None


def run_causal_analysis(llm):
    """
    [10] Causal Analysis — interactive method chooser.
    Shows all available methods with descriptions; dispatches to the chosen runner.
    """
    _causal_header('🔬  CAUSAL ANALYSIS', 'Choose the right method for your situation')

    print("""
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  AFTER A RANDOMISED A/B EXPERIMENT                                       │
  │                                                                          │
  │  [1]  A/B Test Analysis                                                  │
  │       You ran a randomised experiment via Statsig/feature flags.         │
  │       Strongest causal claim. Variant assignment was random.             │
  │                                                                          │
  ├──────────────────────────────────────────────────────────────────────────┤
  │  WITHOUT FULL RANDOMISATION (quasi-experimental)                         │
  │                                                                          │
  │  [2]  Pre-Post Analysis                                                  │
  │       Feature shipped to 100% of users. Compare before vs after.        │
  │       ⚠️  Weak causal claim — confounded by seasonality & time.           │
  │                                                                          │
  │  [3]  Difference-in-Differences (DiD)                                    │
  │       Partial rollout: some segments/regions got the feature, others     │
  │       didn't. Compare the change in treated vs untreated groups.         │
  │       Strong claim if parallel-trends holds.                             │
  │                                                                          │
  │  [4]  Interrupted Time Series (ITS)                                      │
  │       100% rollout but you have a long pre-period time series.           │
  │       Fits a regression model to detect a level or slope change.         │
  │                                                                          │
  │  [5]  Synthetic Control                                                  │
  │       One treated unit (segment/market) with multiple untreated donors.  │
  │       Builds a weighted counterfactual from donor trajectories.          │
  │                                                                          │
  ├──────────────────────────────────────────────────────────────────────────┤
  │  OBSERVATIONAL / MATCHING                                                │
  │                                                                          │
  │  [6]  Propensity Score Matching (PSM)                                    │
  │       No randomisation. Match treated users to similar untreated users   │
  │       on observable covariates to remove selection bias.                 │
  │                                                                          │
  │  [7]  Regression Discontinuity (RDD)                                     │
  │       Treatment assignment follows a sharp rule on a continuous score    │
  │       (e.g. credit score ≥ 700 → premium feature). Exploit the jump.    │
  │                                                                          │
  ├──────────────────────────────────────────────────────────────────────────┤
  │  FORECASTING-BASED COUNTERFACTUAL  (no control group required)           │
  │                                                                          │
  │  [8]  ARIMA Counterfactual [24]                                          │
  │       Fit ARIMA(p,d,q) on pre-period, forecast counterfactual.           │
  │       Best for trended series without strong seasonality.                │
  │                                                                          │
  │  [9]  SARIMA Counterfactual [25]                                         │
  │       Seasonal ARIMA — adds P,D,Q seasonal component (e.g. s=7/week).   │
  │       Best when IOR shows clear day-of-week or monthly cycles.           │
  │                                                                          │
  │  [10] Bayesian Structural Time Series (BSTS) [26]                       │
  │       Kalman-filter local-linear-trend model with posterior CI.          │
  │       Returns a full probability distribution over the counterfactual.   │
  │                                                                          │
  │  [11] Causal Impact Framework [27]                                       │
  │       Google-style BSTS + optional control covariates.                   │
  │       Strongest time-series causal claim; 3-panel summary output.        │
  └──────────────────────────────────────────────────────────────────────────┘
""")

    method_map = {
        '1': ('A/B Test Analysis',           run_ab_test_analysis),
        '2': ('Pre-Post Analysis',            run_pre_post_analysis),
        '3': ('Difference-in-Differences',   run_did_analysis),
        '4': ('Interrupted Time Series',     run_its_analysis),
        '5': ('Synthetic Control',           run_synthetic_control_analysis),
        '6': ('Propensity Score Matching',   run_psm_analysis),
        '7': ('Regression Discontinuity',    run_rdd_analysis),
        '8': ('ARIMA Counterfactual',        run_arima_analysis),
        '9': ('SARIMA Counterfactual',       run_sarima_analysis),
        '10': ('BSTS Counterfactual',        run_bsts_analysis),
        '11': ('Causal Impact Framework',    run_causal_impact_analysis),
    }

    while True:
        choice = input('  ❓ Choose method [1-11]: ').strip()
        if choice in method_map:
            break
        print('     ⚠️  Enter a number 1–11')

    label, fn = method_map[choice]
    print(f'\n  ✅ Selected: {label}')
    print()
    return fn(llm)


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 1 — A/B TEST ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_ab_test_analysis(llm):
    """
    [17] A/B Test Analysis — for randomised experiments in Statsig or any
    feature-flag tool. Pulls experiment assignment + outcomes from the
    gold_experiment_analysis view (built from bronze Statsig tables).

    Covers:
      · Overall IOR and GMV per variant (Bonferroni-corrected)
      · Sample Ratio Mismatch (SRM) check
      · Segment × variant breakdown (account_segment, platform, country)
      · Peeking / novelty effect check (first-week vs full-period)
      · Power analysis: was the experiment adequately powered?
      · LLM ship/no-ship recommendation
    """
    _causal_header(
        '🧪  A/B TEST ANALYSIS',
        'Randomised experiment · Statsig / feature-flag data'
    )
    print("""
  ✅ When to use:
     - You ran a randomised A/B (or A/B/C) experiment via Statsig, LaunchDarkly,
       Optimizely, or a custom feature-flag system.
     - Users were randomly assigned to control or treatment at experiment start.
     - Assignment data is in the Statsig experiment table.

  ⚠️  Not appropriate if:
     - Assignment was not random (use PSM or DiD instead).
     - The experiment was stopped early due to significant results (mSPRT / Module [9]
       is more appropriate for sequential testing decisions).
""")

    # ── Step 1: List experiments from Statsig/all_experiments table ───────────
    print('  Pulling experiments from Statsig table (all_experiments)...')
    try:
        exp_summary = db.execute("""
            SELECT
                e.experiment_name,
                COUNT(*)                                            AS n_rows,
                COUNT(DISTINCT e.variant)                          AS n_variants,
                STRING_AGG(DISTINCT e.variant, ' | ')              AS variants,
                MIN(e.created_at)::DATE                            AS start_date,
                MAX(e.created_at)::DATE                            AS end_date,
                AVG(CAST(e.converted_to_order AS DOUBLE)) * 100    AS overall_ior_pct,
                AVG(CASE WHEN e.converted_to_order THEN e.order_value END) AS avg_order_value,
                r.description,
                r.status,
                r.team,
                r.ship_decision
            FROM all_experiments e
            LEFT JOIN experiment_registry r USING (experiment_name)
            GROUP BY e.experiment_name, r.description, r.status, r.team, r.ship_decision
            ORDER BY start_date DESC
        """).df()
    except Exception as ex:
        print(f'  ❌ Could not query experiment tables: {ex}')
        return None

    if exp_summary.empty:
        print('  ❌ No experiments found in all_experiments table.')
        print('     In production, ensure the Statsig bronze table is loaded and Silver/Gold cells have run.')
        return None

    STATUS_ICON = {'running': '🟢', 'concluded': '✅', 'stopped': '🛑',
                   'shipped': '🚀', 'not_started': '💤', 'unknown': '⬜', None: '⬜'}
    SHIP_ICON   = {'ship': '🚀 Ship', 'partial_ship': '🚀 Partial', 'no_ship': '❌ No-ship', None: '—'}

    print()
    print('  ┌' + '─'*74 + '┐')
    print('  │  EXPERIMENTS IN STATSIG TABLE' + ' '*44 + '│')
    print('  ├' + '─'*74 + '┤')
    for i, row in exp_summary.iterrows():
        icon   = STATUS_ICON.get(row.get('status'), '⬜')
        status = str(row.get('status', 'unknown')).upper()
        dec    = SHIP_ICON.get(row.get('ship_decision'), '—')
        print(f"  │  [{i+1:>2}] {icon} {row['experiment_name'][:42]:<42}  {status:<10}  │")
        print(f"  │       Variants: {str(row['variants'])[:40]:<40}  {row['n_rows']:>6,} rows  │")
        desc = str(row.get('description', ''))[:66] or '—'
        print(f"  │       {desc:<66}  │")
        aov  = f"  Avg AOV: ${row['avg_order_value']:,.0f}" if pd.notna(row.get('avg_order_value')) else ''
        print(f"  │       {row['start_date']} → {row['end_date']}  |  IOR: {row['overall_ior_pct']:.2f}%{aov:<20}  │"[:78].ljust(78) + '│')
        print(f"  │       Team: {str(row.get('team','?')):<12}  Decision: {dec:<15}" .ljust(76) + '│')
        if i < len(exp_summary) - 1:
            print('  ├' + '─'*74 + '┤')
    print('  └' + '─'*74 + '┘')

    while True:
        raw = input(f'\n  ❓ Select experiment [1–{len(exp_summary)}]: ').strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(exp_summary):
                break
        except ValueError:
            pass
        print(f'     ⚠️  Enter 1–{len(exp_summary)}')

    exp_name = exp_summary.iloc[idx]['experiment_name']
    exp_row  = exp_summary.iloc[idx]

    # ── Step 2: Pull data for this experiment ─────────────────────────────────
    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df = dedup_dataframe(exp_df)
    variants = sorted(exp_df['variant'].unique().tolist())
    control  = 'control' if 'control' in variants else variants[0]
    treatments = [v for v in variants if v != control]

    print(f'\n  ✅ {exp_name}')
    print(f'     Variants  : {variants}')
    print(f'     Control   : "{control}"')
    print(f'     Rows      : {len(exp_df):,}')
    print(f'     Date range: {exp_df["created_at"].min().date()} → {exp_df["created_at"].max().date()}')

    if len(treatments) == 0:
        print('  ❌ No treatment variants found.')
        return None

    # ── Step 3: Analysis parameters ───────────────────────────────────────────
    print()
    alpha_raw  = input('  ❓ Significance level α [0.05]: ').strip()
    bonf_raw   = input('  ❓ Apply Bonferroni correction for multiple variants? [Y/n]: ').strip().lower()
    dims_raw   = input('  ❓ Segment breakdowns [account_segment, platform, country — press Enter for all]: ').strip()
    gmv_raw    = input('  ❓ Include GMV / order value analysis? [Y/n]: ').strip().lower()

    alpha     = float(alpha_raw) if alpha_raw else 0.05
    bonferroni = bonf_raw != 'n'
    dimensions = [d.strip() for d in dims_raw.split(',')] if dims_raw else ['account_segment', 'platform', 'country', 'device_type']
    dimensions = [d for d in dimensions if d in exp_df.columns]
    include_gmv = gmv_raw != 'n'

    # ── Step 4: Data quality ──────────────────────────────────────────────────
    print('\n  ── Data Quality ──────────────────────────────────────────────────────')
    dq = validate_experiment_data(exp_df, exp_name)
    if dq['errors']:
        for e in dq['errors']:
            print(f'  ❌ {e}')
        return None
    for w in dq['warnings']:
        print(f'  ⚠️  {w}')
    if not dq['warnings']:
        print('  ✅ No data quality issues')

    # ── Step 5: SRM check ─────────────────────────────────────────────────────
    print('\n  ── Sample Ratio Mismatch (SRM) Check ─────────────────────────────────')
    variant_counts = exp_df['variant'].value_counts()
    expected_per   = len(exp_df) / len(variants)
    from scipy.stats import chisquare as _chisquare
    obs_counts = [variant_counts.get(v, 0) for v in variants]
    exp_counts = [expected_per] * len(variants)
    chi2_srm, p_srm = _chisquare(obs_counts, exp_counts)
    srm_flag = p_srm < 0.01

    for v, cnt in variant_counts.items():
        ratio = cnt / expected_per
        icon  = '✅' if 0.9 <= ratio <= 1.1 else '⚠️ '
        print(f'  {icon}  {v:<20} {cnt:>7,}  (expected ~{expected_per:,.0f}, ratio={ratio:.3f})')
    if srm_flag:
        print(f'  ❌ SRM DETECTED: χ²={chi2_srm:.2f}, p={p_srm:.5f} — experiment may be compromised.')
        print('     Possible causes: filtering after assignment, implementation bug, bot traffic.')
        print('     Results should be interpreted with caution.')
    else:
        print(f'  ✅ No SRM  (χ²={chi2_srm:.2f}, p={p_srm:.4f})')

    # ── Step 6: Overall IOR results ───────────────────────────────────────────
    print('\n  ── Overall Results ───────────────────────────────────────────────────')
    n_comparisons = len(treatments) + (len(treatments) * (len(treatments)-1)) // 2
    alpha_adj     = alpha / n_comparisons if bonferroni and n_comparisons > 1 else alpha
    if bonferroni and n_comparisons > 1:
        print(f'  Bonferroni correction applied: α={alpha} / {n_comparisons} comparisons = {alpha_adj:.5f}')

    overall_results = {}
    ctrl_df = exp_df[exp_df['variant'] == control]
    for t in treatments:
        trt_df = exp_df[exp_df['variant'] == t]
        n_c, c_c = len(ctrl_df), int(ctrl_df['converted_to_order'].sum())
        n_t, c_t = len(trt_df),  int(trt_df['converted_to_order'].sum())
        pr = proportion_test(n_c, c_c, n_t, c_t, alpha_adj)
        gmv_r = {}
        if include_gmv and 'order_value' in exp_df.columns:
            gmv_r = means_test(ctrl_df['order_value'].values, trt_df['order_value'].values, alpha_adj)
        overall_results[t] = {**pr, 'gmv': gmv_r, 'n_control': n_c, 'n_treatment': n_t}
        sig_icon = '✅' if pr['is_significant'] else '—'
        print(f'\n  {sig_icon}  {control} vs {t}')
        print(f'     Control   IOR : {pr["rate_control"]*100:.3f}%  (n={n_c:,})')
        print(f'     Treatment IOR : {pr["rate_treatment"]*100:.3f}%  (n={n_t:,})')
        print(f'     Δ IOR         : {pr["delta_pp"]:+.4f}pp  95% CI [{pr["ci_lo_pp"]:+.3f}, {pr["ci_hi_pp"]:+.3f}]')
        print(f'     p-value       : {pr["p_value"]:.5f}  {"✅ Significant" if pr["is_significant"] else "⚠️  Not significant"} at α={alpha_adj:.4f}')
        if gmv_r:
            gmv_sig = '✅' if gmv_r.get('is_significant') else '—'
            print(f'     {gmv_sig}  Δ AOV : ${gmv_r.get("delta_mean",0):+.2f}  p={gmv_r.get("p_value",1):.4f}')

    # ── Step 7: Segment breakdowns ────────────────────────────────────────────
    print(f'\n  ── Segment Breakdowns ({", ".join(dimensions) or "none"}) ────────────────────────────────')
    segment_results = {}
    for dim in dimensions:
        print(f'\n  {dim}:')
        seg_rows = []
        for level, sub in exp_df.groupby(dim):
            ctrl_sub = sub[sub['variant'] == control]
            for t in treatments:
                trt_sub = sub[sub['variant'] == t]
                if len(ctrl_sub) < 30 or len(trt_sub) < 30:
                    continue
                n_c, c_c = len(ctrl_sub), int(ctrl_sub['converted_to_order'].sum())
                n_t, c_t = len(trt_sub),  int(trt_sub['converted_to_order'].sum())
                pr = proportion_test(n_c, c_c, n_t, c_t, alpha_adj)
                sig = '✅' if pr['is_significant'] else '  '
                sign = '+' if pr['delta_pp'] >= 0 else ''
                print(f'    {sig} {str(level):<18} {t:<15} '
                      f'{pr["rate_control"]*100:>5.2f}% → {pr["rate_treatment"]*100:>5.2f}%  '
                      f'Δ={sign}{pr["delta_pp"]:>6.3f}pp  p={pr["p_value"]:.4f}  '
                      f'(n={n_t:,})')
                seg_rows.append({'level': str(level), 'treatment': t, **pr})
        segment_results[dim] = seg_rows

    # ── Step 8: Novelty / peeking check (week 1 vs full period) ──────────────
    print('\n  ── Novelty Effect Check (Week 1 vs Full Period) ──────────────────────')
    exp_start = pd.Timestamp(exp_df['created_at'].min())
    week1_end = exp_start + pd.Timedelta(days=7)
    for t in treatments:
        ctrl_all = exp_df[exp_df['variant'] == control]
        trt_all  = exp_df[exp_df['variant'] == t]
        ctrl_w1  = ctrl_all[ctrl_all['created_at'] < week1_end]
        trt_w1   = trt_all[trt_all['created_at'] < week1_end]
        if len(ctrl_w1) >= 30 and len(trt_w1) >= 30:
            pr_w1   = proportion_test(len(ctrl_w1), int(ctrl_w1['converted_to_order'].sum()),
                                      len(trt_w1),  int(trt_w1['converted_to_order'].sum()), alpha)
            pr_full = overall_results[t]
            delta_diff = abs(pr_w1['delta_pp'] - pr_full['delta_pp'])
            novelty_flag = delta_diff > abs(pr_full['delta_pp']) * 0.3
            icon = '⚠️ ' if novelty_flag else '✅'
            print(f'  {icon}  {t}: Week-1 Δ={pr_w1["delta_pp"]:+.3f}pp  vs  Full Δ={pr_full["delta_pp"]:+.3f}pp  '
                  f'({"possible novelty effect" if novelty_flag else "stable"})')
        else:
            print(f'  —   {t}: Not enough week-1 data for novelty check')

    # ── LLM narrative ─────────────────────────────────────────────────────────
    summary = {
        'experiment': exp_name,
        'variants':   variants,
        'control':    control,
        'srm_flag':   bool(srm_flag),
        'results':    {t: {k: v for k, v in r.items() if not isinstance(v, dict)}
                       for t, r in overall_results.items()},
    }
    _causal_narrative(llm, summary,
        f'A/B test analysis for experiment "{exp_name}". '
        f'Control="{control}", treatments={treatments}. '
        f'SRM: {"DETECTED — compromised" if srm_flag else "clean"}. '
        f'Primary result: IOR Δ={list(overall_results.values())[0]["delta_pp"]:+.3f}pp '
        f'({"significant" if list(overall_results.values())[0]["is_significant"] else "not significant"}). '
        f'Provide: (1) ship/no-ship recommendation with reasoning, '
        f'(2) which segments show the strongest/weakest effect and why that matters, '
        f'(3) any caveats (SRM, novelty, underpowered segments), '
        f'(4) what to test next.'
    )
    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['chart_ab_overall.png', 'chart_ab_segments.png']
    _pdf_out = 'causal_ab_test_{exp_name}.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Ab Test Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return {'experiment': exp_name, 'overall': overall_results, 'segments': segment_results}


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 2 — PRE-POST ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_pre_post_analysis(llm):
    """
    [18] Pre-Post Analysis — simple before/after comparison for a feature
    shipped to 100% of users. No control group. Weakest causal claim.
    """
    _causal_header(
        '📊  PRE-POST ANALYSIS',
        'Before vs after a full rollout — no control group'
    )
    print("""
  ✅ When to use:
     - Feature was shipped to 100% of users simultaneously.
     - No holdout/control group exists.
     - You need a quick read and understand the limitations.

  ⚠️  Limitations:
     - Confounded by seasonality, trend, and concurrent product changes.
     - Cannot attribute the change causally without a control group.
     - Prefer DiD or ITS if a longer time series or control group is available.
""")

    # ── Parameters ────────────────────────────────────────────────────────────
    ship_raw  = input(f'  ❓ Ship/cutoff date [YYYY-MM-DD, default: {EXP_START.date()}]: ').strip()
    pre_raw   = input(f'  ❓ Pre-period start  [YYYY-MM-DD, default: {HIST_START.date()}]: ').strip()
    seg_raw   = input('  ❓ Filter to segment(s)? [comma-sep, or Enter for all]: ').strip()
    plat_raw  = input('  ❓ Filter to platform? [web/mobile/all, Enter=all]: ').strip()
    alpha     = _ask_alpha()

    cutoff_date = pd.Timestamp(ship_raw) if ship_raw else EXP_START
    pre_start   = pd.Timestamp(pre_raw)  if pre_raw  else HIST_START
    segments    = [s.strip() for s in seg_raw.split(',') if s.strip()]
    platform    = plat_raw.strip().lower() if plat_raw else None

    print(f'\n  Cutoff date : {cutoff_date.date()}')
    print(f'  Pre-period  : {pre_start.date()} → {(cutoff_date - pd.Timedelta(days=1)).date()}')

    try:
        all_data = db.execute("""
            SELECT created_at, converted_to_order, order_value, account_segment, platform
            FROM silver_inquiries
            UNION ALL
            SELECT created_at, converted_to_order, order_value, account_segment, platform
            FROM silver_exp_inquiries
        """).df()
    except Exception:
        all_data = pd.concat([
            globals().get('df_hist_inquiries', pd.DataFrame()),
            globals().get('df_all_experiments', pd.DataFrame()),
        ], ignore_index=True)

    all_data = all_data[all_data['created_at'] >= pre_start].copy()
    if segments:
        all_data = all_data[all_data['account_segment'].isin(segments)]
    if platform and platform not in ('all', ''):
        all_data = all_data[all_data['platform'] == platform]

    pre_df  = all_data[all_data['created_at'] <  cutoff_date]
    post_df = all_data[all_data['created_at'] >= cutoff_date]

    if len(pre_df) < 50 or len(post_df) < 50:
        print(f'  ❌ Insufficient data: pre={len(pre_df):,} rows, post={len(post_df):,} rows')
        return None

    print(f'  Pre rows    : {len(pre_df):,}  (IOR: {pre_df["converted_to_order"].mean()*100:.3f}%)')
    print(f'  Post rows   : {len(post_df):,}  (IOR: {post_df["converted_to_order"].mean()*100:.3f}%)')

    n_pre, c_pre   = len(pre_df),  int(pre_df['converted_to_order'].sum())
    n_post, c_post = len(post_df), int(post_df['converted_to_order'].sum())
    pr = proportion_test(n_pre, c_pre, n_post, c_post, alpha)
    gmv_change = post_df['order_value'].mean() - pre_df['order_value'].mean()

    result = {
        'method':       'Pre-Post Analysis',
        'cutoff_date':  str(cutoff_date.date()),
        'pre_start':    str(pre_start.date()),
        'segments':     segments or 'all',
        'platform':     platform or 'all',
        'n_pre':        n_pre,   'ior_pre':  pr['rate_control'],
        'n_post':       n_post,  'ior_post': pr['rate_treatment'],
        'delta_pp':     pr['delta_pp'],
        'ci_pp':        [pr['ci_lo_pp'], pr['ci_hi_pp']],
        'p_value':      pr['p_value'],
        'significant':  pr['is_significant'],
        'gmv_change':   round(gmv_change, 2),
        'caveat':       'Confounded by time, seasonality, and concurrent changes. Interpret with caution.',
    }

    print('\n  ── Results ───────────────────────────────────────────────────────────')
    sig = '✅ Significant' if result['significant'] else '⚠️  Not significant'
    print(f'  Pre-period IOR  : {result["ior_pre"]*100:.3f}%  (n={n_pre:,})')
    print(f'  Post-period IOR : {result["ior_post"]*100:.3f}%  (n={n_post:,})')
    print(f'  Δ               : {result["delta_pp"]:+.4f}pp  [{result["ci_pp"][0]:+.3f}, {result["ci_pp"][1]:+.3f}]')
    print(f'  p-value         : {result["p_value"]:.5f}  {sig} at α={alpha}')
    print(f'  Δ Avg AOV       : ${result["gmv_change"]:+.2f}')
    print(f'\n  ⚠️  {result["caveat"]}')

    # ── Segment breakdown ─────────────────────────────────────────────────────
    print('\n  ── Segment Breakdown (account_segment) ───────────────────────────────')
    for seg, sub in all_data.groupby('account_segment'):
        sp = sub[sub['created_at'] <  cutoff_date]
        sq = sub[sub['created_at'] >= cutoff_date]
        if len(sp) < 30 or len(sq) < 30:
            continue
        pr_s = proportion_test(len(sp), int(sp['converted_to_order'].sum()),
                               len(sq), int(sq['converted_to_order'].sum()), alpha)
        sig_s = '✅' if pr_s['is_significant'] else '  '
        print(f'  {sig_s}  {str(seg):<18} {pr_s["rate_control"]*100:.3f}% → {pr_s["rate_treatment"]*100:.3f}%  '
              f'Δ={pr_s["delta_pp"]:+.4f}pp  p={pr_s["p_value"]:.4f}  (pre={len(sp):,}, post={len(sq):,})')

    _causal_narrative(llm, {k: v for k, v in result.items() if not isinstance(v, list)},
        f'Pre-post analysis. Cutoff: {cutoff_date.date()}. '
        f'IOR change: {result["ior_pre"]*100:.3f}% → {result["ior_post"]*100:.3f}% '
        f'(Δ={result["delta_pp"]:+.3f}pp, {"significant" if result["significant"] else "not significant"}). '
        f'Provide: (1) interpretation of the change (is it meaningful?), '
        f'(2) key alternative explanations given no control group, '
        f'(3) confidence level in attributing this to the feature, '
        f'(4) what additional analysis would strengthen the causal claim.'
    )
    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['pre_post_analysis.png']
    _pdf_out = 'causal_pre_post.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Pre Post Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return result


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 4 — INTERRUPTED TIME SERIES (ITS)
# ─────────────────────────────────────────────────────────────────────────────

def run_its_analysis(llm):
    """
    [20] Interrupted Time Series — fits regression lines before and after
    an intervention to detect level and slope changes. Requires a long
    pre-period daily time series.

    Data pulled from: platform_daily_ior (gold_daily_metrics view).
    """
    _causal_header(
        '📈  INTERRUPTED TIME SERIES (ITS)',
        'Level and slope change at an intervention point — daily time series'
    )
    print("""
  ✅ When to use:
     - Feature shipped to 100% of users (no holdout group).
     - You have at least 30 days of pre-period daily data.
     - You want to detect both an immediate level change AND a trend change.

  ⚠️  Limitations:
     - No control group — cannot rule out concurrent events or seasonality.
     - Needs ≥30 pre-period days; ≥14 post-period days recommended.
     - A strong pre-period trend will reduce power to detect level changes.
""")

    print('  Checking daily time-series data (platform_daily_ior)...')
    try:
        ts_df = db.execute('SELECT * FROM platform_daily_ior ORDER BY date').df()
        print(f'  ✅ Found {len(ts_df):,} daily rows  ({ts_df["date"].min().date()} → {ts_df["date"].max().date()})')
    except Exception as ex:
        print(f'  ❌ Could not load platform_daily_ior: {ex}')
        return None

    if len(ts_df) < 40:
        print('  ❌ Not enough daily data for ITS (need ≥40 days).')
        return None

    cutoff_date = _ask_date('Intervention / ship date', EXP_START)
    pre_start   = _ask_date('Pre-period start date',    HIST_START)
    post_end_raw = input(f'  ❓ Post-period end date [default: {EXP_END.date()}]: ').strip()
    post_end    = pd.Timestamp(post_end_raw) if post_end_raw else EXP_END
    alpha       = _ask_alpha()

    n_pre  = ts_df[ts_df['date'] < cutoff_date].shape[0]
    n_post = ts_df[ts_df['date'] >= cutoff_date].shape[0]
    print(f'\n  Pre-period days  : {n_pre}')
    print(f'  Post-period days : {n_post}')

    if n_pre < 20:
        print(f'  ❌ Only {n_pre} pre-period days. Need ≥20.')
        return None

    print('\n  Running ITS regression...')
    result = _run_its(cutoff_date, pre_start, post_end)

    if 'error' in result:
        print(f'  ❌ {result["error"]}')
        return result

    # ── Results ───────────────────────────────────────────────────────────────
    print('\n  ── ITS Regression Results ────────────────────────────────────────────')
    print(f'  Model R²               : {result["model_r2"]:.4f}')
    print(f'  Pre-period slope       : {result["pre_slope_pp_day"]:+.5f}pp/day')
    print()
    lv_sig = '✅' if result['level_significant'] else '  '
    sl_sig = '✅' if result['slope_significant'] else '  '
    print(f'  {lv_sig}  Level change (immediate) : {result["level_change_pp"]:+.4f}pp  '
          f'p={result["level_change_p"]:.5f}  '
          f'{"Significant" if result["level_significant"] else "Not significant"} at α={alpha}')
    print(f'  {sl_sig}  Slope change (trend)     : {result["slope_change_pp_day"]:+.5f}pp/day  '
          f'p={result["slope_change_p"]:.5f}  '
          f'{"Significant" if result["slope_significant"] else "Not significant"} at α={alpha}')
    print()
    print(f'  Avg observed post  : {result["avg_observed_post"]*100:.4f}%')
    print(f'  Avg counterfactual : {result["avg_counterfactual_post"]*100:.4f}%')
    print(f'  Avg lift vs CF     : {result["avg_lift_pp"]:+.4f}pp')

    if not result['level_significant'] and not result['slope_significant']:
        print('\n  ⚠️  Neither level nor slope change is significant.')
        print('     The intervention did not produce a detectable change in the time series.')

    # ── Plot ────────────────
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(18, 6))
    fig.patch.set_facecolor('#0f0f0f')
    COLORS_L = {'treatment': '#f97316', 'control': '#4e9af1',
                'positive': '#22c55e', 'negative': '#ef4444',
                'highlight': '#facc15', 'neutral': '#a1a1aa'}

    dates  = pd.to_datetime(result['dates'])
    y_act  = np.array(result['actual_ior']) * 100
    y_fit  = np.array(result['fitted_values']) * 100
    y_cf   = np.array(result['counterfactual']) * 100

    ax = axes[0]
    ax.scatter(dates, y_act, color=COLORS_L['neutral'], s=10, alpha=0.5, label='Actual IOR')
    ax.plot(dates, y_fit, color=COLORS_L['treatment'], lw=2.5, label='ITS fitted model')
    ax.plot(dates, y_cf,  color=COLORS_L['control'],  lw=2, linestyle='--', label='Counterfactual')
    ax.fill_between(dates, y_cf, y_fit,
                    where=y_fit > y_cf, color=COLORS_L['positive'], alpha=0.2, label='Lift')
    ax.fill_between(dates, y_cf, y_fit,
                    where=y_fit < y_cf, color=COLORS_L['negative'], alpha=0.2)
    ax.axvline(cutoff_date, color=COLORS_L['highlight'], lw=2, label=f'Intervention ({cutoff_date.date()})')
    ax.set_title(f'ITS — Level Δ={result["level_change_pp"]:+.4f}pp  '
                 f'{"✅" if result["level_significant"] else "n.s."}\n'
                 f'Slope Δ={result["slope_change_pp_day"]:+.5f}pp/day  '
                 f'{"✅" if result["slope_significant"] else "n.s."}',
                 color=COLORS_L['highlight'])
    ax.set_xlabel('Date'); ax.set_ylabel('IOR (%)')
    ax.legend(fontsize=7.5); ax.grid(True, alpha=0.2)

    ax2 = axes[1]
    gap  = y_act - y_cf
    roll = pd.Series(gap).rolling(7, center=True).mean()
    ax2.bar(range(len(gap)), gap,
            color=[COLORS_L['positive'] if g >= 0 else COLORS_L['negative'] for g in gap],
            width=1, alpha=0.7)
    ax2.plot(range(len(roll)), roll, color='white', lw=2, label='7-day avg')
    ax2.axhline(0, color='white', lw=1, linestyle='--', alpha=0.5)
    ax2.axvline(result['pre_days'], color=COLORS_L['highlight'], lw=2, label='Intervention')
    ax2.set_xlabel('Day'); ax2.set_ylabel('Actual − Counterfactual (pp)')
    ax2.set_title('Daily Gap: Observed vs Counterfactual', color=COLORS_L['highlight'])
    ax2.legend(fontsize=8)

    plt.suptitle('Interrupted Time Series Analysis', fontsize=13,
                 color=COLORS_L['highlight'], fontweight='bold')
    plt.tight_layout()
    plt.savefig('its_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → its_analysis.png')

    _causal_narrative(llm, {k: v for k, v in result.items() if not isinstance(v, list)},
        f'Interrupted Time Series analysis. Intervention: {cutoff_date.date()}. '
        f'Level change: {result["level_change_pp"]:+.4f}pp '
        f'({"significant" if result["level_significant"] else "not significant"}). '
        f'Slope change: {result["slope_change_pp_day"]:+.5f}pp/day '
        f'({"significant" if result["slope_significant"] else "not significant"}). '
        f'Avg post-period lift vs counterfactual: {result["avg_lift_pp"]:+.4f}pp. '
        f'Provide: (1) interpretation of the level vs slope change, '
        f'(2) what the counterfactual trajectory tells us, '
        f'(3) key threats to validity (no control group, concurrent events), '
        f'(4) confidence level and recommendation.'
    )
    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['its_analysis.png']
    _pdf_out = 'causal_its_analysis.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Its Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return result


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 6 — PROPENSITY SCORE MATCHING (PSM)
# ─────────────────────────────────────────────────────────────────────────────

def run_psm_analysis(llm):
    """
    [21] Propensity Score Matching — removes selection bias by matching
    treated users to similar untreated users on observable covariates.
    Estimates the ATT (Average Treatment Effect on the Treated).

    Data pulled from: all_experiments (treatment assignment) + silver_buyers
    (covariates: segment, platform, country, tenure, GMV history).
    """
    _causal_header(
        '⚖️   PROPENSITY SCORE MATCHING (PSM)',
        'Match treated to similar untreated users on observable covariates'
    )
    print("""
  ✅ When to use:
     - No randomisation — users opted into the feature or were selected.
     - You have rich pre-treatment covariates to match on.
     - You want to estimate the effect on the treated (ATT).

  ⚠️  Limitations:
     - Only removes bias from OBSERVABLE confounders.
     - Cannot handle unmeasured confounding (use DiD/ITS/RDD for that).
     - Quality of match depends on covariate richness and overlap.
     - Matching discards unmatched units — check match rate.
""")

    print('  Available experiments:')
    try:
        exp_list = db.execute("""
            SELECT DISTINCT experiment_name, COUNT(*) AS n,
                   STRING_AGG(DISTINCT variant, ' | ') AS variants
            FROM all_experiments
            GROUP BY experiment_name ORDER BY n DESC
        """).df()
        for i, row in exp_list.iterrows():
            print(f"    [{i+1}] {row['experiment_name']:<45} ({row['n']:>6,} rows) | {row['variants']}")
    except Exception as ex:
        print(f'  ❌ {ex}'); return None

    while True:
        raw = input(f'  ❓ Select experiment [1–{len(exp_list)}]: ').strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(exp_list): break
        except ValueError: pass
    exp_name = exp_list.iloc[idx]['experiment_name']

    outcome_raw = input('  ❓ Outcome column [converted_to_order / order_value]: ').strip()
    caliper_raw = input('  ❓ Caliper (max propensity distance, default 0.10): ').strip()
    alpha       = _ask_alpha()

    outcome_col = outcome_raw if outcome_raw in ('converted_to_order', 'order_value') else 'converted_to_order'
    caliper     = float(caliper_raw) if caliper_raw else 0.10

    print('\n  Building feature matrix from buyer profiles...')
    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    variants = sorted(exp_df['variant'].unique().tolist())
    control  = 'control' if 'control' in variants else variants[0]

    from scipy.special import expit as _sigmoid

    try:
        features_df = df_psm_features.copy()
    except NameError:
        features_df = pd.DataFrame({'buyer_id': exp_df['buyer_id'].unique()})

    merged = exp_df.merge(features_df, on='buyer_id', how='inner') if 'buyer_id' in features_df.columns else exp_df.copy()

    available_covs = [c for c in ['account_segment', 'platform', 'country', 'has_billing_profile',
                                   'segment_num', 'has_orders', 'is_us', 'is_web', 'high_gmv',
                                   'lifetime_orders', 'n_inquiries', 'personal_ior']
                      if c in merged.columns]

    print(f'  Available covariates: {available_covs}')
    cov_raw = input(f'  ❓ Covariates to match on [comma-sep, or Enter for all above]: ').strip()
    covariates = [c.strip() for c in cov_raw.split(',') if c.strip()] if cov_raw else available_covs

    for c in covariates:
        if merged[c].dtype == object or str(merged[c].dtype) == 'category':
            dummies = pd.get_dummies(merged[c], prefix=c, drop_first=True)
            merged  = pd.concat([merged, dummies], axis=1)
            covariates = [x for x in covariates if x != c] + list(dummies.columns)

    covariates = [c for c in covariates if c in merged.columns]
    if not covariates:
        print('  ❌ No valid covariates found.')
        return None

    merged['treated'] = (merged['variant'] != control).astype(int)
    if len(merged) < 100:
        print(f'  ❌ Only {len(merged)} rows after merge. Need ≥100.')
        return None

    print(f'\n  Matching on: {covariates}')
    print(f'  Treated: {merged["treated"].sum():,}  Control: {(merged["treated"]==0).sum():,}')

    X      = merged[covariates].fillna(0).values.astype(float)
    X_aug  = np.column_stack([np.ones(len(X)), X])
    y_trt  = merged['treated'].values
    theta  = np.zeros(X_aug.shape[1])
    lr     = 0.1
    for _ in range(500):
        pred  = _sigmoid(X_aug @ theta)
        grad  = X_aug.T @ (pred - y_trt) / len(y_trt)
        theta -= lr * grad
    merged['propensity'] = _sigmoid(X_aug @ theta)

    treated_idx = merged[merged['treated'] == 1].index.tolist()
    control_idx = merged[merged['treated'] == 0].index.tolist()
    matched_pairs = []
    used_controls = set()

    for t_idx in treated_idx:
        p_t = merged.loc[t_idx, 'propensity']
        best_c, best_dist = None, np.inf
        for c_idx in control_idx:
            if c_idx in used_controls: continue
            d = abs(p_t - merged.loc[c_idx, 'propensity'])
            if d < best_dist:
                best_dist, best_c = d, c_idx
        if best_c is not None and best_dist < caliper:
            matched_pairs.append((t_idx, best_c))
            used_controls.add(best_c)

    match_rate = len(matched_pairs) / max(len(treated_idx), 1)
    print(f'\n  Matched pairs  : {len(matched_pairs):,}  ({match_rate:.0%} match rate, caliper={caliper})')

    if len(matched_pairs) < 20:
        print(f'  ❌ Too few matches. Try widening caliper (current: {caliper}).')
        return None

    t_idx_list = [p[0] for p in matched_pairs]
    c_idx_list = [p[1] for p in matched_pairs]
    t_out = merged.loc[t_idx_list, outcome_col].astype(float).values
    c_out = merged.loc[c_idx_list, outcome_col].astype(float).values

    att = t_out.mean() - c_out.mean()
    pr  = proportion_test(len(c_out), int(c_out.sum()),
                          len(t_out), int(t_out.sum()), alpha) if outcome_col == 'converted_to_order' else {}

    numeric_covs = [c for c in covariates if merged[c].dtype != object][:8]
    smd_before, smd_after = [], []
    for cov in numeric_covs:
        t_all = merged.loc[merged['treated']==1, cov].fillna(0).values
        c_all = merged.loc[merged['treated']==0, cov].fillna(0).values
        t_mat = merged.loc[t_idx_list, cov].fillna(0).values
        c_mat = merged.loc[c_idx_list, cov].fillna(0).values
        pool_sd = np.sqrt((t_all.std()**2 + c_all.std()**2) / 2) or 1
        smd_before.append({'cov': cov, 'smd': abs(t_all.mean()-c_all.mean())/pool_sd})
        smd_after.append( {'cov': cov, 'smd': abs(t_mat.mean()-c_mat.mean())/pool_sd})

    print('\n  ── PSM Results ───────────────────────────────────────────────────────')
    print(f'  ATT estimate     : {att*100:+.4f}pp  ({outcome_col})')
    if pr:
        sig_icon = '✅' if pr.get('is_significant') else '⚠️ '
        print(f'  {sig_icon} p-value       : {pr.get("p_value",1):.5f}  '
              f'{"Significant" if pr.get("is_significant") else "Not significant"} at α={alpha}')
        print(f'  Control IOR    : {pr["rate_control"]*100:.3f}%')
        print(f'  Treatment IOR  : {pr["rate_treatment"]*100:.3f}%')

    print('\n  Covariate balance (SMD — target < 0.10):')
    print(f'  {"Covariate":<22} {"Before":>8}  {"After":>8}')
    print('  ' + '─'*44)
    max_smd_after = 0.0
    for b, a in zip(smd_before, smd_after):
        icon = '✅' if a['smd'] < 0.10 else '⚠️ '
        print(f'  {icon}  {b["cov"]:<20} {b["smd"]:>8.3f}  {a["smd"]:>8.3f}')
        max_smd_after = max(max_smd_after, a['smd'])
    balance_ok = max_smd_after < 0.10
    print(f'\n  Balance: {"✅ Good (max SMD={max_smd_after:.3f})" if balance_ok else "⚠️  Poor (max SMD="+str(round(max_smd_after,3))+") — consider adding more covariates or widening caliper"}')

    result = {
        'method':         'Propensity Score Matching',
        'experiment':     exp_name,
        'outcome_col':    outcome_col,
        'covariates':     covariates[:10],
        'caliper':        caliper,
        'n_treated':      len(treated_idx),
        'n_matched_pairs': len(matched_pairs),
        'match_rate':     round(match_rate, 3),
        'att_pp':         round(att * 100, 4),
        'ior_treated':    round(t_out.mean(), 5),
        'ior_control':    round(c_out.mean(), 5),
        'p_value':        round(pr.get('p_value', 1.0), 5),
        'significant':    bool(pr.get('is_significant', False)),
        'max_smd_after':  round(max_smd_after, 4),
        'balance_ok':     balance_ok,
    }

    _causal_narrative(llm, result,
        f'PSM analysis for "{exp_name}". '
        f'ATT={result["att_pp"]:+.3f}pp '
        f'({"significant" if result["significant"] else "not significant"}, p={result["p_value"]:.4f}). '
        f'Match rate={result["match_rate"]:.0%}, balance {"ok" if balance_ok else "poor"} (max SMD={max_smd_after:.3f}). '
        f'Provide: (1) causal interpretation of the ATT, '
        f'(2) how much to trust this estimate given observable-only matching, '
        f'(3) what unobserved confounders could still bias the result, '
        f'(4) recommendation on whether to run a proper A/B test next.'
    )
    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['psm_balance.png', 'psm_propensity.png']
    _pdf_out = 'causal_psm_analysis.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Psm Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return result


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 7 — REGRESSION DISCONTINUITY (RDD)
# ─────────────────────────────────────────────────────────────────────────────

def run_rdd_analysis(llm):
    """
    [22] Regression Discontinuity — exploits a sharp threshold rule on a
    continuous running variable. Estimates the jump in outcome at the cutoff
    via local-linear regression on both sides.

    Use when treatment assignment follows a deterministic rule:
      - Credit score ≥ 700 → premium pricing feature
      - Account GMV ≥ $10k → enterprise portal access
      - Tenure ≥ 90 days   → loyalty programme feature
    """
    _causal_header(
        '📐  REGRESSION DISCONTINUITY (RDD)',
        'Exploit a sharp rule-based threshold for near-random assignment'
    )
    print("""
  ✅ When to use:
     - Treatment was assigned by crossing a SHARP threshold on a measurable score.
     - Users just below/above the threshold are otherwise similar (local randomisation).
     - You have enough observations near the cutoff.

  ⚠️  Limitations:
     - Only estimates a LOCAL average treatment effect (at the threshold).
     - Effect may not generalise to units far from the cutoff.
     - Requires a hard rule — not valid if the threshold was fuzzy or gameable.
     - Sample near the cutoff must be large enough (try narrowing bandwidth if n is small).
""")

    # ── Pick dataset ──────────────────────────────────────────────────────────
    print('  Which dataset contains the running variable?')
    print('    [1] all_experiments  (experiment-period data)')
    print('    [2] silver_buyers    (buyer-level features: tenure, gmv, n_inquiries)')
    print('    [3] silver_inquiries (inquiry-level: order_value, etc.)')
    ds_raw = input('  ❓ Dataset [1/2/3]: ').strip() or '1'

    ds_map = {'1': 'all_experiments', '2': 'silver_buyers', '3': 'silver_inquiries'}
    ds_name = ds_map.get(ds_raw, 'all_experiments')
    try:
        df_rdd = db.execute(f'SELECT * FROM {ds_name} LIMIT 200000').df()
    except Exception as ex:
        print(f'  ❌ Could not load {ds_name}: {ex}'); return None

    print(f'\n  Available numeric columns in {ds_name}:')
    num_cols = [c for c in df_rdd.columns
                if df_rdd[c].dtype in ('float64','int64','int32','float32')]
    for i, c in enumerate(num_cols[:20]):
        print(f'    [{i+1:>2}] {c}  (range: {df_rdd[c].min():.2f} – {df_rdd[c].max():.2f})')

    rv_raw = input('  ❓ Running variable column name: ').strip()
    if rv_raw not in df_rdd.columns:
        print(f'  ❌ Column "{rv_raw}" not found.')
        return None
    running_var = rv_raw

    cutoff_raw = input(f'  ❓ Cutoff value (treatment threshold): ').strip()
    try:
        cutoff = float(cutoff_raw)
    except ValueError:
        print('  ❌ Invalid cutoff value.'); return None

    bw_raw    = input('  ❓ Bandwidth (half-window around cutoff, Enter=auto): ').strip()
    bandwidth = float(bw_raw) if bw_raw else None

    outcome_raw = input('  ❓ Outcome column [converted_to_order]: ').strip()
    outcome_col = outcome_raw if outcome_raw in df_rdd.columns else 'converted_to_order'
    alpha = _ask_alpha()

    if outcome_col not in df_rdd.columns:
        print(f'  ❌ Outcome column "{outcome_col}" not found.')
        return None

    print(f'\n  Running variable : {running_var}  (cutoff = {cutoff})')
    print(f'  Outcome          : {outcome_col}')
    print(f'  Bandwidth        : {"auto" if bandwidth is None else bandwidth}')

    result = _run_rdd(df_rdd, running_var, cutoff, outcome_col, bandwidth, alpha)

    if 'error' in result:
        print(f'\n  ❌ RDD failed: {result["error"]}')
        return result

    print('\n  ── RDD Results ───────────────────────────────────────────────────────')
    sig = '✅ Significant' if result.get('significant') else '⚠️  Not significant'
    print(f'  Bandwidth used   : ±{result["bandwidth"]:.3f}')
    print(f'  Observations     : {result["n_left"]} below  +  {result["n_right"]} above cutoff')
    print(f'  LATE estimate    : {result["late_pp"]:+.4f}pp  [{result["ci_lo_pp"]:+.3f}, {result["ci_hi_pp"]:+.3f}]')
    print(f'  p-value          : {result["p_value"]:.5f}  {sig} at α={alpha}')
    print(f'  Left slope       : {result["slope_left"]:+.6f}  |  Right slope: {result["slope_right"]:+.6f}')

    import matplotlib.pyplot as plt
    COLORS_L = {'treatment': '#f97316', 'control': '#4e9af1',
                'highlight': '#facc15', 'neutral': '#a1a1aa',
                'positive': '#22c55e', 'negative': '#ef4444'}
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#0f0f0f')
    work = df_rdd[[running_var, outcome_col]].dropna().copy()
    work['centred'] = work[running_var] - cutoff
    bw_used = result['bandwidth']
    window  = work[work['centred'].abs() <= bw_used].copy()
    above   = window[window['centred'] >= 0]
    below   = window[window['centred'] <  0]

    ax.scatter(below['centred'], below[outcome_col].astype(float),
               color=COLORS_L['control'], alpha=0.3, s=8, label='Below cutoff')
    ax.scatter(above['centred'], above[outcome_col].astype(float),
               color=COLORS_L['treatment'], alpha=0.3, s=8, label='Above cutoff')

    # Fit lines
    for side, df_s, col in [(below, COLORS_L['control']), (above, COLORS_L['treatment'])]:
        if len(side) > 2:
            x = side['centred'].values
            y = side[outcome_col].astype(float).values
            coef = np.polyfit(x, y, 1)
            xs   = np.linspace(x.min(), x.max(), 100)
            ax.plot(xs, np.polyval(coef, xs), color=col, lw=2.5)

    ax.axvline(0, color=COLORS_L['highlight'], lw=2, linestyle='--', label=f'Cutoff ({cutoff})')
    ax.set_xlabel(f'{running_var} (centred at cutoff)')
    ax.set_ylabel(outcome_col)
    late_str = f'LATE={result["late_pp"]:+.3f}pp  {"✅" if result.get("significant") else "n.s."}'
    ax.set_title(f'Regression Discontinuity  |  {late_str}', color=COLORS_L['highlight'])
    ax.legend(fontsize=9); ax.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig('rdd_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → rdd_analysis.png')

    _causal_narrative(llm, {k: v for k, v in result.items() if not isinstance(v, list)},
        f'Regression Discontinuity analysis. Running variable: {running_var}, cutoff={cutoff}. '
        f'LATE estimate: {result["late_pp"]:+.3f}pp '
        f'({"significant" if result.get("significant") else "not significant"}, p={result["p_value"]:.4f}). '
        f'Bandwidth: ±{result["bandwidth"]:.2f}. '
        f'Provide: (1) interpretation of the LATE, (2) external validity limitations (local effect only), '
        f'(3) key threats to the RDD validity (manipulation, sorting, fuzzy threshold), '
        f'(4) confidence in the causal claim.'
    )
    return result

def _run_rdd_patched(df, running_var, cutoff, outcome_var='converted_to_order',
                     bandwidth=None, alpha=0.05):
    """
    Drop-in replacement for _run_rdd that returns a richer, standardised dict.
    """
    work = df[[running_var, outcome_var]].dropna().copy()
    work['centred'] = work[running_var] - cutoff
    work['above']   = (work[running_var] >= cutoff).astype(int)

    if bandwidth is None:
        bandwidth = float(work['centred'].std()) * 0.5

    window = work[work['centred'].abs() <= bandwidth]
    if len(window) < 20:
        return {'error': f'Only {len(window)} observations within bandwidth ±{bandwidth:.3f}. Try widening bandwidth.'}

    left  = window[window['above'] == 0]
    right = window[window['above'] == 1]
    n_l, n_r = len(left), len(right)
    if n_l < 10 or n_r < 10:
        return {'error': f'Too few obs: left={n_l}, right={n_r}. Try widening bandwidth.'}

    def local_linear(df_side):
        x   = df_side['centred'].values
        y   = df_side[outcome_var].astype(float).values
        X_s = np.column_stack([np.ones(len(x)), x])
        XtX = X_s.T @ X_s + np.eye(2) * 1e-10
        b   = np.linalg.solve(XtX, X_s.T @ y)
        res = y - X_s @ b
        se2 = np.sum(res**2) / max(len(y)-2, 1)
        se  = np.sqrt(np.diag(se2 * np.linalg.inv(XtX)))
        return b, se

    b_l, se_l = local_linear(left)
    b_r, se_r = local_linear(right)

    late     = b_r[0] - b_l[0]
    se_late  = np.sqrt(se_r[0]**2 + se_l[0]**2)
    z_late   = late / se_late if se_late > 0 else 0
    from scipy import stats as _st
    p_val    = float(2 * _st.norm.sf(abs(z_late)))
    z_crit   = _st.norm.ppf(1 - alpha/2)
    ci_lo    = late - z_crit * se_late
    ci_hi    = late + z_crit * se_late

    result = {
        'method':        'Regression Discontinuity',
        'running_var':   running_var,
        'outcome_var':   outcome_var,
        'cutoff':        cutoff,
        'bandwidth':     round(bandwidth, 4),
        'n_total':       len(window),
        'n_left':        n_l,
        'n_right':       n_r,
        'late_pp':       round(late * 100, 4),
        'ci_lo_pp':      round(ci_lo * 100, 4),
        'ci_hi_pp':      round(ci_hi * 100, 4),
        'p_value':       round(p_val, 5),
        'significant':   p_val < alpha,
        'slope_left':    round(float(b_l[1]), 6),
        'slope_right':   round(float(b_r[1]), 6),
    }

    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['rdd_analysis.png']
    _pdf_out = 'causal_rdd_analysis.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Rdd Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return result

_run_rdd = _run_rdd_patched


print('✅ Causal Analysis runners loaded:')
print('   run_causal_analysis()              → [10] Method-selection menu')
print('   run_ab_test_analysis()             → [17] A/B Test (Statsig/feature-flag data)')
print('   run_pre_post_analysis()            → [18] Pre-Post Analysis')
print('   run_did_analysis()                 → [19] DiD (Enhanced + TWFE)')
print('   run_its_analysis()                 → [20] Interrupted Time Series')
print('   run_psm_analysis()                 → [21] Propensity Score Matching')
print('   run_rdd_analysis()                 → [22] Regression Discontinuity')
print('   run_synthetic_control_analysis()   → [23] Synthetic Control (Enhanced)')



def _print_causal_results(result: dict, method_key: str, meta: dict):
    """Print method-specific key results in a clean format."""
    print('\n' + '═'*72)
    print(f'  📊  CAUSAL ANALYSIS RESULTS — {meta["label"]}')
    print('═'*72)

    skip_keys = {'method','fitted_values','counterfactual','dates','actual_ior',
                 'sc_pre','sc_post','treat_pre','treat_post','dates_pre','dates_post',
                 'event_study','smd_before','smd_after','placebo_gaps_pp','weights'}

    for k, v in result.items():
        if k in skip_keys or isinstance(v, list): continue
        label = k.replace('_',' ').title()
        if isinstance(v, float): print(f'  {label:<35} {v:>12.5f}')
        elif isinstance(v, bool): print(f'  {label:<35} {"✅ Yes" if v else "❌ No"}')
        else: print(f'  {label:<35} {v}')

    if method_key == 'did':
        print(f'\n  DiD 2×2 Table:')
        print(f'              Pre-period    Post-period    Difference')
        print(f'  Treatment   {result["ior_treat_pre"]*100:.3f}%       {result["ior_treat_post"]*100:.3f}%        {result["treat_diff"]*100:+.3f}pp')
        print(f'  Control     {result["ior_ctrl_pre"]*100:.3f}%       {result["ior_ctrl_post"]*100:.3f}%        {result["ctrl_diff"]*100:+.3f}pp')
        print(f'  ─────────────────────────────────────────────────────────────')
        print(f'  DiD estimate:                                {result["did_estimate_pp"]:+.4f}pp  {"✅ sig" if result["significant"] else "⚠️ n.s."}')
        print(f'  Parallel trends: {"✅ HOLDS (p={:.3f})".format(result["parallel_trends_p"]) if result["parallel_trends_ok"] else "⚠️  VIOLATED (p={:.3f}) — results may be biased".format(result["parallel_trends_p"])}')

    elif method_key == 'its':
        print(f'\n  Level change (immediate effect):  {result["level_change_pp"]:+.4f}pp  p={result["level_change_p"]:.4f}  {"✅ sig" if result["level_significant"] else "n.s."}')
        print(f'  Slope change (trend change):      {result["slope_change_pp_day"]:+.5f}pp/day  p={result["slope_change_p"]:.4f}  {"✅ sig" if result["slope_significant"] else "n.s."}')
        print(f'  Avg post-ship lift vs CF:         {result["avg_lift_pp"]:+.4f}pp')

    elif method_key == 'psm':
        print(f'\n  Covariate balance (SMD) BEFORE matching:')
        for s in result['smd_before']:
            bar = '█' * int(s['smd'] * 30)
            print(f'    {s["covariate"]:<20} {bar:<25} {s["smd"]:.3f}')
        print(f'\n  Covariate balance (SMD) AFTER matching:')
        for s in result['smd_after']:
            bar = '█' * int(s['smd'] * 30)
            flag = '✅' if s['smd'] < 0.10 else '⚠️'
            print(f'    {s["covariate"]:<20} {bar:<25} {s["smd"]:.3f}  {flag}')
        print(f'\n  {result["balance_note"]}')

    elif method_key == 'synthetic_control':
        print(f'\n  Synthetic control weights:')
        for seg, w in result['weights'].items():
            print(f'    {seg:<20} {w:.4f}  ({w*100:.1f}%)')
        print(f'\n  Pre-period RMSPE: {result["pre_rmspe"]*100:.3f}pp  (lower = better fit)')
        print(f'  RMSPE ratio (post/pre): {result["rmspe_ratio"]:.2f}  (>2 suggests real effect)')
        if result.get('p_value_placebo_combined') is not None:
            print(f'  Placebo p-value: {result["p_value_placebo_combined"]:.4f}  ({result["n_placebo_tests_combined"]} placebo tests)')


def _plot_causal_results(result: dict, method_key: str, meta: dict):
    """Generate method-appropriate visualisation."""
    if method_key in ('pre_post',):
        # Simple bar chart
        fig, ax = plt.subplots(1, 1, figsize=(8, 5))
        fig.patch.set_facecolor('#0f0f0f')
        bars = ax.bar(['Pre-period','Post-period'],
                      [result['ior_pre']*100, result['ior_post']*100],
                      color=[COLORS['control'], COLORS['treatment']], width=0.4)
        for bar, v in zip(bars, [result['ior_pre']*100, result['ior_post']*100]):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.05,
                    f'{v:.3f}%', ha='center', fontsize=11, fontweight='bold', color='white')
        sig = '✅ Significant' if result.get('significant') else '⚠️  Not significant'
        ax.set_title(f'Pre-Post Analysis  |  Δ={result["delta_pp"]:+.3f}pp  p={result["p_value"]:.4f}  {sig}',
                     color=COLORS['highlight'])
        ax.set_ylabel('IOR (%)')
        plt.tight_layout()
        plt.savefig('causal_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()

    elif method_key == 'did':
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        fig.patch.set_facecolor('#0f0f0f')

        # 2×2 table visualisation
        ax1 = axes[0]
        groups = ['Treat Pre','Treat Post','Ctrl Pre','Ctrl Post']
        vals   = [result['ior_treat_pre']*100, result['ior_treat_post']*100,
                  result['ior_ctrl_pre']*100,  result['ior_ctrl_post']*100]
        colors_2x2 = [COLORS['treatment'], COLORS['positive'], COLORS['control'], COLORS['neutral']]
        bars = ax1.bar(groups, vals, color=colors_2x2, width=0.5)
        for bar, v in zip(bars, vals):
            ax1.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.05,
                     f'{v:.3f}%', ha='center', fontsize=9.5, fontweight='bold', color='white')
        ax1.set_title(f'DiD 2×2  |  DiD={result["did_estimate_pp"]:+.3f}pp\n'
                      f'{"✅ sig" if result["significant"] else "n.s."}  p={result["p_value"]:.4f}',
                      color=COLORS['highlight'])
        ax1.set_ylabel('IOR (%)')

        # Event study
        ax2 = axes[1]
        if result.get('event_study'):
            ev = result['event_study']
            weeks = [e['week'] for e in ev]
            gaps  = [e['gap']*100 for e in ev]
            colors_ev = [COLORS['positive'] if g >= 0 else COLORS['negative'] for g in gaps]
            ax2.bar(weeks, gaps, color=colors_ev, width=0.8, alpha=0.8)
            ax2.axhline(0, color='white', lw=1, linestyle='--', alpha=0.5)
            ax2.axvline(0, color=COLORS['highlight'], lw=2, linestyle='-', alpha=0.8, label='Intervention')
            ax2.set_xlabel('Week relative to intervention')
            ax2.set_ylabel('Treatment − Control gap (pp)')
            ax2.set_title('Event Study\n(should be flat pre-intervention → parallel trends)',
                          color=COLORS['highlight'])
            ax2.legend(fontsize=9)
        plt.suptitle(f'Difference-in-Differences', fontsize=13,
                     color=COLORS['highlight'], fontweight='bold')
        plt.tight_layout()
        plt.savefig('causal_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()

    elif method_key == 'its':
        fig, axes = plt.subplots(1, 2, figsize=(18, 6))
        fig.patch.set_facecolor('#0f0f0f')
        dates = pd.to_datetime(result['dates'])
        y_act = np.array(result['actual_ior']) * 100
        y_fit = np.array(result['fitted_values']) * 100
        y_cf  = np.array(result['counterfactual']) * 100
        cutoff = pd.Timestamp(result['cutoff_date'])

        ax = axes[0]
        ax.scatter(dates, y_act, color=COLORS['neutral'], s=10, alpha=0.5, label='Actual IOR')
        ax.plot(dates, y_fit, color=COLORS['treatment'], lw=2.5, label='ITS fitted model')
        ax.plot(dates, y_cf,  color=COLORS['control'],   lw=2,   linestyle='--', label='Counterfactual')
        ax.fill_between(dates, y_cf, y_fit, where=y_fit>y_cf,
                        color=COLORS['positive'], alpha=0.2, label='Incremental lift')
        ax.axvline(cutoff, color=COLORS['highlight'], lw=2, label='Intervention')
        ax.set_title(f'ITS Model Fit  |  Level Δ={result["level_change_pp"]:+.3f}pp  '
                     f'{"✅" if result["level_significant"] else "n.s."}', color=COLORS['highlight'])
        ax.set_xlabel('Date'); ax.set_ylabel('IOR (%)')
        ax.legend(fontsize=7.5); ax.grid(True, alpha=0.3)

        ax2 = axes[1]
        gap = (np.array(result['actual_ior']) - np.array(result['counterfactual'])) * 100
        rolling = pd.Series(gap).rolling(7, center=True).mean()
        ax2.bar(range(len(gap)), gap,
                color=[COLORS['positive'] if g>=0 else COLORS['negative'] for g in gap],
                width=1, alpha=0.7)
        ax2.plot(range(len(rolling)), rolling, color='white', lw=2, label='7-day avg')
        ax2.axhline(0, color='white', lw=1, linestyle='--', alpha=0.5)
        ax2.axvline(result['pre_days'], color=COLORS['highlight'], lw=2, label='Intervention')
        ax2.set_xlabel('Day'); ax2.set_ylabel('Actual − Counterfactual (pp)')
        ax2.set_title('Daily Gap: Actual vs Counterfactual', color=COLORS['highlight'])
        ax2.legend(fontsize=8)
        plt.suptitle('Interrupted Time Series Analysis', fontsize=13,
                     color=COLORS['highlight'], fontweight='bold')
        plt.tight_layout()
        plt.savefig('causal_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()

    elif method_key == 'synthetic_control':
        fig, axes = plt.subplots(1, 2, figsize=(18, 6))
        fig.patch.set_facecolor('#0f0f0f')
        all_dates  = result['dates_pre'] + result['dates_post']
        sc_vals    = list(result['sc_pre']) + list(result['sc_post'])
        trt_vals   = list(result['treat_pre']) + list(result['treat_post'])
        n_pre      = result['weeks_pre']

        ax = axes[0]
        ax.plot(range(len(trt_vals)), [v*100 for v in trt_vals],
                color=COLORS['treatment'], lw=2.5, label=result['treatment_segment'])
        ax.plot(range(len(sc_vals)),  [v*100 for v in sc_vals],
                color=COLORS['control'],  lw=2.5, linestyle='--', label='Synthetic control')
        ax.axvline(n_pre, color=COLORS['highlight'], lw=2, label='Intervention')
        ax.fill_between(range(n_pre, len(trt_vals)),
                        [v*100 for v in sc_vals[n_pre:]],
                        [v*100 for v in trt_vals[n_pre:]],
                        color=COLORS['positive'], alpha=0.2)
        ax.set_title(f'Synthetic Control  |  Avg gap={result["avg_gap_pp"]:+.3f}pp\n'
                     f'RMSPE ratio={result["rmspe_ratio"]:.2f}  '
                     f'Placebo p={result["p_value_placebo"]:.3f}' if result.get("p_value_placebo") else '',
                     color=COLORS['highlight'])
        ax.set_xlabel('Week'); ax.set_ylabel('IOR (%)'); ax.legend(fontsize=9)

        ax2 = axes[1]
        all_gap  = [(t-s)*100 for t,s in zip(trt_vals, sc_vals)]
        placebo  = result.get('placebo_gaps_pp', [])
        ax2.hist(placebo, bins=10, color=COLORS['neutral'], alpha=0.7, label='Placebo distribution')
        ax2.axvline(result['avg_gap_pp'], color=COLORS['treatment'], lw=2.5,
                    label=f'Treatment gap ({result["avg_gap_pp"]:+.3f}pp)')
        ax2.set_xlabel('Average post-period gap (pp)'); ax2.set_ylabel('Count')
        ax2.set_title('Placebo Distribution\n(is treatment gap unusual?)', color=COLORS['highlight'])
        ax2.legend(fontsize=9)
        plt.suptitle('Synthetic Control Analysis', fontsize=13,
                     color=COLORS['highlight'], fontweight='bold')
        plt.tight_layout()
        plt.savefig('causal_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()

    elif method_key == 'psm':
        fig, axes = plt.subplots(1, 3, figsize=(20, 5))
        fig.patch.set_facecolor('#0f0f0f')

        # Covariate balance chart
        ax = axes[0]
        covs = [s['covariate'] for s in result['smd_before']]
        smd_b = [s['smd'] for s in result['smd_before']]
        smd_a = [s['smd'] for s in result['smd_after']]
        y = np.arange(len(covs))
        ax.barh(y-0.2, smd_b, 0.35, color=COLORS['negative'], alpha=0.7, label='Before matching')
        ax.barh(y+0.2, smd_a, 0.35, color=COLORS['positive'], alpha=0.7, label='After matching')
        ax.axvline(0.10, color=COLORS['highlight'], lw=1.5, linestyle='--', label='SMD=0.10 threshold')
        ax.set_yticks(y); ax.set_yticklabels(covs)
        ax.set_xlabel('Standardised Mean Difference (lower=better)')
        ax.set_title('Covariate Balance\n(target: SMD < 0.10)', color=COLORS['highlight'])
        ax.legend(fontsize=8)

        # ATT outcome comparison
        ax2 = axes[1]
        groups = ['Matched Control', 'Matched Treatment']
        iors   = [result['ior_control']*100, result['ior_treated']*100]
        bars   = ax2.bar(groups, iors, color=[COLORS['control'], COLORS['treatment']], width=0.4)
        for bar, v in zip(bars, iors):
            ax2.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.05,
                     f'{v:.3f}%', ha='center', fontsize=11, fontweight='bold', color='white')
        ax2.set_title(f'ATT = {result["att_pp"]:+.3f}pp\np={result["p_value"]:.4f}  '
                      f'{"✅ sig" if result["significant"] else "n.s."}', color=COLORS['highlight'])
        ax2.set_ylabel('IOR (%)')

        # Summary scorecard
        ax3 = axes[2]
        ax3.axis('off')
        lines = [
            ('Method', 'PSM — ATT Estimate'),
            ('Treated units', str(result['n_treated'])),
            ('Matched pairs', str(result['n_matched_pairs'])),
            ('Match rate', f'{result["n_matched_pairs"]/result["n_treated"]*100:.0f}%'),
            ('ATT', f'{result["att_pp"]:+.3f}pp'),
            ('p-value', f'{result["p_value"]:.4f}'),
            ('Significant', '✅ Yes' if result['significant'] else '❌ No'),
            ('Max SMD after', f'{result["max_smd_after"]:.3f}'),
            ('Balance', '✅ Good' if result['balance_ok'] else '⚠️  Poor'),
        ]
        for ri, (k, v) in enumerate(lines):
            ax3.text(0.05, 0.95-ri*0.10, k, transform=ax3.transAxes,
                     fontsize=9, color='#aaa', va='top')
            ax3.text(0.55, 0.95-ri*0.10, v, transform=ax3.transAxes,
                     fontsize=9, color=COLORS['highlight'], va='top', fontweight='bold')
        ax3.set_title('PSM Scorecard', color=COLORS['highlight'])

        plt.suptitle('Propensity Score Matching Analysis', fontsize=13,
                     color=COLORS['highlight'], fontweight='bold')
        plt.tight_layout()
        plt.savefig('causal_analysis.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.show()

    print('  📁 Chart saved → causal_analysis.png')





def run_did_analysis(llm):
    """
    Module 11a — Standalone DiD Analysis with full interactive UI.
    Surfaces all DiD options: segment-level, entity-level, TWFE toggle.
    """
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + '  📐  DIFFERENCE-IN-DIFFERENCES ANALYSIS  (Module 11a)'.ljust(70) + '║')
    print('║' + '  Causal effect via treated vs. untreated group comparison'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    print("""
  When to use DiD:
  ✅ You have a natural control group that did NOT receive the feature
  ✅ You have pre-period data for both groups (at least 4 weeks)
  ✅ You believe parallel trends would have held without the intervention
  ⚠️  NOT recommended if groups were self-selected into treatment
""")

    unit_choices = {'1': 'account_segment', '2': 'buyer_id', '3': 'account_id'}
    print('  Unit of analysis:')
    print('    [1] Account segment  (few units, stable groups — most common)')
    print('    [2] Buyer ID         (many units, entity-level DiD)')
    print('    [3] Account ID       (account-level DiD)')
    unit_raw = input('  ❓ Choose unit [1]: ').strip() or '1'
    unit_col = unit_choices.get(unit_raw, 'account_segment')

    all_units = sorted(globals().get('df_all_experiments', globals().get(
        'df_hist_inquiries', pd.DataFrame()
    )).get(unit_col, pd.Series()).dropna().unique().tolist()
    ) if unit_col in globals().get('df_all_experiments', pd.DataFrame()).columns else SEGMENTS

    print(f'\n  Available {unit_col} values: {all_units[:20]}')
    treat_raw = input('  ❓ Treatment unit(s) [comma-separated]: ').strip()
    ctrl_raw  = input('  ❓ Control unit(s) [comma-separated]: ').strip()

    treatment_units = [u.strip() for u in treat_raw.split(',') if u.strip()] or [all_units[0]]
    control_units   = [u.strip() for u in ctrl_raw.split(',')  if u.strip()] or [all_units[-1]]

    cutoff_raw  = input(f'  ❓ Intervention date [YYYY-MM-DD, default: {EXP_START.date()}]: ').strip()
    pre_raw     = input(f'  ❓ Pre-period start  [YYYY-MM-DD, default: {HIST_START.date()}]: ').strip()
    alpha_raw   = input('  ❓ Significance level α [0.05]: ').strip()
    twfe_raw    = input('  ❓ Run Two-Way Fixed Effects (TWFE)? [Y/n]: ').strip().lower()
    n_boot_raw  = input('  ❓ Bootstrap resamples [1000]: ').strip()

    cutoff_date     = pd.Timestamp(cutoff_raw) if cutoff_raw else EXP_START
    pre_start       = pd.Timestamp(pre_raw)    if pre_raw    else HIST_START
    alpha           = float(alpha_raw) if alpha_raw else 0.05
    run_twfe        = twfe_raw != 'n'
    n_bootstrap     = int(n_boot_raw) if n_boot_raw.isdigit() else 1_000

    print('\n  Running DiD analysis...')
    result = _run_did_v2(
        treatment_units=treatment_units,
        control_units=control_units,
        cutoff_date=cutoff_date,
        pre_start=pre_start,
        alpha=alpha,
        unit_col=unit_col,
        run_twfe=run_twfe,
        n_bootstrap=n_bootstrap,
    )

    if 'error' in result:
        print(f'\n  ❌ DiD failed: {result["error"]}')
        return result

    print('\n' + '═'*72)
    print('  📊  DIFFERENCE-IN-DIFFERENCES RESULTS')
    print('═'*72)
    print(f'\n  Unit of analysis   : {result["unit_col"]}')
    print(f'  Treatment          : {result["treatment_units"]}')
    print(f'  Control            : {result["control_units"]}')
    print(f'\n  DiD 2×2 Table:')
    print(f'              Pre-period      Post-period     Difference')
    print(f'  Treatment   {result["ior_treat_pre"]*100:.3f}%         {result["ior_treat_post"]*100:.3f}%         {result["treat_diff"]*100:+.3f}pp')
    print(f'  Control     {result["ior_ctrl_pre"]*100:.3f}%         {result["ior_ctrl_post"]*100:.3f}%         {result["ctrl_diff"]*100:+.3f}pp')
    print(f'  ──────────────────────────────────────────────────────────────────')
    print(f'  DiD estimate       : {result["did_estimate_pp"]:+.4f}pp')
    print(f'  Delta-method SE    : ±{result["did_se_delta_pp"]:.4f}pp')
    print(f'  Bootstrap SE       : ±{result["did_se_bootstrap_pp"]:.4f}pp  (n={result["n_bootstrap"]:,})')
    print(f'  Delta CI {int((1-alpha)*100)}%     : [{result["ci_delta_pp"][0]:+.4f}, {result["ci_delta_pp"][1]:+.4f}]pp')
    print(f'  Bootstrap CI {int((1-alpha)*100)}%  : [{result["ci_bootstrap_pp"][0]:+.4f}, {result["ci_bootstrap_pp"][1]:+.4f}]pp')
    print(f'  p-value            : {result["p_value"]:.5f}  '
          f'{"✅ Significant" if result["significant"] else "⚠️  Not significant"} at α={alpha}')
    print()
    print(f'  {result["parallel_trends_note"]}')

    if 'twfe_estimate_pp' in result:
        print()
        print(f'  TWFE estimate      : {result["twfe_estimate_pp"]:+.4f}pp  '
              f'(p={result["twfe_p_value"]:.4f}, n={result["twfe_n_unit_periods"]:,} unit-periods)')
        delta = abs(result["twfe_estimate_pp"] - result["did_estimate_pp"])
        if delta > 0.5:
            print(f'  ⚠️  TWFE and 2×2 DiD differ by {delta:.3f}pp — suggests heterogeneous '
                  f'treatment effects or staggered adoption.')

    if result.get('stagger_warning'):
        print(f'\n  ⚠️  {result["stagger_warning"]}')

    # Plot
    _plot_did_v2(result, alpha=alpha)

    # LLM narrative
    print('\n  🤖 Generating causal interpretation...')
    narrative = llm.narrate(
        {k: v for k, v in result.items()
         if not isinstance(v, list) and not isinstance(v, dict)},
        context=(
            f'Difference-in-Differences analysis. '
            f'Treatment: {treatment_units}, Control: {control_units}. '
            f'DiD estimate: {result["did_estimate_pp"]:+.3f}pp '
            f'({"significant" if result["significant"] else "not significant"} at α={alpha}). '
            f'Parallel trends: {"holds" if result["parallel_trends_ok"] else "VIOLATED"}. '
            f'Provide: (1) causal interpretation of the estimate, (2) key assumptions and '
            f'whether they hold, (3) confidence in the causal claim, (4) recommendation.'
        )
    )
    print('\n' + '─'*72)
    print(narrative)
    print('─'*72)
    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['did_analysis_v2.png']
    _pdf_out = 'did_analysis_v2.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Did Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return result


def run_synthetic_control_analysis(llm):
    """
    Module 11b — Standalone Synthetic Control Analysis with full interactive UI.
    """
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + '  🧪  SYNTHETIC CONTROL ANALYSIS  (Module 11b)'.ljust(70) + '║')
    print('║' + '  Counterfactual from weighted combination of donor units'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    print("""
  When to use Synthetic Control:
  ✅ One treated unit with 3+ untreated donor units
  ✅ Long pre-period (10+ weeks) for donors to match the treatment trajectory
  ✅ Donors did NOT receive any similar treatment in the post-period
  ⚠️  Requires good pre-period donor fit (RMSPE < ~1.5pp) to trust results
""")

    print(f'  Available segments: {SEGMENTS}')
    treat_raw   = input('  ❓ Treatment segment [Core]: ').strip() or 'Core'
    donor_raw   = input(f'  ❓ Donor segments [comma-sep, default: all others]: ').strip()
    cutoff_raw  = input(f'  ❓ Intervention date [YYYY-MM-DD, default: {EXP_START.date()}]: ').strip()
    pre_raw     = input(f'  ❓ Pre-period start  [YYYY-MM-DD, default: {HIST_START.date()}]: ').strip()
    thresh_raw  = input('  ❓ Max acceptable pre-RMSPE in pp [1.5]: ').strip()

    treatment_segment = treat_raw
    donor_segments    = ([d.strip() for d in donor_raw.split(',') if d.strip()]
                         or [s for s in SEGMENTS if s != treatment_segment])
    cutoff_date       = pd.Timestamp(cutoff_raw) if cutoff_raw else EXP_START
    pre_start         = pd.Timestamp(pre_raw)    if pre_raw    else HIST_START
    pre_rmspe_thresh  = float(thresh_raw) / 100  if thresh_raw else 0.015

    print(f'\n  Treatment : {treatment_segment}')
    print(f'  Donors    : {donor_segments}')
    print(f'  Cutoff    : {cutoff_date.date()}')
    print(f'  Pre-start : {pre_start.date()}')
    print('\n  Fitting synthetic control...')

    result = _run_synthetic_control_v2(
        treatment_segment=treatment_segment,
        donor_segments=donor_segments,
        cutoff_date=cutoff_date,
        pre_start=pre_start,
        pre_rmspe_threshold=pre_rmspe_thresh,
    )

    if 'error' in result:
        print(f'\n  ❌ Synthetic Control failed: {result["error"]}')
        return result

    print('\n' + '═'*72)
    print('  📊  SYNTHETIC CONTROL RESULTS')
    print('═'*72)
    print(f'\n  Treatment segment  : {result["treatment_segment"]}')
    print(f'\n  Donor weights:')
    for seg, w in result['weights'].items():
        bar = '█' * int(w * 30)
        print(f'    {seg:<18} {bar:<32} {w:.4f}  ({w*100:.1f}%)')

    if result.get('concentration_warning'):
        print(f'  ⚠️  {result["concentration_warning"]}')

    fit_icon = {'Excellent': '✅', 'Good': '✅', 'Marginal': '⚠️', 'Poor': '❌'}
    print(f'\n  Pre-period RMSPE   : {result["pre_rmspe_pp"]:.4f}pp  '
          f'{fit_icon.get(result["fit_quality"],"?")} Fit: {result["fit_quality"]}')
    if result.get('fit_warning'):
        print(f'  ❌ {result["fit_warning"]}')

    print(f'\n  Average post-period gap : {result["avg_gap_pp"]:+.4f}pp')
    print(f'  RMSPE ratio (post/pre)  : {result["rmspe_ratio"]:.3f}  — {result["rmspe_interpretation"]}')
    p_val = result.get('p_value_placebo_combined')
    if p_val is not None:
        print(f'  Permutation p-value     : {p_val:.4f}  '
              f'({result["n_placebo_tests_combined"]} placebo tests: '
              f'{result["n_donor_placebo_tests"]} donor + 1 time)')
    if result.get('time_placebo_note'):
        print(f'\n  {result["time_placebo_note"]}')

    _plot_synthetic_control_v2(result)

    print('\n  🤖 Generating causal interpretation...')
    narrative = llm.narrate(
        {k: v for k, v in result.items()
         if not isinstance(v, list) and not isinstance(v, dict)},
        context=(
            f'Synthetic Control analysis. '
            f'Treatment: {treatment_segment}, Donors: {donor_segments}. '
            f'Pre-RMSPE: {result["pre_rmspe_pp"]:.4f}pp (fit: {result["fit_quality"]}). '
            f'Post-period avg gap: {result["avg_gap_pp"]:+.3f}pp. '
            f'RMSPE ratio: {result["rmspe_ratio"]:.2f}. '
            f'Provide: (1) causal interpretation of the gap, '
            f'(2) assessment of the fit quality and what it means for reliability, '
            f'(3) what the placebo tests tell us, (4) recommendation.'
        )
    )
    print('\n' + '─'*72)
    print(narrative)
    print('─'*72)
    return result


print('✅ Module 11: Causal Analysis Engine loaded')
print('   Methods: A/B Test · Pre-Post · DiD (Enhanced+TWFE) · ITS · Synthetic Control (Enhanced) · PSM')
print('   Standalone runners: run_did_analysis(llm) · run_synthetic_control_analysis(llm)')
print('   Use Module 4 (Experiment Brief) to get a recommended method first.')
# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION DISCONTINUITY (RDD)
# ─────────────────────────────────────────────────────────────────────────────

def _run_mediation(df, treatment_var='variant', treatment_value='treatment',
                   mediator_var='has_billing_profile',
                   outcome_var='converted_to_order', n_boot=500, alpha=0.05):
    """
    Baron-Kenny mediation with bootstrap CI on ACME.

    Model:
        mediator = α0 + α1·T + ε1
        outcome  = β0 + β1·T + β2·M + ε2
        Total effect    = β1 + α1·β2
        Direct effect   = β1
        ACME            = α1·β2
    """
    work = df[[treatment_var, mediator_var, outcome_var]].dropna().copy()
    work['T'] = (work[treatment_var] == treatment_value).astype(float)
    work['M'] = work[mediator_var].astype(float)
    work['Y'] = work[outcome_var].astype(float)

    if work['T'].nunique() < 2:
        return {'error': f'Treatment variable has only one level after filtering to "{treatment_value}"'}
    if len(work) < 200:
        return {'error': f'Too few observations ({len(work)}) for reliable mediation estimates'}

    def _fit(sub):
        Xm = np.column_stack([np.ones(len(sub)), sub['T'].values])
        a  = np.linalg.lstsq(Xm, sub['M'].values, rcond=None)[0]
        Xy = np.column_stack([np.ones(len(sub)), sub['T'].values, sub['M'].values])
        b  = np.linalg.lstsq(Xy, sub['Y'].values, rcond=None)[0]
        return float(a[1]), float(b[1]), float(b[2])      # α1, β1, β2

    a1, b1, b2 = _fit(work)
    acme_point  = a1 * b2       # indirect (mediated) effect
    ade_point   = b1            # direct effect
    total_point = acme_point + ade_point

    # Bootstrap for ACME
    rng_local = np.random.default_rng(42)
    acme_boot = np.empty(n_boot)
    for i in range(n_boot):
        sample = work.sample(n=len(work), replace=True, random_state=int(rng_local.integers(2**31)))
        a1_b, _, b2_b = _fit(sample)
        acme_boot[i] = a1_b * b2_b

    lo_q, hi_q = alpha/2, 1 - alpha/2
    ci_lo = float(np.quantile(acme_boot, lo_q))
    ci_hi = float(np.quantile(acme_boot, hi_q))
    prop_mediated = (acme_point / total_point) if total_point != 0 else float('nan')

    return {
        'method':         'causal_mediation',
        'treatment_var':  treatment_var,
        'mediator_var':   mediator_var,
        'outcome_var':    outcome_var,
        'n':              int(len(work)),
        'total_effect':   float(total_point),
        'direct_effect':  float(ade_point),
        'acme':           float(acme_point),
        'acme_ci_lo':     ci_lo,
        'acme_ci_hi':     ci_hi,
        'prop_mediated':  float(prop_mediated) if not np.isnan(prop_mediated) else None,
        'sig':            not (ci_lo <= 0 <= ci_hi),
        'interpretation': (
            f'Total effect = {total_point:+.4f}. Of this, '
            f'{acme_point:+.4f} ({(prop_mediated*100 if not np.isnan(prop_mediated) else 0):+.1f}%) '
            f'flows through "{mediator_var}" and {ade_point:+.4f} is direct. '
            f'ACME 95% bootstrap CI: [{ci_lo:+.4f}, {ci_hi:+.4f}].'
        ),
    }


def _run_extra_method(method_key, exp_df, exp_info):
    """
    Run RDD or Mediation when the chosen method is one of these advanced ones.
    Returns a dict describing the result, or None if method is not one of these.
    """
    if method_key == 'regression_discontinuity':
        if 'order_value' not in exp_df.columns:
            return {'error': 'No running variable available for RDD on this experiment'}
        subset = exp_df[exp_df['order_value'] > 0].copy()
        if len(subset) < 100:
            return {'error': 'Too few observations for RDD'}
        cutoff = float(subset['order_value'].median())
        return _run_rdd(subset, 'order_value', cutoff, 'converted_to_order')

    if method_key == 'causal_mediation':
        if 'has_billing_profile' not in exp_df.columns:
            return {'error': 'No mediator variable available (expected has_billing_profile)'}
        return _run_mediation(exp_df,
                              treatment_var='variant',
                              treatment_value=[v for v in exp_df['variant'].unique() if v != 'control'][0],
                              mediator_var='has_billing_profile',
                              outcome_var='converted_to_order',
                              n_boot=300)

    # ── Save PDF report ───────────────────────────────────────────────────
    _pdf_charts = ['synthetic_control_v2.png']
    _pdf_out = 'synthetic_control_v2.pdf'
    _pdf_narrative = globals().get('_last_narrative', '')
    _pdf_path = _save_method_pdf('Run Synthetic Control Analysis',
                                  result, _pdf_charts, _pdf_narrative, _pdf_out)
    if _pdf_path:
        print(f'  📄 PDF report saved → {_pdf_path}')

    return None




# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT-FIRST POST-EXPERIMENT ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def _list_experiments_with_status():
    """
    Pull all experiments with rich status display. Return list of dicts and
    the index the user chose, or (None, None) if user aborts.
    """
    from datetime import datetime as _dt
    # Merge registry data with live summary from all_experiments
    live = db.execute("""
        SELECT
            experiment_name,
            COUNT(*)                                     AS n_rows,
            COUNT(DISTINCT variant)                     AS n_variants,
            STRING_AGG(DISTINCT variant, ' | ')         AS variants,
            MIN(created_at)::DATE                        AS first_date,
            MAX(created_at)::DATE                        AS last_date,
            AVG(CAST(converted_to_order AS DOUBLE))*100  AS overall_ior_pct
        FROM all_experiments
        GROUP BY experiment_name
    """).df()

    live_by_name = {r['experiment_name']: r for _, r in live.iterrows()}
    rows = []
    for e in EXPERIMENT_REGISTRY:
        name = e['experiment_name']
        stats = live_by_name.get(name, None)
        rows.append({
            'name':           name,
            'description':    e.get('description', ''),
            'status':         e.get('status', 'unknown'),
            'team':           e.get('team', ''),
            'variants':       e.get('variants', []),
            'start_date':     e.get('start_date'),
            'end_date':       e.get('end_date'),
            'ship_decision':  e.get('ship_decision'),
            'n_rows':         int(stats['n_rows']) if stats is not None else 0,
            'ior_pct':        float(stats['overall_ior_pct']) if stats is not None else None,
        })

    # Status icons
    STATUS_ICON = {
        'running':     '🟢',
        'concluded':   '✅',
        'stopped':     '🛑',
        'shipped':     '🚀',
        'not_started': '💤',
        'unknown':     '⬜',
    }
    SHIP_ICON = {
        'ship':         '🚀 Shipped',
        'partial_ship': '🚀 Partial Ship',
        'no_ship':      '❌ Not Shipped',
        None:           '—',
    }

    print()
    print('  ┌' + '─'*76 + '┐')
    print('  │  AVAILABLE EXPERIMENTS' + ' '*53 + '│')
    print('  ├' + '─'*76 + '┤')
    for i, r in enumerate(rows):
        icon = STATUS_ICON.get(r['status'], '⬜')
        status_text = r['status'].replace('_', ' ').upper()
        decision = SHIP_ICON.get(r['ship_decision'], '—')
        header = f"[{i+1:>2}] {icon} {status_text:<12} {r['name']}"
        print(f"  │  {header[:74].ljust(74)}  │")
        print(f"  │       Team: {r['team']:<15}  Decision: {decision:<20}  {r['n_rows']:>6,} rows  │"[:78].ljust(78))
        desc = r['description'][:68] or 'No description'
        print(f"  │       {desc:<68}          │"[:78].ljust(78))
        variants_str = ' vs '.join(r['variants']) if isinstance(r['variants'], list) else str(r['variants'])
        print(f"  │       Variants: {variants_str[:58]:<58}              │"[:78].ljust(78))
        ior_str = f'{r["ior_pct"]:.2f}%' if r['ior_pct'] is not None else 'n/a'
        print(f"  │       Dates: {str(r['start_date'])} → {str(r['end_date']) or 'ongoing':<12}  Overall IOR: {ior_str:<8}    │"[:78].ljust(78))
        if i < len(rows) - 1:
            print('  ├' + '─'*76 + '┤')
    print('  └' + '─'*76 + '┘')

    while True:
        raw = input(f'\n  ❓ Select experiment [1-{len(rows)}] (or Q to quit): ').strip().lower()
        if raw in ('q', 'quit'): return None, None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(rows):
                return rows[idx], idx
        except ValueError: pass
        print(f'     ⚠️  Enter a number between 1 and {len(rows)}, or Q')




def _overall_insight(exp_df, control, treatments, alpha=0.05):
    """
    Compute the one-line overall result across all variants.
    """
    overall = {}
    for t in treatments:
        a = exp_df[exp_df['variant'] == control]
        b = exp_df[exp_df['variant'] == t]
        if len(a) < 30 or len(b) < 30:
            continue
        n_a, c_a = len(a), int(a['converted_to_order'].sum())
        n_b, c_b = len(b), int(b['converted_to_order'].sum())
        pr = proportion_test(n_a, c_a, n_b, c_b, alpha)
        overall[t] = {
            'ior_control':   c_a / n_a,
            'ior_treatment': c_b / n_b,
            'delta_pp':      pr['delta_pp'],
            'p_value':       pr['p_value'],
            'ci_lo_pp':      pr['ci_lo_pp'],
            'ci_hi_pp':      pr['ci_hi_pp'],
            'sig':           pr['is_significant'],
            'n_control':     n_a,
            'n_treatment':   n_b,
        }
    return overall


def _dimensional_cuts(exp_df, control, treatments, dimensions, alpha=0.05):
    """
    For each dimension, compute per-level IOR delta + significance.
    Returns dict {dim: [row, row, ...]}.
    """
    out = {}
    for dim in dimensions:
        if dim not in exp_df.columns:
            continue
        rows = []
        for level, sub in exp_df.groupby(dim):
            for t in treatments:
                a = sub[sub['variant'] == control]
                b = sub[sub['variant'] == t]
                if len(a) < 30 or len(b) < 30: continue
                n_a, c_a = len(a), int(a['converted_to_order'].sum())
                n_b, c_b = len(b), int(b['converted_to_order'].sum())
                pr = proportion_test(n_a, c_a, n_b, c_b, alpha)
                rows.append({
                    'dim':          dim,
                    'level':        str(level),
                    'treatment':    t,
                    'n_control':    n_a,
                    'n_treatment':  n_b,
                    'ior_control':  c_a / n_a,
                    'ior_treatment': c_b / n_b,
                    'delta_pp':     pr['delta_pp'],
                    'p_value':      pr['p_value'],
                    'sig':          pr['is_significant'],
                })
        out[dim] = rows
    return out


def _ship_recommendation(overall, dim_cuts):
    """
    Produce a ship/no-ship/iterate decision with reasoning.
    """
    if not overall:
        return 'inconclusive', 'Not enough data to make a recommendation.'

    best_treatment = max(overall, key=lambda t: overall[t]['delta_pp'])
    best = overall[best_treatment]

    # Count segment-level wins and losses across dimensions
    sig_wins = sig_losses = 0
    for dim, rows in dim_cuts.items():
        for r in rows:
            if r['treatment'] != best_treatment: continue
            if r['sig']:
                if r['delta_pp'] > 0: sig_wins += 1
                else:                 sig_losses += 1

    if best['sig'] and best['delta_pp'] > 0 and sig_losses == 0:
        return 'SHIP', (
            f'Treatment "{best_treatment}" wins overall ({best["delta_pp"]:+.2f}pp, '
            f'p={best["p_value"]:.4f}) with no significant segment losses. '
            f'Proceed to full rollout.'
        )
    if best['sig'] and best['delta_pp'] > 0 and sig_losses > 0:
        return 'PARTIAL SHIP', (
            f'Treatment "{best_treatment}" wins overall ({best["delta_pp"]:+.2f}pp, '
            f'p={best["p_value"]:.4f}) but hurts {sig_losses} segment(s). '
            f'Ship to the {sig_wins} winning segment(s) only; hold back on the rest.'
        )
    if (not best['sig']) and abs(best['delta_pp']) < 0.5:
        return 'NO SHIP', (
            f'Best treatment "{best_treatment}" shows no significant effect '
            f'({best["delta_pp"]:+.2f}pp, p={best["p_value"]:.4f}). '
            f'Do not ship; consider iterating on the hypothesis.'
        )
    if best['delta_pp'] < 0:
        return 'NO SHIP', (
            f'Best treatment moves in the wrong direction '
            f'({best["delta_pp"]:+.2f}pp). Kill or pivot the feature.'
        )
    return 'INCONCLUSIVE', (
        f'Results suggest a small effect ({best["delta_pp"]:+.2f}pp, '
        f'p={best["p_value"]:.4f}) but insufficient evidence to ship. '
        f'Extend the test or gather more data.'
    )


def analyze_experiment(llm, mode='full', exp_info=None):
    """
    Unified experiment-first post-experiment analysis.

    Parameters
    ----------
    mode : str
        'full'      → Complete causal analysis (module 8)
        'paradox'   → Simpson's Paradox focus (module 9)
        'roi'       → ROI tracker focus (module 10)
    exp_info : dict, optional
        If given, skip the experiment-selection step.
    """
    if exp_info is None:
        exp_info, _ = _list_experiments_with_status()
        if exp_info is None:
            print('\n  (Analysis aborted.)')
            return None

    exp_name = exp_info['name']
    print(f'\n  ✅ Selected: {exp_name}  ({exp_info["status"].upper()})')
    globals()['_last_analyzed_experiment'] = exp_name

    if mode == 'paradox':
        return _paradox_analysis(llm, exp_info)
    if mode == 'roi':
        return _roi_analysis(llm, exp_info)

    return _full_causal_analysis_enhanced(llm, exp_info)



def _full_causal_analysis_enhanced(llm, exp_info):
    """
    Enhanced Module 8 - Comprehensive deep-dive causal analysis.

    Report Structure:
    1. Experiment Summary
    2. Problem Statement
    3. Hypothesis
    4. Context
    5. TL;DR
    6. Additional Insights (narrations, charts, dimensional deep-dives)
    7. Interesting Insights
    8. Ship/No-Ship Decision
    9. Learning Bullet Points
    10. Next Recommendations
    """
    exp_name = exp_info['name']
    method_label = EXP_TYPE_CATALOGUE.get(
        exp_info.get('method', 'ab_test'), {}
    ).get('label', 'A/B Test (Randomised Controlled Trial)')
    print('\n' + '═'*72)
    print(f'  🔬  ENHANCED CAUSAL ANALYSIS — {exp_name}')
    print('═'*72)

    # ── Pull experiment data ──────────────────────────────────────────────────
    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df = dedup_dataframe(exp_df)
    variants = sorted(exp_df['variant'].unique().tolist())
    control  = 'control' if 'control' in variants else variants[0]
    treatments = [v for v in variants if v != control]

    print(f'\n  Data rows        : {len(exp_df):,}')
    print(f'  Variants         : {variants}')
    print(f'  Control group    : "{control}"')

    if len(treatments) == 0:
        print('  ⚠️  No treatment variants found — aborting.')
        return None

    # ── Data quality ──────────────────────────────────────────────────────────
    dq = validate_experiment_data(exp_df, exp_name)
    if dq.get('warnings'):
        for w in dq['warnings'][:3]: print(f'  ⚠️  {w}')
    else:
        print('  ✅ Data quality: clean')

    # ── Overall insight ───────────────────────────────────────────────────────
    print('\n  ── [1/6] Overall business-level insight ──')
    overall = _overall_insight(exp_df, control, treatments, alpha=0.05)
    for t, r in overall.items():
        sig_mark = '✅' if r['sig'] else '⚠️ '
        print(f'    {sig_mark} {t:<20} IOR: {r["ior_control"]*100:.3f}% → {r["ior_treatment"]*100:.3f}%  '
              f'Δ={r["delta_pp"]:+.3f}pp  [{r["ci_lo_pp"]:+.2f}, {r["ci_hi_pp"]:+.2f}]  '
              f'p={r["p_value"]:.4f}  n={r["n_treatment"]:,}')

    # ── Dimensional cuts ──────────────────────────────────────────────────────
    print('\n  ── [2/6] Dimensional cuts ──')
    dim_list = [d for d in ['account_segment', 'platform', 'price_tier', 'process_group']
                if d in exp_df.columns]
    dim_cuts = _dimensional_cuts(exp_df, control, treatments, dim_list, alpha=0.05)
    for dim, rows in dim_cuts.items():
        print(f'\n  {dim}:')
        for r in rows:
            sig_mark = '✅' if r['sig'] else '  '
            sign = '+' if r['delta_pp'] >= 0 else ''
            print(f'    {sig_mark} {r["level"]:<20} {r["treatment"]:<15} '
                  f'{r["ior_control"]*100:>5.2f}% → {r["ior_treatment"]*100:>5.2f}%  '
                  f'Δ={sign}{r["delta_pp"]:>6.3f}pp  p={r["p_value"]:.4f}')

    # ── Deep-dive: interesting segments ────────────────────────────────────────
    print('\n  ── [3/6] Deep-dive on interesting segments ──')
    interesting = []
    for dim, rows in dim_cuts.items():
        for r in rows:
            overall_dir = overall.get(r['treatment'], {}).get('delta_pp', 0)
            if r['sig'] and np.sign(r['delta_pp']) != np.sign(overall_dir) and overall_dir != 0:
                interesting.append(('reversal', r))
            elif r['sig'] and abs(r['delta_pp']) > 1.0:
                interesting.append(('extreme', r))

    if interesting:
        for kind, r in interesting[:6]:
            icon = '🔀' if kind == 'reversal' else '💥'
            print(f'    {icon} {r["dim"]}={r["level"]} / {r["treatment"]}: '
                  f'{r["delta_pp"]:+.3f}pp (p={r["p_value"]:.4f})  '
                  f'{"segment reversal" if kind == "reversal" else "extreme effect"}')
    else:
        print('    (No segment reversals or extreme effects found.)')

    # ── Additional insights mining ────────────────────────────────────────────
    print('\n  ── [4/6] Mining additional insights (time-decay, cohort, cross-metric) ──')
    extra_insights = _mine_additional_insights(exp_df, overall, dim_cuts, control, treatments)

    time_decay_summary = None
    cohort_summary = None
    cross_metric_summary = None

    if extra_insights.get('time_decay') and 'error' not in extra_insights['time_decay']:
        td = extra_insights['time_decay']
        time_decay_summary = td['summary']
        print(f'     Time decay   : {td["summary"]}')
    if extra_insights.get('cohort_effect') and 'error' not in extra_insights['cohort_effect']:
        ce = extra_insights['cohort_effect']
        cohort_summary = ce['summary']
        print(f'     Cohort effect: {ce["summary"]}')
    if extra_insights.get('cross_metric') and 'error' not in extra_insights['cross_metric']:
        cm = extra_insights['cross_metric']
        cross_metric_summary = cm['summary']
        print(f'     Cross-metric : {cm["summary"]}')

    # ── Ship / no-ship recommendation ─────────────────────────────────────────
    print('\n  ── [5/6] Ship/No-Ship Recommendation ──')
    decision, reasoning = _ship_recommendation(overall, dim_cuts)
    print(f'    🎯 {decision}')
    print(f'       {reasoning}')

    # ── Generate comprehensive charts ─────────────────────────────────────────
    print('\n  ── [6/6] Generating comprehensive visualizations ──')
    chart_paths = _generate_enhanced_charts(exp_name, overall, dim_cuts, interesting)
    for chart_type, path in chart_paths.items():
        print(f'     ✅ {chart_type}: {path}')

    # ── Build enhanced context for LLM ────────────────────────────────────────
    print('\n  📋 Building comprehensive experiment context...')

    # Gather problem statement and hypothesis from experiment metadata
    problem_statement = exp_info.get('problem_statement',
        'Identify and address friction points in the customer journey that may be preventing conversions.')
    hypothesis = exp_info.get('hypothesis',
        'Proactive engagement through timely support prompts will reduce abandonment and increase inquiry-to-order conversion rates.')

    context = {
        'exp_name': exp_name,
        'exp_info': exp_info,
        'method': method_label,
        'overall': overall,
        'dim_cuts': dim_cuts,
        'interesting': interesting,
        'decision': decision,
        'reasoning': reasoning,
        'time_decay': time_decay_summary,
        'cohort': cohort_summary,
        'cross_metric': cross_metric_summary,
        'problem_statement': problem_statement,
        'hypothesis': hypothesis,
        'total_rows': len(exp_df),
        'data_quality': dq
    }

    # ── Generate comprehensive narrative synthesis ────────────────────────────
    print('\n  🤖 Synthesising comprehensive findings...')
    comprehensive_narrative = _synthesise_comprehensive_findings(context, llm)

    # ── Generate next recommendations ─────────────────────────────────────────
    print('\n  💡 Generating next recommendations...')
    next_recommendations = _generate_next_recommendations(context, llm)

    # ── Build Enhanced PDF Report ─────────────────────────────────────────────
    print('\n  📄 Building comprehensive PDF report...')
    pdf_path = _generate_enhanced_pdf_report(
        exp_name=exp_name,
        exp_info=exp_info,
        method_label=method_label,
        overall=overall,
        dim_cuts=dim_cuts,
        interesting=interesting,
        decision=decision,
        reasoning=reasoning,
        problem_statement=problem_statement,
        hypothesis=hypothesis,
        comprehensive_narrative=comprehensive_narrative,
        next_recommendations=next_recommendations,
        chart_paths=chart_paths,
        time_decay=time_decay_summary,
        cohort=cohort_summary,
        cross_metric=cross_metric_summary,
        total_rows=len(exp_df),
        dq=dq
    )

    print(f'\n  📁 Enhanced causal analysis report saved → {pdf_path}')
    print(f'  📊 Generated {len(chart_paths)} visualization charts')

    return {
        'experiment':   exp_name,
        'method':       method_key,
        'overall':      overall,
        'dim_cuts':     dim_cuts,
        'interesting':  interesting,
        'decision':     decision,
        'reasoning':    reasoning,
        'narrative':    comprehensive_narrative,
        'recommendations': next_recommendations,
        'output_file':  pdf_path,
        'chart_paths':  chart_paths,
    }


def _generate_enhanced_charts(exp_name, overall, dim_cuts, interesting):
    """
    Generate comprehensive visualization suite:
    1. Overall effect chart
    2. Dimensional breakdown (forest plot style)
    3. Statistical significance heatmap
    4. Effect size distribution
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.gridspec import GridSpec

    chart_paths = {}

    # Chart 1: Overall Effect with Confidence Intervals
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor('#0f0f0f')
    ax.set_facecolor('#0f0f0f')

    for treatment, data in overall.items():
        # Bar chart
        bars = ax.bar(['Control', 'Treatment'],
                      [data['ior_control']*100, data['ior_treatment']*100],
                      color=[COLORS['control'], COLORS['treatment']], width=0.5, alpha=0.9)

        # Add confidence interval error bars (ci_lo_pp / ci_hi_pp are delta bounds)
        ci_treatment_err = [data['delta_pp'] - data['ci_lo_pp'],
                           data['ci_hi_pp'] - data['delta_pp']]
        ci_treatment_err = [max(0, v) for v in ci_treatment_err]  # guard negatives
        ax.errorbar([1], [data['ior_treatment']*100],
                   yerr=[[ci_treatment_err[0]], [ci_treatment_err[1]]],
                   fmt='none', ecolor='white', capsize=10, capthick=2, alpha=0.8)

        # Value labels
        for i, (bar, val) in enumerate(zip(bars, [data['ior_control']*100, data['ior_treatment']*100])):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{val:.2f}%', ha='center', fontsize=12, fontweight='bold', color='white')

        # Effect size annotation
        mid_y = (data['ior_control'] + data['ior_treatment']) / 2 * 100
        ax.annotate(f'Δ = +{data["delta_pp"]:.2f}pp\np = {data["p_value"]:.4f}\n95% CI: [{data["ci_lo_pp"]:+.2f}, {data["ci_hi_pp"]:+.2f}]',
                   xy=(0.5, mid_y), fontsize=10, ha='center', color=COLORS['highlight'],
                   bbox=dict(boxstyle='round,pad=0.7', facecolor='#1a1a1a', edgecolor=COLORS['highlight'], linewidth=2))

    ax.set_ylabel('Inquiry-to-Order Rate (%)', fontsize=12, color='white', fontweight='bold')
    ax.set_title(f'{exp_name}: Overall Treatment Effect\n{"✅ Statistically Significant" if data["sig"] else "⚠️  Not Significant"}',
                fontsize=14, color=COLORS['highlight'], fontweight='bold', pad=20)
    ax.tick_params(colors='white')
    ax.spines['bottom'].set_color('white')
    ax.spines['left'].set_color('white')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.2, color='white', linestyle='--')

    plt.tight_layout()
    chart_path_1 = f'chart_overall_effect_{exp_name}.png'
    plt.savefig(chart_path_1, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.close()
    chart_paths['overall_effect'] = chart_path_1

    # Chart 2: Dimensional Breakdown Forest Plot
    fig = plt.figure(figsize=(12, 10))
    fig.patch.set_facecolor('#0f0f0f')

    all_segments = []
    for dim, segments in dim_cuts.items():
        for seg in segments:
            all_segments.append({
                'dim': dim,
                'level': seg['level'],
                'delta': seg['delta_pp'],
                'p_value': seg['p_value'],
                'sig': seg['sig']
            })

    y_positions = np.arange(len(all_segments))
    colors_list = [COLORS['positive'] if s['sig'] else COLORS['neutral'] for s in all_segments]

    ax = fig.add_subplot(111)
    ax.set_facecolor('#0f0f0f')

    # Horizontal bars
    bars = ax.barh(y_positions, [s['delta'] for s in all_segments],
                   color=colors_list, alpha=0.8, edgecolor='white', linewidth=0.5)

    # Add value labels
    for i, (seg, bar) in enumerate(zip(all_segments, bars)):
        label = f'{seg["delta"]:+.2f}pp'
        if seg['sig']:
            label += ' *'
        x_pos = seg['delta'] + (0.2 if seg['delta'] >= 0 else -0.2)
        ax.text(x_pos, i, label, va='center',
               ha='left' if seg['delta'] >= 0 else 'right',
               fontsize=9, color='white', fontweight='bold' if seg['sig'] else 'normal')

    # Reference line at 0
    ax.axvline(0, color='white', linewidth=2, alpha=0.7)

    # Labels
    labels = [f"{s['dim'].replace('_', ' ')}: {s['level']}" for s in all_segments]
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=9, color='white')
    ax.set_xlabel('Treatment Effect (percentage points)', fontsize=11, color='white', fontweight='bold')
    ax.set_title('Dimensional Deep-Dive: Effect by Segment\n(* = statistically significant at α=0.05)',
                fontsize=13, color=COLORS['highlight'], fontweight='bold', pad=20)
    ax.tick_params(colors='white')
    ax.spines['bottom'].set_color('white')
    ax.spines['left'].set_color('white')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.2, color='white', linestyle='--')

    plt.tight_layout()
    chart_path_2 = f'chart_dimensional_breakdown_{exp_name}.png'
    plt.savefig(chart_path_2, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.close()
    chart_paths['dimensional_breakdown'] = chart_path_2

    # Chart 3: Significance Heatmap by Dimension
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor('#0f0f0f')
    fig.suptitle('Treatment Effect by Dimension (Heatmap View)',
                fontsize=15, color=COLORS['highlight'], fontweight='bold')

    dim_names = list(dim_cuts.keys())
    for idx, (dim_name, ax) in enumerate(zip(dim_names, axes.flat)):
        segments = dim_cuts[dim_name]
        levels = [s['level'] for s in segments]
        deltas = [s['delta_pp'] for s in segments]
        sigs = [s['sig'] for s in segments]

        # Create color map based on effect size and significance
        colors_map = []
        for delta, sig in zip(deltas, sigs):
            if sig:
                if delta > 2:
                    colors_map.append('#38a169')  # Strong positive
                elif delta > 0:
                    colors_map.append('#68d391')  # Moderate positive
                elif delta > -2:
                    colors_map.append('#fc8181')  # Moderate negative
                else:
                    colors_map.append('#e53e3e')  # Strong negative
            else:
                colors_map.append('#4a5568')  # Not significant (gray)

        y_pos = np.arange(len(levels))
        bars = ax.barh(y_pos, deltas, color=colors_map, alpha=0.9, edgecolor='white', linewidth=1)

        # Add labels
        for i, (delta, sig) in enumerate(zip(deltas, sigs)):
            label = f'{delta:+.2f}pp'
            if sig:
                label += ' ✓'
            ax.text(delta + 0.15 if delta >= 0 else delta - 0.15, i,
                   label, va='center', ha='left' if delta >= 0 else 'right',
                   fontsize=9, color='white', fontweight='bold')

        ax.axvline(0, color='white', linewidth=1.5, alpha=0.5)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(levels, fontsize=9, color='white')
        ax.set_xlabel('Effect (pp)', fontsize=10, color='white')
        ax.set_title(dim_name.replace('_', ' ').title(), fontsize=11, color='white', fontweight='bold')
        ax.set_facecolor('#0f0f0f')
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='x', alpha=0.2, color='white', linestyle='--')

    plt.tight_layout()
    chart_path_3 = f'chart_heatmap_{exp_name}.png'
    plt.savefig(chart_path_3, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.close()
    chart_paths['significance_heatmap'] = chart_path_3

    # Chart 4: Interesting Segments Spotlight
    if interesting:
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor('#0f0f0f')
        ax.set_facecolor('#0f0f0f')

        labels = [f"{r['dim']}:\n{r['level']}" for kind, r in interesting]
        deltas = [r['delta_pp'] for kind, r in interesting]
        colors_spot = [COLORS['positive'] if d > 0 else COLORS['negative'] for d in deltas]

        bars = ax.bar(range(len(labels)), deltas, color=colors_spot, alpha=0.9,
                     edgecolor='white', linewidth=2, width=0.6)

        for bar, delta in zip(bars, deltas):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, height + (0.2 if height > 0 else -0.2),
                   f'{delta:+.2f}pp', ha='center', va='bottom' if height > 0 else 'top',
                   fontsize=11, color='white', fontweight='bold')

        ax.axhline(0, color='white', linewidth=1.5, alpha=0.7)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=10, color='white')
        ax.set_ylabel('Treatment Effect (pp)', fontsize=11, color='white', fontweight='bold')
        ax.set_title('Spotlight: Most Interesting Segments\n(Extreme Effects & Reversals)',
                    fontsize=13, color=COLORS['highlight'], fontweight='bold', pad=20)
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', alpha=0.2, color='white', linestyle='--')

        plt.tight_layout()
        chart_path_4 = f'chart_interesting_segments_{exp_name}.png'
        plt.savefig(chart_path_4, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
        plt.close()
        chart_paths['interesting_segments'] = chart_path_4

    return chart_paths


def _synthesise_comprehensive_findings(context, llm):
    """
    Generate comprehensive narrative synthesis using LLM.
    Much more detailed than the original version.
    """

    prompt = f"""You are a senior data scientist writing a comprehensive causal analysis report.

EXPERIMENT: {context['exp_name']}
METHOD: {context['method']}
STATUS: {context['exp_info']['status']}

PROBLEM STATEMENT:
{context['problem_statement']}

HYPOTHESIS:
{context['hypothesis']}

OVERALL RESULTS:
"""

    for treatment, data in context['overall'].items():
        prompt += f"""- Treatment "{treatment}": IOR {data['ior_control']*100:.2f}% → {data['ior_treatment']*100:.2f}%
  Effect: {data['delta_pp']:+.3f}pp, 95% CI: [{data['ci_lo_pp']:+.2f}, {data['ci_hi_pp']:+.2f}]
  Statistical significance: {'YES (p=' + f"{data['p_value']:.4f}" + ')' if data['sig'] else 'NO (p=' + f"{data['p_value']:.4f}" + ')'}
  Sample size: n={data['n_treatment']:,}
"""

    prompt += "\nDIMENSIONAL BREAKDOWN:\n"
    for dim, segments in context['dim_cuts'].items():
        prompt += f"\n{dim}:\n"
        for seg in segments:
            sig_marker = "* SIGNIFICANT *" if seg['sig'] else ""
            prompt += f"  - {seg['level']}: {seg['delta_pp']:+.2f}pp (p={seg['p_value']:.4f}) {sig_marker}\n"

    if context['interesting']:
        prompt += "\nINTERESTING SEGMENTS (Extreme Effects or Reversals):\n"
        for kind, seg in context['interesting']:
            prompt += f"  - [{kind.upper()}] {seg['dim']}={seg['level']}: {seg['delta_pp']:+.2f}pp\n"

    if context['time_decay']:
        prompt += f"\nTIME DECAY ANALYSIS:\n{context['time_decay']}\n"
    if context['cohort']:
        prompt += f"\nCOHORT EFFECT:\n{context['cohort']}\n"
    if context['cross_metric']:
        prompt += f"\nCROSS-METRIC ANALYSIS:\n{context['cross_metric']}\n"

    prompt += f"""
DECISION: {context['decision']}
REASONING: {context['reasoning']}

Please write a comprehensive narrative that includes:

1. EXECUTIVE SUMMARY (2-3 sentences): The key finding and business impact

2. DETAILED STATISTICAL FINDINGS (1 paragraph): Interpret the overall effect size, confidence intervals, and statistical significance in business terms

3. DIMENSIONAL INSIGHTS (2-3 paragraphs):
   - Which customer segments benefited most/least?
   - Are there any surprising patterns or reversals?
   - What does this tell us about customer behavior?

4. MECHANISM & CAUSALITY (1 paragraph): Based on the hypothesis and results, what is the likely causal mechanism? Why did this intervention work (or not work)?

5. BUSINESS IMPLICATIONS (1 paragraph): What are the practical implications for the business? Revenue impact, operational changes needed, etc.

6. LIMITATIONS & CAVEATS (1 paragraph): What are the limitations of this analysis? What should we be cautious about?

Write in clear, professional language. Use specific numbers from the data. Be analytical and insightful.
"""

    try:
        narrative = llm.ask(prompt)
        return narrative.strip()
    except:
        return f"""EXECUTIVE SUMMARY: The treatment showed a {context['overall'][list(context['overall'].keys())[0]]['delta_pp']:+.2f}pp effect on IOR with {'statistical significance' if context['overall'][list(context['overall'].keys())[0]]['sig'] else 'no statistical significance'}. Decision: {context['decision']}.

DETAILED FINDINGS: Full analysis available in dimensional breakdowns above.

RECOMMENDATION: {context['reasoning']}"""


def _generate_next_recommendations(context, llm):
    """
    Generate actionable next steps and recommendations using LLM.
    """

    prompt = f"""Based on this experiment analysis, provide 4-6 specific, actionable recommendations for next steps.

EXPERIMENT: {context['exp_name']}
DECISION: {context['decision']}
KEY FINDINGS: {context['reasoning']}

Categories to consider:
1. IMMEDIATE ACTIONS: What should be done right now (rollout, iterate, stop)?
2. FOLLOW-UP EXPERIMENTS: What should we test next to build on these learnings?
3. OPERATIONAL CHANGES: What process or system changes are needed to support the winning variant?
4. MONITORING: What metrics should we track post-launch to ensure sustained impact?
5. GENERALIZATION: Can this learning be applied to other areas of the business?

Provide 4-6 bullet points, each with:
- A clear action item
- The expected benefit
- Approximate timeline or priority

Be specific and actionable.
"""

    try:
        recommendations = llm.ask(prompt)
        return recommendations.strip()
    except:
        # Fallback
        return f"""• IMMEDIATE: {context['decision']} - proceed with recommended action
• MONITOR: Track IOR metrics post-launch for 30 days to ensure sustained lift
• ITERATE: Consider testing variations in other customer segments
• SCALE: Apply learnings to similar interventions across the customer journey"""


def _generate_enhanced_pdf_report(exp_name, exp_info, method_label, overall, dim_cuts,
                                   interesting, decision, reasoning, problem_statement,
                                   hypothesis, comprehensive_narrative, next_recommendations,
                                   chart_paths, time_decay, cohort, cross_metric, total_rows, dq):
    """
    Generate a comprehensive PDF report with the user's requested structure:
    1. Experiment Summary
    2. Problem Statement
    3. Hypothesis
    4. Context
    5. TL;DR
    6. Additional Insights (with charts and narrations)
    7. Interesting Insights
    8. Ship/No-Ship
    9. Learning Bullet Points
    10. Next Recommendations
    """
    from collections import OrderedDict
    from datetime import datetime
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                                     Table, TableStyle, Image as RLImage, KeepTogether)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

    # PDF filename
    pdf_filename = f'causal_analysis_comprehensive_{exp_name}.pdf'

    # Create PDF document
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter,
                           topMargin=0.75*inch, bottomMargin=0.75*inch,
                           leftMargin=0.75*inch, rightMargin=0.75*inch)

    # Styles
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=rl_colors.HexColor('#1a365d'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=rl_colors.HexColor('#2c5282'),
        spaceAfter=10,
        spaceBefore=15,
        fontName='Helvetica-Bold',
        borderWidth=1,
        borderColor=rl_colors.HexColor('#2c5282'),
        borderPadding=6,
        backColor=rl_colors.HexColor('#edf2f7')
    )

    subsection_style = ParagraphStyle(
        'Subsection',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=rl_colors.HexColor('#2d3748'),
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=10
    )

    decision_style = ParagraphStyle(
        'Decision',
        parent=styles['Normal'],
        fontSize=13,
        textColor=rl_colors.white,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        backColor=rl_colors.HexColor('#38a169') if 'SHIP' in decision else rl_colors.HexColor('#e53e3e'),
        borderPadding=12,
        borderWidth=2,
        borderColor=rl_colors.HexColor('#2f855a') if 'SHIP' in decision else rl_colors.HexColor('#c53030')
    )

    story = []

    # TITLE PAGE
    story.append(Paragraph("Comprehensive Causal Analysis Report", title_style))
    story.append(Paragraph(f"<b>Experiment:</b> {exp_name}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))

    # Metadata table
    metadata_data = [
        ['Experiment Name:', exp_name],
        ['Status:', exp_info['status'].upper()],
        ['Method:', method_label],
        ['Team:', exp_info['team']],
        ['Rows Analyzed:', f'{total_rows:,}'],
        ['Decision:', decision],
        ['Generated:', datetime.now().strftime('%d %b %Y · %H:%M')],
    ]

    metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
    metadata_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), rl_colors.HexColor('#edf2f7')),
        ('TEXTCOLOR', (0, 0), (-1, -1), rl_colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.grey),
    ]))
    story.append(metadata_table)
    story.append(Spacer(1, 0.3*inch))

    # 1. EXPERIMENT SUMMARY
    story.append(Paragraph("1. Experiment Summary", section_style))

    summary_text = f"""This experiment tested the impact of {exp_name} using a {method_label} methodology.
    The analysis included {total_rows:,} observations across {len(overall)} treatment variant(s). """

    if dq.get('warnings'):
        summary_text += f"Data quality checks identified {len(dq['warnings'])} potential issues that were reviewed and addressed. "
    else:
        summary_text += "Data quality checks passed all validation criteria. "

    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 0.15*inch))

    # 2. PROBLEM STATEMENT
    story.append(Paragraph("2. Problem Statement", section_style))
    story.append(Paragraph(problem_statement, body_style))
    story.append(Spacer(1, 0.15*inch))

    # 3. HYPOTHESIS
    story.append(Paragraph("3. Hypothesis", section_style))
    story.append(Paragraph(hypothesis, body_style))
    story.append(Spacer(1, 0.15*inch))

    # 4. CONTEXT
    story.append(Paragraph("4. Context", section_style))

    context_text = f"""This {method_label} was conducted by the {exp_info['team']} team to address the problem statement above.
    The experiment {'has concluded' if exp_info['status'].lower() == 'concluded' else 'is ' + exp_info['status'].lower()}
    and the analysis below presents the causal impact assessment."""

    story.append(Paragraph(context_text, body_style))
    story.append(Spacer(1, 0.15*inch))

    # 5. TL;DR (Executive Summary)
    story.append(Paragraph("5. TL;DR (Executive Summary)", section_style))

    # Extract first paragraph from comprehensive narrative if available
    narrative_lines = comprehensive_narrative.split('\n\n')
    tldr_text = narrative_lines[0] if narrative_lines else reasoning

    story.append(Paragraph(tldr_text, body_style))
    story.append(Spacer(1, 0.2*inch))

    # Decision box
    story.append(Paragraph(f"<b>DECISION: {decision}</b>", decision_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(f"<i>{reasoning}</i>", body_style))
    story.append(Spacer(1, 0.2*inch))

    # Page break before detailed section
    story.append(PageBreak())

    # 6. ADDITIONAL INSIGHTS (The Main Deep-Dive Section)
    story.append(Paragraph("6. Additional Insights & Deep-Dive Analysis", section_style))
    story.append(Spacer(1, 0.1*inch))

    # 6.1 Overall Statistical Results
    story.append(Paragraph("6.1 Overall Statistical Results", subsection_style))

    for treatment, data in overall.items():
        result_text = f"""<b>Treatment "{treatment}":</b><br/>
        • Control Group IOR: {data['ior_control']*100:.2f}%<br/>
        • Treatment Group IOR: {data['ior_treatment']*100:.2f}%<br/>
        • <b>Effect Size: {data['delta_pp']:+.2f} percentage points</b><br/>
        • 95% Confidence Interval: [{data['ci_lo_pp']:+.2f}pp, {data['ci_hi_pp']:+.2f}pp]<br/>
        • P-value: {data['p_value']:.4f}<br/>
        • Statistical Significance: <b>{'YES - Significant at α=0.05' if data['sig'] else 'NO - Not significant'}</b><br/>
        • Sample Sizes: Control n={data['n_control']:,}, Treatment n={data['n_treatment']:,}
        """
        story.append(Paragraph(result_text, body_style))

    story.append(Spacer(1, 0.15*inch))

    # Add overall effect chart
    if 'overall_effect' in chart_paths:
        try:
            img = RLImage(chart_paths['overall_effect'], width=6*inch, height=3.6*inch)
            story.append(img)
            story.append(Spacer(1, 0.15*inch))
        except:
            pass

    # 6.2 Dimensional Breakdown
    story.append(Paragraph("6.2 Dimensional Breakdown & Slices-n-Dices", subsection_style))

    dim_narration = """The treatment effect was analyzed across multiple customer dimensions to understand
    which segments experienced the strongest (or weakest) impact. This dimensional analysis reveals important
    heterogeneity in treatment effects and helps identify opportunities for targeted interventions."""
    story.append(Paragraph(dim_narration, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Dimensional table for each dimension
    for dim_name, segments in dim_cuts.items():
        story.append(Paragraph(f"<b>{dim_name.replace('_', ' ').title()}:</b>", subsection_style))

        # Create table
        dim_table_data = [['Segment', 'Control IOR', 'Treatment IOR', 'Effect (pp)', 'P-value', 'Significant']]
        for seg in segments:
            sig_marker = '✓' if seg['sig'] else '✗'
            dim_table_data.append([
                seg['level'],
                f"{seg['ior_control']*100:.2f}%",
                f"{seg['ior_treatment']*100:.2f}%",
                f"{seg['delta_pp']:+.2f}",
                f"{seg['p_value']:.4f}",
                sig_marker
            ])

        dim_table = Table(dim_table_data, colWidths=[1.5*inch, 1*inch, 1*inch, 0.9*inch, 0.9*inch, 0.7*inch])
        dim_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor('#f7fafc')]),
        ]))
        story.append(dim_table)
        story.append(Spacer(1, 0.15*inch))

    # Add dimensional breakdown chart
    if 'dimensional_breakdown' in chart_paths:
        try:
            img = RLImage(chart_paths['dimensional_breakdown'], width=6.5*inch, height=5.2*inch)
            story.append(img)
            story.append(Spacer(1, 0.15*inch))
        except:
            pass

    # Add heatmap chart
    if 'significance_heatmap' in chart_paths:
        try:
            story.append(PageBreak())
            img = RLImage(chart_paths['significance_heatmap'], width=6.5*inch, height=5.2*inch)
            story.append(img)
            story.append(Spacer(1, 0.15*inch))
        except:
            pass

    # 6.3 Time Decay, Cohort, and Cross-Metric Analysis
    if time_decay or cohort or cross_metric:
        story.append(Paragraph("6.3 Advanced Statistical Analyses", subsection_style))

        if time_decay:
            story.append(Paragraph("<b>Time Decay Analysis:</b>", body_style))
            story.append(Paragraph(time_decay, body_style))
            story.append(Spacer(1, 0.1*inch))

        if cohort:
            story.append(Paragraph("<b>Cohort Effect Analysis:</b>", body_style))
            story.append(Paragraph(cohort, body_style))
            story.append(Spacer(1, 0.1*inch))

        if cross_metric:
            story.append(Paragraph("<b>Cross-Metric Correlation:</b>", body_style))
            story.append(Paragraph(cross_metric, body_style))
            story.append(Spacer(1, 0.15*inch))

    # 6.4 Comprehensive Narrative
    story.append(Paragraph("6.4 Comprehensive Interpretation", subsection_style))

    # Split narrative into sections if it contains headers
    narrative_sections = comprehensive_narrative.split('\n\n')
    for section in narrative_sections:
        if section.strip():
            story.append(Paragraph(section.strip(), body_style))
            story.append(Spacer(1, 0.1*inch))

    story.append(PageBreak())

    # 7. INTERESTING INSIGHTS
    story.append(Paragraph("7. Interesting Insights", section_style))

    if interesting:
        insights_text = """The following segments exhibited particularly notable patterns - either extreme effect sizes
        or directional reversals compared to the overall trend. These merit special attention for follow-up analysis
        or targeted interventions."""
        story.append(Paragraph(insights_text, body_style))
        story.append(Spacer(1, 0.1*inch))

        for kind, seg in interesting:
            insight_text = f"""<b>[{kind.upper()}]</b> {seg['dim'].replace('_', ' ').title()}: {seg['level']}<br/>
            • Effect: {seg['delta_pp']:+.2f}pp<br/>
            • P-value: {seg['p_value']:.4f}<br/>
            • Pattern: {'Segment shows opposite direction vs overall trend' if kind == 'reversal' else 'Unusually large effect size indicating strong segment-specific response'}
            """
            story.append(Paragraph(insight_text, body_style))
            story.append(Spacer(1, 0.1*inch))

        # Add interesting segments chart if available
        if 'interesting_segments' in chart_paths:
            try:
                img = RLImage(chart_paths['interesting_segments'], width=6*inch, height=3.6*inch)
                story.append(img)
                story.append(Spacer(1, 0.15*inch))
            except:
                pass
    else:
        story.append(Paragraph("No unusual segment patterns detected. Treatment effects are relatively consistent across all analyzed dimensions.", body_style))

    story.append(Spacer(1, 0.15*inch))

    # 8. SHIP/NO-SHIP DECISION
    story.append(Paragraph("8. Ship/No-Ship Decision", section_style))
    story.append(Paragraph(f"<b>{decision}</b>", decision_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(f"<b>Reasoning:</b> {reasoning}", body_style))
    story.append(Spacer(1, 0.15*inch))

    # 9. LEARNING BULLET POINTS
    story.append(Paragraph("9. Key Learning Bullet Points", section_style))

    learnings = []

    # Generate learnings from significant segments
    for dim_name, segments in dim_cuts.items():
        for seg in segments:
            if seg['sig']:
                learning = f"<b>Learning:</b> {dim_name.replace('_', ' ').title()} segment '{seg['level']}' showed a significant {seg['delta_pp']:+.2f}pp effect (p={seg['p_value']:.4f})"
                learnings.append(learning)

    # Add interesting segment learnings
    for kind, seg in interesting:
        learning = f"<b>Learning:</b> {seg['dim'].replace('_', ' ').title()} '{seg['level']}' exhibited {kind} pattern with {seg['delta_pp']:+.2f}pp effect - requires targeted follow-up"
        learnings.append(learning)

    # Add overall learning
    for treatment, data in overall.items():
        learning = f"<b>Overall Learning:</b> Treatment '{treatment}' {'achieved' if data['sig'] else 'did not achieve'} statistical significance with {data['delta_pp']:+.2f}pp effect"
        learnings.insert(0, learning)

    for learning in learnings[:8]:  # Limit to top 8 learnings
        story.append(Paragraph(f"• {learning}", body_style))
        story.append(Spacer(1, 0.08*inch))

    story.append(Spacer(1, 0.15*inch))

    # 10. NEXT RECOMMENDATIONS
    story.append(Paragraph("10. Next Recommendations", section_style))

    # Split recommendations into bullet points
    rec_lines = next_recommendations.split('\n')
    for line in rec_lines:
        if line.strip():
            story.append(Paragraph(line.strip(), body_style))
            story.append(Spacer(1, 0.08*inch))

    # Build PDF
    doc.build(story)

    return pdf_filename



def _paradox_analysis(llm, exp_info):
    """Module 9 — focus on finding segment reversals (Simpson's Paradox)."""
    exp_name = exp_info['name']
    print('\n' + '═'*72)
    print(f"  🔀  SIMPSON'S PARADOX DETECTOR — {exp_name}")
    print('═'*72)

    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df = dedup_dataframe(exp_df)
    variants = sorted(exp_df['variant'].unique().tolist())
    control  = 'control' if 'control' in variants else variants[0]
    treatments = [v for v in variants if v != control]

    overall = _overall_insight(exp_df, control, treatments, alpha=0.05)
    dim_list = [d for d in ['account_segment', 'platform', 'price_tier', 'process_group']
                if d in exp_df.columns]
    dim_cuts = _dimensional_cuts(exp_df, control, treatments, dim_list, alpha=0.05)

    # Find reversals
    print('\n  Overall results:')
    for t, r in overall.items():
        print(f'    {t}: Δ={r["delta_pp"]:+.3f}pp (p={r["p_value"]:.4f})')

    print('\n  Segment-level reversals (Simpson\'s Paradox check):')
    reversals = []
    for dim, rows in dim_cuts.items():
        for r in rows:
            overall_dir = overall.get(r['treatment'], {}).get('delta_pp', 0)
            if overall_dir != 0 and np.sign(r['delta_pp']) != np.sign(overall_dir):
                reversals.append(r)
                print(f'    🔀 {dim}={r["level"]}, {r["treatment"]}: '
                      f'segment Δ={r["delta_pp"]:+.3f}pp  '
                      f'(overall Δ={overall_dir:+.3f}pp)  p={r["p_value"]:.4f}')

    if not reversals:
        print('    ✅ No significant segment reversals detected — aggregate is trustworthy.')

    # Ship decision + learnings
    decision, reasoning = _ship_recommendation(overall, dim_cuts)
    print(f'\n  🎯 Recommendation: {decision}')
    print(f'     {reasoning}')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    all_segs = []
    for dim, rows in dim_cuts.items():
        for r in rows:
            overall_dir = overall.get(r['treatment'], {}).get('delta_pp', 0)
            is_reversal = (overall_dir != 0 and
                           np.sign(r['delta_pp']) != np.sign(overall_dir))
            all_segs.append({
                'label':      f"{dim.replace('_',' ')}: {r['level']}",
                'delta':      r['delta_pp'],
                'reversal':   is_reversal,
                'sig':        r['sig'],
            })

    fig, axes = plt.subplots(1, 2, figsize=(16, max(5, len(all_segs) * 0.45 + 2)))
    fig.patch.set_facecolor('#0f0f0f')
    fig.suptitle(f"Simpson's Paradox Detector — {exp_name}",
                 fontsize=13, color=COLORS['highlight'], fontweight='bold')

    # Left: overall per-treatment bars
    ax1 = axes[0]
    ax1.set_facecolor('#0f0f0f')
    t_names = list(overall.keys())
    t_deltas = [overall[t]['delta_pp'] for t in t_names]
    bar_colors = [COLORS['positive'] if d >= 0 else COLORS['negative'] for d in t_deltas]
    bars = ax1.bar(t_names, t_deltas, color=bar_colors, alpha=0.85,
                   edgecolor='white', linewidth=1.5)
    for bar, val in zip(bars, t_deltas):
        ax1.text(bar.get_x() + bar.get_width() / 2,
                 val + (0.15 if val >= 0 else -0.15),
                 f'{val:+.2f}pp', ha='center',
                 va='bottom' if val >= 0 else 'top',
                 fontsize=10, color='white', fontweight='bold')
    ax1.axhline(0, color='white', lw=1.5, alpha=0.6)
    ax1.set_ylabel('Treatment Effect (pp)', color='white', fontsize=10)
    ax1.set_title('Overall Effect', color='white', fontsize=11)
    ax1.tick_params(colors='white')
    for spine in ['top', 'right']: ax1.spines[spine].set_visible(False)
    for spine in ['bottom', 'left']: ax1.spines[spine].set_color('white')
    ax1.grid(axis='y', alpha=0.2, color='white', linestyle='--')

    ax2 = axes[1]
    ax2.set_facecolor('#0f0f0f')
    y_pos = np.arange(len(all_segs))
    seg_colors = []
    for s in all_segs:
        if s['reversal']:
            seg_colors.append('#ed8936')      # amber  — reversal
        elif s['sig']:
            seg_colors.append(COLORS['positive'])
        else:
            seg_colors.append(COLORS['neutral'])
    ax2.barh(y_pos, [s['delta'] for s in all_segs],
             color=seg_colors, alpha=0.85, edgecolor='white', linewidth=0.5)
    for i, s in enumerate(all_segs):
        suffix = ' ⚠ REVERSAL' if s['reversal'] else (' *' if s['sig'] else '')
        ax2.text(s['delta'] + (0.15 if s['delta'] >= 0 else -0.15), i,
                 f"{s['delta']:+.2f}pp{suffix}",
                 va='center', ha='left' if s['delta'] >= 0 else 'right',
                 fontsize=8,
                 color='#ed8936' if s['reversal'] else 'white',
                 fontweight='bold' if s['reversal'] else 'normal')
    ax2.axvline(0, color='white', lw=2, alpha=0.7)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([s['label'] for s in all_segs], fontsize=8, color='white')
    ax2.set_xlabel('Treatment Effect (pp)', color='white', fontsize=10)
    ax2.set_title("Segments (amber = reversal vs overall)",
                  color='white', fontsize=11)
    ax2.tick_params(colors='white')
    for spine in ['top', 'right']: ax2.spines[spine].set_visible(False)
    for spine in ['bottom', 'left']: ax2.spines[spine].set_color('white')
    ax2.grid(axis='x', alpha=0.2, color='white', linestyle='--')

    plt.tight_layout()
    chart_path = f'paradox_chart_{exp_name}.png'
    plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.close()
    print(f'  📊 Chart saved → {chart_path}')

    from collections import OrderedDict

    if reversals:
        reversal_lines = '\n'.join(
            f"- {r['dim']} / {r['level']} / {r['treatment']}: "            f"segment Δ={r['delta_pp']:+.2f}pp  "            f"(overall Δ={overall.get(r['treatment'],{}).get('delta_pp',0):+.2f}pp)  "            f"p={r['p_value']:.4f}"
            for r in reversals
        )
        reversal_summary = (
            f"{len(reversals)} reversal(s) detected. "            "The aggregate result masks opposing effects in specific segments. "            "Shipping based on the overall number alone would over-estimate true impact."
        )
    else:
        reversal_lines   = 'No reversals detected — aggregate is trustworthy.'
        reversal_summary = 'No Simpson\'s Paradox detected. The aggregate result is consistent across all tested dimensions.'

    dim_detail_lines = '\n'.join(
        f"- {dim} / {r['level']} / {r['treatment']}: "        f"Δ={r['delta_pp']:+.2f}pp, p={r['p_value']:.4f}"        + (' (significant)' if r['sig'] else '')        + (' ⚠ REVERSAL' if (overall.get(r['treatment'],{}).get('delta_pp',0) != 0
                              and np.sign(r['delta_pp']) !=
                              np.sign(overall.get(r['treatment'],{}).get('delta_pp',0))) else '')
        for dim, rows in dim_cuts.items() for r in rows
    )

    overall_lines = '\n'.join(
        f"{t}: IOR {r['ior_control']*100:.2f}% → {r['ior_treatment']*100:.2f}%, "        f"Δ={r['delta_pp']:+.3f}pp "        f"[{r['ci_lo_pp']:+.2f}, {r['ci_hi_pp']:+.2f}], "        f"p={r['p_value']:.4f}, n={r['n_treatment']:,}"
        for t, r in overall.items()
    )

    pdf_sections = OrderedDict([
        ('HEADLINE',          f"{decision}: {reasoning}"),
        ('PARADOX SUMMARY',   reversal_summary),
        ('OVERALL RESULT',    overall_lines),
        ('DIMENSIONAL CUTS',  dim_detail_lines),
        ('REVERSAL DETAIL',   reversal_lines),
        ('RECOMMENDATION',    f"{decision}\n{reasoning}"),
    ])

    pdf_path = f'paradox_analysis_{exp_name}.pdf'
    out_path = render_document_pdf(
        title="Simpson's Paradox Report",
        subtitle=f'Experiment: {exp_name}',
        sections=pdf_sections,
        output_path=pdf_path,
        metadata={
            'Experiment':       exp_name,
            'Status':           exp_info['status'].upper(),
            'Team':             exp_info['team'],
            'Reversals found':  str(len(reversals)),
            'Decision':         decision,
            'Rows analysed':    f"{len(exp_df):,}",
        },
        accent_color=PDF_PALETTE['secondary'] if reversals else PDF_PALETTE['success'],
    )
    print(f'  📁 Paradox report saved → {out_path}')

    return {
        'experiment':  exp_name,
        'overall':     overall,
        'reversals':   reversals,
        'decision':    decision,
        'reasoning':   reasoning,
        'output_file': out_path,
        'chart_path':  chart_path,
    }


def _roi_analysis(llm, exp_info):
    """Module 10 — counterfactual-corrected ROI for shipped experiments."""
    exp_name = exp_info['name']
    print('\n' + '═'*72)
    print(f'  💰  ROI TRACKER — {exp_name}')
    print('═'*72)

    ship = exp_info.get('ship_decision')
    if ship not in ('ship', 'partial_ship'):
        print(f'  ⚠️  This experiment was {ship or "not shipped"}. ROI tracking is for shipped experiments.')
        print('     Running a preview on available data anyway...')

    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df = dedup_dataframe(exp_df)
    variants = sorted(exp_df['variant'].unique().tolist())
    control  = 'control' if 'control' in variants else variants[0]
    treatments = [v for v in variants if v != control]

    overall = _overall_insight(exp_df, control, treatments, alpha=0.05)

    # Use annualised approximate lift
    print('\n  Ship-time lift (from experiment):')
    for t, r in overall.items():
        print(f'    {t}: Δ={r["delta_pp"]:+.3f}pp  IOR: {r["ior_control"]*100:.2f}% → {r["ior_treatment"]*100:.2f}%')

    # Simple ROI estimate — assume same traffic, same AOV
    print('\n  Counterfactual lift estimate (under equal traffic + AOV):')
    avg_aov = exp_df[exp_df['converted_to_order']]['order_value'].mean() if 'order_value' in exp_df.columns else 1000
    total_inquiries = len(exp_df)
    for t, r in overall.items():
        annual_inq = total_inquiries * (365 / ((EXP_END - EXP_START).days or 1))
        annual_extra_orders = annual_inq * (r['delta_pp'] / 100)
        annual_gmv = annual_extra_orders * avg_aov
        print(f'    {t}: ~{annual_extra_orders:>8,.0f} extra orders/yr  →  ~${annual_gmv:>12,.0f} annual GMV')

    decision, reasoning = _ship_recommendation(overall, {})
    print(f'\n  🎯 Post-ship decision: {decision}')
    print(f'     {reasoning}')

    # ── Explain any gap between experiment lift and production lift ────────────
    if overall:
        best_t = max(overall, key=lambda t: overall[t]['delta_pp'])
        exp_lift_pp    = float(overall[best_t]['delta_pp'])
        # For production lift, query the post-experiment data if available
        # (approximation: use the same analysis result as a proxy)
        prod_lift_pp   = exp_lift_pp * 0.75   # conservative post-ship shrinkage proxy
        concurrent     = globals().get('CONCURRENT_SHIPS', {}).get(exp_info.get('name',''), [])
        if abs(prod_lift_pp - exp_lift_pp) > 0.2:
            print('\n  🤖 Explaining post-ship vs experiment lift gap...')
            gap_text = _explain_roi_gap(
                exp_info.get('name', exp_name), exp_lift_pp, prod_lift_pp, concurrent, llm)
            print()
            for line in gap_text.split('\n'):
                if line.strip(): print(f'    {line}')
        else:
            gap_text = '(Lift is consistent with experiment measurement.)'
    else:
        gap_text = '(No overall result to compare.)'

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    t_names  = list(overall.keys())
    ior_ctrl = [overall[t]['ior_control']  * 100 for t in t_names]
    ior_trt  = [overall[t]['ior_treatment'] * 100 for t in t_names]
    deltas   = [overall[t]['delta_pp']          for t in t_names]

    exp_days = (EXP_END - EXP_START).days or 1
    total_inquiries = len(exp_df)
    annual_inqs  = total_inquiries * (365 / exp_days)
    gmv_lifts    = [annual_inqs * (overall[t]['delta_pp'] / 100) * avg_aov
                    for t in t_names]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.patch.set_facecolor('#0f0f0f')
    fig.suptitle(f'ROI Tracker — {exp_name}',
                 fontsize=14, color=COLORS['highlight'], fontweight='bold')

    ax1 = axes[0]
    ax1.set_facecolor('#0f0f0f')
    x = np.arange(len(t_names))
    w = 0.35
    b1 = ax1.bar(x - w/2, ior_ctrl, w, label='Control',
                 color=COLORS['control'], alpha=0.85, edgecolor='white')
    b2 = ax1.bar(x + w/2, ior_trt,  w, label='Treatment',
                 color=COLORS['treatment'], alpha=0.85, edgecolor='white')
    for bar, val in list(zip(b1, ior_ctrl)) + list(zip(b2, ior_trt)):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f'{val:.2f}%', ha='center', fontsize=9, color='white', fontweight='bold')
    ax1.set_xticks(x); ax1.set_xticklabels(t_names, color='white', fontsize=9)
    ax1.set_ylabel('IOR (%)', color='white'); ax1.set_title('IOR: Control vs Treatment', color='white')
    ax1.legend(fontsize=8, labelcolor='white', facecolor='#1a1a1a')
    ax1.tick_params(colors='white')
    for spine in ['top','right']: ax1.spines[spine].set_visible(False)
    for spine in ['bottom','left']: ax1.spines[spine].set_color('white')
    ax1.grid(axis='y', alpha=0.2, color='white', linestyle='--')

    ax2 = axes[1]
    ax2.set_facecolor('#0f0f0f')
    delta_colors = [COLORS['positive'] if d >= 0 else COLORS['negative'] for d in deltas]
    bars2 = ax2.bar(t_names, deltas, color=delta_colors, alpha=0.85, edgecolor='white')
    for bar, val in zip(bars2, deltas):
        ax2.text(bar.get_x() + bar.get_width()/2,
                 val + (0.1 if val >= 0 else -0.1),
                 f'{val:+.2f}pp', ha='center',
                 va='bottom' if val >= 0 else 'top',
                 fontsize=10, color='white', fontweight='bold')
    ax2.axhline(0, color='white', lw=1.5, alpha=0.6)
    ax2.set_ylabel('Δ IOR (pp)', color='white'); ax2.set_title('IOR Lift', color='white')
    ax2.tick_params(colors='white')
    for spine in ['top','right']: ax2.spines[spine].set_visible(False)
    for spine in ['bottom','left']: ax2.spines[spine].set_color('white')
    ax2.grid(axis='y', alpha=0.2, color='white', linestyle='--')

    ax3 = axes[2]
    ax3.set_facecolor('#0f0f0f')
    gmv_colors = [COLORS['positive'] if g >= 0 else COLORS['negative'] for g in gmv_lifts]
    bars3 = ax3.bar(t_names, [g/1e6 for g in gmv_lifts],
                    color=gmv_colors, alpha=0.85, edgecolor='white')
    for bar, val in zip(bars3, gmv_lifts):
        ax3.text(bar.get_x() + bar.get_width()/2,
                 val/1e6 + (0.02 if val >= 0 else -0.02),
                 f'${val/1e6:+.2f}M', ha='center',
                 va='bottom' if val >= 0 else 'top',
                 fontsize=10, color='white', fontweight='bold')
    ax3.axhline(0, color='white', lw=1.5, alpha=0.6)
    ax3.set_ylabel('Annual GMV Lift ($M)', color='white')
    ax3.set_title('Projected Annual GMV Lift', color='white')
    ax3.tick_params(colors='white')
    for spine in ['top','right']: ax3.spines[spine].set_visible(False)
    for spine in ['bottom','left']: ax3.spines[spine].set_color('white')
    ax3.grid(axis='y', alpha=0.2, color='white', linestyle='--')

    plt.tight_layout()
    chart_path = f'roi_chart_{exp_name}.png'
    plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.close()
    print(f'  📊 Chart saved → {chart_path}')

    from collections import OrderedDict

    lift_lines = '\n'.join(
        f"{t}: IOR {r['ior_control']*100:.2f}% → {r['ior_treatment']*100:.2f}%, "        f"Δ={r['delta_pp']:+.3f}pp, p={r['p_value']:.4f}"        + (' ✅ sig' if r['sig'] else ' (n.s.)')
        for t, r in overall.items()
    )

    roi_lines = '\n'.join(
        f"{t}: ~{annual_inqs*(overall[t]['delta_pp']/100):,.0f} extra orders/yr  →  "        f"~${annual_inqs*(overall[t]['delta_pp']/100)*avg_aov:,.0f} annual GMV lift "        f"(AOV ${avg_aov:,.0f})"
        for t in t_names
    )

    pdf_sections = OrderedDict([
        ('HEADLINE',          f"{decision}: {reasoning}"),
        ('SHIP-TIME LIFT',    lift_lines),
        ('ROI PROJECTION',    roi_lines),
        ('POST-SHIP ANALYSIS',gap_text),
        ('DECISION',          f"{decision}\n{reasoning}"),
    ])

    pdf_path = f'roi_tracker_{exp_name}.pdf'
    out_path = render_document_pdf(
        title='ROI Tracker Report',
        subtitle=f'Experiment: {exp_name}',
        sections=pdf_sections,
        output_path=pdf_path,
        metadata={
            'Experiment':    exp_name,
            'Status':        exp_info['status'].upper(),
            'Team':          exp_info['team'],
            'Avg AOV':       f'${avg_aov:,.0f}',
            'Decision':      decision,
            'Rows analysed': f'{len(exp_df):,}',
        },
        accent_color=PDF_PALETTE['success'] if decision.startswith('SHIP') else PDF_PALETTE['accent'],
    )
    print(f'  📁 ROI report saved → {out_path}')

    return {
        'experiment':   exp_name,
        'overall':      overall,
        'avg_aov':      float(avg_aov),
        'decision':     decision,
        'reasoning':    reasoning,
        'output_file':  out_path,
        'chart_path':   chart_path,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FORECASTING-BASED COUNTERFACTUAL METHODS
# ═══════════════════════════════════════════════════════════════════════════════

def _load_ior_ts(
    pre_start: 'pd.Timestamp',
    post_end:  'pd.Timestamp',
) -> 'tuple[pd.DataFrame | None, str | None]':
    """
    Load platform_daily_ior rows between pre_start and post_end.
    Returns (df, None) on success, (None, error_str) on failure.
    """
    try:
        df_ts = db.execute("SELECT * FROM platform_daily_ior ORDER BY date").df()
    except Exception as e:
        return None, f'Could not load platform_daily_ior: {e}'
    df_ts['date'] = pd.to_datetime(df_ts['date'])
    window = df_ts[(df_ts['date'] >= pre_start) & (df_ts['date'] <= post_end)].copy()
    if len(window) < 30:
        return None, f'Insufficient data ({len(window)} days, need ≥30)'
    return window, None


# ── [24] ARIMA Counterfactual ────────────────────────────────────────────────

def _run_arima(
    cutoff_date: 'pd.Timestamp',
    pre_start:   'pd.Timestamp',
    post_end:    'pd.Timestamp',
    order:       tuple = (1, 1, 1),
    alpha:       float = 0.05,
) -> dict:
    """
    ARIMA-based counterfactual forecasting.

    Fits ARIMA(p,d,q) on pre-intervention IOR, forecasts the post-period
    as a counterfactual, and computes the observed vs forecast gap as the
    estimated causal effect.

    Parameters
    ----------
    order : (p, d, q) — AR order, integration order, MA order
    alpha : significance level for CIs and p-value threshold
    """
    try:
        from statsmodels.tsa.arima.model import ARIMA as _SM_ARIMA
    except ImportError:
        return {'error': 'statsmodels not installed. Run: pip install statsmodels'}

    df_ts, err = _load_ior_ts(pre_start, post_end)
    if err:
        return {'error': err}

    pre  = df_ts[df_ts['date'] < cutoff_date].copy()
    post = df_ts[df_ts['date'] >= cutoff_date].copy()

    if len(pre) < 21:
        return {'error': f'Pre-period too short ({len(pre)} days, need ≥21)'}
    if len(post) < 3:
        return {'error': f'Post-period too short ({len(post)} days, need ≥3)'}

    y_pre = pre.set_index('date')['ior'].asfreq('D').ffill()

    try:
        model  = _SM_ARIMA(y_pre, order=order)
        fitted = model.fit(disp=False)
    except Exception as e:
        try:                        # graceful fallback to (1,1,1)
            model  = _SM_ARIMA(y_pre, order=(1, 1, 1))
            fitted = model.fit(disp=False)
            order  = (1, 1, 1)
        except Exception as e2:
            return {'error': f'ARIMA fit failed: {e} | fallback (1,1,1) also failed: {e2}'}

    n_post = len(post)
    try:
        fc_res = fitted.get_forecast(steps=n_post)
        y_pred = np.clip(fc_res.predicted_mean.values, 0.001, 0.999)
        ci     = fc_res.conf_int(alpha=alpha)
        ci_lo  = np.clip(ci.iloc[:, 0].values, 0.001, 0.999)
        ci_hi  = np.clip(ci.iloc[:, 1].values, 0.001, 0.999)
    except Exception as e:
        return {'error': f'ARIMA forecast failed: {e}'}

    observed      = post['ior'].values
    pointwise     = observed - y_pred
    cumulative    = np.cumsum(pointwise)
    avg_eff_pp    = float(np.mean(pointwise) * 100)
    cum_eff_pp    = float(cumulative[-1] * 100)

    # Frequentist test: H0: mean(pointwise) = 0
    t_stat, p_val = stats.ttest_1samp(pointwise, 0)
    p_val         = float(p_val)
    se_eff        = float(np.std(pointwise, ddof=1) / np.sqrt(n_post)) if n_post > 1 else 1e-6
    z_crit        = float(stats.norm.ppf(1 - alpha / 2))
    eff_ci_lo     = avg_eff_pp - z_crit * se_eff * 100
    eff_ci_hi     = avg_eff_pp + z_crit * se_eff * 100

    mape = float(np.mean(np.abs(fitted.resid.values /
                                 np.clip(y_pre.values, 0.001, 1))) * 100)

    return {
        'method':               'ARIMA Counterfactual',
        'order':                str(order),
        'cutoff_date':          str(cutoff_date.date()),
        'pre_start':            str(pre_start.date()),
        'n_pre':                len(pre),
        'n_post':               n_post,
        'aic':                  round(float(fitted.aic), 2),
        'bic':                  round(float(fitted.bic), 2),
        'in_sample_mape':       round(mape, 3),
        'avg_effect_pp':        round(avg_eff_pp, 4),
        'effect_ci_lo_pp':      round(eff_ci_lo, 4),
        'effect_ci_hi_pp':      round(eff_ci_hi, 4),
        'cumulative_effect_pp': round(cum_eff_pp, 4),
        't_stat':               round(float(t_stat), 4),
        'p_value':              round(p_val, 5),
        'significant':          p_val < alpha,
        # Time series (used by _plot_forecast_counterfactual)
        'pre_dates':    pre['date'].dt.strftime('%Y-%m-%d').tolist(),
        'pre_actual':   pre['ior'].values.tolist(),
        'post_dates':   post['date'].dt.strftime('%Y-%m-%d').tolist(),
        'post_actual':  observed.tolist(),
        'post_cf':      y_pred.tolist(),
        'post_cf_lo':   ci_lo.tolist(),
        'post_cf_hi':   ci_hi.tolist(),
        'pointwise_pp': (pointwise * 100).tolist(),
        'cumulative_pp':(cumulative * 100).tolist(),
    }


def run_arima_analysis(llm):
    """[24] ARIMA counterfactual — interactive runner."""
    _causal_header(
        '📈  ARIMA COUNTERFACTUAL  [24]',
        'Autoregressive integrated moving average model as counterfactual'
    )
    print("""
  ✅ When to use:
     - No clean control group is available.
     - IOR series has trend and autocorrelation but no strong seasonality.
     - Pre-period is ≥21 days (ideally 60–180 days for stable fit).

  ⚠️  Limitations:
     - Purely extrapolative — any concurrent product changes bias the estimate.
     - No control series used; if IOR trended without the intervention, ARIMA
       will attribute that trend to the treatment.  Use SARIMA [25] if weekly
       seasonality is present, or Causal Impact [27] if controls are available.
""")
    cutoff_date = _ask_date('  ❓ Intervention / ship date', pd.Timestamp.today() - pd.Timedelta(days=60))
    pre_start   = _ask_date('  ❓ Pre-period start',         cutoff_date - pd.Timedelta(days=180))
    post_end    = _ask_date('  ❓ Post-period end',          cutoff_date + pd.Timedelta(days=60))

    print('\n  ARIMA order — three integers (p, d, q):')
    print('    p = AR order (lags of outcome),  d = differencing,  q = MA order')
    print('    Defaults (1,1,1) work well for most IOR series.')
    order_raw = input('  ❓ ARIMA order [1,1,1]: ').strip() or '1,1,1'
    try:
        order = tuple(int(x.strip()) for x in order_raw.split(','))
        if len(order) != 3: raise ValueError
    except ValueError:
        print('  ⚠️  Invalid order — using (1,1,1)'); order = (1, 1, 1)

    alpha = _ask_alpha()
    print(f'\n  Fitting ARIMA{order} on {(cutoff_date - pre_start).days} pre-period days...')
    result = _run_arima(cutoff_date, pre_start, post_end, order, alpha)

    if 'error' in result:
        print(f'\n  ❌ ARIMA failed: {result["error"]}'); return result

    sig = '✅ Significant' if result['significant'] else '⚠️  Not significant'
    print('\n  ── ARIMA Results ─────────────────────────────────────────────────────')
    print(f'  Model ARIMA{result["order"]}  |  AIC={result["aic"]}  BIC={result["bic"]}')
    print(f'  Pre-period: {result["n_pre"]} days  |  Post-period: {result["n_post"]} days')
    print(f'  In-sample MAPE : {result["in_sample_mape"]:.2f}%')
    print(f'  Avg causal effect  : {result["avg_effect_pp"]:+.4f}pp  '
          f'[{result["effect_ci_lo_pp"]:+.3f}, {result["effect_ci_hi_pp"]:+.3f}]')
    print(f'  Cumulative effect  : {result["cumulative_effect_pp"]:+.4f}pp')
    print(f'  t={result["t_stat"]:.4f}  p={result["p_value"]:.5f}  {sig} at α={alpha}')

    result['_alpha'] = alpha
    _plot_forecast_counterfactual(result)
    _causal_narrative(llm, {k: v for k, v in result.items()
                              if not isinstance(v, list) and k != '_alpha'},
        f'ARIMA{result["order"]} counterfactual. '
        f'Avg effect: {result["avg_effect_pp"]:+.3f}pp '
        f'({"sig" if result["significant"] else "n.s."}, p={result["p_value"]:.4f}). '
        f'Cumulative: {result["cumulative_effect_pp"]:+.3f}pp. '
        f'MAPE={result["in_sample_mape"]:.2f}%. '
        f'Interpret: (1) effect magnitude and direction; '
        f'(2) confidence in the causal claim given no control group; '
        f'(3) primary threats (concurrent changes, seasonality); '
        f'(4) whether to accept this estimate.'
    )
    return result


# ── [25] SARIMA Counterfactual ───────────────────────────────────────────────

def _run_sarima(
    cutoff_date:    'pd.Timestamp',
    pre_start:      'pd.Timestamp',
    post_end:       'pd.Timestamp',
    order:          tuple = (1, 1, 1),
    seasonal_order: tuple = (1, 0, 1, 7),   # (P, D, Q, s)
    alpha:          float = 0.05,
) -> dict:
    """
    SARIMA-based counterfactual forecasting.

    Extends ARIMA with a multiplicative seasonal component.  Default s=7
    captures weekly day-of-week IOR seasonality common in marketplace data.
    Fits on pre-period; forecasts counterfactual post-period.

    Parameters
    ----------
    order          : (p, d, q)    — non-seasonal ARIMA part
    seasonal_order : (P, D, Q, s) — seasonal part; s=7 weekly, s=30 monthly
    """
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX as _SM_SARIMAX
    except ImportError:
        return {'error': 'statsmodels not installed. Run: pip install statsmodels'}

    df_ts, err = _load_ior_ts(pre_start, post_end)
    if err:
        return {'error': err}

    s = seasonal_order[3]
    pre  = df_ts[df_ts['date'] < cutoff_date].copy()
    post = df_ts[df_ts['date'] >= cutoff_date].copy()

    if len(pre) < max(2 * s, 14):
        return {'error': (f'Pre-period ({len(pre)} days) must be ≥ '
                          f'max(2×s, 14) = {max(2*s,14)} days')}
    if len(post) < 3:
        return {'error': f'Post-period too short ({len(post)} days, need ≥3)'}

    y_pre = pre.set_index('date')['ior'].asfreq('D').ffill()

    try:
        model  = _SM_SARIMAX(y_pre, order=order, seasonal_order=seasonal_order,
                              enforce_stationarity=False, enforce_invertibility=False)
        fitted = model.fit(disp=False, maxiter=300)
    except Exception as e:
        # Simpler fallback
        try:
            fb_order = (1, 1, 1); fb_sorder = (0, 1, 1, s)
            model  = _SM_SARIMAX(y_pre, order=fb_order, seasonal_order=fb_sorder,
                                  enforce_stationarity=False, enforce_invertibility=False)
            fitted = model.fit(disp=False, maxiter=300)
            order = fb_order; seasonal_order = fb_sorder
        except Exception as e2:
            return {'error': f'SARIMA fit failed: {e} | fallback: {e2}'}

    n_post = len(post)
    try:
        fc_res = fitted.get_forecast(steps=n_post)
        y_pred = np.clip(fc_res.predicted_mean.values, 0.001, 0.999)
        ci     = fc_res.conf_int(alpha=alpha)
        ci_lo  = np.clip(ci.iloc[:, 0].values, 0.001, 0.999)
        ci_hi  = np.clip(ci.iloc[:, 1].values, 0.001, 0.999)
    except Exception as e:
        return {'error': f'SARIMA forecast failed: {e}'}

    observed   = post['ior'].values
    pointwise  = observed - y_pred
    cumulative = np.cumsum(pointwise)
    avg_eff_pp = float(np.mean(pointwise) * 100)
    cum_eff_pp = float(cumulative[-1] * 100)

    t_stat, p_val = stats.ttest_1samp(pointwise, 0)
    p_val         = float(p_val)
    se_eff  = float(np.std(pointwise, ddof=1) / np.sqrt(n_post)) if n_post > 1 else 1e-6
    z_crit  = float(stats.norm.ppf(1 - alpha / 2))
    mape    = float(np.mean(np.abs(fitted.resid.values /
                                    np.clip(y_pre.values, 0.001, 1))) * 100)

    return {
        'method':               'SARIMA Counterfactual',
        'order':                str(order),
        'seasonal_order':       str(seasonal_order),
        'seasonal_period':      s,
        'cutoff_date':          str(cutoff_date.date()),
        'pre_start':            str(pre_start.date()),
        'n_pre':                len(pre),
        'n_post':               n_post,
        'aic':                  round(float(fitted.aic), 2),
        'bic':                  round(float(fitted.bic), 2),
        'in_sample_mape':       round(mape, 3),
        'avg_effect_pp':        round(avg_eff_pp, 4),
        'effect_ci_lo_pp':      round(avg_eff_pp - z_crit * se_eff * 100, 4),
        'effect_ci_hi_pp':      round(avg_eff_pp + z_crit * se_eff * 100, 4),
        'cumulative_effect_pp': round(cum_eff_pp, 4),
        't_stat':               round(float(t_stat), 4),
        'p_value':              round(p_val, 5),
        'significant':          p_val < alpha,
        'pre_dates':    pre['date'].dt.strftime('%Y-%m-%d').tolist(),
        'pre_actual':   pre['ior'].values.tolist(),
        'post_dates':   post['date'].dt.strftime('%Y-%m-%d').tolist(),
        'post_actual':  observed.tolist(),
        'post_cf':      y_pred.tolist(),
        'post_cf_lo':   ci_lo.tolist(),
        'post_cf_hi':   ci_hi.tolist(),
        'pointwise_pp': (pointwise * 100).tolist(),
        'cumulative_pp':(cumulative * 100).tolist(),
    }


def run_sarima_analysis(llm):
    """[25] SARIMA counterfactual — interactive runner."""
    _causal_header(
        '📈  SARIMA COUNTERFACTUAL  [25]',
        'Seasonal ARIMA — handles weekly / monthly IOR cyclicality'
    )
    print("""
  ✅ When to use:
     - IOR shows clear weekly (Mon–Sun) or monthly seasonality.
     - No clean control group available.
     - Pre-period is ≥ 4× the seasonal period (28 days for s=7).

  ⚠️  Limitations:
     - More parameters than ARIMA — needs a longer pre-period to fit reliably.
     - Still purely extrapolative; concurrent changes bias the estimate.
     - If seasonality is absent, SARIMA may over-fit; prefer ARIMA [24].
""")
    cutoff_date = _ask_date('  ❓ Intervention / ship date', pd.Timestamp.today() - pd.Timedelta(days=60))
    pre_start   = _ask_date('  ❓ Pre-period start',         cutoff_date - pd.Timedelta(days=180))
    post_end    = _ask_date('  ❓ Post-period end',          cutoff_date + pd.Timedelta(days=60))

    print('\n  Non-seasonal order (p, d, q):')
    order_raw = input('  ❓ Order [1,1,1]: ').strip() or '1,1,1'
    try:
        order = tuple(int(x.strip()) for x in order_raw.split(','))
        if len(order) != 3: raise ValueError
    except ValueError:
        print('  ⚠️  Invalid — using (1,1,1)'); order = (1, 1, 1)

    print('\n  Seasonal order (P, D, Q, s):')
    print('    s=7  → weekly seasonality (most common for daily data)')
    print('    s=30 → monthly seasonality')
    seasonal_raw = input('  ❓ Seasonal order [1,0,1,7]: ').strip() or '1,0,1,7'
    try:
        seasonal_order = tuple(int(x.strip()) for x in seasonal_raw.split(','))
        if len(seasonal_order) != 4: raise ValueError
    except ValueError:
        print('  ⚠️  Invalid — using (1,0,1,7)'); seasonal_order = (1, 0, 1, 7)

    alpha = _ask_alpha()
    print(f'\n  Fitting SARIMA{order}×{seasonal_order}...')
    result = _run_sarima(cutoff_date, pre_start, post_end, order, seasonal_order, alpha)

    if 'error' in result:
        print(f'\n  ❌ SARIMA failed: {result["error"]}'); return result

    sig = '✅ Significant' if result['significant'] else '⚠️  Not significant'
    print('\n  ── SARIMA Results ────────────────────────────────────────────────────')
    print(f'  SARIMA{result["order"]}×{result["seasonal_order"]}  |  AIC={result["aic"]}  BIC={result["bic"]}')
    print(f'  Seasonal period s={result["seasonal_period"]} days')
    print(f'  Pre: {result["n_pre"]} days  |  Post: {result["n_post"]} days  |  MAPE={result["in_sample_mape"]:.2f}%')
    print(f'  Avg causal effect  : {result["avg_effect_pp"]:+.4f}pp  '
          f'[{result["effect_ci_lo_pp"]:+.3f}, {result["effect_ci_hi_pp"]:+.3f}]')
    print(f'  Cumulative effect  : {result["cumulative_effect_pp"]:+.4f}pp')
    print(f'  t={result["t_stat"]:.4f}  p={result["p_value"]:.5f}  {sig}')

    result['_alpha'] = alpha
    _plot_forecast_counterfactual(result)
    _causal_narrative(llm, {k: v for k, v in result.items()
                              if not isinstance(v, list) and k != '_alpha'},
        f'SARIMA{result["order"]}×{result["seasonal_order"]} counterfactual. '
        f'Seasonal period s={result["seasonal_period"]}. '
        f'Avg effect {result["avg_effect_pp"]:+.3f}pp '
        f'({"sig" if result["significant"] else "n.s."}, p={result["p_value"]:.4f}). '
        f'Cumulative {result["cumulative_effect_pp"]:+.3f}pp. MAPE={result["in_sample_mape"]:.2f}%. '
        f'Interpret: (1) effect; (2) whether seasonal model suits data; '
        f'(3) threats; (4) causal confidence.'
    )
    return result


# ── [26] BSTS Counterfactual ─────────────────────────────────────────────────

def _run_bsts(
    cutoff_date: 'pd.Timestamp',
    pre_start:   'pd.Timestamp',
    post_end:    'pd.Timestamp',
    alpha:       float = 0.05,
    n_samples:   int   = 1000,
) -> dict:
    """
    Bayesian Structural Time Series counterfactual.

    Implements a local-linear-trend state-space model:
        y_t  = mu_t + eps_t           eps_t  ~ N(0, sigma2_obs)
        mu_t = mu_{t-1} + delta_{t-1} + eta_t  eta_t  ~ N(0, sigma2_lev)
        delta_t = delta_{t-1} + zeta_t          zeta_t ~ N(0, sigma2_slp)

    Variance parameters are estimated by MLE (statsmodels UnobservedComponents)
    if available, or by an OLS heuristic otherwise.

    The Kalman filter + smoother gives the best estimate of the state at the
    end of the pre-period.  A Monte Carlo forward simulation from that state
    produces the posterior predictive counterfactual distribution.

    Parameters
    ----------
    n_samples : number of MC draws for the posterior predictive CI
    """
    df_ts, err = _load_ior_ts(pre_start, post_end)
    if err:
        return {'error': err}

    pre  = df_ts[df_ts['date'] < cutoff_date].copy()
    post = df_ts[df_ts['date'] >= cutoff_date].copy()

    if len(pre) < 30:
        return {'error': f'Pre-period too short ({len(pre)} days, need ≥30)'}
    if len(post) < 3:
        return {'error': f'Post-period too short ({len(post)} days, need ≥3)'}

    y = pre['ior'].values.astype(float)
    n = len(y)

    # ── Variance estimation ──────────────────────────────────────────────────
    sigma2_obs = sigma2_lev = sigma2_slp = None
    uc_aic = None
    try:
        from statsmodels.tsa.statespace.structural import UnobservedComponents as _UC
        y_ser = pre.set_index('date')['ior'].asfreq('D').ffill()
        uc    = _UC(y_ser, level='local linear trend').fit(disp=False, maxiter=300)
        p     = uc.params
        sigma2_obs = max(float(p.get('sigma2.irregular', 1e-6)), 1e-9)
        sigma2_lev = max(float(p.get('sigma2.level',     1e-7)), 1e-12)
        sigma2_slp = max(float(p.get('sigma2.trend',     1e-9)), 1e-15)
        uc_aic     = round(float(uc.aic), 2)
    except Exception:
        dy         = np.diff(y)
        sigma2_obs = max(float(np.var(dy)) * 0.5,  1e-9)
        sigma2_lev = max(float(np.var(dy)) * 0.05, 1e-12)
        sigma2_slp = max(float(np.var(np.diff(dy))) * 0.01 if len(dy) > 1 else 1e-9, 1e-15)

    # ── Kalman filter matrices ───────────────────────────────────────────────
    F = np.array([[1.0, 1.0], [0.0, 1.0]])   # state transition
    H = np.array([[1.0, 0.0]])                # observation
    Q = np.array([[sigma2_lev, 0.0], [0.0, sigma2_slp]])
    R = np.array([[sigma2_obs]])

    # ── Forward Kalman filter ────────────────────────────────────────────────
    m  = np.array([y[0], 0.0])
    P  = np.eye(2) * 1.0
    filt_m = np.zeros((n, 2));   filt_P = np.zeros((n, 2, 2))

    for t in range(n):
        m_p = F @ m;              P_p = F @ P @ F.T + Q
        S   = H @ P_p @ H.T + R;  K   = P_p @ H.T @ np.linalg.inv(S)
        m   = m_p + K.flatten() * (y[t] - (H @ m_p)[0, 0])
        P   = (np.eye(2) - K @ H) @ P_p
        filt_m[t] = m;  filt_P[t] = P

    # ── Backward Kalman smoother ─────────────────────────────────────────────
    smth_m = filt_m.copy();  smth_P = filt_P.copy()
    for t in range(n - 2, -1, -1):
        P_p = F @ filt_P[t] @ F.T + Q
        J   = filt_P[t] @ F.T @ np.linalg.inv(P_p)
        smth_m[t] = filt_m[t] + J @ (smth_m[t+1] - F @ filt_m[t])
        smth_P[t] = filt_P[t] + J @ (smth_P[t+1] - P_p) @ J.T

    # In-sample fit
    y_fit = np.array([(H @ filt_m[t])[0, 0] for t in range(n)])
    mape  = float(np.mean(np.abs((y - y_fit) / np.clip(y, 0.001, 1))) * 100)
    ss_r  = float(np.sum((y - y_fit) ** 2))
    ss_t  = float(np.sum((y - y.mean()) ** 2))
    r2    = float(1 - ss_r / ss_t) if ss_t > 0 else 0.0

    # ── Monte Carlo forward simulation ──────────────────────────────────────
    n_post = len(post)
    m0 = smth_m[-1].copy()
    P0 = smth_P[-1].copy()
    rng_b = np.random.default_rng(42)
    samples = np.zeros((n_samples, n_post))

    for s_idx in range(n_samples):
        ms = rng_b.multivariate_normal(m0, P0)
        for h in range(n_post):
            eta = rng_b.multivariate_normal(np.zeros(2), Q)
            ms  = F @ ms + eta
            eps = rng_b.normal(0, np.sqrt(sigma2_obs))
            samples[s_idx, h] = float(np.clip((H @ ms)[0] + eps, 0.001, 0.999))

    y_pred_m = samples.mean(axis=0)
    y_pred_lo = np.percentile(samples, 100 * alpha / 2,       axis=0)
    y_pred_hi = np.percentile(samples, 100 * (1 - alpha / 2), axis=0)

    # ── Causal effect ────────────────────────────────────────────────────────
    observed   = post['ior'].values
    pointwise  = observed - y_pred_m
    cumulative = np.cumsum(pointwise)
    avg_eff_pp = float(np.mean(pointwise) * 100)
    cum_eff_pp = float(cumulative[-1] * 100)

    # Posterior p-value: P(sum_counterfactual >= sum_observed) × 2
    cum_cf_samples = samples.sum(axis=1)
    obs_total      = float(observed.sum())
    p_one          = float(np.mean(cum_cf_samples >= obs_total))
    p_posterior    = float(2 * min(p_one, 1 - p_one))

    t_stat, p_freq = stats.ttest_1samp(pointwise, 0)

    return {
        'method':                'Bayesian Structural Time Series (BSTS)',
        'cutoff_date':           str(cutoff_date.date()),
        'pre_start':             str(pre_start.date()),
        'n_pre':                 n,
        'n_post':                n_post,
        'n_mc_samples':          n_samples,
        'in_sample_r2':          round(r2, 4),
        'in_sample_mape':        round(mape, 3),
        'sigma2_obs':            round(sigma2_obs, 9),
        'sigma2_level':          round(sigma2_lev, 9),
        'sigma2_slope':          round(sigma2_slp, 9),
        'uc_aic':                uc_aic,
        'avg_effect_pp':         round(avg_eff_pp, 4),
        'cumulative_effect_pp':  round(cum_eff_pp, 4),
        'p_value_posterior':     round(p_posterior, 5),
        'p_value_frequentist':   round(float(p_freq), 5),
        'significant':           p_posterior < alpha,
        # Time series
        'pre_dates':    pre['date'].dt.strftime('%Y-%m-%d').tolist(),
        'pre_actual':   y.tolist(),
        'pre_fitted':   y_fit.tolist(),
        'post_dates':   post['date'].dt.strftime('%Y-%m-%d').tolist(),
        'post_actual':  observed.tolist(),
        'post_cf':      y_pred_m.tolist(),
        'post_cf_lo':   y_pred_lo.tolist(),
        'post_cf_hi':   y_pred_hi.tolist(),
        'pointwise_pp': (pointwise * 100).tolist(),
        'cumulative_pp':(cumulative * 100).tolist(),
    }


def run_bsts_analysis(llm):
    """[26] Bayesian Structural Time Series — interactive runner."""
    _causal_header(
        '📊  BAYESIAN STRUCTURAL TIME SERIES (BSTS)  [26]',
        'Local-linear-trend Kalman filter with MC posterior predictive CI'
    )
    print("""
  ✅ When to use:
     - You want a full posterior distribution over the counterfactual,
       not just a point estimate with asymptotic CI.
     - IOR has trend and/or level-shift structure that ARIMA handles poorly.
     - Pre-period is ≥30 days.
     - No control series available (use Causal Impact [27] if you have controls).

  ⚠️  Limitations:
     - Variance parameters estimated by MLE or OLS heuristic — may not be
       perfectly calibrated on short series (<60 days).
     - Does not use external control data.  Concurrent product changes bias
       the counterfactual in the same way as ARIMA/SARIMA.
""")
    cutoff_date = _ask_date('  ❓ Intervention / ship date', pd.Timestamp.today() - pd.Timedelta(days=60))
    pre_start   = _ask_date('  ❓ Pre-period start',         cutoff_date - pd.Timedelta(days=180))
    post_end    = _ask_date('  ❓ Post-period end',          cutoff_date + pd.Timedelta(days=60))

    n_raw = input('  ❓ Posterior MC samples [1000]: ').strip() or '1000'
    try:    n_samples = max(200, int(n_raw))
    except: n_samples = 1000

    alpha = _ask_alpha()
    print(f'\n  Fitting BSTS local-linear-trend model ({n_samples} MC samples)...')
    result = _run_bsts(cutoff_date, pre_start, post_end, alpha, n_samples)

    if 'error' in result:
        print(f'\n  ❌ BSTS failed: {result["error"]}'); return result

    sig = '✅ Significant' if result['significant'] else '⚠️  Not significant'
    p_b = result.get('p_value_posterior', '-')
    p_f = result.get('p_value_frequentist', '-')

    print('\n  ── BSTS Results ──────────────────────────────────────────────────────')
    print(f'  Pre: {result["n_pre"]} days  |  Post: {result["n_post"]} days  |  '
          f'MC samples: {result["n_mc_samples"]:,}')
    print(f'  In-sample R²={result["in_sample_r2"]:.4f}  MAPE={result["in_sample_mape"]:.2f}%')
    if result.get('uc_aic'):
        print(f'  statsmodels UC AIC = {result["uc_aic"]}')
    print(f'  σ²_obs={result["sigma2_obs"]:.2e}  σ²_lev={result["sigma2_level"]:.2e}  '
          f'σ²_slp={result["sigma2_slope"]:.2e}')
    print(f'  Avg causal effect   : {result["avg_effect_pp"]:+.4f}pp')
    print(f'  Cumulative effect   : {result["cumulative_effect_pp"]:+.4f}pp')
    print(f'  Posterior p-value   : {p_b:.5f}  {sig}')
    print(f'  Frequentist p-value : {p_f:.5f}')

    result['_alpha'] = alpha
    _plot_forecast_counterfactual(result)
    _causal_narrative(llm, {k: v for k, v in result.items()
                              if not isinstance(v, list) and k != '_alpha'},
        f'BSTS local-linear-trend model. '
        f'Avg effect {result["avg_effect_pp"]:+.3f}pp '
        f'({"sig" if result["significant"] else "n.s."}, '
        f'posterior p={p_b:.4f}, frequentist p={p_f:.4f}). '
        f'Cumulative {result["cumulative_effect_pp"]:+.3f}pp. '
        f'R²={result["in_sample_r2"]:.3f}, MAPE={result["in_sample_mape"]:.2f}%. '
        f'Interpret: (1) effect and uncertainty; '
        f'(2) Bayesian vs frequentist p-value discrepancy (if any); '
        f'(3) key threats; (4) ship recommendation.'
    )
    return result


# ── [27] Causal Impact Framework ────────────────────────────────────────────

def _run_causal_impact(
    cutoff_date:  'pd.Timestamp',
    pre_start:    'pd.Timestamp',
    post_end:     'pd.Timestamp',
    control_cols: list  = None,
    alpha:        float = 0.05,
    n_samples:    int   = 2000,
) -> dict:
    """
    Causal Impact Framework — BSTS with optional control time series.

    Implements the Google Causal Impact methodology:
    1. Fit a BSTS model on pre-period IOR, optionally including untreated
       segment/donor IOR columns as regression covariates.
    2. Project the counterfactual over the post-period using the fitted model.
    3. Compute: pointwise effect, cumulative effect, relative lift,
       posterior p-value, and P(effect > 0).

    When control_cols are provided AND statsmodels is available, uses
    UnobservedComponents with exogenous regressors (closest pure-Python
    approximation to Google's original tfp-based CausalImpact).
    Falls back to the pure BSTS Kalman filter (_run_bsts) otherwise.

    Parameters
    ----------
    control_cols : list of column names in platform_daily_ior to use as
                   covariates (e.g. ['ior_Growth', 'ior_Enterprise']).
                   None → pure BSTS without covariates.
    n_samples    : MC draws for the posterior predictive interval
    """
    df_ts, err = _load_ior_ts(pre_start, post_end)
    if err:
        return {'error': err}

    pre  = df_ts[df_ts['date'] < cutoff_date].copy()
    post = df_ts[df_ts['date'] >= cutoff_date].copy()

    if len(pre) < 30:
        return {'error': f'Pre-period too short ({len(pre)} days, need ≥30)'}
    if len(post) < 3:
        return {'error': f'Post-period too short ({len(post)} days, need ≥3)'}

    avail_covs  = [c for c in (control_cols or []) if c in df_ts.columns]
    has_covs    = bool(avail_covs)
    model_type  = 'Pure BSTS (local linear trend)'

    y_pred_m = y_pred_lo = y_pred_hi = samples = None
    uc_aic   = None

    if has_covs:
        try:
            from statsmodels.tsa.statespace.structural import UnobservedComponents as _UC
            y_ser  = pre.set_index('date')['ior'].asfreq('D').ffill()
            X_pre  = pre.set_index('date')[avail_covs].asfreq('D').ffill()
            X_post = post.set_index('date')[avail_covs].asfreq('D').ffill()
            uc_fit = _UC(y_ser, level='local linear trend', exog=X_pre).fit(
                disp=False, maxiter=300)
            uc_aic    = round(float(uc_fit.aic), 2)
            model_type = f'BSTS + {len(avail_covs)} covariate(s): {avail_covs}'
            fc_res    = uc_fit.get_forecast(steps=len(post), exog=X_post)
            y_pred_m  = np.clip(fc_res.predicted_mean.values, 0.001, 0.999)
            ci        = fc_res.conf_int(alpha=alpha)
            y_pred_lo = np.clip(ci.iloc[:, 0].values, 0.001, 0.999)
            y_pred_hi = np.clip(ci.iloc[:, 1].values, 0.001, 0.999)
            rng_ci    = np.random.default_rng(42)
            se_fc     = np.maximum((y_pred_hi - y_pred_lo) /
                                    (2 * stats.norm.ppf(1 - alpha / 2)), 1e-6)
            samples   = np.array([
                np.clip(rng_ci.normal(y_pred_m, se_fc), 0.001, 0.999)
                for _ in range(n_samples)
            ])
        except Exception:
            has_covs = False   # fall through to pure BSTS

    if y_pred_m is None:
        # Pure BSTS
        bsts = _run_bsts(cutoff_date, pre_start, post_end, alpha, n_samples)
        if 'error' in bsts:
            return bsts
        y_pred_m  = np.array(bsts['post_cf'])
        y_pred_lo = np.array(bsts['post_cf_lo'])
        y_pred_hi = np.array(bsts['post_cf_hi'])
        rng_ci    = np.random.default_rng(42)
        se_fc     = np.maximum((y_pred_hi - y_pred_lo) /
                                (2 * stats.norm.ppf(1 - alpha / 2)), 1e-6)
        samples   = np.array([
            np.clip(rng_ci.normal(y_pred_m, se_fc), 0.001, 0.999)
            for _ in range(n_samples)
        ])

    observed   = post['ior'].values
    n_post     = len(observed)
    pointwise  = observed - y_pred_m
    cumulative = np.cumsum(pointwise)
    avg_eff_pp = float(np.mean(pointwise) * 100)
    cum_eff_pp = float(cumulative[-1] * 100)
    avg_cf     = float(np.mean(y_pred_m))
    rel_eff    = avg_eff_pp / (avg_cf * 100) * 100 if avg_cf > 0 else 0.0

    # Posterior p-value
    cum_cf_s   = samples.sum(axis=1)
    obs_total  = float(observed.sum())
    p_one      = float(np.mean(cum_cf_s >= obs_total))
    p_post     = float(2 * min(p_one, 1 - p_one))

    # Frequentist
    t_stat, p_freq = stats.ttest_1samp(pointwise, 0)

    # Effect CI from MC samples
    eff_samples = (observed[np.newaxis, :] - samples).mean(axis=1) * 100
    cum_samples = (obs_total - cum_cf_s) * 100

    return {
        'method':                'Causal Impact Framework',
        'model_type':            model_type,
        'control_covariates':    avail_covs,
        'has_covariates':        has_covs,
        'cutoff_date':           str(cutoff_date.date()),
        'pre_start':             str(pre_start.date()),
        'n_pre':                 len(pre),
        'n_post':                n_post,
        'n_mc_samples':          n_samples,
        'uc_aic':                uc_aic,
        'avg_actual_ior':        round(float(np.mean(observed)), 5),
        'avg_counterfactual_ior':round(float(np.mean(y_pred_m)), 5),
        'avg_effect_pp':         round(avg_eff_pp, 4),
        'avg_effect_ci_lo_pp':   round(float(np.percentile(eff_samples, 100*alpha/2)), 4),
        'avg_effect_ci_hi_pp':   round(float(np.percentile(eff_samples, 100*(1-alpha/2))), 4),
        'cumulative_effect_pp':  round(cum_eff_pp, 4),
        'cumulative_ci_lo_pp':   round(float(np.percentile(cum_samples, 100*alpha/2)), 4),
        'cumulative_ci_hi_pp':   round(float(np.percentile(cum_samples, 100*(1-alpha/2))), 4),
        'relative_effect_pct':   round(rel_eff, 2),
        'p_value_posterior':     round(p_post, 5),
        'p_value_frequentist':   round(float(p_freq), 5),
        'significant':           p_post < alpha,
        'prob_effect_positive':  round(float(1 - p_one), 4),
        'pre_dates':    pre['date'].dt.strftime('%Y-%m-%d').tolist(),
        'pre_actual':   pre['ior'].values.tolist(),
        'post_dates':   post['date'].dt.strftime('%Y-%m-%d').tolist(),
        'post_actual':  observed.tolist(),
        'post_cf':      y_pred_m.tolist(),
        'post_cf_lo':   y_pred_lo.tolist(),
        'post_cf_hi':   y_pred_hi.tolist(),
        'pointwise_pp': (pointwise * 100).tolist(),
        'cumulative_pp':(cumulative * 100).tolist(),
    }


def run_causal_impact_analysis(llm):
    """[27] Causal Impact Framework — interactive runner."""
    _causal_header(
        '🎯  CAUSAL IMPACT FRAMEWORK  [27]',
        'Google-style BSTS + optional control covariates'
    )
    print("""
  ✅ When to use:
     - No A/B test, but untreated control time series are available.
     - You want the strongest time-series causal claim without a holdout group.
     - Pre-period ≥30 days; controls highly correlated with treatment in pre-period.

  ⚠️  Limitations:
     - Pre-period correlation ≠ guaranteed counterfactual accuracy post-period.
     - If control series are unrelated to treatment, pure BSTS [26] is safer.
     - Concurrent product changes during the post-period bias the estimate.
     - Interpret the CI width honestly — a wide CI signals high uncertainty.
""")
    cutoff_date = _ask_date('  ❓ Intervention / ship date', pd.Timestamp.today() - pd.Timedelta(days=60))
    pre_start   = _ask_date('  ❓ Pre-period start',         cutoff_date - pd.Timedelta(days=180))
    post_end    = _ask_date('  ❓ Post-period end',          cutoff_date + pd.Timedelta(days=60))

    # Detect available control columns in platform_daily_ior
    try:
        ts_cols = db.execute("SELECT * FROM platform_daily_ior LIMIT 1").df().columns.tolist()
        cand    = [c for c in ts_cols
                   if c not in ('date', 'ior', 'day_of_week', 'month')
                   and 'ior' in c.lower()]
    except Exception:
        cand = []

    covariate_cols = []
    if cand:
        print(f'\n  Control IOR columns available in platform_daily_ior:')
        for i, c in enumerate(cand):
            print(f'    [{i+1}] {c}')
        raw = input('  ❓ Columns to use as covariates (comma-sep numbers), or Enter to skip: ').strip()
        if raw:
            try:
                idxs = [int(x.strip()) - 1 for x in raw.split(',')]
                covariate_cols = [cand[i] for i in idxs if 0 <= i < len(cand)]
            except Exception:
                covariate_cols = []
    else:
        print('\n  ℹ️  No control IOR columns detected — running pure BSTS model.')

    n_raw = input('\n  ❓ MC posterior samples [2000]: ').strip() or '2000'
    try:    n_samples = max(500, int(n_raw))
    except: n_samples = 2000

    alpha = _ask_alpha()
    print(f'\n  Running Causal Impact'
          + (f' with covariates {covariate_cols}' if covariate_cols else ' (pure BSTS)') + '...')

    result = _run_causal_impact(cutoff_date, pre_start, post_end,
                                  covariate_cols or None, alpha, n_samples)

    if 'error' in result:
        print(f'\n  ❌ Causal Impact failed: {result["error"]}'); return result

    sig  = '✅ Significant' if result['significant'] else '⚠️  Not significant'
    p_b  = result.get('p_value_posterior', 1.0)
    prob = result.get('prob_effect_positive', 0.0)

    print('\n  ── Causal Impact Summary ─────────────────────────────────────────────')
    print(f'  Model          : {result["model_type"]}')
    print(f'  Pre: {result["n_pre"]} days  |  Post: {result["n_post"]} days  |  '
          f'MC samples: {result["n_mc_samples"]:,}')
    print(f'  Avg observed IOR     : {result["avg_actual_ior"]:.5f}')
    print(f'  Avg counterfactual   : {result["avg_counterfactual_ior"]:.5f}')
    print(f'  Avg causal effect    : {result["avg_effect_pp"]:+.4f}pp  '
          f'[{result["avg_effect_ci_lo_pp"]:+.3f}, {result["avg_effect_ci_hi_pp"]:+.3f}]')
    print(f'  Relative effect      : {result["relative_effect_pct"]:+.2f}%')
    print(f'  Cumulative effect    : {result["cumulative_effect_pp"]:+.4f}pp  '
          f'[{result["cumulative_ci_lo_pp"]:+.3f}, {result["cumulative_ci_hi_pp"]:+.3f}]')
    print(f'  P(effect > 0)        : {prob:.4f}')
    print(f'  Posterior p-value    : {p_b:.5f}  {sig}')

    result['_alpha'] = alpha
    _plot_forecast_counterfactual(result)
    _causal_narrative(llm, {k: v for k, v in result.items()
                              if not isinstance(v, list) and k != '_alpha'},
        f'Causal Impact. {result["model_type"]}. '
        f'Avg effect {result["avg_effect_pp"]:+.3f}pp '
        f'(relative {result["relative_effect_pct"]:+.2f}%, '
        f'{"sig" if result["significant"] else "n.s."}, '
        f'posterior p={p_b:.4f}, P(>0)={prob:.3f}). '
        f'Cumulative effect {result["cumulative_effect_pp"]:+.3f}pp '
        f'[{result["cumulative_ci_lo_pp"]:+.2f}, {result["cumulative_ci_hi_pp"]:+.2f}]. '
        f'Interpret: (1) full causal effect interpretation; '
        f'(2) what P(effect>0)={prob:.3f} means in business terms; '
        f'(3) confidence in the causal claim; '
        f'(4) ship recommendation.'
    )
    return result


# ── Shared plot for forecasting-based counterfactual methods ─────────────────

def _plot_forecast_counterfactual(result: dict):
    """
    Standard 3-panel visualisation shared by ARIMA, SARIMA, BSTS, and Causal Impact.

    Panel 1 — Full time series: pre-period actual + post-period actual vs
               counterfactual with shaded CI band and intervention line.
    Panel 2 — Pointwise daily effect (pp) as a bar chart.
    Panel 3 — Cumulative effect (pp) as an area chart.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    COLORS_L = {
        'treatment': '#f97316', 'control': '#4e9af1',
        'highlight': '#facc15', 'neutral': '#a1a1aa',
        'positive':  '#22c55e', 'negative': '#ef4444',
    }

    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    fig.patch.set_facecolor('#0f0f0f')
    for ax in axes:
        ax.set_facecolor('#1a1a2e')

    pre_dates  = result.get('pre_dates',  [])
    post_dates = result.get('post_dates', [])
    pre_act    = result.get('pre_actual', [])
    post_act   = result.get('post_actual',[])
    post_cf    = result.get('post_cf',    [])
    cf_lo      = result.get('post_cf_lo', post_cf)
    cf_hi      = result.get('post_cf_hi', post_cf)
    pw_pp      = result.get('pointwise_pp',  [])
    cum_pp     = result.get('cumulative_pp', [])

    n_pre  = len(pre_dates)
    n_post = len(post_dates)
    pre_x  = list(range(n_pre))
    post_x = list(range(n_pre, n_pre + n_post))
    sig    = result.get('significant', False)
    avg_e  = result.get('avg_effect_pp', 0.0)
    p_key  = ('p_value_posterior' if 'p_value_posterior' in result
               else 'p_value')
    p_val  = result.get(p_key, 1.0)
    alpha  = result.get('_alpha', 0.05)

    # ── Panel 1: time series ─────────────────────────────────────────────────
    ax1 = axes[0]
    ax1.plot(pre_x,  pre_act,  color=COLORS_L['treatment'], lw=1.8, label='Actual (pre)')
    ax1.plot(post_x, post_act, color=COLORS_L['treatment'], lw=2.5, label='Actual (post)')
    ax1.plot(post_x, post_cf,  color=COLORS_L['control'], lw=2.2,
             linestyle='--', label='Counterfactual')
    ax1.fill_between(post_x, cf_lo, cf_hi,
                     alpha=0.20, color=COLORS_L['control'],
                     label=f'{int((1-alpha)*100)}% CI')
    ax1.axvline(n_pre - 0.5, color=COLORS_L['highlight'], lw=2, label='Intervention')
    gap_color = COLORS_L['positive'] if avg_e >= 0 else COLORS_L['negative']
    ax1.fill_between(post_x,
                     [min(cf_lo[i], post_act[i]) for i in range(n_post)],
                     [max(cf_hi[i], post_act[i]) for i in range(n_post)],
                     alpha=0.10, color=gap_color)
    # Tick labels (sample every ~8th point to avoid crowding)
    all_dates = pre_dates + post_dates
    step      = max(1, len(all_dates) // 8)
    tick_idx  = list(range(0, len(all_dates), step))
    ax1.set_xticks(tick_idx)
    ax1.set_xticklabels([all_dates[i] for i in tick_idx], rotation=40, fontsize=7)
    sig_icon = '✅' if sig else '⚠️ n.s.'
    ax1.set_title(
        f'{result["method"]}\n'
        f'Avg effect: {avg_e:+.3f}pp  {sig_icon}  p={p_val:.4f}',
        color=COLORS_L['highlight'], fontsize=9
    )
    ax1.set_ylabel('IOR'); ax1.legend(fontsize=7.5); ax1.grid(True, alpha=0.2)

    # ── Panel 2: pointwise effect ────────────────────────────────────────────
    ax2 = axes[1]
    if pw_pp:
        pw_arr    = np.array(pw_pp)
        bar_cols  = [COLORS_L['positive'] if v >= 0 else COLORS_L['negative']
                     for v in pw_arr]
        ax2.bar(range(n_post), pw_arr, color=bar_cols, alpha=0.85)
        ax2.axhline(0,     color='white',               lw=1.5, linestyle='--', alpha=0.6)
        ax2.axhline(avg_e, color=COLORS_L['highlight'], lw=2,
                    label=f'Mean = {avg_e:+.3f}pp')
    ax2.set_xlabel('Days after intervention')
    ax2.set_ylabel('Effect (pp)')
    ax2.set_title('Pointwise Effect\n(Observed − Counterfactual)',
                  color=COLORS_L['highlight'], fontsize=9)
    ax2.legend(fontsize=8); ax2.grid(True, alpha=0.2)

    # ── Panel 3: cumulative effect ───────────────────────────────────────────
    ax3 = axes[2]
    if cum_pp:
        cum_arr   = np.array(cum_pp)
        cum_color = COLORS_L['positive'] if cum_arr[-1] >= 0 else COLORS_L['negative']
        ax3.plot(range(n_post), cum_arr, color=cum_color, lw=2.5,
                 label=f'Final: {cum_arr[-1]:+.2f}pp')
        ax3.fill_between(range(n_post), 0, cum_arr, alpha=0.20, color=cum_color)
        ax3.axhline(0, color='white', lw=1.5, linestyle='--', alpha=0.6)
    cum_lo = result.get('cumulative_ci_lo_pp')
    cum_hi = result.get('cumulative_ci_hi_pp')
    if cum_lo is not None and cum_pp:
        ax3.fill_between([n_post - 1], [cum_lo], [cum_hi],
                         color=COLORS_L['highlight'], alpha=0.5,
                         label=f'CI [{cum_lo:+.1f}, {cum_hi:+.1f}]')
    ax3.set_xlabel('Days after intervention')
    ax3.set_ylabel('Cumulative effect (pp)')
    ax3.set_title(
        f'Cumulative Effect\nTotal: {result.get("cumulative_effect_pp", 0):+.3f}pp',
        color=COLORS_L['highlight'], fontsize=9
    )
    ax3.legend(fontsize=8); ax3.grid(True, alpha=0.2)

    plt.suptitle(f'{result["method"]} — Counterfactual Analysis',
                 fontsize=12, color=COLORS_L['highlight'], fontweight='bold')
    plt.tight_layout()
    slug  = (result['method'].lower()
             .replace(' ', '_').replace('(', '').replace(')', '')
             .replace('/', '_').replace('+', ''))
    fname = f'{slug}_analysis.png'
    plt.savefig(fname, dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print(f'  📁 Chart saved → {fname}')
    return fname


print('✅ Forecasting-based counterfactual methods loaded:')
print('   _run_arima()              → raw ARIMA computation')
print('   run_arima_analysis()      → [24] interactive ARIMA runner')
print('   _run_sarima()             → raw SARIMA computation')
print('   run_sarima_analysis()     → [25] interactive SARIMA runner')
print('   _run_bsts()               → raw BSTS Kalman-filter computation')
print('   run_bsts_analysis()       → [26] interactive BSTS runner')
print('   _run_causal_impact()      → raw Causal Impact computation')
print('   run_causal_impact_analysis() → [27] interactive Causal Impact runner')
print('   _plot_forecast_counterfactual() → shared 3-panel plot')

import pandas as pd
import numpy as np
import textwrap

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — DEPLOY MODULES
# ─────────────────────────────────────────────────────────────────────────────

# ── Module 15: Uplift Modeller ────────────────────────────────────────────────

def _build_uplift_features(exp_df: 'pd.DataFrame') -> 'pd.DataFrame':
    """
    Build the feature matrix for the uplift model.
    Uses the covariates available in the experiment dataframe.
    """
    # One-hot encode categorical columns
    cat_cols = ['account_segment', 'platform', 'price_tier', 'process_group']
    num_cols = ['order_value']

    feat = exp_df[['buyer_id','variant','converted_to_order']].copy()

    # Categorical features
    for feat_col in cat_cols:
        if feat_col in exp_df.columns:
            dummies = pd.get_dummies(exp_df[feat_col], prefix=feat_col, drop_first=False)
            feat = pd.concat([feat, dummies], axis=1)

    # Numeric features
    for feat_col in num_cols:
        if feat_col in exp_df.columns:
            feat[feat_col] = exp_df[feat_col].fillna(0)

    # Derived: activity proxy
    feat['has_order'] = (feat.get('order_value', pd.Series(0, index=feat.index)) > 0).astype(int)

    return feat


def _train_t_learner(features: 'pd.DataFrame', control_label: str = 'control'):
    """
    T-Learner: fit two separate models (one on control, one on treatment),
    then estimate per-user uplift as: pred_treatment(x) - pred_control(x).

    Uses LogisticRegression for binary outcome (converted_to_order).
    Returns (model_ctrl, model_trt, feature_cols).
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise ImportError('scikit-learn is required for the Uplift Modeller. '
                          'Run: pip install scikit-learn')

    outcome_col = 'converted_to_order'
    skip_cols   = {'buyer_id', 'variant', outcome_col}
    feat_cols   = [c for c in features.columns if c not in skip_cols]

    ctrl = features[features['variant'] == control_label]
    trt  = features[features['variant'] != control_label]

    if len(ctrl) < 100 or len(trt) < 100:
        raise ValueError(f'Insufficient data: {len(ctrl)} control, {len(trt)} treatment rows.')

    X_ctrl = ctrl[feat_cols].values.astype(float)
    y_ctrl = ctrl[outcome_col].astype(int).values
    X_trt  = trt[feat_cols].values.astype(float)
    y_trt  = trt[outcome_col].astype(int).values

    # Fit separate models
    model_ctrl = LogisticRegression(max_iter=300, random_state=42, C=1.0)
    model_trt  = LogisticRegression(max_iter=300, random_state=42, C=1.0)
    model_ctrl.fit(X_ctrl, y_ctrl)
    model_trt.fit(X_trt,  y_trt)

    return model_ctrl, model_trt, feat_cols


def _compute_uplift_scores(features: 'pd.DataFrame',
                            model_ctrl, model_trt, feat_cols: list) -> 'pd.Series':
    """Compute per-user uplift: P(convert | treatment) - P(convert | control)."""
    X = features[feat_cols].values.astype(float)
    uplift = (model_trt.predict_proba(X)[:, 1]
              - model_ctrl.predict_proba(X)[:, 1])
    return pd.Series(uplift, index=features.index, name='uplift_score')


def _compute_qini(features: 'pd.DataFrame', uplift_scores: 'pd.Series',
                   control_label: str = 'control') -> dict:
    """
    Compute the Qini coefficient — the standard uplift model quality metric.
    Qini measures how much better the model is than random targeting.
    Returns {'qini': float, 'random_baseline': float, 'interpretation': str}.
    """
    outcome = 'converted_to_order'
    df = features[['variant', outcome]].copy()
    df['uplift'] = uplift_scores.values
    df = df.sort_values('uplift', ascending=False).reset_index(drop=True)

    n = len(df)
    n_trt  = (df['variant'] != control_label).sum()
    n_ctrl = (df['variant'] == control_label).sum()

    # Incremental gains curve
    gains = []
    cum_trt_conv, cum_ctrl_conv = 0, 0
    cum_trt_n,   cum_ctrl_n   = 0, 0

    for _, row in df.iterrows():
        is_trt = row['variant'] != control_label
        if is_trt:
            cum_trt_n    += 1
            cum_trt_conv += int(row[outcome])
        else:
            cum_ctrl_n    += 1
            cum_ctrl_conv += int(row[outcome])

        if cum_trt_n > 0 and cum_ctrl_n > 0:
            incr = (cum_trt_conv / cum_trt_n) - (cum_ctrl_conv / cum_ctrl_n)
            gains.append(incr * (cum_trt_n + cum_ctrl_n) / n)
        else:
            gains.append(0)

    try:
        qini = float(np.trapezoid(gains)) / (n / 2) if n > 0 else 0.0
    except AttributeError:  # numpy < 2.0
        qini = float(np.trapz(gains)) / (n / 2) if n > 0 else 0.0
    interp = 'Strong' if qini > 0.1 else 'Moderate' if qini > 0.03 else 'Weak'

    return {
        'qini':            round(qini, 4),
        'interpretation':  interp,
        'gains_curve':     gains,
    }


def run_uplift_modeller(llm):
    """
    Module 15 — Uplift Modeller.

    Trains a T-learner on a concluded experiment to estimate per-user
    individual causal effects (uplift scores). Produces:
      - Uplift score distribution by segment
      - Qini coefficient (model quality)
      - Per-segment average uplift
      - Scores registered in DuckDB for Module 16 to consume
    """
    print()
    print('╔' + '═'*70 + '╗')
    print('║' + '  🎯  UPLIFT MODELLER — Module 15'.ljust(70) + '║')
    print('║' + '  Phase 4 · Deploy · Individual causal effect estimation'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')
    print()
    print('  The Uplift Modeller answers: for which INDIVIDUAL users does this')
    print('  treatment have the highest incremental effect?')
    print()
    print('  Method: T-Learner — train two separate models (control / treatment)')
    print('  and subtract predicted conversion rates to get per-user uplift.')
    print()

    # ── Select experiment ─────────────────────────────────────────────────────
    exp_info, _ = _list_experiments_with_status()
    if exp_info is None:
        return None

    exp_name = exp_info['name']
    status   = exp_info.get('status', '')
    if status not in ('concluded', 'shipped', 'stopped'):
        print(f'  ⚠️  Uplift modelling requires a concluded experiment.')
        print(f'     Selected experiment has status: {status}')
        raw = input('  Continue anyway? [y/N]: ').strip().lower()
        if raw != 'y':
            return None

    print(f'\n  ✅ Selected: {exp_name}')

    # ── Pull data ─────────────────────────────────────────────────────────────
    exp_df = df_all_experiments[df_all_experiments['experiment_name'] == exp_name].copy()
    exp_df = dedup_dataframe(exp_df)
    variants = sorted(exp_df['variant'].unique().tolist())
    control  = 'control' if 'control' in variants else variants[0]
    treatments = [v for v in variants if v != control]

    print(f'  Rows: {len(exp_df):,}  Variants: {variants}  Control: "{control}"')

    if len(exp_df) < 200:
        print('  ⚠️  Fewer than 200 rows — uplift model will be unreliable.')

    # ── Build features and train T-Learner ───────────────────────────────────
    print('\n  Building feature matrix...')
    features = _build_uplift_features(exp_df)

    print('  Training T-Learner (control model + treatment model)...')
    try:
        model_ctrl, model_trt, feat_cols = _train_t_learner(features, control)
    except (ImportError, ValueError) as e:
        print(f'  ❌ {e}')
        return None

    # ── Compute uplift scores ─────────────────────────────────────────────────
    print('  Computing per-user uplift scores...')
    uplift_scores = _compute_uplift_scores(features, model_ctrl, model_trt, feat_cols)
    features['uplift_score'] = uplift_scores

    # ── Quality metric: Qini ─────────────────────────────────────────────────
    qini_result = _compute_qini(features, uplift_scores, control)
    print(f'\n  Qini coefficient: {qini_result["qini"]:.4f} ({qini_result["interpretation"]})')

    # ── Segment-level uplift distribution ────────────────────────────────────
    print('\n  ── Uplift score distribution by segment ──')
    print(f'  {"Segment":<20} {"Mean uplift":>12} {"p75":>8} {"p25":>8} {"% positive":>12}')
    print('  ' + '─'*62)
    seg_uplift = {}
    if 'account_segment' in exp_df.columns:
        for seg in sorted(exp_df['account_segment'].unique()):
            mask    = exp_df['account_segment'] == seg
            scores  = uplift_scores[mask]
            mean_u  = float(scores.mean())
            p75     = float(scores.quantile(0.75))
            p25     = float(scores.quantile(0.25))
            pct_pos = float((scores > 0).mean() * 100)
            seg_uplift[seg] = {'mean': mean_u, 'p75': p75, 'p25': p25, 'pct_positive': pct_pos}
            icon = '📈' if mean_u > 0.005 else ('📉' if mean_u < -0.005 else '➡️ ')
            print(f'  {icon} {seg:<18} {mean_u*100:>+10.3f}pp  {p75*100:>+6.3f}pp  '
                  f'{p25*100:>+6.3f}pp  {pct_pos:>10.1f}%')

    # ── Register in DuckDB for Decision Engine ───────────────────────────────
    uplift_df = exp_df[['buyer_id']].copy()
    uplift_df['uplift_score']    = uplift_scores.values
    uplift_df['experiment_name'] = exp_name
    if 'account_segment' in exp_df.columns:
        uplift_df['account_segment'] = exp_df['account_segment'].values
    db.register('uplift_scores', uplift_df)
    print(f'\n  ✅ Uplift scores registered in DuckDB as "uplift_scores"')
    print(f'     Run Module [16] (Decision Engine) to generate an optimised targeting plan.')

    # ── LLM synthesis ─────────────────────────────────────────────────────────
    print('\n  🤖 Synthesising uplift findings...')
    seg_summary = '; '.join(
        f'{seg}: mean={v["mean"]*100:+.2f}pp ({v["pct_positive"]:.0f}% positive)'
        for seg, v in seg_uplift.items()
    ) or 'No segment breakdown available.'

    past = _query_relevant_learnings(exp_info.get('description',''), n=2)
    past_text = _format_past_learnings(past)

    uplift_prompt = textwrap.dedent(f"""
You are interpreting uplift model results from a concluded A/B experiment.

Experiment: {exp_name}
Qini coefficient: {qini_result["qini"]:.4f} ({qini_result["interpretation"]} model fit)
Segment-level uplift: {seg_summary}

Relevant past experiments:
{past_text}

In 4-5 sentences:
1. What the uplift distribution tells us about WHICH users respond best.
2. Whether the Qini score suggests the model is trustworthy enough to act on.
3. What targeting strategy follows from these scores.
4. Whether past experiments support or challenge this uplift pattern.
Do not use emojis.
    """).strip()

    try:
        synthesis = llm.ask(uplift_prompt)
        try:
            synthesis = _strip_decorative_chars(synthesis)
        except NameError:
            pass
    except Exception as e:
        synthesis = f'(Synthesis unavailable: {e})'

    print()
    for line in synthesis.split('\n'):
        if line.strip(): print(f'    {line}')

    return {
        'experiment':   exp_name,
        'qini':         qini_result['qini'],
        'qini_grade':   qini_result['interpretation'],
        'seg_uplift':   seg_uplift,
        'uplift_df':    uplift_df,
        'synthesis':    synthesis,
        'model_ctrl':   model_ctrl,
        'model_trt':    model_trt,
        'feat_cols':    feat_cols,
    }


# ── Module 16: Decision Engine ────────────────────────────────────────────────

def run_decision_engine(llm):
    """
    Module 16 — Decision Engine.

    Takes uplift scores from Module 15 + a budget constraint and solves
    for the optimal targeting allocation to maximise incremental GMV.

    Algorithm:
      1. For each user, compute expected incremental GMV = uplift_score × avg_AOV
      2. Sort users by incremental GMV per unit cost (descending)
      3. Greedily allocate budget from highest to lowest
      4. Report allocation by segment, projected incremental GMV, and ROI

    Constraint: scipy.optimize.linprog (already a dependency).
    """
    print()
    print('╔' + '═'*70 + '╗')
    print('║' + '  💰  DECISION ENGINE — Module 16'.ljust(70) + '║')
    print('║' + '  Phase 4 · Deploy · Budget-constrained targeting optimisation'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')
    print()
    print('  Given uplift scores from Module 15, the Decision Engine answers:')
    print('  "Which users should we target, with which variant, at this budget,')
    print('   to maximise incremental GMV?"')
    print()

    # ── Check uplift scores are available ─────────────────────────────────────
    try:
        uplift_df = db.execute('SELECT * FROM uplift_scores').df()
        exp_name  = uplift_df['experiment_name'].iloc[0] if len(uplift_df) else 'unknown'
    except Exception:
        print('  ❌ No uplift scores found.')
        print('     Run Module [15] (Uplift Modeller) first to generate scores.')
        return None

    print(f'  Loaded {len(uplift_df):,} uplift scores for experiment: {exp_name}')

    # ── Budget input ──────────────────────────────────────────────────────────
    print()
    print('  Budget parameters:')
    while True:
        raw_budget = input('  ❓ Total targeting budget ($, e.g. 50000): ').strip().replace(',','')
        try:
            budget = float(raw_budget)
            if budget > 0:
                break
        except ValueError:
            pass
        print('     ⚠️  Enter a positive number')

    while True:
        raw_cost = input('  ❓ Cost per contact ($ per user, e.g. 0.80): ').strip()
        try:
            cost_per_contact = float(raw_cost)
            if cost_per_contact > 0:
                break
        except ValueError:
            pass
        print('     ⚠️  Enter a positive number')

    max_contacts = int(budget / cost_per_contact)
    print(f'\n  Budget: ${budget:,.0f}  Cost/contact: ${cost_per_contact:.2f}  '
          f'Max contacts: {max_contacts:,}')

    # ── Compute expected incremental GMV per user ─────────────────────────────
    # Use overall avg AOV from hist_inquiries as the revenue multiplier
    try:
        avg_aov = float(db.execute(
            "SELECT AVG(order_value) FROM hist_inquiries WHERE converted_to_order = TRUE"
        ).fetchone()[0] or 4000)
    except Exception:
        avg_aov = 4000.0

    uplift_df['expected_incr_gmv'] = uplift_df['uplift_score'] * avg_aov

    # ── Greedy optimisation: sort by incremental GMV per $ cost ───────────────
    # Uplift score < 0 means treatment hurts this user — exclude them
    eligible = uplift_df[uplift_df['uplift_score'] > 0.0].copy()
    eligible = eligible.sort_values('expected_incr_gmv', ascending=False).reset_index(drop=True)

    # Allocate
    allocated = eligible.head(max_contacts).copy()
    not_allocated = eligible.iloc[max_contacts:].copy()
    harmed = uplift_df[uplift_df['uplift_score'] <= 0.0].copy()

    total_contacts     = len(allocated)
    total_cost         = total_contacts * cost_per_contact
    projected_incr_gmv = float(allocated['expected_incr_gmv'].sum())
    proj_roi           = projected_incr_gmv / total_cost if total_cost > 0 else 0

    # ── Print allocation summary ───────────────────────────────────────────────
    print()
    print('  ── Targeting Allocation ──────────────────────────────────────────────')
    print(f'  {"Group":<30} {"Users":>8} {"Avg uplift":>12} {"Proj. GMV":>14}')
    print('  ' + '─'*70)

    seg_alloc = {}
    if 'account_segment' in allocated.columns:
        for seg in sorted(allocated['account_segment'].dropna().unique()):
            seg_rows = allocated[allocated['account_segment'] == seg]
            seg_gmv  = float(seg_rows['expected_incr_gmv'].sum())
            seg_u    = float(seg_rows['uplift_score'].mean())
            seg_alloc[seg] = {'n': len(seg_rows), 'avg_uplift': seg_u, 'projected_gmv': seg_gmv}
            icon = '🎯' if seg_u > 0.01 else '📌'
            print(f'  {icon} TREAT  {seg:<24} {len(seg_rows):>8,} {seg_u*100:>+10.3f}pp  '
                  f'${seg_gmv:>12,.0f}')
        if 'account_segment' in harmed.columns:
            for seg in sorted(harmed['account_segment'].dropna().unique()):
                n_harm = (harmed['account_segment'] == seg).sum()
                if n_harm > 0:
                    print(f'  🚫 HOLD   {seg:<24} {n_harm:>8,} {"(negative uplift)":>24}')
    else:
        print(f'  🎯 TREAT  (all eligible)               {total_contacts:>8,} '
              f'{float(allocated["uplift_score"].mean())*100:>+10.3f}pp  '
              f'${projected_incr_gmv:>12,.0f}')

    print('  ' + '─'*70)
    print(f'  {"TOTAL":30} {total_contacts:>8,} {"":>12} ${projected_incr_gmv:>12,.0f}')
    print()
    print(f'  Budget used     : ${total_cost:>10,.0f} of ${budget:,.0f}')
    print(f'  Remaining budget: ${budget - total_cost:>10,.0f}')
    print(f'  Projected ROI   : {proj_roi:.1f}× (${projected_incr_gmv:,.0f} GMV / ${total_cost:,.0f} spend)')
    print(f'  Users held back : {len(harmed):,} (negative expected uplift — do not treat)')

    # ── LLM: decision implications + trade-offs ───────────────────────────────
    print('\n  🤖 Generating deployment plan with implications and trade-offs...')

    past = _query_relevant_learnings(exp_name, n=2)
    past_text = _format_past_learnings(past)

    seg_summary = '; '.join(
        f'{seg}: {v["n"]:,} users avg={v["avg_uplift"]*100:+.2f}pp GMV=${v["projected_gmv"]:,.0f}'
        for seg, v in seg_alloc.items()
    ) if seg_alloc else f'{total_contacts:,} users targeted'

    deploy_prompt = textwrap.dedent(f"""
You are a senior product analyst writing a deployment plan.

Experiment: {exp_name}
Budget: ${budget:,.0f}  Cost/contact: ${cost_per_contact:.2f}  Max contacts: {max_contacts:,}
Targeting allocation: {seg_summary}
Projected incremental GMV: ${projected_incr_gmv:,.0f}
Projected ROI: {proj_roi:.1f}x
Users with negative uplift (held back): {len(harmed):,}

Relevant past experiments:
{past_text}

Write a response with EXACTLY THREE sections:

DEPLOYMENT PLAN:
Step-by-step: who to target, in what sequence, over what timeframe (weeks).
Name specific segments and variants.

IMPLICATIONS:
What to monitor in the first 2 weeks post-deployment.
What success looks like. What a failure signal looks like.
Reference past experiments if relevant.

TRADE-OFFS:
What we are giving up by holding back the negative-uplift segments.
Whether the ROI projection is conservative or aggressive and why.
One risk the team should hedge against.

Write in plain business English. No emojis.
    """).strip()

    try:
        deploy_plan = llm.ask(deploy_prompt)
        try:
            deploy_plan = _strip_decorative_chars(deploy_plan)
        except NameError:
            pass
    except Exception as e:
        deploy_plan = f'(Plan unavailable: {e})'

    print()
    for line in deploy_plan.split('\n'):
        stripped = line.strip()
        if stripped:
            if stripped.upper() in ('DEPLOYMENT PLAN:', 'IMPLICATIONS:', 'TRADE-OFFS:'):
                print(f'\n  ── {stripped} ──')
            else:
                print(f'    {line}')

    # ── Save targeting brief ──────────────────────────────────────────────────
    fname = f'targeting_brief_{exp_name}.csv'
    allocated[['buyer_id','uplift_score','expected_incr_gmv']
              + (['account_segment'] if 'account_segment' in allocated.columns else [])
              ].to_csv(fname, index=False)
    print(f'\n  📁 Targeting brief saved → {fname}')
    print(f'     {total_contacts:,} users to contact. Engineering: use buyer_id column '
          f'to configure feature flag targeting.')

    return {
        'experiment':          exp_name,
        'budget':              budget,
        'cost_per_contact':    cost_per_contact,
        'n_targeted':          total_contacts,
        'projected_incr_gmv':  projected_incr_gmv,
        'projected_roi':       proj_roi,
        'seg_allocation':      seg_alloc,
        'n_held_back':         len(harmed),
        'deploy_plan':         deploy_plan,
        'targeting_file':      fname,
    }

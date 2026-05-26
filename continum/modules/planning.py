import pandas as pd
import numpy as np
import textwrap

# ─────────────────────────────────────────────────────────────────────────────
# BALANCE TEST ENGINE — Covariate balance validation for experiment assignment
# ─────────────────────────────────────────────────────────────────────────────


from scipy.stats import ttest_ind, chi2_contingency
SMD_THRESHOLD   = 0.10
BALANCE_MAX_ITER = 10

BALANCE_COVARIATES = [
    ('account_segment',    'categorical'),
    ('platform',           'categorical'),
    ('lifetime_orders',    'continuous'),
    ('personal_ior',       'continuous'),
    ('avg_order_value',    'continuous'),
    ('days_since_last',    'continuous'),
    ('n_inquiries',        'continuous'),
]


def _compute_smd(vals_a: 'pd.Series', vals_b: 'pd.Series') -> float:
    """
    Standardised Mean Difference between two groups on a continuous covariate.
    SMD = (mean_a - mean_b) / pooled_SD
    """
    n_a, n_b = len(vals_a.dropna()), len(vals_b.dropna())
    if n_a < 5 or n_b < 5:
        return float('nan')
    mu_a, mu_b = vals_a.mean(), vals_b.mean()
    sd_a, sd_b = vals_a.std(), vals_b.std()
    pooled_sd  = np.sqrt(((n_a - 1) * sd_a**2 + (n_b - 1) * sd_b**2) / (n_a + n_b - 2))
    if pooled_sd == 0:
        return 0.0
    return float(abs(mu_a - mu_b) / pooled_sd)


def _run_balance_battery(assignments: 'pd.DataFrame') -> dict:
    """
    Run the full covariate balance battery on the assignment DataFrame.

    assignments must have columns: buyer_id, group, + covariate columns
    (merged from df_buyers + computed features during propensity scoring).

    Returns a dict: {covariate: {smd, p_value, mean_ctrl, mean_trt, flag}}
    """
    groups   = sorted(assignments['group'].unique())
    control  = 'control' if 'control' in groups else groups[0]
    treatment_groups = [g for g in groups if g != control]
    ctrl_df  = assignments[assignments['group'] == control]

    results = {}
    for cov_name, ctype in BALANCE_COVARIATES:
        if cov_name not in assignments.columns:
            continue
        for trt in treatment_groups:
            trt_df = assignments[assignments['group'] == trt]
            key    = f'{cov_name}' if len(treatment_groups) == 1 else f'{cov_name}__{trt}'
            row    = {'covariate': cov_name, 'treatment': trt, 'type': ctype}

            if ctype == 'continuous':
                a = pd.to_numeric(ctrl_df[cov_name], errors='coerce').dropna()
                b = pd.to_numeric(trt_df[cov_name],  errors='coerce').dropna()
                if len(a) < 5 or len(b) < 5:
                    continue
                smd    = _compute_smd(a, b)
                _, pv  = ttest_ind(a, b, equal_var=False)
                row.update({
                    'smd':      round(smd, 4),
                    'p_value':  round(float(pv), 4),
                    'mean_ctrl': round(float(a.mean()), 4),
                    'mean_trt':  round(float(b.mean()), 4),
                    'flag':      smd > SMD_THRESHOLD,
                })

            else:  # categorical
                ctrl_counts = ctrl_df[cov_name].value_counts()
                trt_counts  = trt_df[cov_name].value_counts()
                all_cats    = sorted(set(ctrl_counts.index) | set(trt_counts.index))
                contingency = np.array([
                    [ctrl_counts.get(c, 0) for c in all_cats],
                    [trt_counts.get(c, 0)  for c in all_cats],
                ])
                try:
                    _, pv, _, _ = chi2_contingency(contingency)
                except Exception:
                    pv = 1.0
                # For categorical, use the max proportion difference as SMD proxy
                ctrl_prop = ctrl_counts / ctrl_counts.sum()
                trt_prop  = trt_counts  / trt_counts.sum()
                max_diff  = float((ctrl_prop - trt_prop).abs().max()) if not trt_prop.empty else 0.0
                row.update({
                    'smd':      round(max_diff, 4),
                    'p_value':  round(float(pv), 4),
                    'mean_ctrl': str(ctrl_counts.idxmax()) if not ctrl_counts.empty else '—',
                    'mean_trt':  str(trt_counts.idxmax())  if not trt_counts.empty else '—',
                    'flag':      pv < 0.05,
                })

            results[key] = row

    return results


def _print_balance_report(results: dict, n_ctrl: int, n_trt: int) -> bool:
    """
    Print the balance table. Returns True if all checks pass, False if any flag.
    """
    n_flags = sum(1 for r in results.values() if r.get('flag', False))
    print()
    print('  ── Covariate Balance Report ──────────────────────────────────────────')
    print(f'  {"Covariate":<26} {"Ctrl mean":<16} {"Trt mean":<16} {"SMD":>6}  {"p-val":>6}  {"Status"}')
    print('  ' + '─'*80)

    for key, r in results.items():
        icon   = '⚠️ ' if r.get('flag') else '✅ '
        smd    = f'{r["smd"]:.4f}' if isinstance(r["smd"], float) else '—'
        pv     = f'{r["p_value"]:.4f}'
        mc     = f'{r["mean_ctrl"]:.4f}' if isinstance(r["mean_ctrl"], float) else str(r["mean_ctrl"])
        mt     = f'{r["mean_trt"]:.4f}'  if isinstance(r["mean_trt"],  float) else str(r["mean_trt"])
        print(f'  {r["covariate"]:<26} {mc:<16} {mt:<16} {smd:>6}  {pv:>6}  {icon}')

    print('  ' + '─'*80)
    print(f'  n(control)={n_ctrl:,}  n(treatment)={n_trt:,}')
    threshold_note = f'  SMD threshold: {SMD_THRESHOLD}  (flag if SMD > {SMD_THRESHOLD} or p < 0.05 for categoricals)'
    print(threshold_note)

    if n_flags == 0:
        print()
        print('  ✅ Balance: PASS — all covariates within acceptable bounds.')
        print('     Groups are statistically equivalent. Safe to launch.')
    else:
        print()
        print(f'  ⚠️  Balance: FAIL — {n_flags} covariate(s) flagged.')
        print('     Imbalanced groups risk confounding the experiment results.')

    return n_flags == 0


def _plot_love_plot(balance_results: dict, exp_name: str = '') -> str:
    """
    Generate a Love plot (Austin 2009) showing SMD per covariate.
    A vertical dashed line at SMD=0.10 marks the balance threshold.
    Returns the saved filename.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    cov_list = [r['covariate'] for r in balance_results.values()]
    smds     = [r['smd'] if isinstance(r['smd'], float) else 0.0
                for r in balance_results.values()]
    flags    = [r.get('flag', False) for r in balance_results.values()]

    if not cov_list:
        return None

    fig, ax = plt.subplots(figsize=(8, max(3, len(cov_list) * 0.55)))
    colors = ['#E74C3C' if f else '#2ECC71' for f in flags]
    y_pos  = range(len(cov_list))

    ax.barh(list(y_pos), smds, color=colors, alpha=0.80, edgecolor='white', height=0.65)
    ax.axvline(x=SMD_THRESHOLD, color='#E74C3C', linestyle='--', linewidth=1.4,
               label=f'Threshold (SMD={SMD_THRESHOLD})', alpha=0.7)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(cov_list, fontsize=10)
    ax.set_xlabel('Standardised Mean Difference (SMD)', fontsize=10)
    title = f'Love Plot — Covariate Balance{" · " + exp_name if exp_name else ""}'
    ax.set_title(title, fontsize=11, fontweight='bold', color='#1B4F72')
    ax.axvline(x=0, color='grey', linewidth=0.5, alpha=0.4)
    ax.set_xlim(left=0)

    pass_patch  = mpatches.Patch(color='#2ECC71', alpha=0.8, label='Balanced (SMD ≤ 0.10)')
    fail_patch  = mpatches.Patch(color='#E74C3C', alpha=0.8, label='Imbalanced (SMD > 0.10)')
    ax.legend(handles=[pass_patch, fail_patch,
                        plt.Line2D([0],[0], color='#E74C3C', linestyle='--', label=f'Threshold ({SMD_THRESHOLD})')],
              fontsize=9, loc='lower right')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    fname = f'balance_love_plot{"_" + exp_name if exp_name else ""}.png'
    plt.savefig(fname, dpi=130, bbox_inches='tight')
    plt.close()
    return fname


def _rerandomise_until_balanced(features_df, n_per_group, n_groups,
                                 exp_name, max_iter=BALANCE_MAX_ITER):
    """
    Re-draw group assignment until covariate balance passes, or max_iter is reached.

    Uses simple random re-assignment (no complex optimisation) — this is the
    rerandomisation approach from Morgan & Rudin (2012): draw randomly, test
    balance, reject and redraw if balance fails.

    Returns (assignments_df, balance_results, passed: bool)
    """
    group_names = ['control'] + [f'treatment_{i}' if n_groups > 2 else 'treatment'
                                  for i in range(1, n_groups)]
    n_total = n_per_group * n_groups
    eligible = features_df.sample(min(n_total, len(features_df)),
                                   random_state=None).reset_index(drop=True)

    for attempt in range(1, max_iter + 1):
        # Random shuffle and assign groups
        shuffled = eligible.sample(frac=1, random_state=attempt * 17).reset_index(drop=True)
        shuffled['group'] = np.repeat(group_names,
                                       [len(shuffled) // n_groups + (1 if i < len(shuffled) % n_groups else 0)
                                        for i in range(n_groups)])[:len(shuffled)]
        shuffled['experiment_name']  = exp_name
        shuffled['selection_mode']   = 'propensity_balanced'
        shuffled['propensity_score'] = features_df.get('propensity_score',
                                        pd.Series(np.nan, index=shuffled.index))

        balance = _run_balance_battery(shuffled)
        passed  = all(not r.get('flag', False) for r in balance.values())

        if passed:
            print(f'     ✅ Balance achieved on attempt {attempt}/{max_iter}')
            return shuffled, balance, True

        if attempt < max_iter:
            n_flags = sum(1 for r in balance.values() if r.get('flag'))
            print(f'     ↩️  Attempt {attempt}: {n_flags} flag(s) — re-drawing...')

    print(f'     ⚠️  Balance not achieved after {max_iter} attempts.')
    print('         Proceeding with best available assignment.')
    print('         Consider reducing MDE or increasing sample size.')
    return shuffled, balance, False


# ─────────────────────────────────────────────────────────────────────────────
# FUNNEL TAXONOMY
# ─────────────────────────────────────────────────────────────────────────────

FUNNEL_TAXONOMY = {
    'acquisition': {
        'label':       'Traffic & Sign-Up (Acquisition)',
        'description': '''
            This stage focuses on all top-of-funnel activities responsible for bringing new users
            into the ecosystem and converting them into registered or identifiable users.
            It includes both paid and organic acquisition channels such as SEO, ads, referrals,
            partnerships, and direct traffic. Additionally, it covers the full authentication
            experience including login, signup, and onboarding entry points.

            The primary goal at this stage is to maximize high-quality traffic and efficiently
            convert visitors into signed-up users while maintaining cost efficiency and traffic relevance.
        ''',
        'keywords':    ['login','sign','auth','oauth','social','register','onboard',
                        'traffic','landing','seo','ad','referral','invite'],
        'primary_metric': 'sign_up_rate',

        'questions': [
            ('monthly_visitors',    'Monthly unique visitors to the page/funnel',  'visitors/month', False),
            ('signup_rate',         'Current sign-up or sign-in rate (%)',          'rate %',         True),
            ('activation_rate',     'Of new sign-ups, % who submit a first inquiry within 30 days', 'rate %', True),
            ('aov',                 'Average order value ($)',                      'dollars',        False),
            ('gross_margin',        'Gross margin (%)',                             'rate %',         True),
            ('horizon',             'Time horizon for sizing (months)',             'months',         False),

            ('bounce_rate',         'Percentage of visitors who leave without interaction', 'rate %', False),
            ('traffic_quality_score','Weighted score of traffic based on downstream conversion', 'score', False),
            ('cost_per_visitor',    'Average acquisition cost per visitor ($)', 'dollars', False),
            ('cost_per_signup',     'Customer acquisition cost per signup ($)', 'dollars', False),
            ('channel_mix',         'Traffic distribution by channel (%)', 'distribution %', False),
            ('form_completion_rate','% users who start vs complete signup form', 'rate %', False),
        ],

        'downstream': [('activation_rate', None), ('ior', None)],

        'tracking_plan': '''
            - Track source/medium, campaign, and keyword attribution using UTM parameters.
            - Implement event tracking for: page_view → signup_start → signup_complete.
            - Measure drop-offs at each field level in signup forms (field analytics).
            - Cohort users by acquisition channel to evaluate downstream activation and revenue quality.
            - Use multi-touch attribution models to understand contribution of channels.
            - Track device, geography, and page load speed as influencing factors.
            - Set up funnel visualization dashboards (e.g., visitor → signup → activation).
        ''',

        'mde_benchmarks': {'typical_min_rel': 0.10, 'typical_max_rel': 0.30,
                           'label': '10–30% relative lift on sign-up rate'},
    },

    'activation': {
        'label':       'Activation & Onboarding',
        'description': '''
            This stage ensures that newly acquired users reach their first meaningful action
            (activation milestone), which strongly correlates with long-term retention and monetization.
            It includes onboarding flows, tutorials, guided setups, nudges, lifecycle emails,
            and any mechanism that helps users realize product value quickly.

            The focus is on reducing time-to-value (TTV) and eliminating friction in early user experience.
        ''',
        'keywords':    ['onboard','first','welcome','setup','profile','complete','wizard',
                        'activation','getting started','tutorial','nudge','email'],
        'primary_metric': 'activation_rate',

        'questions': [
            ('monthly_signups',     'Monthly new sign-ups (users entering onboarding)', 'users/month', False),
            ('activation_rate',     'Current % who complete the activation step (%)',  'rate %',      True),
            ('ior',                 'IOR for activated users (%)',                      'rate %',      True),
            ('aov',                 'Average order value ($)',                          'dollars',     False),
            ('gross_margin',        'Gross margin (%)',                                 'rate %',      True),
            ('horizon',             'Time horizon (months)',                             'months',      False),

            ('time_to_activation',  'Median time taken to reach activation (hours/days)', 'time', False),
            ('onboarding_completion_rate','% users completing onboarding flow', 'rate %', False),
            ('drop_off_step',       'Step with highest drop-off in onboarding funnel', 'step index', False),
            ('nudge_effectiveness', '% lift in activation due to nudges/emails', 'rate %', False),
            ('feature_adoption_rate','% users using key features within first session', 'rate %', False),
        ],

        'downstream': [('ior', None)],

        'tracking_plan': '''
            - Track step-by-step onboarding funnel with timestamps.
            - Instrument key activation events (e.g., profile completion, first action).
            - Use cohort analysis to compare activation across signup dates and channels.
            - Measure impact of lifecycle messaging (email, push) on activation.
            - Track time-to-first-key-action as a critical KPI.
            - Run A/B tests on onboarding variants (guided vs unguided).
            - Capture qualitative feedback (surveys, session recordings).
        ''',

        'mde_benchmarks': {'typical_min_rel': 0.05, 'typical_max_rel': 0.20,
                           'label': '5–20% relative lift on activation rate'},
    },

    'conversion': {
        'label':       'Conversion Rate (Checkout / Funnel / Lead-to-Sale)',
        'description': '''
            This stage captures the efficiency of converting high-intent users into paying customers.
            It includes the entire purchase journey: browsing/browsing to cart, cart to checkout,
            checkout to payment, payment confirmation. Applies equally to e-commerce (cart → purchase),
            marketplace (inquiry/quote → order), SaaS (trial → paid), and retail (browse → buy).

            Optimization here directly impacts revenue and is often sensitive to friction, trust,
            pricing clarity, and UX performance.
        ''',
        'keywords':    ['checkout','funnel','cart','billing','payment','order','quote',
                        'ior','conversion','buy','purchase','accept','confirm','submit',
                        'lead','sale','transaction','basket'],
        'primary_metric': 'ior',

        'questions': [
            ('monthly_inquiries',   'Monthly inquiries / leads / carts / quotes (primary volume metric)',  'units/month', False),
            ('ior',                 'Current conversion rate (cart-to-purchase, quote-to-order, lead-to-sale %) ', 'rate %', True),
            ('aov',                 'Average order value ($)',                  'dollars',         False),
            ('gross_margin',        'Gross margin (%)',                         'rate %',          True),
            ('horizon',             'Time horizon (months)',                    'months',          False),

            ('checkout_dropoff_rate','% users dropping off during checkout', 'rate %', False),
            ('payment_success_rate','% successful payments vs attempts', 'rate %', False),
            ('error_rate',          'Technical or validation error rate during checkout', 'rate %', False),
            ('avg_checkout_time',   'Average time to complete checkout', 'time', False),
            ('cart_abandonment_rate','% carts abandoned before purchase', 'rate %', False),
        ],

        'downstream': [],

        'tracking_plan': '''
            - Track each step in checkout funnel (cart → address → payment → confirmation).
            - Capture payment failures with detailed error codes.
            - Monitor latency and page performance across checkout steps.
            - Segment conversion by device, payment method, and geography.
            - Track coupon usage and pricing exposure.
            - Run funnel A/B tests (e.g., fewer steps, guest checkout).
            - Implement session replay to identify UX friction.
        ''',

        'mde_benchmarks': {'typical_min_rel': 0.05, 'typical_max_rel': 0.15,
                           'label': '5–15% relative IOR lift (0.5–2pp absolute)'},
    },

    'retention': {
        'label':       'Repeat Orders & Retention',
        'description': '''
            This stage focuses on maximizing customer lifetime value by encouraging repeat usage
            and reducing churn. It includes post-purchase experiences, re-engagement campaigns,
            loyalty programs, and personalized recommendations.

            Strong retention indicates product-market fit and sustainable growth.
        ''',
        'keywords':    ['repeat','retention','return','reorder','summary','post.order',
                        'ltv','churn','re-engage','loyalty','upsell','cross-sell'],
        'primary_metric': 'repeat_order_rate',

        'questions': [
            ('monthly_orders',      'Monthly completed orders',                  'orders/month', False),
            ('repeat_rate',         'Current repeat order rate (%)',              'rate %',       True),
            ('aov',                 'Average order value for repeat orders ($)',  'dollars',      False),
            ('gross_margin',        'Gross margin (%)',                           'rate %',       True),
            ('horizon',             'Time horizon (months)',                      'months',       False),

            ('customer_ltv',        'Customer lifetime value ($)', 'dollars', False),
            ('churn_rate',          'Percentage of users not returning', 'rate %', False),
            ('repeat_frequency',    'Average number of repeat purchases per user', 'count', False),
            ('cohort_retention',    'Retention rate by cohort over time', 'rate %', False),
            ('email_reengagement_rate','% users reactivated via campaigns', 'rate %', False),
        ],

        'downstream': [],

        'tracking_plan': '''
            - Build cohort retention tables (weekly/monthly cohorts).
            - Track repeat purchase intervals and frequency distribution.
            - Attribute repeat orders to re-engagement campaigns.
            - Monitor churn signals (inactivity duration, drop in usage).
            - Track LTV by acquisition source.
            - Measure effectiveness of loyalty programs and incentives.
        ''',

        'mde_benchmarks': {'typical_min_rel': 0.05, 'typical_max_rel': 0.15,
                           'label': '5–15% relative lift on repeat order rate'},
    },

    'engagement': {
        'label':       'UI / UX & Engagement',
        'description': '''
            This stage includes all improvements related to user interaction, interface design,
            and engagement mechanisms. While these changes may not directly drive revenue,
            they significantly influence user behavior and downstream conversion.

            It includes search, recommendations, notifications, UI layouts, and interaction design.
        ''',
        'keywords':    ['ui','ux','design','layout','search','recommend','notification',
                        'email','push','banner','modal','tooltip','button','cta','page'],
        'primary_metric': 'ior',

        'questions': [
            ('monthly_users',       'Monthly active users who see this feature',  'users/month', False),
            ('current_ctr',         'Current click-through or engagement rate (%)', 'rate %',    True),
            ('ctr_to_ior_rate',     'Of engaged users, % who eventually convert (%)', 'rate %',  True),
            ('aov',                 'Average order value ($)',                    'dollars',     False),
            ('gross_margin',        'Gross margin (%)',                           'rate %',      True),
            ('horizon',             'Time horizon (months)',                      'months',      False),

            ('session_duration',    'Average session time (minutes)', 'time', False),
            ('pages_per_session',   'Average pages viewed per session', 'count', False),
            ('interaction_depth',   'Number of interactions per session', 'count', False),
            ('feature_usage_rate',  '% users engaging with feature', 'rate %', False),
            ('scroll_depth',        'Average scroll percentage on pages', 'rate %', False),
        ],

        'downstream': [('ctr_to_ior_rate', None)],

        'tracking_plan': '''
            - Track user interaction events (clicks, scrolls, hovers).
            - Use heatmaps and session recordings for UX insights.
            - Segment engagement by user cohorts and device types.
            - Measure feature adoption and repeat usage.
            - Run A/B tests on UI components (buttons, layouts, messaging).
            - Track notification performance (open rate, CTR).
        ''',

        'mde_benchmarks': {'typical_min_rel': 0.03, 'typical_max_rel': 0.10,
                           'label': '3–10% relative lift (UX changes tend to be smaller)'},
    },

    'pricing': {
        'label':       'Pricing & Monetisation',
        'description': '''
            This stage focuses on optimizing pricing strategies to maximize revenue and profitability.
            It includes pricing display, discount strategies, bundling, tiering, and psychological pricing.

            Pricing changes often have trade-offs between conversion rate and average order value,
            making careful experimentation critical.
        ''',
        'keywords':    ['price','pricing','discount','fee','rate','tier','plan','package',
                        'revenue','monetis','anchor','display','promo','coupon'],
        'primary_metric': 'ior',

        'questions': [
            ('monthly_inquiries',   'Monthly quotes that see the pricing change', 'inquiries/month', False),
            ('ior',                 'Current IOR (%)',                           'rate %',          True),
            ('aov',                 'Current average order value ($)',           'dollars',         False),
            ('aov_delta_pct',       'Expected % change in AOV from pricing change (%)', 'rate %',  True),
            ('gross_margin',        'Gross margin (%)',                          'rate %',          True),
            ('horizon',             'Time horizon (months)',                     'months',          False),

            ('price_elasticity',    'Sensitivity of demand to price changes', 'elasticity', False),
            ('discount_uplift',     'Conversion lift due to discounts', 'rate %', False),
            ('margin_after_discount','Effective margin after discounts (%)', 'rate %', False),
            ('plan_selection_distribution','% users selecting each pricing tier', 'distribution %', False),
            ('revenue_per_user',    'Average revenue per user ($)', 'dollars', False),
        ],

        'downstream': [],

        'tracking_plan': '''
            - Track exposure to pricing variants (A/B testing).
            - Measure both conversion rate and AOV simultaneously.
            - Segment pricing performance by customer cohorts.
            - Track discount usage and incremental revenue impact.
            - Monitor margin impact post pricing changes.
            - Conduct elasticity analysis using historical experiments.
        ''',

        'mde_benchmarks': {'typical_min_rel': 0.03, 'typical_max_rel': 0.12,
                           'label': '3–12% relative lift (pricing changes have mixed effects)'},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# FUNNEL CLASSIFIER — uses LLM to map free-text description to taxonomy
# ─────────────────────────────────────────────────────────────────────────────

def classify_feature(description: str, llm) -> str:
    """
    Returns a key from FUNNEL_TAXONOMY, or 'other' for novel/uncategorised features.

    Three-stage classification:
    Stage 1: keyword scoring (instant, no LLM)
    Stage 2: LLM disambiguation when scores are tied or zero
    Stage 3: 'other' escape hatch — when LLM confidence is low,
             returns 'other' so the caller can trigger grounding questions
             instead of silently falling back to a wrong category.
    """
    desc_lower = description.lower()

    # Stage 1: keyword scoring
    scores = {}
    for cat, meta in FUNNEL_TAXONOMY.items():
        hits = sum(1 for kw in meta['keywords'] if kw in desc_lower)
        if hits > 0:
            scores[cat] = hits

    if scores:
        top_score = max(scores.values())
        top_cats  = [c for c, s in scores.items() if s == top_score]
        if len(top_cats) == 1 and top_score >= 2:
            return top_cats[0]   # strong unambiguous match — skip LLM

    # Stage 2: LLM disambiguation
    all_cats = list(FUNNEL_TAXONOMY.keys()) + ['other']
    categories_text = '\n'.join(
        f'  {k}: {v["label"]} — {v["description"]}'
        for k, v in FUNNEL_TAXONOMY.items()
    )
    prompt = (
        f'Classify this product feature into exactly one category.\n'
        f'Feature: "{description}"\n\n'
        f'Categories:\n{categories_text}\n'
        f'  other: Does not fit any category above\n\n'
        f'Return ONLY the category key (one of: {", ".join(all_cats)}).\n'
        f'If unsure or it spans multiple categories equally, return: other\n'
        f'No explanation. Just the key.'
    )
    resp = llm.ask(prompt).strip().lower().split()[0]

    for k in all_cats:
        if k in resp:
            return k

    # Stage 3: fallback with warning
    if scores:
        best = max(scores, key=scores.get)
        logger.warning(
            'classify_feature: LLM returned ambiguous response "%s" for "%s". '
            'Falling back to "%s" (keyword match). Consider using "other" path.',
            resp[:30], description[:50], best)
        return best

    logger.warning('classify_feature: no keyword match and LLM ambiguous for "%s". '
                   'Returning "other".', description[:50])
    return 'other'


def handle_other_category(desc: str, llm) -> tuple:
    """
    Escape hatch for features that don't fit the 6 standard categories.
    Asks 3 grounding questions to determine the funnel position and
    the right metrics, then builds a custom opportunity plan. Output is
    a designed PDF document (template-aware).
    """
    print()
    print("  ℹ️  This feature does not clearly fit one of the standard funnel categories.")
    print("  I will ask 3 quick grounding questions to understand it better.")
    print()

    q1 = input(
        '  ❓ [1/3] What specific USER ACTION changes because of this feature?\n'
        '         (e.g. "user can now 3D-preview part before ordering",\n'
        '          "user sees fewer required fields in checkout")\n'
        '  → ').strip()

    q2 = input(
        '\n  ❓ [2/3] What metric would PROVE this feature worked?\n'
        '         (e.g. "more users place an order after viewing the part",\n'
        '          "checkout completion rate increases")\n'
        '  → ').strip()

    q3 = input(
        '\n  ❓ [3/3] What could BREAK or get WORSE if this feature ships?\n'
        '         (e.g. "page load time increases", "AOV drops because users\n'
        '          order simpler parts after seeing 3D preview")\n'
        '  → ').strip()

    # ── Template-aware section list ──────────────────────────────────────────
    default_sections = [
        'FUNNEL POSITION',
        'PRIMARY METRICS',
        'SECONDARY METRICS',
        'GUARDRAIL METRICS',
        'DATA TRACKING REQUIREMENTS',
        'OPPORTUNITY SIZING APPROACH',
    ]
    user_sections, _ = ask_for_template('Custom Measurement Plan', default_sections)
    sections_to_use = user_sections if user_sections else default_sections

    print()
    print('  🤖 Generating custom measurement plan for this feature...')

    context_block = (
        'Feature: "{}"\n'
        'User action that changes: {}\n'
        'Success metric: {}\n'
        'Risk / what could break: {}'
    ).format(desc, q1, q2, q3)

    guidance = (
        'Keep "Field: value" lines (Metric, Definition, Why primary, Direction, '
        'Track, When, Properties, Risk, Threshold) each on its own line so the '
        'renderer formats them as styled cards. For PRIMARY, SECONDARY, and '
        'GUARDRAIL metrics use the Metric / Definition / Why / Direction pattern. '
        'For DATA TRACKING REQUIREMENTS use the Track / When / Properties / Why '
        'needed pattern. OPPORTUNITY SIZING APPROACH should be 2-3 sentences in '
        'plain prose about proxy metrics and estimation method.'
    )

    prompt = build_llm_prompt_from_template(
        role='You are a senior product analytics expert. A PM described a feature that '
             'does not fit standard funnel categories. Generate a custom measurement plan.',
        context_block=context_block,
        sections_to_fill=sections_to_use,
        content_guidance=guidance,
    )

    plan = llm.ask(prompt)
    try:
        plan = _strip_decorative_chars(plan)
    except NameError:
        pass

    print('\n' + '═'*72)
    print('  📋  CUSTOM MEASUREMENT PLAN (Uncategorised Feature)')
    print('  Feature: ' + desc[:65])
    print('═'*72)
    print(plan)
    print('═'*72)
    print()
    print('  ⚠️  This plan was generated for a non-standard feature.')
    print('  Recommend human review before adding to your PRD.')

    # ── Parse + render PDF ───────────────────────────────────────────────────
    parsed = parse_sections_from_llm_output(plan, sections_to_use)
    fname = 'custom_measurement_plan.pdf'
    out_path = render_document_pdf(
        title='Custom Measurement Plan',
        subtitle='Feature: ' + desc[:90],
        sections=parsed,
        output_path=fname,
        metadata={
            'Feature':        desc[:120],
            'User action':    q1[:120],
            'Success signal': q2[:120],
            'Risk':           q3[:120],
            'Category':       'Uncategorised (custom plan)',
        },
        accent_color=PDF_PALETTE['secondary'],
    )
    print('  📁 Saved → ' + out_path)

    custom_answers = {
        'user_action': q1, 'success_metric': q2,
        'risk': q3, 'plan': plan,
        'sections_used': sections_to_use,
        'output_file': out_path,
    }
    return custom_answers, plan


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE PULLER — pulls relevant metrics from historical data
# ─────────────────────────────────────────────────────────────────────────────

def pull_baselines(category: str) -> dict:
    """
    Query DuckDB for baseline metrics, null-safe and schema-config-aware.

    Real-world hardening:
    - Every value has a fallback default (no raw None/NaN propagation)
    - Queries use col() / tbl() so column/table names are client-configurable
    - Traffic query handles both pre-aggregated and row-level granularity
    - Segment-specific IOR baselines for more accurate per-segment MDE
    """
    cfg = CLIENT_SCHEMA
    inq_tbl  = tbl('inquiries')
    traf_tbl = tbl('traffic')
    conv_col = col('converted')
    val_col  = col('order_value')
    seg_col  = col('account_segment')
    date_col = col('created_at')

    # ── Overall inquiry baselines ──────────────────────────────────────────────
    hist_raw = safe_query(f"""
        SELECT
            COUNT(DISTINCT {col('inquiry_id')})
                / NULLIF(DATEDIFF('day', MIN({date_col}), MAX({date_col})) + 1, 0)
                * 30.4                                               AS monthly_inquiries,
            AVG(CAST({conv_col} AS DOUBLE))                         AS ior,
            AVG(CASE WHEN {conv_col} THEN {val_col} END)            AS aov,
            STDDEV(CAST({conv_col} AS DOUBLE))                      AS ior_stddev,
            SUM(CAST({conv_col} AS INTEGER))
                / NULLIF(DATEDIFF('month', MIN({date_col}), MAX({date_col})) + 1, 0)
                                                                     AS monthly_orders
        FROM {inq_tbl}
        WHERE {conv_col} IS NOT NULL
    """)

    if hist_raw is None:
        hist = {'monthly_inquiries': cfg['null_daily_traffic']*30.4,
                'ior': cfg['null_ior_default'], 'aov': cfg['null_aov_default'],
                'ior_stddev': 0.02, 'monthly_orders': cfg['null_daily_traffic']*30.4*cfg['null_ior_default']}
    else:
        r = hist_raw.iloc[0]
        hist = {
            'monthly_inquiries': safe_val(r['monthly_inquiries'], cfg['null_daily_traffic']*30.4),
            'ior':               safe_val(r['ior'],               cfg['null_ior_default']),
            'aov':               safe_val(r['aov'],               cfg['null_aov_default']),
            'ior_stddev':        safe_val(r['ior_stddev'],        0.02),
            'monthly_orders':    safe_val(r['monthly_orders'],    10),
        }

    # ── Segment-specific IOR baselines (for per-segment MDE) ─────────────────
    seg_raw = safe_query(f"""
        SELECT
            {seg_col}                              AS segment,
            AVG(CAST({conv_col} AS DOUBLE))        AS ior,
            COUNT(*)                               AS n_inquiries,
            AVG(CASE WHEN {conv_col} THEN {val_col} END) AS aov
        FROM {inq_tbl}
        WHERE {conv_col} IS NOT NULL
          AND {seg_col}  IS NOT NULL
        GROUP BY {seg_col}
        HAVING COUNT(*) >= {cfg['min_segment_size']}
        ORDER BY n_inquiries DESC
    """)
    segment_baselines = {}
    if seg_raw is not None:
        for _, row in seg_raw.iterrows():
            segment_baselines[str(row['segment'])] = {
                'ior': safe_val(row['ior'], hist['ior']),
                'n':   int(row['n_inquiries']),
                'aov': safe_val(row['aov'], hist['aov']),
            }

    # ── Repeat-order rate ──────────────────────────────────────────────────────
    repeat_raw = safe_query(f"""
        SELECT
            SUM(CASE WHEN order_count > 1 THEN 1 ELSE 0 END) * 1.0
                / NULLIF(COUNT(*), 0)  AS repeat_rate
        FROM (
            SELECT {col('account_id')}, COUNT(*) AS order_count
            FROM {inq_tbl}
            WHERE {conv_col} = true
            GROUP BY {col('account_id')}
        ) buyer_orders
    """)
    repeat_rate = safe_val(
        repeat_raw.iloc[0]['repeat_rate'] if repeat_raw is not None else None, 0.40)

    # ── Traffic baselines ──────────────────────────────────────────────────────
    granularity = cfg.get('traffic_granularity', 'pre_aggregated')

    if granularity == 'pre_aggregated':
        traffic_raw = safe_query(f"""
            SELECT
                SUM({col('total_sessions')})
                    / NULLIF(COUNT(DISTINCT {col('traffic_date')}), 0) * 30.4 AS monthly_visitors,
                SUM({col('new_signups')})
                    / NULLIF(COUNT(DISTINCT {col('traffic_date')}), 0) * 30.4 AS monthly_signups,
                SUM({col('signed_in')})
                    / NULLIF(COUNT(DISTINCT {col('traffic_date')}), 0) * 30.4 AS monthly_signins
            FROM {traf_tbl}
            WHERE {col('traffic_date')} >=
                  ((SELECT MAX({col('traffic_date')}) FROM {traf_tbl})
                   - INTERVAL 3 MONTH)
        """)
    else:
        traffic_raw = safe_query(f"""
            SELECT
                COUNT(*) / NULLIF(COUNT(DISTINCT {col('traffic_date')}), 0) * 30.4 AS monthly_visitors,
                SUM(CASE WHEN is_new_user THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(DISTINCT {col('traffic_date')}), 0) * 30.4  AS monthly_signups,
                SUM(CASE WHEN is_signed_in THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(DISTINCT {col('traffic_date')}), 0) * 30.4  AS monthly_signins
            FROM {traf_tbl}
            WHERE {col('traffic_date')} >=
                  ((SELECT MAX({col('traffic_date')}) FROM {traf_tbl})
                   - INTERVAL 3 MONTH)
        """)

    default_vis = hist['monthly_inquiries'] * 15
    if traffic_raw is None:
        traffic = {'monthly_visitors': default_vis,
                   'monthly_signups': default_vis * 0.03,
                   'monthly_signins': default_vis * 0.45}
    else:
        r = traffic_raw.iloc[0]
        traffic = {
            'monthly_visitors': safe_val(r['monthly_visitors'], default_vis),
            'monthly_signups':  safe_val(r['monthly_signups'],  default_vis * 0.03),
            'monthly_signins':  safe_val(r['monthly_signins'],  default_vis * 0.45),
        }

    monthly_visitors = max(traffic['monthly_visitors'], 1)
    signup_rate = traffic['monthly_signups'] / monthly_visitors

    return {
        'monthly_visitors':    round(monthly_visitors, 0),
        'monthly_signups':     round(traffic['monthly_signups'], 0),
        'monthly_signins':     round(traffic['monthly_signins'], 0),
        'signup_rate':         round(signup_rate, 4),
        'monthly_inquiries':   round(hist['monthly_inquiries'], 0),
        'ior':                 round(hist['ior'], 4),
        'ior_stddev':          round(hist['ior_stddev'], 4),
        'aov':                 round(hist['aov'], 0),
        'monthly_orders':      round(hist['monthly_orders'], 0),
        'repeat_rate':         round(repeat_rate, 4),
        'activation_rate':     0.20,
        'segment_baselines':   segment_baselines,
    }




# ─────────────────────────────────────────────────────────────────────────────
# MDE RECOMMENDER — never asks user; computes from data + benchmarks
# ─────────────────────────────────────────────────────────────────────────────

def recommend_mde(baseline_rate: float, category: str, baselines: dict) -> dict:
    """
    Returns a recommended MDE (absolute and relative) based on:
    1. Statistical minimum: smallest effect detectable with ~4 weeks of data
    2. Business minimum: smallest effect worth caring about (1% of baseline)
    3. Industry benchmark range for this category
    The recommended MDE is the MAXIMUM of (1) and (2) — conservative but practical.
    """
    from scipy.stats import norm as _norm

    if category == 'acquisition':
        daily_n = baselines.get('monthly_visitors', 10000) / 30.4 / 2
    elif category in ('conversion', 'pricing'):
        daily_n = baselines.get('monthly_inquiries', 1000) / 30.4 / 2
    else:
        daily_n = baselines.get('monthly_inquiries', 1000) / 30.4 / 2

    n_4weeks = daily_n * 28
    p = baseline_rate
    se = np.sqrt(2 * p * (1-p) / n_4weeks) if n_4weeks > 0 else 0.01
    stat_min_abs = round(1.96 * se * 2, 4)   # 80% power, approx
    stat_min_rel = round(stat_min_abs / p * 100, 1) if p > 0 else 10.0

    biz_min_abs = round(p * 0.01, 4)   # 1% relative
    biz_min_rel = 1.0

    bench = FUNNEL_TAXONOMY[category]['mde_benchmarks']
    bench_mid_abs = round(p * (bench['typical_min_rel'] + bench['typical_max_rel']) / 2, 4)
    bench_mid_rel = round((bench['typical_min_rel'] + bench['typical_max_rel']) / 2 * 100, 1)

    recommended_abs = round(max(stat_min_abs, biz_min_abs), 4)
    recommended_rel = round(recommended_abs / p * 100, 1) if p > 0 else 10.0

    return {
        'stat_min_abs':     stat_min_abs,
        'stat_min_rel_pct': stat_min_rel,
        'biz_min_abs':      biz_min_abs,
        'biz_min_rel_pct':  biz_min_rel,
        'bench_range':      bench['label'],
        'bench_mid_abs':    bench_mid_abs,
        'bench_mid_rel_pct': bench_mid_rel,
        'recommended_abs':  recommended_abs,
        'recommended_rel_pct': recommended_rel,
        'n_4weeks':         int(n_4weeks),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC OPPORTUNITY COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_dynamic_opportunity(category: str, answers: dict) -> dict:
    """
    Computes incremental GMV by walking the funnel chain for the given category.
    `answers` contains whatever questions were asked for this category.
    """
    mde_info = answers['_mde']
    rec_abs  = mde_info['recommended_abs']

    horizon  = int(answers.get('horizon', 12))
    gm       = answers.get('gross_margin', 0.30)
    aov      = answers.get('aov', answers.get('aov', 5000))

    funnel_chain = []
    incremental  = 0

    if category == 'acquisition':
        visitors     = answers['monthly_visitors']
        curr_su      = answers['signup_rate']
        target_su    = curr_su + rec_abs
        act_rate     = answers['activation_rate']
        ior          = answers['ior']
        extra_su     = visitors * (target_su - curr_su)
        extra_inq    = extra_su * act_rate
        incremental  = extra_inq * ior
        funnel_chain = [
            ('Visitors', f'{visitors:,.0f}/mo', '', ''),
            ('Sign-up rate', f'{curr_su*100:.2f}%', f'{target_su*100:.2f}%', f'+{(target_su-curr_su)*100:.3f}pp'),
            ('Extra sign-ups', f'{extra_su:,.1f}/mo', '', ''),
            ('Activation rate', f'{act_rate*100:.1f}%', '', f'→ {extra_inq:,.1f} extra inquiries'),
            ('IOR', f'{ior*100:.2f}%', '', f'→ {incremental:,.1f} extra orders/mo'),
        ]

    elif category == 'activation':
        monthly_su   = answers['monthly_signups']
        curr_act     = answers['activation_rate']
        target_act   = curr_act + rec_abs
        ior          = answers['ior']
        extra_act    = monthly_su * (target_act - curr_act)
        incremental  = extra_act * ior
        funnel_chain = [
            ('Monthly sign-ups', f'{monthly_su:,.0f}/mo', '', ''),
            ('Activation rate', f'{curr_act*100:.2f}%', f'{target_act*100:.2f}%', f'+{(target_act-curr_act)*100:.3f}pp'),
            ('Extra activated', f'{extra_act:,.1f}/mo', '', ''),
            ('IOR', f'{ior*100:.2f}%', '', f'→ {incremental:,.1f} extra orders/mo'),
        ]

    elif category in ('conversion', 'pricing'):
        monthly_inq   = answers['monthly_inquiries']
        curr_ior      = answers['ior']
        target_ior    = curr_ior + rec_abs
        aov_mult      = 1 + answers.get('aov_delta_pct', 0)
        effective_aov = aov * aov_mult

        ior_incremental = monthly_inq * (target_ior - curr_ior)
        incremental     = ior_incremental

        funnel_chain = [
            ('Monthly inquiries', f'{monthly_inq:,.0f}/mo', '', ''),
            ('IOR', f'{curr_ior*100:.2f}%', f'{target_ior*100:.2f}%',
             f'+{(target_ior-curr_ior)*100:.3f}pp'),
            ('Extra orders/mo', f'{ior_incremental:,.1f}', '', ''),
        ]

        aov_gmv_uplift = 0.0
        if category == 'pricing' and abs(aov_mult - 1) > 0.001:
            aov_gmv_uplift = monthly_inq * curr_ior * (effective_aov - aov)
            funnel_chain.append((
                'AOV uplift on existing orders',
                f'${aov:,.0f}', f'${effective_aov:,.0f}',
                f'+${aov_gmv_uplift:,.0f} GMV/mo'
            ))
            aov = effective_aov

    elif category == 'retention':
        monthly_ord  = answers['monthly_orders']
        curr_rep     = answers['repeat_rate']
        target_rep   = curr_rep + rec_abs
        incremental  = monthly_ord * (target_rep - curr_rep)
        funnel_chain = [
            ('Monthly orders', f'{monthly_ord:,.0f}/mo', '', ''),
            ('Repeat order rate', f'{curr_rep*100:.2f}%', f'{target_rep*100:.2f}%', f'+{(target_rep-curr_rep)*100:.3f}pp'),
            ('Extra repeat orders', f'{incremental:,.1f}/mo', '', ''),
        ]

    elif category == 'engagement':
        monthly_users = answers['monthly_users']
        curr_ctr      = answers['current_ctr']
        target_ctr    = curr_ctr + rec_abs
        c2o           = answers['ctr_to_ior_rate']
        extra_engaged = monthly_users * (target_ctr - curr_ctr)
        incremental   = extra_engaged * c2o
        funnel_chain  = [
            ('Monthly users', f'{monthly_users:,.0f}/mo', '', ''),
            ('Engagement rate', f'{curr_ctr*100:.2f}%', f'{target_ctr*100:.2f}%', f'+{(target_ctr-curr_ctr)*100:.3f}pp'),
            ('Extra engaged', f'{extra_engaged:,.1f}/mo', '', ''),
            ('Engage→Order rate', f'{c2o*100:.1f}%', '', f'→ {incremental:,.1f} extra orders/mo'),
        ]

    aov_gmv_uplift = locals().get('aov_gmv_uplift', 0.0)  # only set for pricing
    monthly_gmv = incremental * aov + aov_gmv_uplift
    monthly_gm  = monthly_gmv * gm

    return {
        'category':                 category,
        'funnel_chain':             funnel_chain,
        'mde_info':                 mde_info,
        'incremental_orders_mo':    round(incremental, 1),
        'incremental_gmv_mo':       round(monthly_gmv, 0),
        'incremental_gm_mo':        round(monthly_gm, 0),
        'incremental_gmv_total':    round(monthly_gmv * horizon, 0),
        'incremental_gm_total':     round(monthly_gm  * horizon, 0),
        'time_horizon_months':      horizon,
        'aov':                      aov,
        'gross_margin':             gm,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DYNAMIC OPPORTUNITY SIZER
# ─────────────────────────────────────────────────────────────────────────────

def run_opportunity_sizing(llm):
    print('\n' + '═'*72)
    print('  📐  DYNAMIC OPPORTUNITY SIZING')
    print('═'*72)

    # ── Step 1: Feature description ───────────────────────────────────────────
    print('\n  Describe the feature or change you are sizing.')
    print('  (Be specific — e.g. "social login button on sign-up page", '
                            '"reorder billing step in checkout", "new summary page layout")')
    print()
    while True:
        desc = input('  ❓ Feature description: ').strip()
        if len(desc) >= 5: break
        print('     ⚠️  Please describe the feature (at least 5 characters)')

    # ── Step 2: Classify ────────────────────────────────────────────────────────
    print('\n  🔍 Classifying feature...')
    category = classify_feature(desc, llm)

    # Handle 'other' — novel features outside the 6 standard categories
    if category == 'other':
        custom_answers, plan = handle_other_category(desc, llm)
        return {'category': 'other', 'custom_plan': plan}

    taxonomy  = FUNNEL_TAXONOMY[category]
    baselines = pull_baselines(category)

    # ── Data quality check on baselines table ────────────────────────────────
    inq_table = tbl('inquiries')
    try:
        raw_df = safe_query(f'SELECT * FROM {inq_table} LIMIT 50000')
        if raw_df is not None:
            raw_df = dedup_dataframe(raw_df)
            dq_report = validate_experiment_data(raw_df, 'baselines')
            if dq_report['warnings']:
                print(f'\n  ⚠️  Data quality warnings on baseline table:')
                for w in dq_report['warnings']:
                    print(f'     • {w}')
            if not dq_report['ok']:
                print(f'  🚨 Data quality errors — baselines may be unreliable:')
                for e in dq_report['errors']:
                    print(f'     • {e}')
    except Exception as _dq_err:
        logger.warning('DQ check failed: %s', _dq_err)

    print(f'  → Classified as: {taxonomy["label"]}')
    print(f'     {taxonomy["description"]}')

    # ── Step 3: MDE recommendation ────────────────────────────────────────────
    # Determine the primary baseline rate for this category
    primary_metric = taxonomy['primary_metric']
    baseline_rate  = baselines.get(primary_metric, baselines['ior'])
    mde_info       = recommend_mde(baseline_rate, category, baselines)

    print(f'\n  📊 Auto-detected baselines & recommended MDE:')
    print(f'     Primary metric ({primary_metric}): {baseline_rate*100:.3f}%')
    print(f'     Stat. minimum detectable (4 wks): {mde_info["stat_min_rel_pct"]:+.1f}% rel  = {mde_info["stat_min_abs"]*100:+.3f}pp abs')
    print(f'     Business minimum meaningful:      {mde_info["biz_min_rel_pct"]:+.1f}% rel  = {mde_info["biz_min_abs"]*100:+.3f}pp abs')
    print(f'     Industry benchmark ({category}):  {mde_info["bench_range"]}')
    print(f'     ✅ Recommended MDE:               {mde_info["recommended_rel_pct"]:+.1f}% rel  = {mde_info["recommended_abs"]*100:+.3f}pp abs')
    print(f'       (= smallest effect worth detecting, based on your traffic & benchmarks)')

    # Show per-segment baselines for context
    seg_bases = baselines.get('segment_baselines', {})
    if seg_bases:
        print(f'\n  📊 Segment-specific IOR baselines (for segment-level MDE):')
        for seg, sb in seg_bases.items():
            seg_mde = recommend_mde(sb['ior'], category, baselines)
            print(f'     {seg:<18}: IOR={sb["ior"]*100:.2f}%  '
                  f'MDE={seg_mde["recommended_rel_pct"]:+.1f}% rel '
                  f'(n={sb["n"]:,})')

    # ── Step 4: Ask only relevant questions ───────────────────────────────────
    print(f'\n  ── {len(taxonomy["questions"])} questions for {taxonomy["label"]} ──')
    print('     (press Enter to accept the auto-detected default)\n')

    answers = {'_mde': mde_info}

    answers.setdefault('ior',             baselines['ior'])
    answers.setdefault('activation_rate', baselines['activation_rate'])
    answers.setdefault('monthly_signups', baselines['monthly_signups'])
    answers.setdefault('monthly_orders',  baselines['monthly_orders'])
    answers.setdefault('repeat_rate',     baselines['repeat_rate'])
    answers.setdefault('monthly_visitors',baselines['monthly_visitors'])
    answers.setdefault('monthly_inquiries',baselines['monthly_inquiries'])
    answers.setdefault('monthly_users',   baselines['monthly_signins'])

    DEFAULTS = {
        'monthly_visitors':  baselines['monthly_visitors'],
        'signup_rate':       baselines['signup_rate'] * 100,
        'monthly_signups':   baselines['monthly_signups'],
        'activation_rate':   baselines['activation_rate'] * 100,
        'monthly_inquiries': baselines['monthly_inquiries'],
        'ior':               baselines['ior'] * 100,
        'monthly_orders':    baselines['monthly_orders'],
        'repeat_rate':       baselines['repeat_rate'] * 100,
        'aov':               baselines['aov'],
        'gross_margin':      30.0,
        'horizon':           12,
        'monthly_users':     baselines['monthly_signins'],
        'current_ctr':       2.5,
        'ctr_to_ior_rate':   baselines['ior'] * 100,
        'aov_delta_pct':     0.0,
    }

    for key, question_text, unit, is_pct in taxonomy['questions']:
        default = DEFAULTS.get(key, 0)
        while True:
            if is_pct:
                hint = f' [{default:.3f}%]'
            else:
                hint = f' [{default:,.0f} {unit}]' if unit else f' [{default}]'
            raw = input(f'     ❓ {question_text}{hint}: ').strip()
            if raw == '':
                val = float(default)
            else:
                try:
                    val = float(raw)
                except ValueError:
                    print('        ⚠️  Please enter a number'); continue
            if is_pct: val = val / 100
            answers[key] = val
            break

    # ── Step 5: Compute opportunity ───────────────────────────────────────────
    result = compute_dynamic_opportunity(category, answers)

    # ── Step 6: Print results ─────────────────────────────────────────────────
    print('\n' + '─'*72)
    print('  📊  RESULTS')
    print('─'*72)
    print(f'  Feature category   : {taxonomy["label"]}')
    print(f'  Feature description: {desc}')
    print(f'  Recommended MDE    : {mde_info["recommended_rel_pct"]:+.1f}% relative '
          f'= {mde_info["recommended_abs"]*100:+.3f}pp absolute')
    print(f'\n  Funnel chain:')
    for row in result['funnel_chain']:
        if row[2]:  # has current → target
            print(f'    {row[0]:<26} {row[1]:<15} → {row[2]:<15} {row[3]}')
        else:
            print(f'    {row[0]:<26} {row[1]:<15} {row[3]}')
    print(f'\n  ── Using MDE as the uplift target ──')
    print(f'  Incremental orders/month : {result["incremental_orders_mo"]:,.1f}')
    print(f'  Incremental GMV/month    : ${result["incremental_gmv_mo"]:,.0f}')
    print(f'  Incremental GM/month     : ${result["incremental_gm_mo"]:,.0f}')
    print(f'  ── {result["time_horizon_months"]}-month horizon ──')
    print(f'  Incremental GMV total    : ${result["incremental_gmv_total"]:,.0f}')
    print(f'  Incremental GM total     : ${result["incremental_gm_total"]:,.0f}')
    print('─'*72)
    print('  💡 This is the MINIMUM opportunity (at the MDE uplift).')
    print('     If the feature delivers more lift, the upside scales linearly.')

    # ── Step 7: Visualisation ─────────────────────────────────────────────────
    _plot_opportunity(result, desc, taxonomy, mde_info)

    # ── Step 8: LLM Narrative ─────────────────────────────────────────────────
    print('\n  🤖 Generating executive summary...')
    narrative = llm.narrate(
        {'feature': desc, 'category': taxonomy['label'], 'result': result,
         'mde': mde_info, 'funnel': result['funnel_chain']},
        context=(
            f'Opportunity sizing for feature: "{desc}". '
            f'Category: {taxonomy["label"]}. '
            f'MDE used: {mde_info["recommended_rel_pct"]:.1f}% relative. '
            f'Provide: (1) headline opportunity in plain language, '
            f'(2) key assumptions and what could make the number higher/lower, '
            f'(3) recommendation on whether to proceed with an A/B test.'
        )
    )
    print('\n' + '─'*72)
    print('  🤖  EXECUTIVE SUMMARY')
    print('─'*72)
    print(narrative)
    print('─'*72)
    return result


def _plot_opportunity(result, desc, taxonomy, mde_info):
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.patch.set_facecolor('#0f0f0f')
    fig.suptitle(f'📐 Opportunity Sizing: {desc[:55]}', fontsize=13,
                 color=COLORS['highlight'], fontweight='bold')

    # 1. MDE breakdown
    ax = axes[0]
    labels  = ['Statistical\nMinimum', 'Business\nMinimum', 'Industry\nBenchmark', 'Recommended\nMDE']
    values  = [mde_info['stat_min_rel_pct'], mde_info['biz_min_rel_pct'],
               mde_info['bench_mid_rel_pct'], mde_info['recommended_rel_pct']]
    colours = [COLORS['neutral'], COLORS['neutral'], COLORS['control'], COLORS['highlight']]
    bars    = ax.bar(labels, values, color=colours, width=0.55)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.1,
                f'{v:.1f}%', ha='center', fontsize=10, fontweight='bold', color='white')
    ax.set_title('MDE Breakdown\n(relative %)', color=COLORS['highlight'])
    ax.set_ylabel('Relative MDE (%)')

    # 2. Cumulative GMV over horizon
    ax = axes[1]
    months  = np.arange(1, result['time_horizon_months']+1)
    cum_gmv = months * result['incremental_gmv_mo'] / 1e6
    cum_gm  = months * result['incremental_gm_mo']  / 1e6
    ax.fill_between(months, cum_gmv, alpha=0.25, color=COLORS['treatment'])
    ax.plot(months, cum_gmv, color=COLORS['treatment'], lw=2.5, label='GMV')
    ax.fill_between(months, cum_gm,  alpha=0.25, color=COLORS['positive'])
    ax.plot(months, cum_gm,  color=COLORS['positive'],  lw=2.5, label='Gross Margin')
    ax.set_xlabel('Month'); ax.set_ylabel('Cumulative ($M)')
    ax.set_title('Cumulative Opportunity', color=COLORS['highlight'])
    ax.legend(fontsize=9)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f'${x:.2f}M'))

    # 3. Funnel breakdown
    ax = axes[2]
    ax.axis('off')
    ax.set_title('Funnel Chain', color=COLORS['highlight'])
    for ri, row in enumerate(result['funnel_chain']):
        ax.text(0.03, 0.95-ri*0.17, row[0], transform=ax.transAxes,
                fontsize=9, color='#aaa', va='top')
        display_val = f'{row[1]}' + (f' → {row[2]}' if row[2] else '')
        ax.text(0.03, 0.88-ri*0.17, display_val, transform=ax.transAxes,
                fontsize=9.5, color='white', va='top', fontweight='bold')
        if row[3]:
            ax.text(0.03, 0.81-ri*0.17, row[3], transform=ax.transAxes,
                    fontsize=9, color=COLORS['positive'], va='top', fontstyle='italic')

    plt.tight_layout()
    plt.savefig('opportunity_sizing.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → opportunity_sizing.png')


print('✅ Dynamic opportunity sizer loaded')
print('   Supports categories:', list(FUNNEL_TAXONOMY.keys()))


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 5 — AUDIENCE SELECTION
# ═════════════════════════════════════════════════════════════════════════════

# ── Propensity scoring rules per funnel category ───────────────────────────
PROPENSITY_RULES = {
    'conversion': {
        'description': 'Users likely to respond to checkout/funnel changes',
        'high_propensity': {
            'ior_range':      (0.10, 0.30),   # mid-range IOR — not already maxed out
            'n_inquiries_min': 3,              # have submitted quotes before
            'has_billing':     None,           # both relevant
            'segments':        ['Core','Growth'],
        },
        'exclude': {
            'ior_range': (0.40, 1.0),          # already converting very well
            'n_inquiries_max': 1,              # one-time users unlikely to respond
        },
    },
    'acquisition': {
        'description': 'Users likely to respond to sign-up / onboarding changes',
        'high_propensity': {
            'ior_range':      (0.0, 0.20),
            'n_inquiries_min': 0,
            'recency_days_max': 90,
            'segments':        ['Growth','Individuals'],
        },
        'exclude': {
            'n_inquiries_min': 20,             # already very established
        },
    },
    'retention': {
        'description': 'Users likely to respond to re-engagement / repeat order nudges',
        'high_propensity': {
            'orders_range':   (1, 5),          # made 1-5 orders — could repeat
            'recency_days_range': (30, 180),   # not too recent, not churned
            'segments':        ['Core','Enterprise'],
        },
        'exclude': {
            'orders_range': (0, 0),            # never ordered
        },
    },
    'engagement': {
        'description': 'Users likely to respond to UI / UX changes',
        'high_propensity': {
            'n_inquiries_min': 5,
            'ior_range':      (0.05, 0.35),
            'segments':        ['Core','Growth','Enterprise'],
        },
        'exclude': {},
    },
    'pricing': {
        'description': 'Users likely to respond to price display changes',
        'high_propensity': {
            'ior_range':      (0.08, 0.35),
            'n_inquiries_min': 2,
            'segments':        ['Core','Enterprise'],
        },
        'exclude': {},
    },
}


def _build_user_features() -> 'pd.DataFrame':
    """
    Build a per-user feature matrix from buyers + hist_inquiries.
    Used for propensity scoring and matching.
    """
    user_history = db.execute("""
        SELECT
            buyer_id,
            COUNT(*)                                          AS n_inquiries,
            AVG(CAST(converted_to_order AS DOUBLE))          AS personal_ior,
            AVG(CASE WHEN converted_to_order THEN order_value END) AS avg_order_value,
            MAX(created_at)                                   AS last_inquiry_date,
            MIN(created_at)                                   AS first_inquiry_date,
            SUM(CAST(converted_to_order AS INTEGER))          AS total_orders
        FROM hist_inquiries
        GROUP BY buyer_id
    """).df()

    today_dt = pd.Timestamp(TODAY)
    user_history['days_since_last']  = (today_dt - pd.to_datetime(user_history['last_inquiry_date'])).dt.days
    user_history['days_since_first'] = (today_dt - pd.to_datetime(user_history['first_inquiry_date'])).dt.days
    user_history['personal_ior']     = user_history['personal_ior'].fillna(0)
    user_history['avg_order_value']  = user_history['avg_order_value'].fillna(0)

    # Merge with buyer profiles
    features = df_buyers.merge(user_history, on='buyer_id', how='left')
    features['n_inquiries']     = features['n_inquiries'].fillna(0)
    features['personal_ior']    = features['personal_ior'].fillna(0)
    features['total_orders']    = features['total_orders'].fillna(0)
    features['days_since_last'] = features['days_since_last'].fillna(999)
    features['tenure_days']     = (today_dt - pd.to_datetime(features['joined_at'])).dt.days.fillna(0)

    # Normalised features for propensity model
    for col in ['n_inquiries','personal_ior','lifetime_gmv','tenure_days']:
        mn, mx = features[col].min(), features[col].max()
        features[f'{col}_norm'] = (features[col] - mn) / (mx - mn + 1e-8)

    features['is_web']   = (features['primary_platform'] == 'web').astype(int)
    features['is_us']    = (features['country'] == 'US').astype(int)
    features['has_bill'] = features['has_billing_profile'].astype(int)
    features['seg_num']  = pd.Categorical(features['account_segment'],
                                          categories=SEGMENTS).codes

    return features


def _score_propensity(features: 'pd.DataFrame', category: str,
                      hypothesis: str, target_audience: str, llm) -> 'pd.Series':
    """
    Compute a propensity score [0, 1] for each user reflecting how likely they
    are to show a measurable response to this feature.

    Score = weighted combination of:
      - Behavioral fit: does the user's IOR/activity match the feature's target range?
      - Segment fit: are they in the target audience segments?
      - Variance contribution: do they have enough variance to detect the MDE?
      - Recency: are they currently active?
    """
    rules    = PROPENSITY_RULES.get(category, PROPENSITY_RULES['engagement'])
    high     = rules.get('high_propensity', {})
    score    = pd.Series(0.5, index=features.index)   # start neutral

    # Behavioral fit
    if 'ior_range' in high:
        lo, hi = high['ior_range']
        in_range = (features['personal_ior'] >= lo) & (features['personal_ior'] <= hi)
        score += np.where(in_range, 0.25, -0.10)

    if 'n_inquiries_min' in high:
        active = features['n_inquiries'] >= high['n_inquiries_min']
        score += np.where(active, 0.15, -0.05)

    if 'orders_range' in high:
        lo, hi = high['orders_range']
        in_range = (features['total_orders'] >= lo) & (features['total_orders'] <= hi)
        score += np.where(in_range, 0.20, -0.05)

    if 'recency_days_max' in high:
        recent = features['days_since_last'] <= high['recency_days_max']
        score += np.where(recent, 0.15, -0.10)

    if 'recency_days_range' in high:
        lo, hi = high['recency_days_range']
        in_range = (features['days_since_last'] >= lo) & (features['days_since_last'] <= hi)
        score += np.where(in_range, 0.20, -0.05)

    # Segment fit
    if 'segments' in high:
        in_seg = features['account_segment'].isin(high['segments'])
        score += np.where(in_seg, 0.20, 0.0)

    # Exclusion rules
    excl = rules.get('exclude', {})
    if 'ior_range' in excl:
        lo, hi = excl['ior_range']
        exclude_mask = (features['personal_ior'] >= lo) & (features['personal_ior'] <= hi)
        score[exclude_mask] = -1.0   # force exclusion

    if 'n_inquiries_max' in excl:
        exclude_mask = features['n_inquiries'] <= excl['n_inquiries_max']
        score[exclude_mask] = score[exclude_mask] - 0.30

    # Variance contribution: users near the MDE boundary contribute most
    # IOR near 0.0 or 1.0 has low variance; near 0.5 has highest variance
    variance_contribution = 4 * features['personal_ior'] * (1 - features['personal_ior'])
    score += variance_contribution * 0.10

    return np.clip(score, 0.0, 1.0)


def run_audience_selection(llm):
    print('\n' + '╔' + '═'*70 + '╗')
    print('║' + '  🎯  AUDIENCE SELECTION — Module 5'.ljust(70) + '║')
    print('║' + '  Who goes into control and treatment?'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    print("""
  Two modes:
  [A] Manual   — paste or enter a list of user IDs for each group
  [B] Auto     — model selects users based on feature hypothesis and
                 propensity scoring; forms matched, balanced groups
""")
    while True:
        mode = input('  ❓ Choose mode [A/B]: ').strip().upper()
        if mode in ('A','B'): break
        print('     ⚠️  Enter A or B')

    # ── Get experiment context ─────────────────────────────────────────────────
    print('\n  ── Experiment Context ──')
    exp_name   = input('  ❓ Experiment name (used to tag output): ').strip() or 'new_experiment'
    desc       = input('  ❓ Feature description: ').strip() or 'checkout funnel change'
    hypothesis = input('  ❓ Hypothesis: ').strip() or 'will improve IOR for Core buyers'
    target_aud = input('  ❓ Target audience: ').strip() or 'active buyers'
    n_variants = int(input('  ❓ Number of groups (2 = A/B, 3 = A/B/C): ').strip() or '2')

    # ── Classify feature category ──────────────────────────────────────────────
    print('\n  🔍 Classifying feature...')
    category = classify_feature(desc, llm)
    print(f'  → Category: {FUNNEL_TAXONOMY[category]["label"]}')

    # ── Mode A: Manual ─────────────────────────────────────────────────────────
    if mode == 'A':
        print('\n  Manual mode: enter user IDs for each group.')
        print('  Format: comma-separated list of buyer_ids (e.g. BYR00001,BYR00042,...)')
        print('  Or paste a file path to a .txt file with one ID per line.')
        print()

        groups = {}
        group_names = ['control'] + [f'treatment_{i}' if n_variants > 2 else 'treatment'
                                      for i in range(1, n_variants)]
        for g in group_names:
            raw = input(f'  ❓ User IDs for [{g}]: ').strip()
            if raw.endswith('.txt'):
                try:
                    ids = [l.strip() for l in open(raw).readlines() if l.strip()]
                except: ids = []
            else:
                ids = [x.strip() for x in raw.split(',') if x.strip()]
            groups[g] = ids
            print(f'     {len(ids):,} users assigned to {g}')

        # Build assignment DataFrame
        rows = []
        for g, ids in groups.items():
            for uid in ids:
                rows.append({'buyer_id': uid, 'group': g, 'experiment_name': exp_name,
                             'selection_mode': 'manual', 'propensity_score': None})
        assignments = pd.DataFrame(rows)

    # ── Mode B: Auto (propensity-based) ───────────────────────────────────────
    else:
        print('\n  Auto mode: computing propensity scores...')

        # Target sample size from power calc
        baselines = pull_baselines(category)
        ior       = baselines.get('ior', 0.18)
        mde_abs   = ior * 0.10
        ss        = compute_sample_size(ior, mde_abs, 0.05, 0.80, n_variants)
        n_per_group = ss['n_per_variant']
        n_needed    = n_per_group * n_variants
        print(f'  Target: {n_per_group:,} per group ({n_needed:,} total) to detect {mde_abs*100:.3f}pp MDE')

        # Build user features
        print('  Building user feature matrix...')
        features = _build_user_features()
        print(f'  {len(features):,} users in feature matrix')

        # Score propensity
        print('  Scoring response propensity...')
        features['propensity_score'] = _score_propensity(features, category, hypothesis, target_aud, llm)

        # Show propensity distribution
        eligible = features[features['propensity_score'] > 0].copy()
        eligible = eligible.sort_values('propensity_score', ascending=False)
        print(f'\n  Propensity score distribution ({len(eligible):,} eligible users):')
        for pct_label, lo, hi in [('High (>0.7)', 0.70, 1.01),
                                   ('Medium (0.4-0.7)', 0.40, 0.70),
                                   ('Low (<0.4)', 0.0, 0.40)]:
            n = ((eligible['propensity_score'] >= lo) & (eligible['propensity_score'] < hi)).sum()
            pct = n / len(eligible) * 100
            bar = '█' * int(pct / 3)
            print(f'    {pct_label:<18} {n:>5,}  ({pct:.0f}%)  {bar}')

        # Check if we have enough high-propensity users
        high_prop = eligible[eligible['propensity_score'] >= 0.60]
        if len(high_prop) < n_needed:
            print(f'\n  ⚠️  Only {len(high_prop):,} high-propensity users available, need {n_needed:,}.')
            lower = input(f'  ❓ Use propensity ≥ 0.40 instead? [Y/n]: ').strip().lower()
            if lower != 'n':
                high_prop = eligible[eligible['propensity_score'] >= 0.40]
                print(f'  Using {len(high_prop):,} users with score ≥ 0.40')

        if len(high_prop) < n_needed:
            print(f'  ⚠️  Still short — using top {min(n_needed, len(eligible)):,} users by propensity score.')
            high_prop = eligible.head(min(n_needed, len(eligible)))

        # Select pool of top-propensity users
        selected = high_prop.head(n_needed).copy()

        # ── Stratified assignment: ensure balanced segment distribution ───────
        selected = selected.sort_values(['account_segment', 'propensity_score'], ascending=[True, False])
        group_names  = ['control'] + [f'treatment_{i}' if n_variants > 2 else 'treatment'
                                       for i in range(1, n_variants)]
        selected['group'] = [group_names[i % n_variants] for i in range(len(selected))]
        selected['experiment_name'] = exp_name
        selected['selection_mode']  = 'auto_propensity'

        assignments = selected[['buyer_id','group','experiment_name',
                                 'selection_mode','propensity_score',
                                 'account_segment','primary_platform',
                                 'country','personal_ior','n_inquiries']].copy()

    # ── Validate group composition ─────────────────────────────────────────────
    print('\n  ── Group Composition Report ──')
    print(f'\n  {"Group":<20} {"N":>7}  {"% of total":>12}')
    print('  ' + '─'*44)
    for g, grp in assignments.groupby('group'):
        pct = len(grp) / len(assignments) * 100
        print(f'  {g:<20} {len(grp):>7,}  ({pct:.1f}%)')

    # Segment breakdown per group
    if 'account_segment' in assignments.columns:
        print(f'\n  Segment breakdown by group:')
        seg_cross = assignments.groupby(['group','account_segment']).size().unstack(fill_value=0)
        print(seg_cross.to_string())

    # Check balance
    group_sizes = assignments['group'].value_counts()
    if len(group_sizes) > 1:
        balance_ratio = group_sizes.min() / group_sizes.max()
        if balance_ratio < 0.80:
            print(f'\n  ⚠️  Group imbalance detected (ratio={balance_ratio:.2f}). Consider re-balancing.')
        else:
            print(f'\n  ✅ Groups are balanced (ratio={balance_ratio:.2f})')

    # Expected power with this cohort
    if mode == 'B' and 'personal_ior' in assignments.columns:
        cohort_ior = assignments[assignments['group']=='control']['personal_ior'].mean()
        cohort_mde = cohort_ior * 0.10
        n_ctrl     = (assignments['group']=='control').sum()
        n_trt      = (assignments['group'] != 'control').sum()
        expected_ss = compute_sample_size(cohort_ior, cohort_mde, 0.05, 0.80, n_variants)
        print(f'\n  Expected power analysis for this cohort:')
        print(f'    Cohort baseline IOR    : {cohort_ior*100:.3f}%')
        print(f'    Target MDE (10% rel)   : {cohort_mde*100:.3f}pp')
        print(f'    Required per group     : {expected_ss["n_per_variant"]:,}')
        print(f'    Assigned to control    : {n_ctrl:,}')
        if n_ctrl >= expected_ss['n_per_variant']:
            print(f'    ✅ Cohort is sufficient to detect the MDE at 80% power')
        else:
            shortfall = expected_ss['n_per_variant'] - n_ctrl
            print(f'    ⚠️  {shortfall:,} more users needed in each group to reach 80% power')

    # ── Covariate balance check ───────────────────────────────────────────────
    print()
    print('  ── [Auto] Running covariate balance tests ──')
    print('     Verifying treatment and control groups are statistically equivalent')
    print('     on all observable dimensions before the experiment launches...')
    print()

    _features_for_balance = None
    try:
        _features_for_balance = _build_user_features()
        assignments = assignments.merge(
            _features_for_balance[['buyer_id','account_segment','lifetime_orders',
                                    'n_inquiries','personal_ior','avg_order_value',
                                    'days_since_last']],
            on='buyer_id', how='left', suffixes=('','_feat')
        )
    except Exception as _e:
        print(f'     ⚠️  Could not merge feature data for balance tests: {_e}')

    _balance_results = _run_balance_battery(assignments)
    _ctrl_n   = (assignments['group'] == 'control').sum()
    _trt_n    = (assignments['group'] != 'control').sum()
    _balanced = _print_balance_report(_balance_results, _ctrl_n, _trt_n)

    if not _balanced and mode == 'B':
        print()
        raw_rerand = input('  ❓ Re-randomise to improve balance? [Y/n]: ').strip().lower()
        if raw_rerand != 'n':
            print()
            print(f'  ↩️  Re-randomising (up to {BALANCE_MAX_ITER} attempts)...')
            _n_per_group = min(_ctrl_n, _trt_n)
            _n_groups    = assignments['group'].nunique()
            try:
                _features_for_balance = _features_for_balance if _features_for_balance is not None                     else _build_user_features()
                assignments, _balance_results, _balanced = _rerandomise_until_balanced(
                    _features_for_balance, _n_per_group, _n_groups, exp_name
                )
                _ctrl_n  = (assignments['group'] == 'control').sum()
                _trt_n   = (assignments['group'] != 'control').sum()
                print()
                _balanced = _print_balance_report(_balance_results, _ctrl_n, _trt_n)
            except Exception as _e:
                print(f'     ⚠️  Re-randomisation failed: {_e}')
    elif not _balanced and mode == 'A':
        print()
        print('  ℹ️  Manual assignment cannot be re-randomised automatically.')
        print('     Review the flagged covariates and adjust the user lists manually,')
        print('     or switch to Auto mode (B) for balanced group selection.')

    # Generate Love plot
    try:
        _love_path = _plot_love_plot(_balance_results, exp_name)
        if _love_path:
            print(f'  📊 Love plot saved → {_love_path}')
    except Exception as _le:
        print(f'  ⚠️  Love plot skipped: {_le}')

    assignments['balance_pass'] = _balanced
    _n_flags = sum(1 for r in _balance_results.values() if r.get('flag', False))
    print()
    if _balanced:
        print('  ✅ Groups are scientifically valid. Safe to launch experiment.')
    else:
        print(f'  ⚠️  {_n_flags} balance flag(s) remain. Proceed with caution.')
        print('     Results from this experiment may be confounded by the imbalanced covariates.')

    # ── Visualise ──────────────────────────────────────────────────────────────
    _plot_audience_selection(assignments, mode, category)

    # ── Save assignment file for engineering ───────────────────────────────────
    fname = f'audience_assignments_{exp_name}.csv'
    assignments.to_csv(fname, index=False)
    print(f'\n  📁 Assignments saved → {fname}')
    print('  Engineering team: use this file to configure your feature flag targeting.')
    print('  Column "group" = the experiment bucket each user_id should be assigned to.')

    # Register in DuckDB for use by later modules
    db.register('audience_assignments', assignments)
    print(f'\n  ✅ Registered in DuckDB as "audience_assignments" — available to all modules.')

    # ── LLM narrative ─────────────────────────────────────────────────────────
    summary = {
        'experiment': exp_name,
        'feature': desc,
        'category': FUNNEL_TAXONOMY.get(category, {}).get('label', category),
        'mode': 'Manual' if mode == 'A' else 'Propensity-based auto-selection',
        'n_assigned': len(assignments),
        'groups': assignments['group'].value_counts().to_dict(),
        'segment_distribution': assignments['account_segment'].value_counts().to_dict()
            if 'account_segment' in assignments.columns else {},
    }
    narrative = llm.narrate(summary,
        f'Audience selection for experiment "{exp_name}". '
        f'Provide: (1) quality assessment of the selected groups, '
        f'(2) whether the composition is right for the hypothesis, '
        f'(3) any risks with this audience selection, '
        f'(4) recommendation on whether to proceed.')
    print('\n  🤖 ' + '─'*68)
    print(narrative)
    print('  ' + '─'*68)
    return assignments


def _plot_audience_selection(assignments: 'pd.DataFrame', mode: str, category: str):
    has_propensity = 'propensity_score' in assignments.columns and \
                     assignments['propensity_score'].notna().any()
    has_segment    = 'account_segment' in assignments.columns

    ncols = 3 if has_propensity else 2
    fig, axes = plt.subplots(1, ncols, figsize=(6*ncols, 5))
    if ncols == 1: axes = [axes]
    fig.patch.set_facecolor('#0f0f0f')
    fig.suptitle(f'🎯 Audience Selection — {mode} Mode', fontsize=13,
                 color=COLORS['highlight'], fontweight='bold')

    group_colors = {'control': COLORS['control'], 'treatment': COLORS['treatment'],
                    'treatment_1': COLORS['treatment'], 'treatment_2': COLORS['accent']}

    # Chart 1: group size
    ax = axes[0]
    counts = assignments['group'].value_counts()
    colors_bar = [group_colors.get(g, COLORS['neutral']) for g in counts.index]
    bars = ax.bar(counts.index, counts.values, color=colors_bar, width=0.5)
    for bar, v in zip(bars, counts.values):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1,
                f'{v:,}', ha='center', fontsize=11, fontweight='bold', color='white')
    ax.set_title('Group Sizes', color=COLORS['highlight'])
    ax.set_ylabel('Number of users')

    # Chart 2: segment breakdown
    if has_segment:
        ax2 = axes[1]
        groups   = assignments['group'].unique()
        segments = SEGMENTS
        x = np.arange(len(segments))
        w = 0.8 / len(groups)
        for gi, g in enumerate(sorted(groups)):
            grp_counts = assignments[assignments['group']==g]['account_segment'].value_counts()
            vals = [grp_counts.get(s, 0) for s in segments]
            offset = (gi - len(groups)/2 + 0.5) * w
            ax2.bar(x + offset, vals, w, label=g,
                    color=group_colors.get(g, COLORS['neutral']), alpha=0.85)
        ax2.set_xticks(x); ax2.set_xticklabels(segments)
        ax2.set_title('Segment Distribution by Group', color=COLORS['highlight'])
        ax2.set_ylabel('Users'); ax2.legend(fontsize=8)

    # Chart 3: propensity score distribution (auto mode only)
    if has_propensity:
        ax3 = axes[-1]
        for g in sorted(assignments['group'].unique()):
            scores = assignments[assignments['group']==g]['propensity_score'].dropna()
            ax3.hist(scores, bins=20, alpha=0.65, label=g,
                     color=group_colors.get(g, COLORS['neutral']), density=True)
        ax3.set_xlabel('Propensity Score')
        ax3.set_ylabel('Density')
        ax3.set_title('Propensity Score Distribution by Group\n(should overlap — similar users)',
                      color=COLORS['highlight'])
        ax3.legend(fontsize=8)
        ax3.axvline(0.60, color=COLORS['highlight'], lw=1.5, linestyle='--',
                    label='High propensity threshold')

    plt.tight_layout()
    plt.savefig('audience_selection.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → audience_selection.png')


print('✅ Module 5: Audience Selection loaded')
print('   Modes: Manual (upload user IDs) | Auto (propensity-based selection)')


def run_power_calculator(llm, use_synthetic_baseline: bool = True):
    print('\n' + '═'*72)
    print('  ⚡  POWER CALCULATOR')
    print('═'*72)

    # ── Auto-pull baselines ────────────────────────────────────────────────────
    if use_synthetic_baseline:
        base = db.execute("""
            SELECT
                COUNT(*) / DATEDIFF('day', MIN(created_at), MAX(created_at)) AS daily_inq,
                AVG(CAST(converted_to_order AS DOUBLE))                      AS overall_ior
            FROM hist_inquiries
        """).df().iloc[0]
        auto_daily_traffic = round(base['daily_inq'], 0)
        auto_baseline_rate = round(base['overall_ior'], 4)

        print(f'\n  📊 Auto-detected from historical data:')
        print(f'     Daily inquiries  : {auto_daily_traffic:,.0f}')
        print(f'     Overall IOR      : {auto_baseline_rate*100:.2f}%')

    print()

    def prompt_float(question, default=None, min_val=None, max_val=None):
        while True:
            hint = f' [{default}]' if default is not None else ''
            raw  = input(f'  ❓ {question}{hint}: ').strip()
            if raw == '' and default is not None: return float(default)
            try:
                v = float(raw)
                if min_val is not None and v < min_val:
                    print(f'     ⚠️  Must be ≥ {min_val}'); continue
                if max_val is not None and v > max_val:
                    print(f'     ⚠️  Must be ≤ {max_val}'); continue
                return v
            except ValueError:
                print('     ⚠️  Please enter a number')

    def prompt_int(question, default=None, min_val=1):
        while True:
            hint = f' [{default}]' if default is not None else ''
            raw  = input(f'  ❓ {question}{hint}: ').strip()
            if raw == '' and default is not None: return int(default)
            try:
                v = int(raw)
                if v < min_val: print(f'     ⚠️  Must be ≥ {min_val}'); continue
                return v
            except ValueError:
                print('     ⚠️  Please enter a whole number')

    print('  Enter experiment parameters (press Enter for defaults):\n')

    baseline    = prompt_float('Baseline conversion/IOR rate (0–1)',
                               default=auto_baseline_rate if use_synthetic_baseline else None,
                               min_val=0.001, max_val=0.999)
    mde_pct     = prompt_float('MDE — minimum detectable effect (%, e.g. 10 = detect 10% relative lift)',
                               default=10.0, min_val=0.1)
    mde_abs     = baseline * mde_pct / 100
    print(f'                               → absolute MDE = {mde_abs*100:.3f}pp')

    alpha       = prompt_float('Significance level α (e.g. 0.05)',
                               default=0.05, min_val=0.001, max_val=0.30)
    power       = prompt_float('Statistical power 1−β (e.g. 0.80)',
                               default=0.80, min_val=0.50, max_val=0.99)
    n_variants  = prompt_int('Number of variants including control (e.g. 2 = A/B)',
                             default=2, min_val=2)
    daily_traffic = prompt_float('Daily eligible traffic entering the experiment',
                                 default=auto_daily_traffic if use_synthetic_baseline else None,
                                 min_val=1)
    traffic_share = prompt_float('Fraction of traffic in experiment (0–1)',
                                 default=1.0, min_val=0.01, max_val=1.0)

    # ── Compute ───────────────────────────────────────────────────────────────
    ss   = compute_sample_size(baseline, mde_abs, alpha, power, n_variants)
    dur  = compute_duration(ss['n_total'], daily_traffic, traffic_share)

    print('\n' + '─'*72)
    print('  📊  RESULTS')
    print('─'*72)
    print(f'  Baseline rate         : {baseline*100:.2f}%')
    print(f'  MDE                   : {mde_pct:.1f}% relative  = {mde_abs*100:.3f}pp absolute')
    print(f'  Effect size (Cohen h) : {ss["effect_size_h"]:.4f}')
    print(f'  α  (significance)     : {alpha:.3f}   Power: {power:.2f}')
    print(f'  Variants              : {n_variants}')
    print(f'  ─── Sample requirements ───')
    print(f'  Per variant           : {ss["n_per_variant"]:,}')
    print(f'  Total (all variants)  : {ss["n_total"]:,}')
    print(f'  ─── Duration ───')
    print(f'  Daily eligible traffic: {dur["daily_eligible"]:,.1f}')
    print(f'  Required duration     : {dur["days_required"]:,} days  ({dur["weeks_required"]} weeks)')
    print(f'  Estimated end date    : {dur["end_date"]}')
    print('─'*72)

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    mde_range   = np.linspace(0.005, 0.20, 50)   # 0.5% – 20% relative MDE
    power_range = [0.70, 0.80, 0.90]
    alpha_range = [0.01, 0.05, 0.10]

    fig = plt.figure(figsize=(18, 11))
    fig.patch.set_facecolor('#0f0f0f')
    gs  = GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

    sens_colors = ['#4e9af1','#f97316','#22c55e']

    # Plot 1: Sample size vs MDE for different powers
    ax1 = fig.add_subplot(gs[0, 0])
    for pw, col in zip(power_range, sens_colors):
        ns = [compute_sample_size(baseline, baseline*m, alpha, pw, n_variants)['n_per_variant']
              for m in mde_range]
        ax1.plot(mde_range*100, ns, color=col, linewidth=2, label=f'Power={pw:.0%}')
    ax1.axvline(mde_pct, color=COLORS['highlight'], linestyle='--', alpha=0.8, label=f'Your MDE={mde_pct:.0f}%')
    ax1.set_xlabel('MDE (% relative)'); ax1.set_ylabel('Sample size per variant')
    ax1.set_title('Sample Size vs MDE', color=COLORS['highlight'])
    ax1.legend(fontsize=8); ax1.set_yscale('log')
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f'{int(x):,}'))

    # Plot 2: Duration vs MDE for different powers
    ax2 = fig.add_subplot(gs[0, 1])
    for pw, col in zip(power_range, sens_colors):
        ds = [compute_duration(
                compute_sample_size(baseline, baseline*m, alpha, pw, n_variants)['n_total'],
                daily_traffic, traffic_share)['days_required']
              for m in mde_range]
        ax2.plot(mde_range*100, ds, color=col, linewidth=2, label=f'Power={pw:.0%}')
    ax2.axvline(mde_pct, color=COLORS['highlight'], linestyle='--', alpha=0.8)
    ax2.axhline(dur['days_required'], color=COLORS['highlight'], linestyle=':', alpha=0.6,
                label=f'Your result: {dur["days_required"]}d')
    ax2.set_xlabel('MDE (% relative)'); ax2.set_ylabel('Duration (days)')
    ax2.set_title('Duration vs MDE', color=COLORS['highlight'])
    ax2.legend(fontsize=8)

    # Plot 3: Sample size vs α for different MDEs
    ax3 = fig.add_subplot(gs[0, 2])
    alphas = np.linspace(0.01, 0.20, 40)
    mde_lines = [mde_pct*0.5, mde_pct, mde_pct*1.5]
    for m, col in zip(mde_lines, sens_colors):
        ns = [compute_sample_size(baseline, baseline*m/100, a, power, n_variants)['n_per_variant']
              for a in alphas]
        ax3.plot(alphas, ns, color=col, linewidth=2, label=f'MDE={m:.0f}%')
    ax3.axvline(alpha, color=COLORS['highlight'], linestyle='--', alpha=0.8, label=f'Your α={alpha}')
    ax3.set_xlabel('Significance level α'); ax3.set_ylabel('Sample size per variant')
    ax3.set_title('Sample Size vs α', color=COLORS['highlight'])
    ax3.legend(fontsize=8)

    # Plot 4: Heatmap — duration (days) by MDE × traffic share
    ax4 = fig.add_subplot(gs[1, :])
    mde_grid    = np.linspace(0.01, 0.25, 20)
    share_grid  = np.linspace(0.10, 1.0, 20)
    heat = np.zeros((len(share_grid), len(mde_grid)))
    for i, sh in enumerate(share_grid):
        for j, md in enumerate(mde_grid):
            ss_h = compute_sample_size(baseline, baseline*md, alpha, power, n_variants)
            dur_h = compute_duration(ss_h['n_total'], daily_traffic, sh)
            heat[i, j] = dur_h['days_required']

    im = ax4.imshow(heat, aspect='auto', origin='lower', cmap='RdYlGn_r',
                    extent=[mde_grid[0]*100, mde_grid[-1]*100, share_grid[0]*100, share_grid[-1]*100])
    plt.colorbar(im, ax=ax4, label='Days required')
    ax4.set_xlabel('MDE (% relative)'); ax4.set_ylabel('Traffic share (%)')
    ax4.set_title('Duration Heatmap: MDE × Traffic Share  (red=long, green=fast)',
                  color=COLORS['highlight'])
    ax4.scatter([mde_pct], [traffic_share*100], color=COLORS['highlight'],
                marker='*', s=300, zorder=5, label='Your config')
    ax4.legend()

    plt.suptitle('⚡  Power Calculator — Sensitivity Analysis', fontsize=15,
                 color=COLORS['highlight'], fontweight='bold', y=1.01)
    plt.savefig('power_calculator.png', dpi=150, bbox_inches='tight', facecolor='#0f0f0f')
    plt.show()
    print('  📁 Chart saved → power_calculator.png')

    # ── LLM Narrative ─────────────────────────────────────────────────────────
    print('\n  🤖 Generating experiment design summary...')
    narrative = llm.narrate(
        {'sample_size': ss, 'duration': dur},
        context=(
            f'A/B experiment power calculation. '
            f'Baseline IOR: {baseline*100:.2f}%, MDE: {mde_pct:.1f}% relative ({mde_abs*100:.3f}pp absolute). '
            f'Provide: (1) clear summary of what the numbers mean, '
            f'(2) business risk of running shorter/longer, '
            f'(3) specific recommendations for the experiment team.'
        )
    )
    print('\n' + '─'*72)
    print('  🤖  EXPERIMENT DESIGN SUMMARY')
    print('─'*72)
    print(narrative)
    print('─'*72)
    return ss, dur

print('✅ Power calculator module ready')


# ─────────────────────────────────────────────────────────────────────────────
# METRICS KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────────────────────

METRICS_KB = {
    'acquisition': {
        'primary_pool': [
            'Sign-up completion rate (% of users who start and finish sign-up)',
            'New registered users per day / week',
            'Sign-up-to-first-login rate',
        ],
        'secondary_pool': [
            'Sign-up method distribution (email vs social provider)',
            'Median time to complete sign-up (seconds)',
            'Sign-up page bounce rate',
            'Email verification completion rate (for email sign-ups)',
            'Day-7 retention of new sign-ups (did they return?)',
            'First inquiry within 30 days of sign-up (activation proxy)',
        ],
        'guardrail_pool': [
            'Existing user login success rate (must not break current auth)',
            'Account takeover / fraud incident rate',
            'Auth-related support ticket volume',
            'Password reset request rate',
        ],
        'tracking_event_types': [
            'Page load / view on sign-up or login page',
            'Sign-up method selected (which provider or email)',
            'Sign-up form submit attempt',
            'Sign-up success or failure + error code',
            'Email verification link clicked',
            'First login after sign-up',
        ],
    },
    'activation': {
        'primary_pool': [
            'Activation rate (% of sign-ups who reach first key action within N days)',
            'Time to first meaningful action (median days)',
            'Onboarding completion rate',
        ],
        'secondary_pool': [
            'Step-by-step onboarding funnel drop-off by step',
            'Feature discovery rate (% who interact with key features)',
            'Help / tooltip click rate during onboarding',
            'Onboarding skip rate',
            'Profile completeness score at end of onboarding',
        ],
        'guardrail_pool': [
            'Onboarding abandonment rate (must not increase vs baseline)',
            'Email unsubscribe rate from onboarding sequences',
            'Support tickets from new users',
        ],
        'tracking_event_types': [
            'Onboarding step started and completed (per step)',
            'Onboarding skipped or exited early',
            'First key action taken (first inquiry, first upload, etc.)',
            'Help content viewed during onboarding',
            'Profile field completed',
        ],
    },
    'conversion': {
        'primary_pool': [
            'Inquiry-to-order rate / IOR (% of quotes that become orders)',
            'Checkout completion rate (% who reach order confirmation)',
            'Cart / quote abandonment rate (inverse — should decrease)',
        ],
        'secondary_pool': [
            'Checkout funnel step-by-step drop-off rates',
            'Median time from quote acceptance to order placement',
            'Billing profile adoption rate',
            'Payment method distribution',
            'Order error / rejection rate',
            'Re-attempt rate after a failed checkout',
        ],
        'guardrail_pool': [
            'Average order value (must not decrease)',
            'Payment failure rate',
            'Order cancellation rate within 24 hours',
            'Checkout-related support tickets',
            'Revenue per day (no unintended revenue drop)',
        ],
        'tracking_event_types': [
            'Each checkout step entered and exited (with step name)',
            'Checkout abandoned (with last step reached)',
            'Payment method selected',
            'Billing profile created or reused',
            'Order placed successfully',
            'Order placement failed with error type',
            'Order confirmation page viewed',
        ],
    },
    'retention': {
        'primary_pool': [
            'Repeat order rate (% of customers who order again within 90 days)',
            'Time between first and second order (median days)',
            'Monthly active buyer rate',
        ],
        'secondary_pool': [
            'Reorder CTA click rate on the summary or confirmation page',
            'Orders per buyer per quarter',
            'Return visit rate within 30 days of last order',
            'Re-engagement email open and click rates',
            'NPS or CSAT score from post-order survey',
        ],
        'guardrail_pool': [
            'Order cancellation rate (must not increase)',
            'Churn rate (buyers with no activity for 90+ days)',
            'Support ticket rate post-order',
        ],
        'tracking_event_types': [
            'Order summary / confirmation page viewed',
            'Reorder CTA clicked',
            'Return visit to platform (session start) after order',
            'New quote / inquiry started after prior order',
            'Post-order survey submitted',
        ],
    },
    'engagement': {
        'primary_pool': [
            'Feature adoption rate (% of eligible users who interact with the feature)',
            'Click-through rate on the changed element',
            'Task completion rate (% who achieve the intended action)',
        ],
        'secondary_pool': [
            'Time spent on the affected page or flow',
            'Scroll depth on redesigned pages',
            'Secondary action rate (actions taken after the primary one)',
            'Return visits to the feature within 7 days',
            'User preference or feedback signal (thumbs up/down, rating)',
        ],
        'guardrail_pool': [
            'Overall page bounce rate (must not increase)',
            'Page load / response time (performance must not degrade)',
            'Accessibility complaints or error reports',
            'Downstream conversion rate (engagement must lead to orders)',
        ],
        'tracking_event_types': [
            'Feature / component viewed (impression)',
            'Feature / component interacted with (click, hover, expand)',
            'Task started and completed within the feature',
            'User dismissed or closed the feature',
            'Error or empty-state encountered',
        ],
    },
    'pricing': {
        'primary_pool': [
            'Inquiry-to-order rate / IOR (pricing should not hurt conversion)',
            'Average order value (AOV) — should increase if pricing change is designed to',
            'Revenue per inquiry (IOR x AOV combined signal)',
        ],
        'secondary_pool': [
            'Price-sensitivity signals (users requesting requotes after seeing price)',
            'Discount redemption rate',
            'Tier or plan upgrade rate',
            'Time from price display to order placement',
            'Quote comparison rate (did users compare multiple quotes more?)',
        ],
        'guardrail_pool': [
            'Customer satisfaction score (pricing changes can hurt perception)',
            'Complaint and dispute rate',
            'Churn rate in the 30 days post-exposure',
            'Refund or cancellation rate',
        ],
        'tracking_event_types': [
            'Price displayed to user (with price value and context)',
            'Price details expanded or inspected',
            'Quote accepted or rejected after price view',
            'Requote requested after price shown',
            'Pricing-related support contact initiated',
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS — normalise LLM output and build fallback content
# ─────────────────────────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Remove markdown symbols so plain-text card renderer gets clean input."""
    import re
    if not text:
        return ''
    # Remove code fences
    text = re.sub(r'```[^\n]*\n?', '', text)
    # Remove heading markers (## Header → Header)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
    # Collapse 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _normalise_section_output(raw: str) -> str:
    """Ensure each metric/tracking item is on its own line in Field: value format.

    Small LLMs tend to run Field: value items together on one line or use
    inline markdown. This normaliser moves each recognised field label to
    its own line so the PDF card renderer can format them correctly.
    """
    import re
    text = _strip_markdown(raw)

    FIELD_LABELS = [
        'Metric:', 'Definition:', 'Why primary:', 'Why secondary:',
        'Why guardrail:', 'Expected direction:', 'Expected magnitude:',
        'Risk:', 'Threshold:', 'Track:', 'When:', 'Properties:', 'Why needed:',
        'Event name:', 'Trigger:', 'Note:',
    ]

    for label in FIELD_LABELS:
        pattern = re.compile(r'(?<!\n)(' + re.escape(label) + r')', re.IGNORECASE)
        text = pattern.sub(r'\n\1', text)

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _build_primary_metrics_fallback(kb: dict, desc: str, maturity: str,
                                     preference: str) -> str:
    """Build a clean PRIMARY METRICS section directly from METRICS_KB.

    Used when the LLM call fails or returns unusable output.
    Picks 2-3 metrics from primary_pool and formats them as Field: value cards.
    """
    threshold_map = {
        'mvp':       '5-10% degradation tolerance',
        'iteration': '2-3% maximum degradation',
        'critical':  '0.5-1% hard stop threshold',
    }
    direction_map = {
        'primary_pool': 'Increase',
    }
    items = kb.get('primary_pool', [])[:3]
    lines = []
    for metric in items:
        name = metric.split('(')[0].strip().rstrip('/')
        lines.append(f'Metric: {name}')
        lines.append(f'Definition: {metric}')
        lines.append(f'Why primary: Directly measures the impact of this feature on the core funnel outcome.')
        lines.append(f'Expected direction: Increase')
        lines.append(f'Expected magnitude: +2-5% relative lift')
        lines.append('')
    return '\n'.join(lines).strip()


def _build_secondary_metrics_fallback(kb: dict, desc: str) -> str:
    """Build a clean SECONDARY METRICS section from METRICS_KB."""
    items = kb.get('secondary_pool', [])[:4]
    lines = []
    for metric in items:
        name = metric.split('(')[0].strip()
        lines.append(f'Metric: {name}')
        lines.append(f'Definition: {metric}')
        lines.append(f'Why secondary: Provides diagnostic signal to understand why the primary metric moved or did not move.')
        lines.append(f'Expected direction: Varies')
        lines.append(f'Expected magnitude: Monitor for meaningful change')
        lines.append('')
    return '\n'.join(lines).strip()


def _build_guardrail_fallback(kb: dict, maturity: str) -> str:
    """Build a clean GUARDRAIL METRICS section from METRICS_KB."""
    threshold_map = {
        'mvp':       '5-10%',
        'iteration': '2-3%',
        'critical':  '0.5-1%',
    }
    threshold = threshold_map.get(maturity, '3-5%')
    items = kb.get('guardrail_pool', [])
    lines = []
    for metric in items:
        name = metric.split('(')[0].strip().rstrip('—')
        lines.append(f'Metric: {name}')
        lines.append(f'Definition: {metric}')
        lines.append(f'Risk: If this metric degrades the feature is harming the user experience or business KPIs.')
        lines.append(f'Threshold: Must not degrade by more than {threshold} — halt experiment if breached.')
        lines.append(f'Expected direction: Neutral or better')
        lines.append('')
    return '\n'.join(lines).strip()


def _build_tracking_fallback(kb: dict, desc: str, instrumentation: str) -> str:
    """Build a clean DATA TRACKING REQUIREMENTS section from METRICS_KB."""
    depth_map = {
        'none':    kb.get('tracking_event_types', []),
        'partial': kb.get('tracking_event_types', [])[:4],
        'full':    kb.get('tracking_event_types', [])[:2],
    }
    events = depth_map.get(instrumentation, kb.get('tracking_event_types', []))
    lines = []
    for event in events:
        # Build a snake_case event name from the description
        import re
        raw_name = event.split('(')[0].split('/')[0].strip().lower()
        snake = re.sub(r'[^a-z0-9]+', '_', raw_name).strip('_')
        lines.append(f'Track: {snake}')
        lines.append(f'When: {event}')
        lines.append(f'Properties: user_id (string), timestamp (datetime), session_id (string), feature_variant (string)')
        lines.append(f'Why needed: Enables calculation of the primary and secondary metrics above.')
        lines.append('')
    return '\n'.join(lines).strip()


def _build_open_questions_fallback(desc: str, category: str) -> str:
    """Build an OPEN QUESTIONS & ASSUMPTIONS section."""
    return '\n'.join([
        f'1. Confirm the baseline conversion rate is stable across weekdays before launching — check for day-of-week variation in the past 30 days.',
        f'2. Verify that the proposed tracking event names do not collide with existing analytics events in the data warehouse.',
        f'3. Agree on the minimum detectable effect before the experiment launches — run the power calculator (Module 5) to confirm sample size and duration.',
        f'4. Confirm which user segments are in scope for this feature — does it apply to all buyers or a specific tier?',
        f'5. Clarify who owns the guardrail monitoring during the experiment — analytics, engineering, or product?',
    ])


# ─────────────────────────────────────────────────────────────────────────────
# PER-SECTION LLM CALL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_SYSTEM = (
    'You are a senior product analytics expert. '
    'Write in plain business English. '
    'No markdown symbols (no #, **, *, >, -), no code fences, no emojis. '
    'Use ONLY plain "Field: value" lines separated by blank lines. '
    'Do not repeat the section heading. '
    'Do not add a preamble or explanation outside the Field: value blocks.'
)

_CARD_FORMAT_REMINDER = (
    'FORMAT RULES (must follow exactly):\n'
    '- Every item starts on a new line with "Metric: <name>"\n'
    '- Each field (Definition, Why, Expected direction, Expected magnitude) '
    'is on its own line\n'
    '- Separate each item with ONE blank line\n'
    '- No bullet points, no markdown, no headers\n'
    '- Example of correct format:\n'
    'Metric: Checkout completion rate\n'
    'Definition: Percentage of users who complete all checkout steps.\n'
    'Why primary: Directly measures whether the simplified flow reduces drop-off.\n'
    'Expected direction: Increase\n'
    'Expected magnitude: +3-8% relative lift\n'
)


def _call_llm_for_section(llm, section_name: str, prompt: str,
                            fallback_fn, max_tokens: int = 450) -> str:
    """Call the LLM for one section. Returns normalised text or the fallback.

    Uses a higher max_new_tokens than the global AGENT_CONFIG to ensure
    each section gets adequate space. Falls back gracefully on any failure.
    """
    try:
        # Temporarily override max_new_tokens for this call
        original_max = llm.max_new_tokens
        original_kwargs = dict(llm.gen_kwargs)
        llm.max_new_tokens = max_tokens
        llm.gen_kwargs['max_new_tokens'] = max_tokens

        raw = llm.ask(prompt, system=_SECTION_SYSTEM)

        # Restore
        llm.max_new_tokens = original_max
        llm.gen_kwargs = original_kwargs

        if not raw or len(raw.strip()) < 30:
            print(f'     ⚠️  LLM returned too little for {section_name} — using structured fallback')
            return fallback_fn()

        normalised = _normalise_section_output(raw)

        # Sanity check: if the output has no "Field: value" lines at all,
        # the LLM ignored the format — use the fallback instead
        import re
        field_lines = re.findall(
            r'^(?:Metric|Definition|Why|Expected|Risk|Threshold|Track|When|Properties|Why needed):',
            normalised, re.MULTILINE | re.IGNORECASE
        )
        if len(field_lines) < 2:
            print(f'     ⚠️  LLM output for {section_name} lacks structured fields — using structured fallback')
            return fallback_fn()

        return normalised

    except Exception as e:
        print(f'     ⚠️  LLM call failed for {section_name} ({e}) — using structured fallback')
        # Restore on exception
        try:
            llm.max_new_tokens = original_max
            llm.gen_kwargs = original_kwargs
        except Exception:
            pass
        return fallback_fn()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION GENERATORS — one function per section
# ─────────────────────────────────────────────────────────────────────────────

def _gen_primary_metrics(llm, desc, category, kb, maturity, preference,
                          context_block) -> str:
    """Generate PRIMARY METRICS — 2-3 metrics with Definition/Why/Direction/Magnitude."""
    candidates = '\n'.join(f'- {m}' for m in kb['primary_pool'])
    preference_note = {
        'leading':  'Prefer early-signal leading indicators.',
        'balanced': 'Include one leading indicator and one lagging revenue outcome.',
        'lagging':  'Focus on revenue-tied lagging outcomes (conversion rate, AOV, GMV).',
    }.get(preference, '')

    prompt = (
        f'Feature: {desc}\n'
        f'Funnel stage: {category}\n'
        f'Maturity: {maturity}\n\n'
        f'Candidate primary metrics:\n{candidates}\n\n'
        f'{preference_note}\n\n'
        f'Choose 2-3 of the most relevant primary metrics for this feature. '
        f'For each, write:\n'
        f'Metric: <name>\n'
        f'Definition: <exact numerator / denominator in one sentence>\n'
        f'Why primary: <one sentence — what signal does it give for this feature>\n'
        f'Expected direction: Increase or Decrease\n'
        f'Expected magnitude: <realistic range, e.g. +2-5pp or +5-10% relative>\n\n'
        f'{_CARD_FORMAT_REMINDER}'
    )
    return _call_llm_for_section(
        llm, 'PRIMARY METRICS', prompt,
        fallback_fn=lambda: _build_primary_metrics_fallback(kb, desc, maturity, preference),
        max_tokens=480,
    )


def _gen_secondary_metrics(llm, desc, category, kb, context_block) -> str:
    """Generate SECONDARY METRICS — 3-4 supporting/diagnostic metrics."""
    candidates = '\n'.join(f'- {m}' for m in kb['secondary_pool'])
    prompt = (
        f'Feature: {desc}\n'
        f'Funnel stage: {category}\n\n'
        f'Candidate secondary metrics:\n{candidates}\n\n'
        f'Choose 3-4 of the most relevant secondary (diagnostic) metrics. '
        f'These help understand WHY the primary metric moved or did not move.\n'
        f'For each, write:\n'
        f'Metric: <name>\n'
        f'Definition: <exact measurement in one sentence>\n'
        f'Why secondary: <one sentence — what diagnostic signal does it provide>\n'
        f'Expected direction: Increase or Decrease or Neutral\n'
        f'Expected magnitude: <realistic expectation>\n\n'
        f'{_CARD_FORMAT_REMINDER}'
    )
    return _call_llm_for_section(
        llm, 'SECONDARY METRICS', prompt,
        fallback_fn=lambda: _build_secondary_metrics_fallback(kb, desc),
        max_tokens=480,
    )


def _gen_guardrail_metrics(llm, desc, category, kb, maturity,
                            context_block) -> str:
    """Generate GUARDRAIL METRICS — metrics that must not degrade."""
    threshold_map = {
        'mvp':       '5-10%  (MVP: tolerate some variance)',
        'iteration': '2-3%   (v2: tight guardrails)',
        'critical':  '0.5-1% (critical path: hard stop if breached)',
    }
    threshold_note = threshold_map.get(maturity, '3-5%')
    candidates = '\n'.join(f'- {m}' for m in kb['guardrail_pool'])

    prompt = (
        f'Feature: {desc}\n'
        f'Funnel stage: {category}\n'
        f'Maturity: {maturity} (threshold guideline: {threshold_note})\n\n'
        f'Candidate guardrail metrics:\n{candidates}\n\n'
        f'List ALL relevant guardrail metrics. '
        f'These are red lines — if any degrade beyond the threshold, the experiment must stop.\n'
        f'For each, write:\n'
        f'Metric: <name>\n'
        f'Definition: <exact measurement>\n'
        f'Risk: <one sentence — why degradation here is dangerous for the business>\n'
        f'Threshold: Must not degrade by more than {threshold_note.split(" ")[0]} — halt if breached.\n'
        f'Expected direction: Neutral (must not worsen)\n\n'
        f'{_CARD_FORMAT_REMINDER.replace("Why primary", "Risk").replace("Expected magnitude", "Threshold")}'
    )
    return _call_llm_for_section(
        llm, 'GUARDRAIL METRICS', prompt,
        fallback_fn=lambda: _build_guardrail_fallback(kb, maturity),
        max_tokens=480,
    )


def _gen_tracking_requirements(llm, desc, category, kb, instrumentation,
                                 context_block) -> str:
    """Generate DATA TRACKING REQUIREMENTS — concrete events with properties."""
    depth_map = {
        'none':    '6-10 concrete tracking events covering the full user path, not just the new feature.',
        'partial': '4-6 NEW events specific to this feature. For each, note if it extends an existing event.',
        'full':    '2-3 events maximum. Focus on metric definitions that tie to existing events.',
    }
    depth_note = depth_map.get(instrumentation, '4-6 events')
    event_types = '\n'.join(f'- {e}' for e in kb['tracking_event_types'])

    prompt = (
        f'Feature: {desc}\n'
        f'Funnel stage: {category}\n'
        f'Instrumentation: {instrumentation} ({depth_note})\n\n'
        f'Relevant tracking event types:\n{event_types}\n\n'
        f'Design the tracking events needed to measure the metrics above.\n'
        f'For each event, write:\n'
        f'Track: <snake_case_event_name>\n'
        f'When: <exact user action or system event that fires this>\n'
        f'Properties: <comma-separated list with data types — e.g. user_id (string), step_name (string), timestamp (datetime)>\n'
        f'Why needed: <which metric above this event enables>\n\n'
        f'FORMAT RULES:\n'
        f'- Event names must be in snake_case (e.g. checkout_step_completed)\n'
        f'- Properties must include user_id, timestamp, and feature_variant as standard\n'
        f'- No markdown, no bullet points, no headers\n'
        f'- Separate each event with ONE blank line\n'
        f'- Example:\n'
        f'Track: checkout_step_completed\n'
        f'When: User successfully completes a checkout step and advances to the next\n'
        f'Properties: user_id (string), step_name (string), step_index (integer), time_on_step_seconds (float), feature_variant (string), timestamp (datetime)\n'
        f'Why needed: Enables calculation of checkout completion rate and per-step drop-off rates.\n'
    )
    return _call_llm_for_section(
        llm, 'DATA TRACKING REQUIREMENTS', prompt,
        fallback_fn=lambda: _build_tracking_fallback(kb, desc, instrumentation),
        max_tokens=520,
    )


def _gen_open_questions(llm, desc, category, context_block) -> str:
    """Generate OPEN QUESTIONS & ASSUMPTIONS — 4-5 items to resolve before launch."""
    prompt = (
        f'Feature: {desc}\n'
        f'Funnel stage: {category}\n\n'
        f'List 4-5 specific open questions or assumptions the analytics and product team '
        f'must resolve BEFORE this experiment launches.\n'
        f'Focus on: baseline stability, event name collisions, segment scope, '
        f'holdout group design, power calculation inputs, data quality, and attribution.\n\n'
        f'Write each question on its own line starting with a number and a period.\n'
        f'Make each question concrete and specific to this feature — not generic.\n'
        f'Example format:\n'
        f'1. Confirm that the baseline checkout completion rate is stable across weekdays — check for day-of-week variation in the past 30 days before setting the MDE.\n'
        f'2. Verify the proposed event names (checkout_step_completed, checkout_abandoned) do not collide with existing analytics events.\n'
    )
    return _call_llm_for_section(
        llm, 'OPEN QUESTIONS & ASSUMPTIONS', prompt,
        fallback_fn=lambda: _build_open_questions_fallback(desc, category),
        max_tokens=380,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN MODULE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────


def _gen_metrics_bundle(llm, desc, category, kb, maturity, preference, instrumentation, context_block) -> dict:
    """
    One LLM call generates primary + secondary + guardrail metrics together.
    Falls back section-by-section from METRICS_KB if output is malformed.
    """
    threshold_map = {'mvp': '5-10%', 'iteration': '2-3%', 'critical': '0.5-1%'}
    threshold = threshold_map.get(maturity, '3-5%')
    preference_note = {
        'leading':  'Prefer early-signal leading indicators for primary.',
        'balanced': 'Include one leading and one lagging metric for primary.',
        'lagging':  'Focus on revenue-tied lagging outcomes for primary.',
    }.get(preference, '')

    primary_cands   = '\n'.join(f'- {m}' for m in kb['primary_pool'])
    secondary_cands = '\n'.join(f'- {m}' for m in kb['secondary_pool'])
    guardrail_cands = '\n'.join(f'- {m}' for m in kb['guardrail_pool'])

    prompt = (
        f'Feature: {desc}\nFunnel stage: {category}\n'
        f'Maturity: {maturity} — guardrail threshold: {threshold}\n'
        f'{preference_note}\n\n'
        f'Generate THREE metric sections. Each section header in UPPERCASE on its own line.\n'
        f'Use only "Field: value" lines — no markdown, no bullets, no preamble.\n\n'
        f'PRIMARY METRICS\n'
        f'Choose 2-3 from: {primary_cands}\n'
        f'For each: Metric: / Definition: / Why primary: / Expected direction: / Expected magnitude:\n\n'
        f'SECONDARY METRICS\n'
        f'Choose 3-4 from: {secondary_cands}\n'
        f'For each: Metric: / Definition: / Why secondary: / Expected direction:\n\n'
        f'GUARDRAIL METRICS\n'
        f'Choose all relevant from: {guardrail_cands}\n'
        f'For each: Metric: / Definition: / Risk: / Threshold: Must not degrade by more than {threshold}.\n'
        f'\nStart immediately with PRIMARY METRICS — no other text before it.\n'
        + _CARD_FORMAT_REMINDER
    )

    try:
        original_max = llm.max_new_tokens
        original_kwargs = dict(llm.gen_kwargs)
        llm.max_new_tokens = 900
        llm.gen_kwargs['max_new_tokens'] = 900
        raw = llm.ask(prompt, system=_SECTION_SYSTEM)
        llm.max_new_tokens = original_max
        llm.gen_kwargs = original_kwargs
    except Exception as e:
        logger.warning('_gen_metrics_bundle LLM call failed: %s', e)
        raw = ''

    raw = _normalise_section_output(raw)
    sections = parse_sections_from_llm_output(
        raw, ['PRIMARY METRICS', 'SECONDARY METRICS', 'GUARDRAIL METRICS'])

    result = {}
    fallback_map = {
        'PRIMARY METRICS':   lambda: _build_primary_metrics_fallback(kb, desc, maturity, preference),
        'SECONDARY METRICS': lambda: _build_secondary_metrics_fallback(kb, desc),
        'GUARDRAIL METRICS': lambda: _build_guardrail_fallback(kb, maturity),
    }
    for sec_name, fb_fn in fallback_map.items():
        content = sections.get(sec_name, '').strip()
        field_hits = len(re.findall(
            r'^(?:Metric|Definition|Why|Expected|Risk|Threshold):',
            content, re.MULTILINE | re.IGNORECASE
        ))
        if not content or field_hits < 2:
            print(f'     ⚠️  Structured fallback applied for {sec_name}')
            result[sec_name] = fb_fn()
        else:
            result[sec_name] = content
    return result


def _gen_tracking_and_questions_bundle(llm, desc, category, kb, instrumentation, context_block) -> dict:
    """
    One LLM call generates tracking events + open questions together.
    Falls back section-by-section from METRICS_KB if output is malformed.
    """
    depth_map = {
        'none':    '6-8 concrete tracking events covering the full user path.',
        'partial': '4-5 NEW events specific to this feature.',
        'full':    '2-3 events that tie to existing event tracking.',
    }
    depth_note  = depth_map.get(instrumentation, '4-5 events')
    event_types = '\n'.join(f'- {e}' for e in kb['tracking_event_types'])

    prompt = (
        f'Feature: {desc}\nFunnel stage: {category}\nInstrumentation: {instrumentation} ({depth_note})\n\n'
        f'Relevant event types:\n{event_types}\n\n'
        f'Generate TWO sections. Each header in UPPERCASE on its own line.\n'
        f'No markdown, no bullets in the tracking section, no preamble.\n\n'
        f'DATA TRACKING REQUIREMENTS\n'
        f'For each event: Track: <snake_case_name> / When: <exact trigger> / '
        f'Properties: user_id (string), timestamp (datetime), feature_variant (string), <specific props> / '
        f'Why needed: <which metric this enables>\n'
        f'Separate events with ONE blank line.\n\n'
        f'OPEN QUESTIONS & ASSUMPTIONS\n'
        f'List 4-5 numbered questions to resolve before launch. '
        f'Be specific to this feature — not generic.\n'
        f'Cover: baseline stability, event name collisions, segment scope, power calc inputs.\n'
        f'\nStart immediately with DATA TRACKING REQUIREMENTS — no other text before it.\n'
    )

    try:
        original_max = llm.max_new_tokens
        original_kwargs = dict(llm.gen_kwargs)
        llm.max_new_tokens = 700
        llm.gen_kwargs['max_new_tokens'] = 700
        raw = llm.ask(prompt, system=_SECTION_SYSTEM)
        llm.max_new_tokens = original_max
        llm.gen_kwargs = original_kwargs
    except Exception as e:
        logger.warning('_gen_tracking_and_questions_bundle LLM call failed: %s', e)
        raw = ''

    raw = _normalise_section_output(raw)
    sections = parse_sections_from_llm_output(
        raw, ['DATA TRACKING REQUIREMENTS', 'OPEN QUESTIONS & ASSUMPTIONS'])

    result = {}
    fallback_map = {
        'DATA TRACKING REQUIREMENTS': lambda: _build_tracking_fallback(kb, desc, instrumentation),
        'OPEN QUESTIONS & ASSUMPTIONS': lambda: _build_open_questions_fallback(desc, category),
    }
    for sec_name, fb_fn in fallback_map.items():
        content = sections.get(sec_name, '').strip()
        field_hits = len(re.findall(
            r'^(?:Track|When|Properties|Why needed|\d+\.)',
            content, re.MULTILINE | re.IGNORECASE
        ))
        if not content or field_hits < 2:
            print(f'     ⚠️  Structured fallback applied for {sec_name}')
            result[sec_name] = fb_fn()
        else:
            result[sec_name] = content
    return result


# ─────────────────────────────────────────────────────────────────────────────
# EFFICIENCY IMPROVEMENT 6 — Infer maturity / instrumentation / preference
# ─────────────────────────────────────────────────────────────────────────────

def _infer_kpi_config(desc: str, llm) -> tuple:
    """
    Infer maturity, instrumentation, and preference from the feature description.
    Returns (maturity, instrumentation, preference, uncertain_keys).
    """
    prompt = (
        f'Feature: "{desc}"\n\n'
        'Infer the KPI planning configuration. Return ONLY valid JSON — no other text:\n'
        '{\n'
        '  "maturity": "mvp" | "iteration" | "critical",\n'
        '  "instrumentation": "none" | "partial" | "full",\n'
        '  "preference": "leading" | "balanced" | "lagging",\n'
        '  "uncertain": ["maturity"]\n'
        '}\n'
        'maturity=mvp if first launch. instrumentation=full if v2/existing. '
        'preference=lagging if revenue/conversion explicitly mentioned. '
        'uncertain lists only keys that are genuinely ambiguous (1-2 max).'
    )
    try:
        raw = llm.ask(prompt)
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            d = json.loads(m.group())
            maturity        = d.get('maturity',        'iteration')
            instrumentation = d.get('instrumentation', 'partial')
            preference      = d.get('preference',      'balanced')
            uncertain       = d.get('uncertain',       [])
            valid_m  = {'mvp', 'iteration', 'critical'}
            valid_i  = {'none', 'partial', 'full'}
            valid_p  = {'leading', 'balanced', 'lagging'}
            if maturity not in valid_m: maturity = 'iteration'
            if instrumentation not in valid_i: instrumentation = 'partial'
            if preference not in valid_p: preference = 'balanced'
            return maturity, instrumentation, preference, uncertain
    except Exception as e:
        logger.warning('_infer_kpi_config failed: %s', e)
    return 'iteration', 'partial', 'balanced', ['maturity', 'instrumentation', 'preference']


def run_metrics_and_tracking(llm):
    """
    KPI + Data Tracking Planner. Produces a designed PDF with:
      - Primary, secondary, guardrail metrics grounded in the real baselines
      - Concrete tracking events (names, triggers, properties)
      - Guardrail thresholds calibrated to feature maturity

    Architecture change vs. original:
      Each section is generated by a SEPARATE focused LLM call (not one
      monolithic call for all 5 sections). This guarantees every section
      has adequate token budget. If an LLM call fails or returns
      unstructured output, a structured fallback is built automatically
      from METRICS_KB — so no section is ever left empty.
    """
    print('\n' + 'x'*72)
    print('  KPI METRICS & DATA TRACKING PLANNER')
    print('  For Product Managers, Analytics, and Engineering')
    print('x'*72)

    # ── Step 1: Feature description ───────────────────────────────────────────
    print('\n  Describe the feature or initiative you are planning.')
    print('  The more specific you are, the more tailored the output will be.')
    print()
    while True:
        desc = input('  ? Feature description: ').strip()
        if len(desc) >= 10:
            break
        print('     Please describe the feature in a bit more detail')



    # ── Steps 2-4: Infer maturity / instrumentation / preference (Improvement 6)
    # One LLM call replaces 3 serial input() prompts.
    print('\n  Inferring configuration from feature description...')
    maturity, instrumentation, preference, uncertain_keys = _infer_kpi_config(desc, llm)

    CONFIG_OPTIONS = {
        'maturity':        (['mvp', 'iteration', 'critical'],
                            {'mvp': 'MVP / first launch',
                             'iteration': 'v2 iteration',
                             'critical': 'Critical revenue path'}),
        'instrumentation': (['none', 'partial', 'full'],
                            {'none': 'Greenfield',
                             'partial': 'Some events exist',
                             'full': 'Fully instrumented'}),
        'preference':      (['leading', 'balanced', 'lagging'],
                            {'leading': 'Leading indicators',
                             'balanced': 'Balanced',
                             'lagging': 'Lagging / revenue outcomes'}),
    }
    inferred = {
        'maturity': maturity,
        'instrumentation': instrumentation,
        'preference': preference,
    }
    print(f'  Inferred: maturity={maturity}, instrumentation={instrumentation}, preference={preference}')

    if uncertain_keys:
        print(f'\n  Confirming {len(uncertain_keys)} ambiguous value(s):\n')
        for key in uncertain_keys:
            if key not in CONFIG_OPTIONS:
                continue
            options, labels = CONFIG_OPTIONS[key]
            opts_str = '  /  '.join(
                f'[{i+1}] {labels[o]}' for i, o in enumerate(options))
            default_idx = options.index(inferred[key]) + 1
            raw = input(
                f'  ❓ {key.title()}: {opts_str}  (default {default_idx}): '
            ).strip() or str(default_idx)
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                inferred[key] = options[int(raw)-1]

    maturity        = inferred['maturity']
    instrumentation = inferred['instrumentation']
    preference      = inferred['preference']

    maturity_label = {
        'mvp':       'MVP / first launch — higher variance tolerance',
        'iteration': 'v2 iteration — tighter guardrails',
        'critical':  'Critical revenue path — tightest guardrails',
    }[maturity]
    instr_label = {
        'none':    'Greenfield — design all tracking events from scratch',
        'partial': 'Partial — extend existing events with feature-specific properties',
        'full':    'Full — metric definitions only, minimal new tracking',
    }[instrumentation]

    # ── Step 5: Optional PRD context ──────────────────────────────────────────
    print('\n  Optional: paste additional context (problem statement, goals,')
    print('  target users). Press Enter twice when done, or just Enter to skip.')
    print()
    context_lines = []
    while True:
        line = input('  ').strip()
        if line == '' and (not context_lines or context_lines[-1] == ''):
            break
        context_lines.append(line)
    prd_context = ' '.join(l for l in context_lines if l).strip()

    # ── Step 6: Classify feature ──────────────────────────────────────────────
    print('\n  Classifying feature...')
    category = classify_feature(desc, llm)

    if category == 'other':
        print('  Feature classified as uncategorised — switching to guided mode.')
        custom_answers, plan = handle_other_category(desc, llm)
        return {'category': 'other', 'custom_plan': plan,
                'output_file': custom_answers.get('output_file')}

    taxonomy = FUNNEL_TAXONOMY[category]
    kb = METRICS_KB[category]

    print(f'  -> Funnel position : {taxonomy["label"]}')
    print(f'  -> Maturity        : {maturity_label}')
    print(f'  -> Instrumentation : {instr_label}')

    # ── Step 7: Template check ────────────────────────────────────────────────
    default_sections = [
        'PRIMARY METRICS',
        'SECONDARY METRICS',
        'GUARDRAIL METRICS',
        'DATA TRACKING REQUIREMENTS',
        'OPEN QUESTIONS & ASSUMPTIONS',
    ]
    user_sections, _ = ask_for_template('KPI & Tracking Plan', default_sections)
    sections_to_use = user_sections if user_sections else default_sections

    context_block = (
        f'Feature description: "{desc}"\n'
        f'Funnel position: {taxonomy["label"]}\n'
        f'Feature maturity: {maturity_label}\n'
        f'Instrumentation state: {instr_label}\n'
        f'Metric preference: {preference}'
        + (f'\nAdditional context: {prd_context}' if prd_context else '')
    )

    # ── Step 8: Generate all sections in 2 bundled LLM calls
    sections = {}
    section_set = set(sections_to_use)
    METRIC_SECTIONS  = {'PRIMARY METRICS', 'SECONDARY METRICS', 'GUARDRAIL METRICS'}
    TRACKING_SECTIONS = {'DATA TRACKING REQUIREMENTS', 'OPEN QUESTIONS & ASSUMPTIONS'}

    if METRIC_SECTIONS & section_set:
        print('\n  Generating measurement plan (2 bundled calls)...')
        print('  [1/2] Metrics (primary + secondary + guardrail)...', end=' ', flush=True)
        metric_sections = _gen_metrics_bundle(
            llm, desc, category, kb, maturity, preference, instrumentation, context_block)
        total_cards = sum(v.count('Metric:') for v in metric_sections.values())
        print(f'done  ({total_cards} metrics)')
        sections.update({k: v for k, v in metric_sections.items() if k in section_set})
    else:
        print('\n  Generating measurement plan (1 bundled call)...')

    if TRACKING_SECTIONS & section_set:
        print('  [2/2] Tracking events + open questions...', end=' ', flush=True)
        tracking_sections = _gen_tracking_and_questions_bundle(
            llm, desc, category, kb, instrumentation, context_block)
        n_events = tracking_sections.get('DATA TRACKING REQUIREMENTS', '').count('Track:')
        print(f'done  ({n_events} events)')
        sections.update({k: v for k, v in tracking_sections.items() if k in section_set})

    # ── Step 9: Display ───────────────────────────────────────────────────────
    _display_metrics_plan(desc, category, taxonomy, sections)

    # ── Step 10: Render PDF ───────────────────────────────────────────────────
    fname = 'metrics_tracking_plan.pdf'
    # Build ordered dict matching sections_to_use order
    from collections import OrderedDict
    sections_ordered = OrderedDict(
        (s, sections.get(s, '(No content generated for this section.)'))
        for s in sections_to_use
    )

    out_path = render_document_pdf(
        title='KPI & Data Tracking Plan',
        subtitle='Feature: ' + desc[:90],
        sections=sections_ordered,
        output_path=fname,
        metadata={
            'Feature':         desc[:120],
            'Funnel stage':    taxonomy['label'],
            'Maturity':        maturity_label,
            'Instrumentation': instr_label,
            'Preference':      preference,
        },
        accent_color=PDF_PALETTE['accent'],
    )
    print(f'\n  Measurement plan saved -> {out_path}')

    return {
        **sections,
        'category':      category,
        'maturity':      maturity,
        'instrumentation': instrumentation,
        'preference':    preference,
        'output_file':   out_path,
        'sections_used': sections_to_use,
    }


def _display_metrics_plan(desc, category, taxonomy, sections):
    SEP = '=' * 72
    print('\n' + SEP)
    print(f'  MEASUREMENT PLAN')
    print(f'  Feature  : {desc[:65]}')
    print(f'  Category : {taxonomy["label"]}')
    print(SEP)

    # Section key → (display title, subtitle)
    # Keys match what parse/generation functions produce (UPPERCASE SECTION NAMES)
    SECTION_META = [
        ('PRIMARY METRICS',
         'PRIMARY METRICS',
         'The north-star numbers. If these move as expected, the feature worked.'),
        ('SECONDARY METRICS',
         'SECONDARY METRICS',
         'Supporting signals. Help diagnose WHY primary moved or did not.'),
        ('GUARDRAIL METRICS',
         'GUARDRAIL / NO-HARM METRICS',
         'Red lines. The experiment halts if any of these degrade.'),
        ('DATA TRACKING REQUIREMENTS',
         'DATA TRACKING REQUIREMENTS',
         'Events engineering must instrument before the experiment launches.'),
        ('OPEN QUESTIONS & ASSUMPTIONS',
         'OPEN QUESTIONS & ASSUMPTIONS',
         'Items to resolve before launch.'),
    ]

    for sec_key, title, subtitle in SECTION_META:
        content = sections.get(sec_key, '').strip()
        if not content or content.startswith('(No content'):
            continue
        print(f'\n  {title}')
        print(f'  {subtitle}')
        print('  ' + '-' * 68)
        for line in content.split('\n'):
            stripped = line.strip()
            if not stripped:
                print()
                continue
            print(f'  {stripped}')
        print()
    print(SEP)


print('Module 6: KPI Metrics & Data Tracking Planner loaded')
print('  run_metrics_and_tracking(narrative_llm)')
print('  Each section generated by a focused LLM call + structured fallback')

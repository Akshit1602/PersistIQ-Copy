import pandas as pd
import numpy as np
import re
import json
import os
from continum.runtime.config import RUNTIME_DATA_DIR, ensure_runtime_data_dir

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 1 — SCHEMA DISCOVERY & MAPPING (Phase 0 — Foundation)
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_TABLES = {
    # Core transaction tables (required for basic analysis)
    'inquiries':    'Aggregated inquiry/quote/lead rows — primary unit of analysis for conversion rate',
    'quotes':       'Quote / inquiry / lead records — one row per quote / request submitted',
    'orders':       'Order / transaction / purchase records — one row per completed transaction',
    'users':        'User / buyer / customer records — one row per registered user',
    'accounts':     'Account / company / organisation records — one row per business account',
    'experiments':  'Experiment assignment records — one row per user-variant exposure',
    # Optional extended tables
    'traffic':      'Daily platform traffic — sessions, sign-ups, page views by day',
    'products':     'Product / SKU / listing catalogue — one row per product',
    'sessions':     'Session / clickstream records — one row per session or page view',
    'events':       'Raw event log — one row per user action / event',
    'returns':      'Return / refund / cancellation records — one row per return',
    'inventory':    'Inventory / stock records — one row per SKU / location combination',
}

CANONICAL_COLUMNS = {
    # Identity & time (always required)
    'inquiry_id':         'Unique inquiry / quote / lead / request identifier (string or int)',
    'buyer_id':           'Unique user / buyer / customer / member identifier (string or int)',
    'created_at':         'Timestamp the inquiry / event was created (datetime)',
    # Segmentation (highly recommended)
    'account_segment':    'Account or user segment classification (e.g. Core / Growth / Enterprise / SMB)',
    'platform':           'Platform of origin (e.g. web / mobile / desktop / app / api)',
    'category':           'Product, process, or service category (e.g. Electronics / Clothing / CNC)',
    'country':            'Buyer, shipping, or registration country (ISO code or full name)',
    # Conversion / outcome
    'converted_to_order': 'Boolean — did this inquiry/lead/cart become a completed order/purchase?',
    'order_value':        'Transaction value in the client currency (numeric, 0 when not converted)',
    # Experiment
    'variant':            'Experiment variant assignment (e.g. control / treatment / variant_a)',
    'experiment_name':    'Experiment identifier the user was exposed to',
    # Optional but commonly used
    'product_id':         'Product or SKU identifier (for product-level experiments)',
    'channel':            'Marketing or acquisition channel (e.g. organic / paid / email / referral)',
    'device_type':        'Device type (e.g. desktop / mobile / tablet)',
    'industry':           'Industry or vertical classification of the account',
}


def _profile_dataframe(df, table_name, sample_size=2000):
    """Compute per-column profile: nulls, cardinality, dtype, sample values."""
    n_rows = len(df)
    sample = df.sample(min(sample_size, n_rows), random_state=42) if n_rows else df
    profile = []
    for col in df.columns:
        s = sample[col]
        non_null = s.dropna()
        # Try to detect the value family
        family = 'unknown'
        if non_null.empty:
            family = 'all_null'
        elif s.dtype.kind in ('i', 'u'):
            family = 'integer'
        elif s.dtype.kind == 'f':
            family = 'float'
        elif s.dtype.kind == 'b':
            family = 'boolean'
        elif s.dtype.kind == 'M':
            family = 'datetime'
        elif s.dtype.kind == 'O' or str(s.dtype) == 'str':
            sample_strs = non_null.astype(str)
            if sample_strs.str.match(r'^\d{4}-\d{2}-\d{2}').any():
                family = 'date_string'
            elif sample_strs.str.match(r'^[a-zA-Z0-9_]{8,}$').any() and non_null.nunique() > 0.5 * len(non_null):
                family = 'identifier'
            elif non_null.nunique() <= 20:
                family = 'categorical'
            else:
                family = 'string'

        sample_vals = non_null.head(3).tolist()
        profile.append({
            'table':        table_name,
            'column':       col,
            'dtype':        str(s.dtype),
            'family':       family,
            'null_pct':     round(s.isna().mean() * 100, 2),
            'cardinality':  int(non_null.nunique()),
            'sample':       sample_vals,
        })
    return profile


def _build_mapping_prompt(profiles_by_table):
    """Compact representation of the catalog for the LLM."""
    catalog_lines = []
    for tbl, cols in profiles_by_table.items():
        catalog_lines.append(f'\nTABLE: {tbl}  ({len(cols)} columns)')
        for c in cols[:25]:    # cap to avoid prompt bloat
            sample_str = str(c['sample'])[:60]
            catalog_lines.append(
                f"  - {c['column']:<32} {c['family']:<14} null={c['null_pct']:>5.1f}%  "
                f"card={c['cardinality']:>6}  sample={sample_str}"
            )
        if len(cols) > 25:
            catalog_lines.append(f'  ... ({len(cols) - 25} more columns)')

    canonical_tables_text = '\n'.join(f'  - {k}: {v}' for k, v in CANONICAL_TABLES.items())
    canonical_cols_text   = '\n'.join(f'  - {k}: {v}' for k, v in CANONICAL_COLUMNS.items())

    prompt = f"""You are a data engineer mapping a client warehouse to a canonical experimentation schema.

CANONICAL TABLES needed by the platform:
{canonical_tables_text}

CANONICAL COLUMNS the platform expects (after mapping):
{canonical_cols_text}

CLIENT WAREHOUSE CATALOG (profiled):
{chr(10).join(catalog_lines)}

For each canonical table, pick the BEST matching client table from the catalog above.
For each canonical column, pick the BEST matching column from the chosen table.
If no good match exists, return null.

Return ONLY a JSON object in this exact shape, no other text:

{{
  "table_mapping": {{
    "quotes":      "<client_table_name_or_null>",
    "orders":      "<client_table_name_or_null>",
    "users":       "<client_table_name_or_null>",
    "accounts":    "<client_table_name_or_null>",
    "experiments": "<client_table_name_or_null>",
    "inquiries":   "<client_table_name_or_null>",
    "traffic":     "<client_table_name_or_null>"
  }},
  "column_mapping": {{
    "inquiry_id":         "<client_column_or_null>",
    "buyer_id":           "<client_column_or_null>",
    "account_segment":    "<client_column_or_null>",
    "platform":           "<client_column_or_null>",
    "category":           "<client_column_or_null>",
    "country":            "<client_column_or_null>",
    "created_at":         "<client_column_or_null>",
    "converted_to_order": "<client_column_or_null>",
    "order_value":        "<client_column_or_null>",
    "variant":            "<client_column_or_null>",
    "experiment_name":    "<client_column_or_null>"
  }},
  "confidence": <a number 0.0-1.0 reflecting your overall confidence>,
  "warnings":   ["<any caveat the user should review>", ...]
}}
"""
    return prompt


def _verify_mapping(mapping, profiles_by_table):
    """
    Deterministic sanity checks on the LLM's proposed mapping.
    Returns a list of (severity, message) issues.
    """
    issues = []
    table_mapping = mapping.get('table_mapping', {})
    column_mapping = mapping.get('column_mapping', {})

    for canonical, mapped in table_mapping.items():
        if mapped is None or mapped == 'null':
            issues.append(('warn', f'No table mapped for canonical "{canonical}"'))
        elif mapped not in profiles_by_table:
            issues.append(('error', f'Mapped table "{mapped}" not found in catalog'))

    all_columns = {c['column'] for cols in profiles_by_table.values() for c in cols}
    for canonical, mapped in column_mapping.items():
        if mapped is None or mapped == 'null':
            issues.append(('warn', f'No column mapped for canonical "{canonical}"'))
        elif mapped not in all_columns:
            issues.append(('error', f'Mapped column "{mapped}" not found in any table'))

    created_at_col = column_mapping.get('created_at')
    if created_at_col:
        for cols in profiles_by_table.values():
            for c in cols:
                if c['column'] == created_at_col:
                    if c['family'] not in ('datetime', 'date_string'):
                        issues.append(('warn',
                            f'"{created_at_col}" mapped to created_at but family is {c["family"]}'))

    conv_col = column_mapping.get('converted_to_order')
    if conv_col:
        for cols in profiles_by_table.values():
            for c in cols:
                if c['column'] == conv_col:
                    if c['family'] not in ('boolean', 'integer'):
                        issues.append(('warn',
                            f'"{conv_col}" mapped to converted_to_order but family is {c["family"]}'))

    val_col = column_mapping.get('order_value')
    if val_col:
        for cols in profiles_by_table.values():
            for c in cols:
                if c['column'] == val_col:
                    if c['family'] not in ('integer', 'float'):
                        issues.append(('warn',
                            f'"{val_col}" mapped to order_value but family is {c["family"]}'))

    return issues


def _format_client_schema_block(client_name, mapping):
    """Generate a paste-ready CLIENT_SCHEMA dict from the mapping."""
    table_mapping  = mapping.get('table_mapping', {})
    column_mapping = mapping.get('column_mapping', {})

    def _fmt_table(canonical):
        v = table_mapping.get(canonical)
        return repr(v) if v else "''   # ← MAP ME"

    def _fmt_col(canonical):
        v = column_mapping.get(canonical)
        return repr(v) if v else "''   # ← MAP ME"

    col_lines = ['\n'.join(
        f"        '{k}': {_fmt_col(k)},"
        for k in column_mapping.keys()
    )]
    all_tables = list(CANONICAL_TABLES.keys())
    tbl_lines = '\n'.join(
        f"        '{k}': {_fmt_table(k)},"
        for k in all_tables
    )

    return f"""CLIENT_SCHEMA = {{
    'client_name': {client_name!r},
    'tables': {{
{tbl_lines}
    }},
    'columns': {{
        'inquiry_id':         {_fmt_col('inquiry_id')},
        'buyer_id':           {_fmt_col('buyer_id')},
        'account_segment':    {_fmt_col('account_segment')},
        'platform':           {_fmt_col('platform')},
        'category':           {_fmt_col('category')},
        'country':            {_fmt_col('country')},
        'created_at':         {_fmt_col('created_at')},
        'converted_to_order': {_fmt_col('converted_to_order')},
        'order_value':        {_fmt_col('order_value')},
        'variant':            {_fmt_col('variant')},
        'experiment_name':    {_fmt_col('experiment_name')},
        # Extended columns discovered:
{col_lines[0] if col_lines else ''}
    }},
    # Review the mapping above; edit any '' placeholders before using.
}}"""


def run_schema_discovery(llm, _bootstrap_mode=False, _client_name=None):
    """
    Module 1 — Schema Discovery & Mapping.

    Parameters
    ----------
    llm               : LLM client
    _bootstrap_mode   : bool — if True, skip interactive prompts and return
                        the result dict for use by bootstrap_from_connection().
                        The PDF and schema file are still written.
    _client_name      : str — client name to use when _bootstrap_mode=True.
    """
    print()
    print('╔' + '═'*70 + '╗')
    print('║' + '  🔍  SCHEMA DISCOVERY & MAPPING (Phase 0 — Foundation)'.ljust(70) + '║')
    print('║' + '  Auto-generate a CLIENT_SCHEMA from a connected warehouse'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    if _bootstrap_mode:
        # Non-interactive path — use DuckDB session tables, client name from caller
        client_name = _client_name or 'Client'
        print(f'\n  Running in bootstrap mode for client: {client_name}')
    else:
        # ── Source selection ──────────────────────────────────────────────────
        print()
        print('  Available sources:')
        print('    [1] Synthetic data (DuckDB tables registered in this session)')
        print('    [2] Snowflake / Postgres / external warehouse (advanced — needs connection)')
        while True:
            choice = input('  ❓ Choose source [1/2] (default 1): ').strip() or '1'
            if choice in ('1', '2'): break
            print('     ⚠️  Choose 1 or 2')

        if choice == '2':
            print('\n  ℹ️  External warehouse profiling is left as an integration step.')
            print('     For this session, falling back to the synthetic catalog so you')
            print('     can see the full discovery flow end-to-end.')

        client_name = input('\n  Client name (e.g. "Xometry"): ').strip() or 'Demo Client'

    # ── Catalog scan from DuckDB ─────────────────────────────────────────────
    print('\n  🔎 Scanning DuckDB catalog...')
    try:
        catalog_df = db.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
        """).df()
    except Exception:
        catalog_df = db.execute("SHOW TABLES").df()
        catalog_df.columns = ['table_name']

    if len(catalog_df) == 0:
        print('  ⚠️  No tables found. Run cells 5 and 6 first to register synthetic data.')
        return None

    print(f'     Found {len(catalog_df)} tables: {", ".join(catalog_df["table_name"].tolist())}')

    # ── Profile each table ───────────────────────────────────────────────────
    print('\n  🧪 Profiling tables (sampling rows, computing nulls / cardinality / families)...')
    profiles_by_table = {}
    for tbl in catalog_df['table_name']:
        try:
            df_tbl = db.execute(f'SELECT * FROM "{tbl}" LIMIT 5000').df()
            profiles_by_table[tbl] = _profile_dataframe(df_tbl, tbl)
            print(f'     ✅ {tbl:<32} {len(df_tbl):>6,} rows sampled, {len(df_tbl.columns)} columns')
        except Exception as e:
            print(f'     ⚠️  {tbl}: {e}')

    if not profiles_by_table:
        print('  ❌ No tables could be profiled.')
        return None

    # ── LLM mapping ──────────────────────────────────────────────────────────
    print('\n  🤖 Asking the LLM to map catalog → canonical schema...')
    prompt = _build_mapping_prompt(profiles_by_table)
    raw = llm.ask(prompt)
    try:
        json_match = re.search(r'\{[\s\S]*\}', raw)
        mapping = json.loads(json_match.group()) if json_match else {}
    except Exception as e:
        print(f'  ⚠️  Could not parse LLM response as JSON ({e}); proceeding with empty mapping.')
        mapping = {'table_mapping': {}, 'column_mapping': {}, 'confidence': 0.0,
                   'warnings': ['LLM output was not valid JSON; review carefully.']}

    confidence = mapping.get('confidence', 0.0)
    print(f'\n  Mapping confidence: {confidence:.0%}')

    # ── Verify ───────────────────────────────────────────────────────────────
    print('\n  ✅ Verifying mapping with deterministic checks...')
    issues = _verify_mapping(mapping, profiles_by_table)
    n_errors = sum(1 for sev, _ in issues if sev == 'error')
    n_warns  = sum(1 for sev, _ in issues if sev == 'warn')
    if n_errors:
        print(f'     ❌ {n_errors} error(s):')
        for sev, msg in issues:
            if sev == 'error': print(f'        - {msg}')
    if n_warns:
        print(f'     ⚠️  {n_warns} warning(s):')
        for sev, msg in issues:
            if sev == 'warn': print(f'        - {msg}')
    if not issues:
        print('     ✅ All checks passed.')

    # ── Display the proposed mapping ─────────────────────────────────────────
    print('\n  ── Proposed table mapping ──')
    for canonical, mapped in mapping.get('table_mapping', {}).items():
        marker = '✅' if mapped else '⚠️ '
        print(f'    {marker} {canonical:<14} → {mapped or "(no match)"}')

    print('\n  ── Proposed column mapping ──')
    for canonical, mapped in mapping.get('column_mapping', {}).items():
        marker = '✅' if mapped else '⚠️ '
        print(f'    {marker} {canonical:<22} → {mapped or "(no match)"}')

    # ── Generate paste-ready CLIENT_SCHEMA + PDF ─────────────────────────────
    schema_block = _format_client_schema_block(client_name, mapping)
    ensure_runtime_data_dir()
    schema_path = os.path.join(RUNTIME_DATA_DIR, f'client_schema_{client_name.lower().replace(" ", "_")}.py')
    with open(schema_path, 'w', encoding='utf-8') as f:
        f.write(f'# Auto-generated by Continum PersistIQ — Schema Discovery\n')
        f.write(f'# Client: {client_name}\n')
        f.write(f'# Mapping confidence: {confidence:.0%}\n')
        f.write(f'# Review every mapping before pasting into Cell 3.\n\n')
        f.write(schema_block + '\n')
    print(f'\n  📁 Schema block saved → {schema_path}')

    # PDF report
    from collections import OrderedDict
    pdf_sections = OrderedDict([
        ('OVERVIEW',
            f'Schema discovery against {len(profiles_by_table)} tables in the connected source. '
            f'LLM-proposed mapping confidence: {confidence:.0%}. '
            f'{n_errors} error(s) and {n_warns} warning(s) flagged by deterministic checks.'),
        ('TABLE MAPPING', '\n'.join(
            f'- {canonical} → {mapped or "(no match)"}'
            for canonical, mapped in mapping.get('table_mapping', {}).items())),
        ('COLUMN MAPPING', '\n'.join(
            f'- {canonical} → {mapped or "(no match)"}'
            for canonical, mapped in mapping.get('column_mapping', {}).items())),
        ('VERIFICATION ISSUES',
            '\n'.join(f'- [{sev.upper()}] {msg}' for sev, msg in issues) or 'None — all checks passed.'),
        ('NEXT STEPS',
            '- Review every mapped column in the generated schema file.\n'
            '- Replace any (no match) placeholders before deploying.\n'
            '- Paste the CLIENT_SCHEMA block into Cell 3 of the notebook.\n'
            '- Set USE_SYNTHETIC_DATA = False and re-run cells 3, 5, 6.'),
    ])

    ensure_runtime_data_dir()
    pdf_out = render_document_pdf(
        title='Schema Discovery Report',
        subtitle=f'Client: {client_name}',
        sections=pdf_sections,
        output_path=os.path.join(RUNTIME_DATA_DIR, 'schema_discovery_report.pdf'),
        metadata={
            'Client':        client_name,
            'Tables found':  str(len(profiles_by_table)),
            'Confidence':    f'{confidence:.0%}',
            'Errors':        str(n_errors),
            'Warnings':      str(n_warns),
        },
        accent_color=PDF_PALETTE['accent'],
    )
    print(f'  📁 PDF report saved → {pdf_out}')

    return {
        'client_name':   client_name,
        'tables_found':  list(profiles_by_table.keys()),
        'mapping':       mapping,
        'issues':        issues,
        'schema_file':   schema_path,
        'pdf_report':    pdf_out,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2 — PIPELINE HEALTH MONITOR (Phase 0 — Foundation)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_volume_anomaly(daily_counts, baseline_days=28, alert_z=2.5):
    """
    Compare today's volume to the seasonal-adjusted forecast from the prior baseline_days.
    Returns dict with z-score and severity.
    """
    if len(daily_counts) < baseline_days + 1:
        return {'status': 'insufficient_data', 'z_score': None, 'severity': 'info'}

    history = daily_counts.iloc[-(baseline_days + 1):-1]
    today   = float(daily_counts.iloc[-1])

    today_dow = daily_counts.index[-1].dayofweek
    same_dow  = history[history.index.dayofweek == today_dow]
    if len(same_dow) >= 3:
        baseline_mean = float(same_dow.mean())
        baseline_std  = float(same_dow.std()) or 1.0
    else:
        baseline_mean = float(history.mean())
        baseline_std  = float(history.std()) or 1.0

    z = (today - baseline_mean) / baseline_std
    pct_change = (today - baseline_mean) / baseline_mean * 100 if baseline_mean else 0
    severity = 'critical' if abs(z) > alert_z else 'warning' if abs(z) > 1.5 else 'ok'

    return {
        'status':         'analysed',
        'today_value':    today,
        'baseline_mean':  baseline_mean,
        'baseline_std':   baseline_std,
        'z_score':        round(z, 3),
        'pct_change':     round(pct_change, 2),
        'severity':       severity,
    }


def _detect_distribution_shift(today_counts, baseline_counts, alert_p=0.001):
    """χ² test comparing today's category split against baseline."""
    from scipy.stats import chisquare
    today_norm = today_counts.reindex(baseline_counts.index, fill_value=0).astype(float)
    if today_norm.sum() == 0 or baseline_counts.sum() == 0:
        return {'status': 'insufficient_data', 'severity': 'info'}

    expected = baseline_counts / baseline_counts.sum() * today_norm.sum()
    expected = expected.replace(0, 1e-6)
    chi2, p = chisquare(today_norm.values, f_exp=expected.values)
    severity = 'critical' if p < alert_p else 'warning' if p < 0.01 else 'ok'
    return {
        'status':       'analysed',
        'chi2':         round(float(chi2), 3),
        'p_value':      round(float(p), 6),
        'severity':     severity,
        'today_split':  {k: int(v) for k, v in today_norm.items()},
        'baseline_split': {k: int(v) for k, v in baseline_counts.items()},
    }


def _detect_freshness(latest_ts, sla_hours=24):
    """Compare most-recent record to SLA. Always returns all keys."""
    now = pd.Timestamp.now()
    if latest_ts is None or pd.isna(latest_ts):
        return {
            'status':    'no_data',
            'latest':    'n/a',
            'age_hours': 0.0,
            'sla_hours': sla_hours,
            'severity':  'critical',
        }
    age_hours = (now - pd.Timestamp(latest_ts)).total_seconds() / 3600
    severity = 'critical' if age_hours > sla_hours * 2 \
        else 'warning' if age_hours > sla_hours else 'ok'
    return {
        'status':     'analysed',
        'latest':     str(latest_ts),
        'age_hours':  round(age_hours, 2),
        'sla_hours':  sla_hours,
        'severity':   severity,
    }


def _detect_null_spike(df, columns, baseline_null_rates, alert_pp=10):
    """Find columns where null rate jumped vs baseline by alert_pp percentage points."""
    findings = []
    for col in columns:
        if col not in df.columns: continue
        current = df[col].isna().mean() * 100
        baseline = baseline_null_rates.get(col, 0.0)
        jump = current - baseline
        if jump > alert_pp:
            findings.append({
                'column':       col,
                'baseline_pct': round(baseline, 2),
                'current_pct':  round(current, 2),
                'jump_pp':      round(jump, 2),
                'severity':     'critical' if jump > alert_pp * 2 else 'warning',
            })
    return findings


def _detect_schema_drift(current_columns, expected_columns):
    """Compare current schema vs expected; report new / missing columns."""
    current_set  = set(current_columns)
    expected_set = set(expected_columns)
    return {
        'new_columns':     sorted(current_set - expected_set),
        'missing_columns': sorted(expected_set - current_set),
        'severity':        'critical' if (expected_set - current_set) \
                            else 'warning' if (current_set - expected_set) else 'ok',
    }


def run_pipeline_health(llm):
    """
    Module 2 — Pipeline Health Monitor.
    Scans the canonical tables for anomalies and produces a designed PDF.
    """
    print()
    print('╔' + '═'*70 + '╗')
    print('║' + '  🩺  PIPELINE HEALTH MONITOR (Phase 0 — Foundation)'.ljust(70) + '║')
    print('║' + '  Volume · Distribution · Freshness · Schema · Null spikes'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    print()
    print('  Scanning canonical tables for anomalies...')

    # ── Pull primary table for analysis ──────────────────────────────────────
    try:
        df_inq = db.execute("""
            SELECT created_at, account_segment, platform, category, has_billing_profile
            FROM hist_inquiries
            ORDER BY created_at
        """).df()
        df_inq['created_at'] = pd.to_datetime(df_inq['created_at'])
    except Exception as e:
        print(f'  ❌ Could not read hist_inquiries: {e}')
        return None

    print(f'  ✅ Loaded {len(df_inq):,} historical inquiries '
          f'({df_inq["created_at"].min().date()} → {df_inq["created_at"].max().date()})')

    findings = {}

    # ── Volume drift ──────────────────────────────────────────────────────
    daily = df_inq.groupby(df_inq['created_at'].dt.normalize()).size()
    findings['volume'] = _detect_volume_anomaly(daily)
    print(f'\n  [1/5] Volume drift')
    v = findings['volume']
    if v['status'] == 'analysed':
        icon = {'ok':'✅','warning':'⚠️ ','critical':'🚨'}[v['severity']]
        print(f'     {icon} Today: {v["today_value"]:.0f}   Baseline: {v["baseline_mean"]:.0f}   '
              f'Δ={v["pct_change"]:+.1f}%   z={v["z_score"]:+.2f}')
    else:
        print(f'     ℹ️  {v["status"]}')

    # ── Distribution shift on category ────────────────────────────────────
    today_date = daily.index[-1]
    today_rows = df_inq[df_inq['created_at'].dt.normalize() == today_date]
    baseline_rows = df_inq[df_inq['created_at'].dt.normalize() < today_date].tail(28 * 500)
    today_cat   = today_rows['category'].value_counts()
    base_cat    = baseline_rows['category'].value_counts()
    findings['category_shift'] = _detect_distribution_shift(today_cat, base_cat)
    print(f'\n  [2/5] Distribution shift — category')
    d = findings['category_shift']
    if d['status'] == 'analysed':
        icon = {'ok':'✅','warning':'⚠️ ','critical':'🚨'}[d['severity']]
        print(f'     {icon} χ²={d["chi2"]:.2f}   p={d["p_value"]:.4f}')
    else:
        print(f'     ℹ️  {d["status"]}')

    # ── Distribution shift on platform ────────────────────────────────────
    today_plat = today_rows['platform'].value_counts()
    base_plat  = baseline_rows['platform'].value_counts()
    findings['platform_shift'] = _detect_distribution_shift(today_plat, base_plat)
    p = findings['platform_shift']
    if p['status'] == 'analysed':
        icon = {'ok':'✅','warning':'⚠️ ','critical':'🚨'}[p['severity']]
        print(f'         platform: {icon} χ²={p["chi2"]:.2f}   p={p["p_value"]:.4f}')

    # ── Freshness ─────────────────────────────────────────────────────────
    latest = df_inq['created_at'].max()
    findings['freshness'] = _detect_freshness(latest, sla_hours=24*30)  # synthetic data is months old
    f = findings['freshness']
    icon = {'ok':'✅','warning':'⚠️ ','critical':'🚨'}.get(f['severity'], 'ℹ️ ')
    print(f'\n  [3/5] Freshness')
    _age_str = f'{f["age_hours"]:.1f}h' if isinstance(f.get('age_hours'), (int, float)) else 'n/a'
    _sla_str = f'{f["sla_hours"]}h' if isinstance(f.get('sla_hours'), (int, float)) else 'n/a'
    print(f'     {icon} Latest record: {f.get("latest","n/a")}   '
          f'Age: {_age_str}   SLA: {_sla_str}')

    # ── Null spike ────────────────────────────────────────────────────────
    full_null_rates = (df_inq.isna().mean() * 100).to_dict()
    today_nulls = _detect_null_spike(today_rows,
        ['account_segment', 'platform', 'category', 'has_billing_profile'],
        full_null_rates, alert_pp=10)
    findings['null_spikes'] = today_nulls
    print(f'\n  [4/5] Null-rate spikes')
    if today_nulls:
        for n in today_nulls:
            icon = {'warning':'⚠️ ','critical':'🚨'}[n['severity']]
            print(f'     {icon} {n["column"]:<24} baseline={n["baseline_pct"]:.1f}%   '
                  f'today={n["current_pct"]:.1f}%   Δ={n["jump_pp"]:+.1f}pp')
    else:
        print('     ✅ No spikes detected.')

    # ── Schema drift ──────────────────────────────────────────────────────
    expected_cols = {'created_at','account_segment','platform','category','has_billing_profile'}
    findings['schema'] = _detect_schema_drift(df_inq.columns, expected_cols)
    s = findings['schema']
    icon = {'ok':'✅','warning':'⚠️ ','critical':'🚨'}[s['severity']]
    print(f'\n  [5/5] Schema drift')
    print(f'     {icon} New: {s["new_columns"] or "—"}   Missing: {s["missing_columns"] or "—"}')

    # ── Aggregate severity ───────────────────────────────────────────────────
    severities = []
    for _k, _v in findings.items():
        if isinstance(_v, list):
            severities.extend(item['severity'] for item in _v)
        elif isinstance(_v, dict):
            severities.append(_v.get('severity', 'info'))
    if 'critical' in severities:
        overall = '🚨 CRITICAL'
    elif 'warning' in severities:
        overall = '⚠️  WARNING'
    else:
        overall = '✅ HEALTHY'

    print('\n' + '─' * 72)
    print(f'  Overall pipeline status: {overall}')
    print('─' * 72)

    # ── LLM narration ────────────────────────────────────────────────────────
    print('\n  🤖 Generating plain-English summary via LLM...')
    findings_summary = json.dumps(
        {fk: (fv if not isinstance(fv, list) else fv[:5]) for fk, fv in findings.items()},
        default=str, indent=2)[:3000]

    narration_prompt = textwrap.dedent(f"""
        You are a senior data engineer reviewing today's pipeline health.
        Below are the structured findings from automated checks.
        Write a 4-6 sentence executive-friendly summary explaining:
        (1) the overall health,
        (2) the most concerning finding (if any) and likely cause,
        (3) what action the team should take next.
        Be specific. Avoid generic advice. Do not use emojis.

        Findings:
        {findings_summary}
    """).strip()

    try:
        narration = llm.ask(narration_prompt)
        try:
            narration = _strip_decorative_chars(narration)
        except NameError:
            pass
    except Exception as e:
        narration = f'(LLM narration failed: {e})'

    print('\n  ── Narrative ──')
    for line in narration.split('\n'):
        if line.strip(): print(f'    {line}')

    # ── PDF report ───────────────────────────────────────────────────────────
    from collections import OrderedDict
    overall_plain = overall.replace('🚨 ', '').replace('⚠️  ', '').replace('✅ ', '')
    pdf_sections = OrderedDict([
        ('STATUS', f'{overall_plain}  —  scan completed at {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}'),
        ('NARRATIVE', narration),
        ('VOLUME DRIFT',
            (f'- Today: {v["today_value"]:.0f} inquiries\n'
             f'- 28-day baseline: {v["baseline_mean"]:.0f}\n'
             f'- Change: {v["pct_change"]:+.1f}%\n'
             f'- z-score: {v["z_score"]:+.2f}\n'
             f'- Severity: {v["severity"].upper()}') if v['status'] == 'analysed'
            else 'Insufficient data for this check.'),
        ('DISTRIBUTION SHIFTS',
            (f'- Category split: χ²={d["chi2"]:.2f}, p={d["p_value"]:.4f}, severity={d["severity"].upper()}\n'
             f'- Platform split: χ²={p["chi2"]:.2f}, p={p["p_value"]:.4f}, severity={p["severity"].upper()}'
             ) if d['status'] == 'analysed' else 'Insufficient data.'),
        ('FRESHNESS',
            f'- Latest record: {f.get("latest", "n/a")}\n'
            f'- Age: {f.get("age_hours", 0):.1f} hours\n'
            f'- SLA: {f.get("sla_hours", 0)} hours\n'
            f'- Severity: {f["severity"].upper()}'),
        ('NULL-RATE SPIKES',
            ('\n'.join(
                f'- {n["column"]}: baseline {n["baseline_pct"]:.1f}% → '
                f'today {n["current_pct"]:.1f}% (Δ {n["jump_pp"]:+.1f}pp), {n["severity"].upper()}'
                for n in today_nulls)
             ) or 'No null-rate spikes detected.'),
        ('SCHEMA DRIFT',
            f'- New columns: {", ".join(s["new_columns"]) or "none"}\n'
            f'- Missing columns: {", ".join(s["missing_columns"]) or "none"}\n'
            f'- Severity: {s["severity"].upper()}'),
    ])

    accent = (PDF_PALETTE.get('warning', '#f59e0b') if 'WARNING' in overall
              else PDF_PALETTE.get('success', '#22c55e') if 'HEALTHY' in overall
              else PDF_PALETTE.get('secondary', '#f97316'))
    ensure_runtime_data_dir()
    pdf_out = render_document_pdf(
        title='Pipeline Health Report',
        subtitle=f'Daily scan — {pd.Timestamp.now().strftime("%Y-%m-%d")}',
        sections=pdf_sections,
        output_path=os.path.join(RUNTIME_DATA_DIR, 'pipeline_health_report.pdf'),
        metadata={
            'Overall':      overall_plain,
            'Tables scanned': '1 (hist_inquiries)',
            'Checks run':   '5',
            'Critical':     str(sum(1 for s in severities if s == 'critical')),
            'Warnings':     str(sum(1 for s in severities if s == 'warning')),
        },
        accent_color=accent,
    )
    print(f'\n  📁 Pipeline health report saved → {pdf_out}')

    return {
        'overall':    overall,
        'findings':   findings,
        'narrative':  narration,
        'pdf_report': pdf_out,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 14 — WATCHTOWER (Phase 0 · Foundation)
# ─────────────────────────────────────────────────────────────────────────────

WATCHTOWER_METRICS = [
    {'name': 'IOR',         'sql_numerator': 'SUM(CAST(converted_to_order AS INTEGER))',
                             'sql_denominator': 'COUNT(*)',      'table': 'hist_inquiries'},
    {'name': 'Volume',      'sql_numerator': 'COUNT(*)',
                             'sql_denominator': None,            'table': 'hist_inquiries'},
    {'name': 'AOV',         'sql_numerator': 'AVG(CASE WHEN converted_to_order THEN order_value END)',
                             'sql_denominator': None,            'table': 'hist_inquiries'},
]

WATCHTOWER_DIMENSIONS = ['account_segment', 'platform', 'price_tier', 'process_group']
WATCHTOWER_ALERT_Z    = 2.5
WATCHTOWER_BASELINE   = 28


def _compute_metric_series(metric: dict, dim: str, level: str,
                             start_date: 'pd.Timestamp',
                             end_date:   'pd.Timestamp') -> 'pd.Series':
    """
    Compute daily time series for a metric at a specific dimensional slice.
    Returns a pandas Series indexed by date.
    """
    tbl = metric['table']
    num = metric['sql_numerator']
    den = metric['sql_denominator']

    dim_filter = f"AND {dim} = '{level}'" if dim != 'all' else ''

    if den:
        metric_expr = f'({num}) / NULLIF(({den}), 0)'
    else:
        metric_expr = num

    sql = f"""
        SELECT
            created_at::DATE AS day,
            {metric_expr}    AS metric_value
        FROM "{tbl}"
        WHERE created_at::DATE BETWEEN '{start_date.date()}' AND '{end_date.date()}'
          {dim_filter}
        GROUP BY created_at::DATE
        ORDER BY day
    """
    try:
        df = db.execute(sql).df()
        if df.empty:
            return pd.Series(dtype=float)
        df['day'] = pd.to_datetime(df['day'])
        return df.set_index('day')['metric_value'].astype(float)
    except Exception as e:
        return pd.Series(dtype=float)


def _detect_slice_anomaly(series: 'pd.Series',
                           baseline_days: int = WATCHTOWER_BASELINE,
                           alert_z: float = WATCHTOWER_ALERT_Z) -> dict:
    """
    Run the same day-of-week adjusted anomaly detection as Module 2's
    _detect_volume_anomaly(), applied to a single dimensional slice.
    """
    if len(series) < baseline_days + 1:
        return {'status': 'insufficient_data', 'severity': 'info'}

    history = series.iloc[-(baseline_days + 1):-1]
    today   = float(series.iloc[-1])
    if pd.isna(today):
        return {'status': 'no_data', 'severity': 'warning'}

    today_dow = series.index[-1].dayofweek
    same_dow  = history[history.index.dayofweek == today_dow]
    if len(same_dow) >= 3:
        baseline_mean = float(same_dow.mean())
        baseline_std  = float(same_dow.std()) or 1.0
    else:
        baseline_mean = float(history.mean())
        baseline_std  = float(history.std()) or 1.0

    z          = (today - baseline_mean) / baseline_std
    pct_change = (today - baseline_mean) / baseline_mean * 100 if baseline_mean else 0
    severity   = 'critical' if abs(z) > alert_z else                  'warning'  if abs(z) > 1.5     else 'ok'

    return {
        'status':        'analysed',
        'today_value':   round(today, 6),
        'baseline_mean': round(baseline_mean, 6),
        'z_score':       round(z, 3),
        'pct_change':    round(pct_change, 2),
        'severity':      severity,
    }


def _cross_reference_experiments(anomaly_dim: str, anomaly_level: str,
                                   anomaly_date: 'pd.Timestamp') -> list:
    """
    Check if any running experiment overlaps with the anomaly's dimension / level.
    Returns a list of experiment names that could explain the anomaly.
    """
    matches = []
    for exp in globals().get('EXPERIMENT_REGISTRY', []):
        if exp.get('status') not in ('running', 'concluded'):
            continue
        start = pd.Timestamp(exp['start_date'])
        end   = pd.Timestamp(exp['end_date']) if exp.get('end_date') else pd.Timestamp.now()
        if start <= anomaly_date <= end:
            matches.append({
                'experiment_name': exp['experiment_name'],
                'status':          exp['status'],
                'team':            exp.get('team', '—'),
                'start':           str(exp['start_date']),
            })
    return matches


def _cross_reference_pipeline_baseline(metric_name: str, dim: str, level: str,
                                         z_score: float) -> str:
    """
    Check if the alert direction is consistent with the pipeline health baseline.
    If the pipeline baseline shows a historical volume drop in the same slice,
    the anomaly may be a data pipeline issue rather than a business metric change.
    Returns a diagnosis hint string.
    """
    baseline = globals().get('CONTINUM_STATE', {}).get('pipeline_baseline')
    if not baseline:
        return ''

    # Simple heuristic: if this is a volume metric and the baseline was already
    # CRITICAL/WARNING when established, flag as potentially pipeline-related
    overall = baseline.get('overall', '')
    if metric_name == 'Volume' and 'CRITICAL' in str(overall):
        return '⚠️ Pipeline baseline was CRITICAL — may be a data issue'
    if metric_name == 'Volume' and 'WARNING' in str(overall):
        return '⚠️ Pipeline baseline was WARNING — check Module 2 first'

    return ''


def run_watchtower(llm):
    """
    Module 14 — Watchtower Dimensional Anomaly Detection.

    Scans every metric × dimension × level combination for anomalies.
    Cross-references running experiments to disambiguate real signals
    from experiment effects or technical failures.
    Produces a structured alert table + LLM narration + PDF report.
    """
    print()
    print('╔' + '═'*70 + '╗')
    print('║' + '  🔭  WATCHTOWER — Dimensional Anomaly Detection'.ljust(70) + '║')
    print('║' + '  Phase 0 · Foundation · Module 14'.ljust(70) + '║')
    print('║' + '  Monitoring: IOR · Volume · AOV  ×  Segment · Platform · Tier · Process'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')

    try:
        date_range = db.execute(
            'SELECT MIN(created_at)::DATE, MAX(created_at)::DATE FROM hist_inquiries'
        ).fetchone()
        hist_start = pd.Timestamp(date_range[0])
        hist_end   = pd.Timestamp(date_range[1])
    except Exception as e:
        print(f'  ❌ Could not determine date range: {e}')
        return None

    scan_start = hist_end - pd.Timedelta(days=WATCHTOWER_BASELINE + 7)
    print(f'\n  Scan window : {scan_start.date()} → {hist_end.date()}')
    print(f'  Baseline    : {WATCHTOWER_BASELINE} days (day-of-week adjusted)')
    print(f'  Alert threshold: |z| > {WATCHTOWER_ALERT_Z}')
    print()

    alerts     = []
    scan_count = 0

    print('  Scanning metric × dimension × level...')
    print('  (This may take 20–40 seconds for large datasets)')
    print()

    for metric in WATCHTOWER_METRICS:
        for dim in WATCHTOWER_DIMENSIONS:
            try:
                levels = db.execute(
                    f'SELECT DISTINCT {dim} FROM hist_inquiries '
                    f'WHERE {dim} IS NOT NULL ORDER BY {dim}'
                ).df()[dim].tolist()
            except Exception:
                continue

            for level in levels:
                series = _compute_metric_series(
                    metric, dim, level, scan_start, hist_end)
                if series.empty or len(series) < 5:
                    continue

                result = _detect_slice_anomaly(series)
                scan_count += 1

                if result['status'] == 'analysed' and result['severity'] in ('warning', 'critical'):
                    # Cross-reference with running experiments
                    xref = _cross_reference_experiments(dim, level, hist_end)

                    _pipeline_hint = _cross_reference_pipeline_baseline(
                        metric['name'], dim, level, result['z_score'])
                    alerts.append({
                        'metric':         metric['name'],
                        'dimension':      dim,
                        'level':          str(level),
                        'z_score':        result['z_score'],
                        'pct_change':     result['pct_change'],
                        'today_value':    result['today_value'],
                        'baseline':       result['baseline_mean'],
                        'severity':       result['severity'],
                        'experiments':    xref,
                        'pipeline_hint':  _pipeline_hint,
                    })

    sev_order = {'critical': 0, 'warning': 1}
    alerts.sort(key=lambda a: (sev_order.get(a['severity'], 2), -abs(a['z_score'])))

    print(f'  Scanned {scan_count:,} metric × slice combinations.')
    n_critical = sum(1 for a in alerts if a['severity'] == 'critical')
    n_warning  = sum(1 for a in alerts if a['severity'] == 'warning')
    print(f'  Found: {n_critical} critical alert(s), {n_warning} warning(s).')

    # ── Display alert table ───────────────────────────────────────────────────
    if not alerts:
        print()
        print('  ✅ No anomalies detected. All metric × slice combinations are within bounds.')
    else:
        print()
        print('  ┌──────────────┬────────────────────┬────────────┬─────────┬──────────┬──────────────────────────────┐')
        print('  │ Severity     │ Metric × Slice     │ Today val  │ z-score │ Δ%       │ Experiments overlapping      │')
        print('  ├──────────────┼────────────────────┼────────────┼─────────┼──────────┼──────────────────────────────┤')
        for a in alerts[:20]:   # cap display at 20
            sev_str  = '🚨 CRITICAL' if a['severity'] == 'critical' else '⚠️  WARNING '
            slice_str = f'{a["dimension"]}={a["level"]}'[:18]
            metric_str= f'{a["metric"]} · {slice_str}'[:18]
            today_str = f'{a["today_value"]:.4f}'
            z_str     = f'{a["z_score"]:+.2f}'
            pct_str   = f'{a["pct_change"]:+.1f}%'
            exp_names = ', '.join(x['experiment_name'][:15] for x in a['experiments'][:2]) or '—'
            hint_str = a.get('pipeline_hint','')
            note = '🔧' if hint_str else ' '
            print(f'  │ {sev_str:<12} │ {metric_str:<18} │ {today_str:<10} │ {z_str:<7} │ {pct_str:<8} │ {note} {exp_names:<26} │')
        print('  └──────────────┴────────────────────┴────────────┴─────────┴──────────┴──────────────────────────────┘')

        if len(alerts) > 20:
            print(f'  ... and {len(alerts) - 20} more. See PDF report for full list.')

    # ── LLM narration ─────────────────────────────────────────────────────────
    print()
    print('  🤖 Generating Watchtower narrative...')

    alert_summary = '\n'.join(
        f'{a["severity"].upper()}: {a["metric"]} × {a["dimension"]}={a["level"]} '
        f'z={a["z_score"]:+.2f} ({a["pct_change"]:+.1f}%) '
        f'overlaps_with=[{", ".join(x["experiment_name"] for x in a["experiments"][:2])}]'
        for a in alerts[:10]
    ) or 'No anomalies detected.'

    narration_prompt = textwrap.dedent(f"""
        You are a senior data engineer reviewing today's Watchtower scan.
        Write a 4-6 sentence executive summary covering:
        (1) Overall status — how many critical alerts vs normal.
        (2) The most urgent finding and the most likely cause (technical failure,
            experiment effect, or genuine business change).
        (3) Whether any alerts correlate with running experiments and what that implies.
        (4) Recommended immediate action.
        Be specific. Avoid generic advice. Do not use emojis.

        Alert summary:
        {alert_summary}
    """).strip()

    try:
        narration = llm.ask(narration_prompt)
        try:
            narration = _strip_decorative_chars(narration)
        except NameError:
            pass
    except Exception as e:
        narration = f'(LLM narration unavailable: {e})'

    print()
    print('  ── Watchtower Narrative ──')
    for line in narration.split('\n'):
        if line.strip():
            print(f'    {line}')

    # ── PDF report ────────────────────────────────────────────────────────────
    from collections import OrderedDict
    alert_table_str = '\n'.join(
        f'- [{a["severity"].upper()}] {a["metric"]} × {a["dimension"]}={a["level"]}: '
        f'z={a["z_score"]:+.2f}, Δ={a["pct_change"]:+.1f}%'
        + (f', experiments: {", ".join(x["experiment_name"] for x in a["experiments"][:2])}'
           if a["experiments"] else '')
        for a in alerts
    ) or 'No anomalies detected.'

    pdf_sections = OrderedDict([
        ('STATUS',
            f'{n_critical} CRITICAL · {n_warning} WARNING · scanned {scan_count:,} combinations'),
        ('NARRATIVE', narration),
        ('ALERT DETAILS', alert_table_str),
        ('EXPERIMENT CROSS-REFERENCE',
            '\n'.join(
                f'- [{a["severity"].upper()}] {a["metric"]} × {a["dimension"]}={a["level"]} '
                f'overlaps: {", ".join(x["experiment_name"] for x in a["experiments"])}'
                for a in alerts if a["experiments"]
            ) or 'No anomalies overlap with running or recently concluded experiments.'),
        ('RECOMMENDED ACTIONS',
            '- For CRITICAL alerts not overlapping experiments: investigate as technical failure.\n'
            '- For alerts overlapping a running experiment: check Module 8 (Health Monitor).\n'
            '- For gradual declines over multiple days: run Module 2 (Pipeline Health) to rule out data issues.\n'
            '- For alerts in a recently shipped segment: consider pausing rollout and running Module 12 (ROI Tracker).'),
    ])

    overall_plain = 'CRITICAL' if n_critical > 0 else ('WARNING' if n_warning > 0 else 'HEALTHY')
    accent = (PDF_PALETTE.get('secondary', '#f97316') if n_critical > 0
              else PDF_PALETTE.get('warning', '#f59e0b') if n_warning > 0
              else PDF_PALETTE.get('success', '#22c55e'))
    ensure_runtime_data_dir()
    pdf_out = render_document_pdf(
        title='Watchtower Report',
        subtitle=f'Dimensional anomaly scan — {hist_end.date()}',
        sections=pdf_sections,
        output_path=os.path.join(RUNTIME_DATA_DIR, 'watchtower_report.pdf'),
        metadata={
            'Scan date':       str(hist_end.date()),
            'Slices scanned':  str(scan_count),
            'Critical alerts': str(n_critical),
            'Warnings':        str(n_warning),
            'Overall':         overall_plain,
        },
        accent_color=accent,
    )
    print(f'\n  📁 Watchtower report saved → {pdf_out}')

    return {
        'overall':       overall_plain,
        'alerts':        alerts,
        'n_critical':    n_critical,
        'n_warning':     n_warning,
        'scan_count':    scan_count,
        'narrative':     narration,
        'pdf_report':    pdf_out,
    }

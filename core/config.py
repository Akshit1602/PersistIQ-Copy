import os

import os

os.environ.setdefault('TRANSFORMERS_VERBOSITY', 'error')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
os.environ.setdefault('HF_HUB_DISABLE_IMPLICIT_TOKEN', '1')
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

import re, json, time, textwrap, warnings
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any
from enum import Enum
import logging

import torch
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import transformers
try:
    transformers.logging.set_verbosity_error()
except Exception:
    pass

# import snowflake.connector
# import sqlglot
import sqlglot.expressions as exp
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm, t as t_dist
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import duckdb
from tabulate import tabulate

warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=UserWarning, module='transformers')
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Silence chatty loggers from HuggingFace hub
for _log_name in ('huggingface_hub', 'huggingface_hub.utils._http',
                  'transformers', 'transformers.modeling_utils',
                  'transformers.configuration_utils',
                  'transformers.tokenization_utils_base'):
    logging.getLogger(_log_name).setLevel(logging.ERROR)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('continum_agent')

# ── Detect best available device ─────────────────────────────────────────────
if torch.cuda.is_available():
    DEVICE = 'cuda'
elif torch.backends.mps.is_available():   # Apple Silicon
    DEVICE = 'mps'
else:
    DEVICE = 'cpu'
print(f'Device: {DEVICE}')

# ── Matplotlib dark theme ─────────────────────────────────────────────────────
plt.rcParams.update({
    'figure.facecolor': '#0f0f0f', 'axes.facecolor':  '#1a1a2e',
    'axes.edgecolor':   '#444',    'axes.labelcolor': '#e0e0e0',
    'xtick.color':      '#aaa',    'ytick.color':     '#aaa',
    'text.color':       '#e0e0e0', 'grid.color':      '#333',
    'grid.linestyle':   '--',      'grid.alpha':       0.4,
    'font.family':      'monospace',
    'axes.titlesize':   13,        'axes.labelsize':  11,
})
COLORS = {
    'control':   '#4e9af1', 'treatment': '#f97316',
    'positive':  '#22c55e', 'negative':  '#ef4444',
    'neutral':   '#a1a1aa', 'highlight': '#facc15',
    'bg':        '#1a1a2e', 'accent':    '#7c3aed',
}
# ── Domain constants — configurable per client ───────────────────────────────
SEGMENTS  = ['Core', 'Growth', 'Enterprise', 'Individuals']  # default buyer segments
PLATFORMS = ['web', 'mobile']                                  # default platforms
CATEGORIES = ['Category A', 'Category B', 'Category C', 'Category D', 'Category E']
COUNTRIES  = ['US', 'UK', 'CA', 'AU', 'IN']

# ── statsmodels (optional — used by ARIMA/SARIMA/BSTS/Causal Impact) ────────
try:
    import statsmodels.api as sm                                            # noqa: F401
    from statsmodels.tsa.arima.model import ARIMA as SM_ARIMA              # noqa: F401
    from statsmodels.tsa.statespace.sarimax import SARIMAX as SM_SARIMAX  # noqa: F401
    from statsmodels.tsa.statespace.structural import UnobservedComponents as SM_UC  # noqa: F401
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    print('  ℹ️  statsmodels not installed — run: pip install statsmodels')

print('Imports ready')

# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP ORCHESTRATOR — State layer for plug-and-play integration
# Modes:
#   'synthetic'                — use built-in synthetic data
#   'production_bootstrapping' — connected to a real warehouse, not yet mapped
#   'production_ready'         — mapping approved, platform ready to run modules
# ─────────────────────────────────────────────────────────────────────────────

import json as _json
import os as _os
from datetime import datetime as _dt

STATE_FILE = 'continum_state.json'

def _default_state():
    return {
        'mode':                 'synthetic',
        'client_name':          None,
        'connection_fingerprint': None,
        'client_schema':        None,
        'bootstrap_timestamp':  None,
        'approved_by':          None,
        'pipeline_baseline':    None,
        'last_health_check':    None,
        'schema_version':       1,
    }


def _load_state():
    """Read state from disk if it exists; otherwise return defaults."""
    if _os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = _json.load(f)
                # Fill in any missing keys with defaults (forward compat)
                for k, v in _default_state().items():
                    state.setdefault(k, v)
                return state
        except Exception as e:
            print(f'  ⚠️  Could not load {STATE_FILE}: {e}. Using defaults.')
    return _default_state()


def _save_state(state):
    """Persist state to disk."""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            _json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f'  ⚠️  Could not save {STATE_FILE}: {e}')


# Load on cell execution
CONTINUM_STATE = _load_state()


# ─────────────────────────────────────────────────────────────────────────────
# API surface — functions a UI wrapper would call
# ─────────────────────────────────────────────────────────────────────────────

def get_continum_state():
    """Return a copy of current state (read-only from caller's perspective)."""
    return dict(CONTINUM_STATE)


def reset_continum_state():
    """Reset to synthetic mode. Removes the persistence file. For testing / starting over."""
    global CONTINUM_STATE
    CONTINUM_STATE = _default_state()
    if _os.path.exists(STATE_FILE):
        _os.remove(STATE_FILE)
    print('✅ CONTINUM_STATE reset to synthetic mode.')


def is_production_ready():
    """True when the platform is bootstrapped against a real client warehouse."""
    return CONTINUM_STATE.get('mode') == 'production_ready'


def is_synthetic():
    """True when running against built-in synthetic data."""
    return CONTINUM_STATE.get('mode') == 'synthetic'



def bootstrap_from_connection(llm, connection_config=None,
                              skip_confirmation=False,
                              run_health_baseline=True):
    """
    Main entry point for plug-and-play integration.

    Steps
    -----
    1. Print a status banner.
    2. If already production_ready, ask whether to re-run.
    3. Run Module [1] Schema Discovery (programmatic mode — no interactive prompts).
    4. Show a mapping-diff table with confidence scores.
    5. Highlight low-confidence rows; block on human approval unless
       skip_confirmation=True.
    6. On approval: commit to CONTINUM_STATE, persist JSON, set mode=production_ready.
    7. Optionally run Module [2] Pipeline Health to establish a baseline.
    8. Return final state.

    Parameters
    ----------
    llm                 : LLM client (same object passed to all modules)
    connection_config   : dict with 'type' and connection params, e.g.
                          {'type': 'snowflake', 'account': ..., 'user': ...,
                           'password': ..., 'warehouse': ..., 'role': ...}
                          Leave None to use env vars / current DuckDB session.
    skip_confirmation   : bool — if True, commits the mapping without prompting.
                          Use only in automated pipelines where the mapping has
                          already been validated.
    run_health_baseline : bool — run Module [2] after approval to establish
                          a freshness / volume baseline. Default True.
    """
    global CONTINUM_STATE

    print()
    print('╔' + '═'*70 + '╗')
    print('║' + '  🔌  BOOTSTRAP FROM CONNECTION'.ljust(70) + '║')
    print('║' + '  Auto-discover schema → human review → production-ready'.ljust(70) + '║')
    print('╚' + '═'*70 + '╝')
    print()

    # ── Already bootstrapped? ────────────────────────────────────────────────
    if CONTINUM_STATE['mode'] == 'production_ready':
        print(f'  ℹ️  Platform already bootstrapped.')
        print(f'     Client    : {CONTINUM_STATE["client_name"]}')
        print(f'     Timestamp : {CONTINUM_STATE["bootstrap_timestamp"]}')
        print()
        raw = input('  Re-run bootstrap? This will replace the existing mapping. [y/N]: ').strip().lower()
        if raw != 'y':
            print('  Keeping existing configuration.')
            return get_continum_state()
        # Reset before re-running
        CONTINUM_STATE['mode'] = 'production_bootstrapping'

    CONTINUM_STATE['mode'] = 'production_bootstrapping'
    _save_state(CONTINUM_STATE)

    # ── Step 1: Get client name ──────────────────────────────────────────────
    print('  Step 1 of 4 — Connection details')
    print('  ─' * 36)
    client_name = input('  Client / project name: ').strip() or 'Client'

    # ── Step 2: Run Schema Discovery (programmatic, non-interactive) ─────────
    print()
    print('  Step 2 of 4 — Schema Discovery')
    print('  ─' * 36)
    print('  Profiling warehouse tables and mapping to canonical schema...')
    print()

    discovery_result = None
    try:
        discovery_result = run_schema_discovery(
            llm,
            _bootstrap_mode=True,
            _client_name=client_name,
        )
    except Exception as e:
        print(f'  ❌ Schema discovery failed: {e}')
        print('     Run Module [1] manually to diagnose the issue.')
        CONTINUM_STATE['mode'] = 'synthetic'
        _save_state(CONTINUM_STATE)
        return get_continum_state()

    if discovery_result is None:
        print('  ❌ Schema discovery returned no result. Aborting bootstrap.')
        CONTINUM_STATE['mode'] = 'synthetic'
        _save_state(CONTINUM_STATE)
        return get_continum_state()

    mapping    = discovery_result['mapping']
    confidence = mapping.get('confidence', 0.0)
    issues     = discovery_result['issues']
    table_map  = mapping.get('table_mapping', {})
    column_map = mapping.get('column_mapping', {})

    # ── Step 3: Human approval gate ──────────────────────────────────────────
    print()
    print('  Step 3 of 4 — Review proposed mapping')
    print('  ─' * 36)
    print()

    LOW_CONFIDENCE = 0.85    # flag mappings below this threshold
    n_low = 0

    # Table mapping table
    print('  ┌────────────────────────┬──────────────────────────────────┬──────────┐')
    print('  │  Canonical table       │  Client table                    │  Status  │')
    print('  ├────────────────────────┼──────────────────────────────────┼──────────┤')
    for canonical, mapped in table_map.items():
        row_conf = confidence if mapped else 0.0
        if not mapped or row_conf < LOW_CONFIDENCE:
            status = '⚠️  REVIEW'
            n_low += 1
        else:
            status = '✅ OK    '
        mapped_str = (mapped or '(no match)')[:32]
        print(f'  │  {canonical:<22}  │  {mapped_str:<32}  │  {status}  │')
    print('  └────────────────────────┴──────────────────────────────────┴──────────┘')

    print()
    print(f'  Overall confidence   : {confidence:.0%}')
    print(f'  Verification issues  : '
          f'{sum(1 for s,_ in issues if s=="error")} errors, '
          f'{sum(1 for s,_ in issues if s=="warn")} warnings')

    # Column mapping (abbreviated — show only the 8 most important)
    PRIORITY_COLS = ['inquiry_id','buyer_id','account_segment','platform',
                     'created_at','converted_to_order','order_value','variant',
                     'category','country','channel','product_id','device_type']
    print()
    print('  Key column mapping:')
    for c in PRIORITY_COLS:
        mapped_c = column_map.get(c)
        ok = '✅' if mapped_c else '⚠️ '
        print(f'    {ok}  {c:<24} → {mapped_c or "(no match)"}')

    if mapping.get('warnings'):
        print()
        print('  LLM warnings:')
        for w in mapping['warnings']:
            print(f'    ⚠️  {w}')

    # Hard block if there are mapping errors (not warnings)
    n_errors = sum(1 for s,_ in issues if s == 'error')
    if n_errors > 0:
        print()
        print(f'  ❌ {n_errors} mapping error(s) must be resolved before proceeding.')
        print('     Run Module [1] manually, review the PDF, correct the mapping,')
        print('     then call bootstrap_from_connection() again.')
        CONTINUM_STATE['mode'] = 'synthetic'
        _save_state(CONTINUM_STATE)
        return get_continum_state()

    # Soft block for low confidence
    if n_low > 0 and not skip_confirmation:
        print()
        print(f'  ⚠️  {n_low} mapping(s) need review (low confidence or no match).')
        print('     Review them above and edit continum_state.json if needed.')

    # Approval prompt
    if not skip_confirmation:
        print()
        raw = input('  Accept mapping and proceed to production mode? [y/N]: ').strip().lower()
        if raw != 'y':
            print()
            print('  Bootstrap cancelled. Edit the mapping and try again.')
            print('  Tip: run Module [1] manually to get the full PDF report.')
            CONTINUM_STATE['mode'] = 'synthetic'
            _save_state(CONTINUM_STATE)
            return get_continum_state()
    else:
        print()
        print('  skip_confirmation=True — proceeding without manual review.')

    # ── Step 4: Commit state ─────────────────────────────────────────────────
    print()
    print('  Step 4 of 4 — Committing configuration')
    print('  ─' * 36)

    from datetime import datetime as _dt
    CONTINUM_STATE.update({
        'mode':                  'production_ready',
        'client_name':           client_name,
        'connection_fingerprint': str(connection_config)[:200] if connection_config else 'duckdb_local',
        'client_schema': {
            'client_name':              client_name,
            'mapping':                  mapping,
            'segment_map':              {},
            'platform_map':             {},
            'cancelled_order_statuses': [],
            'internal_domains':         [],
            'dedup_key':                column_map.get('inquiry_id', 'inquiry_id'),
            'winsorise_pct':            99,
            'min_segment_size':         30,
            'null_ior_default':         0.18,
            'null_aov_default':         5000,
            'null_daily_traffic':       300,
            # Domain constants (empty = use Cell 2 defaults)
            'segments':   [],
            'platforms':  [],
            'categories': [],
            'countries':  [],
        },
        'bootstrap_timestamp': _dt.now().isoformat(timespec='seconds'),
        'approved_by':         'human' if not skip_confirmation else 'automated',
    })
    _save_state(CONTINUM_STATE)

    print(f'  ✅ State committed: mode=production_ready')
    print(f'     Client          : {client_name}')
    print(f'     Timestamp       : {CONTINUM_STATE["bootstrap_timestamp"]}')
    print(f'     Persisted to    : {STATE_FILE}')
    print()
    print('  ── Next steps ──────────────────────────────────────────────────')
    print('  1. Re-run Cell 3-Auto to rebuild CLIENT_SCHEMA from state.')
    print('  2. Re-run Cell 5-Auto to create canonical DuckDB views.')
    print('  3. Re-run Cell 6-Auto to load the production experiment registry.')
    print('  4. All 13 modules now work against your production data.')
    print()

    # ── Optional: pipeline health baseline ──────────────────────────────────
    if run_health_baseline:
        print('  Running Module [2] Pipeline Health to establish baseline...')
        try:
            health = run_pipeline_health(llm)
            CONTINUM_STATE['pipeline_baseline'] = {
                'timestamp':      _dt.now().isoformat(timespec='seconds'),
                'overall':        health.get('overall', 'unknown'),
                'volume_mean':    health.get('findings', {}).get('volume', {}).get('baseline_mean'),
                'null_rates':     {f['column']: f['baseline_pct']
                                   for f in health.get('findings', {}).get('null_spikes', [])},
            }
            CONTINUM_STATE['last_health_check'] = _dt.now().isoformat(timespec='seconds')
            _save_state(CONTINUM_STATE)
            print(f'  ✅ Health baseline saved (overall: {health.get("overall","?")})')
        except Exception as e:
            print(f'  ⚠️  Pipeline health baseline failed: {e}')
            print('     Run Module [2] manually to establish the baseline.')

    print()
    print('  🟢 Bootstrap complete. Platform is production_ready.')
    print('═'*72)
    return get_continum_state()


if CONTINUM_STATE['mode'] == 'synthetic':
    print('   Running against built-in synthetic data (Cells 5 + 6).')
    print('   To connect to a real warehouse: call bootstrap_from_connection(narrative_llm).')
elif CONTINUM_STATE['mode'] == 'production_ready':
    print(f'   Bootstrapped for client: {CONTINUM_STATE["client_name"]}')
    print(f'   Last bootstrap: {CONTINUM_STATE["bootstrap_timestamp"]}')


# ─────────────────────────────────────────────────────────────────────────────
# DATA_MODE — the only variable you need to change between the three run modes
#
#   'synthetic'   POC mode. Auto-generates realistic fake data. Zero config.
#
#   'csv'         Local file mode. Supply CSV exports from your
#                 warehouse. No live DB connection required.
#                 → call register_csv_source() below for each table before
#                   running Cell 16.
#
#   'production'  Live warehouse mode. Connects to Snowflake (or other DB)
#                 and pulls tables through the BronzeIngestionGateway.
# ─────────────────────────────────────────────────────────────────────────────
DATA_MODE = 'synthetic'   # CHANGE THIS: 'synthetic' | 'csv' | 'production'

USE_SYNTHETIC_DATA = (DATA_MODE != 'production')

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE CONFIG — single source of truth for the Bronze layer.
#
# Medallion roles within this dict:
#   bronze_tables  →  raw source locations (ingested as-is, no column rename)
#   column_map     →  bronze col name → canonical name (consumed by Silver SQL)
#   segment_map    →  raw segment values → canonical labels   (applied in Silver)
#   platform_map   →  raw platform values → canonical labels  (applied in Silver)
#   data quality   →  thresholds for Silver cleaning + module pre-checks
#
# ─────────────────────────────────────────────────────────────────────────────
SOURCE_CONFIG = {
    'client_name': 'ABC',

    # ── Snowflake connection (ignored when USE_SYNTHETIC_DATA = True) ─────────
    'snowflake': {
        'account':   os.environ.get('SNOWFLAKE_ACCOUNT',   'your_account'),
        'user':      os.environ.get('SNOWFLAKE_USER',      'your_user'),
        'password':  os.environ.get('SNOWFLAKE_PASSWORD',  'your_password'),
        'warehouse': os.environ.get('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH'),
        'role':      os.environ.get('SNOWFLAKE_ROLE',      'ANALYST'),
    },

    # ── Bronze table locations ────────────────────────────────────────────────
    'bronze_tables': {
        'quotes':      'QUOTES_SCHEMA.QUOTES',
        'orders':      'ORDERS_SCHEMA.ORDERS',
        'users':       'USERS_SCHEMA.USERS',
        'accounts':    'ACCOUNTS_SCHEMA.ACCOUNT_STATUS',
        'experiments': 'STATSIG_SCHEMA.STATSIG_EXPERIMENTS',
        # Resolved at runtime after Silver materialises
        'inquiries':   'silver_inquiries',
        'all_exp':     'gold_experiment_analysis',
        'traffic':     'silver_traffic',
    },

    # ── Bronze → Silver column map ────────────────────────────────────────────
    'column_map': {
        # Quotes table
        'quote_id':            '_ID',
        'quote_user_id':       'USER',
        'quote_account_id':    'BILLING_ACCOUNT',
        'quote_created_at':    '_CONSTRUCTED',
        'quote_source':        'QUOTE_SOURCE',
        'quote_processes':     'PROCESSES',
        'quote_price':         'TOTAL',
        'quote_status':        'LAST_HISTORY_STATUS',
        # Orders table
        'order_id':            '_ID',
        'order_quote_id':      'QUOTE_ORDER_ID',
        'order_total':         'TOTAL',
        'order_bookings':      'BOOKINGS',
        'order_status':        'LAST_HISTORY_STATUS',
        'order_time':          'ORDER_TIME',
        'order_ship_date':     'SHIP_DATE',
        'order_payment_type':  'PAYMENT_TYPE',
        'order_country':       'SHIPPING_ADDRESS_COUNTRY',
        # Users table
        'user_id':             '_ID',
        'user_account_id':     'ACCOUNT',
        'user_email_flag':     'EMAIL_FLAG',
        'user_customer_flag':  'CURRENT_CUSTOMER_FLAG',
        # Account Status table
        'account_id':          'ACCOUNT_ID',
        'account_segment':     'CONSOLIDATED_BUSINESS_SEGMENT',
        'account_vertical':    'ACCOUNT_VERTICAL_MARKET',
        'account_country':     'BILLING_COUNTRY',
        'account_employees':   'NUMBER_OF_EMPLOYEES',
        # Statsig experiments table
        'exp_user_id':         'USER_ID',
        'exp_group_name':      'GROUP_NAME',
        'exp_experiment_id':   'EXPERIMENT_ID',
        'exp_experiment_name':   'EXPERIMENT_NAME',
        'exp_timestamp':       'TIMESTAMP',
        'exp_account_domain':  'ACCOUNT_DOMAIN',
        # Traffic table
        'traffic_date':        'DATE',
        'total_sessions':      'TOTAL_SESSIONS',
        'new_signups':         'NEW_SIGNUPS',
        'signed_in':           'SIGNED_IN',
        'inquiries_col':       'INQUIRIES',
        # Derived / canonical (what modules use internally)
        'inquiry_id':          'quote_id',
        'buyer_id':            'user_id',
        'converted':           'converted_to_order',
        'order_value':         'order_value',
        'platform':            'quote_source',
        'category':            'quote_processes',
        'variant':             'variant',
        'experiment_name':     'experiment_name',
    },

    # ── Segment value normalisation (applied in Silver) ───────────────────────
    'segment_map': {
        'Individuals':    'Individuals',
        'Small Business': 'SMB',
        'Medium Business':'Growth',
        'Large Business': 'Core',
        'Enterprise':     'Enterprise',
    },

    # ── Platform value normalisation (applied in Silver) ─────────────────────
    'platform_map': {
        'WEBAPP':     'web',
        'FUSION':     'desktop',
        'SOLIDWORKS': 'desktop',
    },

    # ── Silver exclusion filters ──────────────────────────────────────────────
    'cancelled_order_statuses': ['Order Cancelled'],
    'internal_domains':         ['xometry.com', 'staff.xometry.com', 'xometry.eu'],

    # ── Data quality thresholds (Silver cleaning + module pre-checks) ─────────
    'dedup_key':           'quote_id',
    'winsorise_pct':        99,
    'min_segment_size':     30,
    'null_ior_default':     0.18,
    'null_aov_default':     5000,
    'null_daily_traffic':   300,
}

# ── Backward-compat alias ─────────────────────────────────────────────────────
CLIENT_SCHEMA = SOURCE_CONFIG
CLIENT_SCHEMA['tables']  = SOURCE_CONFIG['bronze_tables']
CLIENT_SCHEMA['columns'] = SOURCE_CONFIG['column_map']

# ── CSV / Parquet source registry ─────────────────────────────────────────────
BRONZE_CSV_SOURCES: dict = {}
SCHEMA_REGISTRY:    dict = {}

def register_csv_source(alias: str, path: str, bronze_name: str = None) -> None:
    """Register a CSV or Parquet file as an additional Bronze source table.

    The Silver layer will pick it up automatically if an entry exists in
    SOURCE_CONFIG['column_map'] for the relevant columns.

    Example
    -------
    register_csv_source('events', '/data/user_events_export.csv')
    """
    bname = bronze_name or f'bronze_{alias}'
    BRONZE_CSV_SOURCES[alias] = {'path': path, 'bronze_name': bname}
    print(f'  ✅ CSV source registered: {alias} → {path}  (bronze table: {bname})')

def register_schema(alias: str, schema_path: str, table_name: str = '') -> None:
    """Register an additional DB table as a Bronze source at runtime."""
    full = f'{schema_path}.{table_name}' if table_name and '.' not in schema_path else schema_path
    SCHEMA_REGISTRY[alias] = {'schema': schema_path, 'table': table_name, 'full': full}
    SOURCE_CONFIG['bronze_tables'][alias] = full
    CLIENT_SCHEMA['tables'][alias] = full
    print(f'  ✅ Schema registered: {alias} → {full}')

# ─────────────────────────────────────────────────────────────────────────────
# SILVER SQL BUILDER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def col(canonical: str, table_hint: str = None) -> str:
    """Resolve canonical name → raw bronze column name for Silver SQL generation.

    Parameters
    ----------
    canonical   : The canonical column name used throughout Silver / Gold / modules
    table_hint  : Optional table alias to check table-specific overrides first
                  e.g. col('created_at', 'orders') checks 'orders.created_at' key
    """
    cols = SOURCE_CONFIG['column_map']
    if table_hint:
        tbl_key = f'{table_hint}.{canonical}'
        if tbl_key in cols:
            return cols[tbl_key]
    return cols.get(canonical, canonical)

def tbl(canonical: str) -> str:
    """Resolve canonical table name → bronze warehouse path or DuckDB table name."""
    tbls = SOURCE_CONFIG['bronze_tables']
    resolved = tbls.get(canonical, canonical)
    return resolved.strip('"').strip("'") if resolved else canonical

def tbl_quoted(canonical: str) -> str:
    return f'"{tbl(canonical)}"'

def resolve_columns(table_canonical: str, *canonical_cols) -> dict:
    """Resolve multiple columns for a table at once.

    Returns a dict mapping canonical_name → raw_column_name.
    Useful for building SELECT lists without repeated col() calls.

    Example
    -------
    c = resolve_columns('orders', 'order_id', 'order_total', 'order_status')
    sql = f"SELECT {c['order_id']}, {c['order_total']} FROM {tbl('orders')}"
    """
    return {c: col(c, table_canonical) for c in canonical_cols}

# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY UTILITIES  (shared across all three layers)
# ─────────────────────────────────────────────────────────────────────────────

def safe_query(sql: str, fallback=None):
    """Execute a DuckDB query with full error handling. Returns None on failure.
    Safe to call before Cell 5 — returns None if 'db' is not yet initialised.
    """
    try:
        _db = globals().get('db')
        if _db is None:
            return fallback() if callable(fallback) else None
        result = _db.execute(sql).df()
        return result if not result.empty else (fallback() if callable(fallback) else None)
    except Exception as e:
        logger.warning('Query failed (%s): %s', type(e).__name__, str(e)[:150])
        return fallback() if callable(fallback) else None

def safe_val(v, default=0.0):
    """Safely extract a scalar — guards against NaN, None, and numpy type errors."""
    try:
        x = float(v)
        return x if x == x else float(default)
    except (TypeError, ValueError):
        return float(default)

def winsorise(arr: 'np.ndarray', pct: int = None) -> 'np.ndarray':
    """Clip extreme outliers at the given percentile before statistical testing."""
    pct = pct or SOURCE_CONFIG.get('winsorise_pct', 99)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0: return arr
    upper = np.percentile(arr, pct)
    lower = np.percentile(arr, 100 - pct)
    return np.clip(arr, lower, upper)

def dedup_dataframe(df: 'pd.DataFrame', key_col: str = None) -> 'pd.DataFrame':
    """Remove duplicate rows on dedup_key. Keeps the last occurrence.
    Critical for event-level data where ETL pipelines double-fire.
    """
    key = key_col or SOURCE_CONFIG.get('dedup_key')
    if not key or key not in df.columns: return df
    n_before = len(df)
    df = df.drop_duplicates(subset=[key], keep='last').reset_index(drop=True)
    dropped = n_before - len(df)
    if dropped > 0:
        print(f'  ⚠️  Dedup: removed {dropped:,} duplicate rows on "{key}"')
        logger.warning('Dedup removed %d rows on %s', dropped, key)
    return df

def validate_experiment_data(df: 'pd.DataFrame', exp_name: str) -> dict:
    """Pre-analysis data quality checks. Returns dict with warnings, errors, ok flag."""
    report = {'warnings': [], 'errors': [], 'ok': True}
    if len(df) == 0:
        report['errors'].append('No rows found')
        report['ok'] = False
        return report
    for c_name in ['converted_to_order', 'variant', 'created_at']:
        if c_name not in df.columns:
            report['errors'].append(f'Required column missing: {c_name}')
            report['ok'] = False
            continue
        null_pct = df[c_name].isna().mean() * 100
        if null_pct > 5:
            report['warnings'].append(f'{c_name}: {null_pct:.1f}% null values')
    if 'variant' in df.columns:
        counts = df['variant'].value_counts()
        for v, c in counts.items():
            if c < SOURCE_CONFIG['min_segment_size']:
                report['warnings'].append(f'Variant "{v}" has only {c} rows')
        if len(counts) > 1 and counts.min() / counts.max() < 0.7:
            report['warnings'].append(
                f'Variant imbalance: ratio={counts.min()/counts.max():.2f} — possible SRM')
    if 'order_value' in df.columns:
        vals = df['order_value'].dropna()
        pos  = vals[vals > 0]
        if len(pos) > 10:
            p99, vmax = np.percentile(pos, 99), pos.max()
            if vmax > p99 * 10:
                report['warnings'].append(
                    f'Extreme outlier in order_value: max=${vmax:,.0f} vs p99=${p99:,.0f}. '
                    f'Winsorisation applied automatically.')
    report['ok'] = len(report['errors']) == 0
    return report

# ── Snowflake connector (used by Bronze ingestion in production mode) ─────────
def get_snowflake_conn():
    """Returns a Snowflake connection using credentials from SOURCE_CONFIG."""
    try:
        import snowflake.connector
        cfg = SOURCE_CONFIG['snowflake']
        conn = snowflake.connector.connect(
            account=cfg['account'], user=cfg['user'],
            password=cfg['password'], warehouse=cfg['warehouse'], role=cfg['role'])
        print(f'  ✅ Snowflake connected: {cfg["account"]} / {cfg["warehouse"]}')
        return conn
    except Exception as e:
        print(f'  ❌ Snowflake connection failed: {e}')
        print(f'     Set env vars: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD')
        return None

# ── Synthetic-mode column identity override ───────────────────────────────────
if USE_SYNTHETIC_DATA:
    _identity_cols = [
        'inquiry_id', 'buyer_id', 'converted', 'order_value',
        'created_at', 'platform', 'category', 'variant',
        'experiment_name', 'account_segment', 'country',
    ]
    for _n in _identity_cols:
        SOURCE_CONFIG['column_map'][_n] = _n
    SOURCE_CONFIG['column_map']['account_id']    = 'buyer_id'
    SOURCE_CONFIG['column_map']['converted']     = 'converted_to_order'
    SOURCE_CONFIG['column_map']['order_total']   = 'order_value'
    SOURCE_CONFIG['column_map']['traffic_date']  = 'date'
    SOURCE_CONFIG['column_map']['total_sessions']= 'total_sessions'
    SOURCE_CONFIG['column_map']['new_signups']   = 'new_signups'
    SOURCE_CONFIG['column_map']['signed_in']     = 'signed_in'
    CLIENT_SCHEMA['columns'] = SOURCE_CONFIG['column_map']

def _refresh_runtime_constants() -> None:
    global SEGMENTS, PLATFORMS, CATEGORIES, COUNTRIES
    for attr, key in [('SEGMENTS','segments'),('PLATFORMS','platforms'),
                      ('CATEGORIES','categories'),('COUNTRIES','countries')]:
        vals = SOURCE_CONFIG.get(key, [])
        if vals: globals()[attr] = list(vals)


mode = {'synthetic': '🧪 Synthetic (POC)', 'csv': '📁 CSV Files', 'production': '❄️  Snowflake'}.get(DATA_MODE, DATA_MODE)
print(f'✅ Source Config + Bronze Schema loaded — Mode: {mode}')

# ─────────────────────────────────────────────────────────────────────────────
# CSV MODE SETUP  (only needed when DATA_MODE = 'csv')
#
# Call register_csv_source() once per table below.
# The alias must match a key in SOURCE_CONFIG['bronze_tables'] above.
#
# Example:
#   register_csv_source('quotes',      'exports/quotes_2024.csv')
#   register_csv_source('orders',      'exports/orders_2024.csv')
#   register_csv_source('users',       'exports/users.csv')
# ─────────────────────────────────────────────────────────────────────────────
print(f'   Client   : {SOURCE_CONFIG["client_name"]}')
print(f'   Dedup key: {SOURCE_CONFIG["dedup_key"]}')
print(f'   Winsorise: {SOURCE_CONFIG["winsorise_pct"]}th percentile')
print()
if USE_SYNTHETIC_DATA:
    print('   ┌─ Medallion path (synthetic) ─────────────────────────────────────────')
    print('   │  Bronze  → Cell 5  : generate raw DataFrames, register bronze_* tables')
    print('   │  Silver  → Cell 5-S: DuckDB views — canonicalise, clean, unify sources')
    print('   │  Gold    → Cell 6  : DuckDB views — cohorts, dim breakdowns, time-series')
    print('   └──────────────────────────────────────────────────────────────────────')

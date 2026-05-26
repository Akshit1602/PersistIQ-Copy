import pandas as pd
import numpy as np
import duckdb

# ─────────────────────────────────────────────────────────────────────────────
# CELL 3-AUTO — Bronze-Auto: Production Config Rebuild
#
# Reads from CONTINUM_STATE when bootstrapped; otherwise a clean no-op.
# ─────────────────────────────────────────────────────────────────────────────

DATA_PATH = 'synthetic'   # updated below if production_ready

def _build_source_config_from_state(state_schema: dict) -> dict:
    """
    Convert CONTINUM_STATE['client_schema'] (produced by Module [1]) into
    the full SOURCE_CONFIG structure expected by col(), tbl(), Silver SQL,
    and all downstream helpers.
    """
    mapping     = state_schema.get('mapping', {})
    table_map   = mapping.get('table_mapping', {})
    column_map  = mapping.get('column_mapping', {})
    client_name = state_schema.get('client_name', 'Unknown')
    conn_cfg    = state_schema.get('connection', {})

    columns = dict(column_map)
    for c in [
        'inquiry_id', 'buyer_id', 'converted', 'order_value', 'created_at',
        'platform', 'category', 'variant', 'experiment_name', 'account_segment',
        'country', 'order_total', 'traffic_date', 'account_id',
        'quote_id', 'quote_user_id', 'quote_account_id', 'quote_created_at',
        'quote_source', 'quote_processes', 'quote_price', 'quote_status',
        'order_id', 'order_quote_id', 'order_bookings', 'order_status',
        'order_time', 'order_ship_date', 'order_payment_type', 'order_country',
        'user_id', 'user_account_id', 'user_email_flag', 'user_customer_flag',
        'account_vertical', 'account_country', 'account_employees',
        'exp_user_id', 'exp_group_name', 'exp_experiment_id',
        'exp_timestamp', 'exp_account_domain',
    ]:
        columns.setdefault(c, c)

    cfg = {
        'client_name': client_name,
        'snowflake': {
            'account':   conn_cfg.get('account',   os.environ.get('SNOWFLAKE_ACCOUNT', '')),
            'user':      conn_cfg.get('user',       os.environ.get('SNOWFLAKE_USER', '')),
            'password':  conn_cfg.get('password',   os.environ.get('SNOWFLAKE_PASSWORD', '')),
            'warehouse': conn_cfg.get('warehouse',  os.environ.get('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH')),
            'role':      conn_cfg.get('role',       os.environ.get('SNOWFLAKE_ROLE', 'ANALYST')),
        },
        'bronze_tables': {
            'quotes':      table_map.get('quotes',      ''),
            'orders':      table_map.get('orders',      ''),
            'users':       table_map.get('users',       ''),
            'accounts':    table_map.get('accounts',    ''),
            'experiments': table_map.get('experiments', ''),
            'inquiries':   'silver_inquiries',    # resolved after Silver runs
            'all_exp':     'gold_experiment_analysis',
            'traffic':     'silver_traffic',
        },
        'column_map':   columns,
        'segment_map':  state_schema.get('segment_map',  {}),
        'platform_map': state_schema.get('platform_map', {}),
        'cancelled_order_statuses': state_schema.get('cancelled_order_statuses', []),
        'internal_domains':         state_schema.get('internal_domains',         []),
        'dedup_key':          state_schema.get('dedup_key',        'inquiry_id'),
        'winsorise_pct':      state_schema.get('winsorise_pct',    99),
        'min_segment_size':   state_schema.get('min_segment_size', 30),
        'null_ior_default':   state_schema.get('null_ior_default', 0.18),
        'null_aov_default':   state_schema.get('null_aov_default', 5000),
        'null_daily_traffic': state_schema.get('null_daily_traffic', 300),
        'segments':   state_schema.get('segments',   []),
        'platforms':  state_schema.get('platforms',  []),
        'categories': state_schema.get('categories', []),
        'countries':  state_schema.get('countries',  []),
    }
    cfg['tables']  = cfg['bronze_tables']
    cfg['columns'] = cfg['column_map']
    return cfg


def _validate_bronze_connection(cfg: dict) -> bool:
    """
    Lightweight connectivity check: opens a real Snowflake connection,
    runs SELECT 1, and closes it. Uses only cfg['snowflake'] — does NOT
    reference db (DuckDB), which is created later in Cell 5.
    """
    sf_cfg = cfg.get('snowflake', {})
    if not sf_cfg.get('account'):
        print('     ⚠️  No Snowflake account configured — skipping probe.')
        return True   # optimistic pass; Cell 5 will surface real errors
    try:
        import snowflake.connector as _sf
        _probe_conn = _sf.connect(
            account=sf_cfg['account'],   user=sf_cfg['user'],
            password=sf_cfg['password'], warehouse=sf_cfg['warehouse'],
            role=sf_cfg.get('role', 'ANALYST'),
            login_timeout=10,
        )
        _probe_conn.cursor().execute('SELECT 1')
        _probe_conn.close()
        return True
    except Exception as e:
        print(f'     ⚠️  Snowflake connection probe failed: {e}')
        return False


# ─── Main execution ──────────────────────────────────────────────────────────
_state = globals().get('CONTINUM_STATE', {})

if _state.get('mode') != 'production_ready' or _state.get('client_schema') is None:
    print('  ℹ️  Cell 3-Auto: mode is not production_ready — using existing Cell 3 config.')
    DATA_PATH = 'synthetic'

else:
    print('  🔧 Cell 3-Auto: production_ready detected — rebuilding SOURCE_CONFIG...')

    SOURCE_CONFIG = _build_source_config_from_state(_state['client_schema'])
    CLIENT_SCHEMA = SOURCE_CONFIG   # keep alias live
    USE_SYNTHETIC_DATA = False

    print(f'     Client: {SOURCE_CONFIG["client_name"]}')
    print('     Validating Bronze connection...', end=' ')
    _conn_ok = _validate_bronze_connection(SOURCE_CONFIG)
    print('✅' if _conn_ok else '❌')

    if not _conn_ok:
        print('  ⚠️  Connection failed — falling back to synthetic mode.')
        USE_SYNTHETIC_DATA = True
        DATA_PATH = 'synthetic'
    else:
        DATA_PATH = 'production'
        print(f'  ✅ SOURCE_CONFIG rebuilt. Bronze → Silver → Gold pipeline ready.')
        print(f'     Bronze tables: {", ".join(k+"→"+v for k,v in SOURCE_CONFIG["bronze_tables"].items() if v and "silver" not in v and "gold" not in v)}')
        CLIENT_SCHEMA = SOURCE_CONFIG
        CLIENT_SCHEMA['tables']  = SOURCE_CONFIG['bronze_tables']
        CLIENT_SCHEMA['columns'] = SOURCE_CONFIG['column_map']
        try:
            _refresh_runtime_constants()
        except NameError:
            pass

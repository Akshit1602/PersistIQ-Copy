import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class SchemaDriftWarning:
    table: str
    added_cols: list
    removed_cols: list
    dtype_changes: dict

    def __str__(self):
        parts = []
        if self.removed_cols:
            parts.append(f"REMOVED cols (will be NULL in Silver): {self.removed_cols}")
        if self.added_cols:
            parts.append(f"NEW cols (ignored by Silver): {self.added_cols}")
        if self.dtype_changes:
            changes = ', '.join(f'{c}: {old}→{new}' for c, (old, new) in self.dtype_changes.items())
            parts.append(f"DTYPE changes: {changes}")
        return f"Schema drift on '{self.table}': " + " | ".join(parts)

class BronzeIngestionGateway:
    """
    Single entry point for all data entering the Bronze layer.

    Responsibilities
    ────────────────
    1. ALLOWLIST  — only tables declared in ALLOWED_TABLES reach DuckDB.
    2. VALIDATION — checks columns, row count, and schema drift on each push.
    3. SEPARATION — enforces Bronze = raw paths only; Silver config is separate.
    4. PUSH MODE  — ETL/ELT tools call register_etl_push(); no code change needed.
    5. PULL MODE  — direct Snowflake/DB pull via pull_from_snowflake().

    Usage (push from ETL/ELT tool)
    ───────────────────────────────
        gateway = BronzeIngestionGateway(db, SOURCE_CONFIG)
        gateway.register_etl_push('quotes',    df_raw_quotes)
        gateway.register_etl_push('orders',    df_raw_orders)
        gateway.register_etl_push('users',     df_raw_users)
        # 'accounts' not sent → stays empty, Silver view still runs (nullable)
        status = gateway.get_status()

    Usage (pull mode — original Snowflake approach)
    ────────────────────────────────────────────────
        gateway.pull_from_snowflake(conn, tables=['quotes','orders','experiments'])
    """

    # ── Canonical set of tables this platform understands ────────────────────
    ALLOWED_TABLES = {
        'quotes', 'orders', 'users', 'accounts', 'experiments', 'traffic',
    }

    # ── Required canonical columns per table (from SOURCE_CONFIG column_map) ─
    REQUIRED_COLUMNS: dict = {
        'quotes':      ['_ID', 'USER', 'BILLING_ACCOUNT', '_CONSTRUCTED'],
        'orders':      ['_ID', 'QUOTE_ORDER_ID', 'TOTAL', 'LAST_HISTORY_STATUS'],
        'users':       ['_ID', 'ACCOUNT'],
        'accounts':    ['ACCOUNT_ID', 'CONSOLIDATED_BUSINESS_SEGMENT'],
        'experiments': ['USER_ID', 'GROUP_NAME', 'EXPERIMENT_ID', 'EXPERIMENT_NAME', 'TIMESTAMP'],
        'traffic':     ['DATE', 'TOTAL_SESSIONS'],
    }

    def __init__(self, db, source_config: dict):
        self._db             = db
        self._cfg            = source_config
        self._registered     : dict[str, dict] = {}   # alias → {rows, cols, bronze_name}
        self._schema_baseline: dict[str, dict] = {}   # alias → {col_name: dtype}
        self._drift_log      : list[SchemaDriftWarning] = []
        self._push_mode      = False   # True once first ETL push arrives
        print('  ✅ BronzeIngestionGateway initialised')
        print(f'     Allowed tables: {sorted(self.ALLOWED_TABLES)}')
        print(f'     Mode: pull (default) — call register_etl_push() to switch to push mode')

    # ── Public API ──────────────────────────────────────────────────────────

    def register_etl_push(
        self,
        table_alias: str,
        df: 'pd.DataFrame',
        *,
        allow_empty: bool = False,
        schema_drift_policy: str = 'warn',   # 'warn' | 'raise' | 'ignore'
    ) -> bool:
        """
        Called by an ETL/ELT tool to push a raw table into the Bronze layer.

        Parameters
        ──────────
        table_alias        : canonical alias ('quotes', 'orders', etc.)
        df                 : raw DataFrame — not yet renamed or transformed
        allow_empty        : if False, rejects tables with 0 rows
        schema_drift_policy: what to do when schema differs from baseline

        Returns True on success, False on validation failure.
        """
        self._push_mode = True
        alias = table_alias.lower().strip()

        # ── Gate 1: allowlist ──────────────────────────────────────────────
        if alias not in self.ALLOWED_TABLES:
            print(f'  ❌ Gateway REJECTED "{alias}": not in ALLOWED_TABLES')
            print(f'     Allowed: {sorted(self.ALLOWED_TABLES)}')
            print(f'     To add it: BronzeIngestionGateway.ALLOWED_TABLES.add("{alias}")')
            return False

        # ── Gate 2: row count ─────────────────────────────────────────────
        if len(df) == 0 and not allow_empty:
            print(f'  ⚠️  Gateway WARNING "{alias}": empty DataFrame — skipped')
            print(f'     To allow empty tables: register_etl_push(..., allow_empty=True)')
            return False

        # ── Gate 3: required columns ──────────────────────────────────────
        required = self.REQUIRED_COLUMNS.get(alias, [])
        # In synthetic mode, required cols are already canonical → skip check
        if not globals().get('USE_SYNTHETIC_DATA', True):
            missing = [c for c in required if c not in df.columns]
            if missing:
                print(f'  ❌ Gateway REJECTED "{alias}": missing required columns: {missing}')
                print(f'     Available columns: {list(df.columns)[:20]}')
                print(f'     Fix: update SOURCE_CONFIG[\'column_map\'] or the ETL mapping.')
                return False

        # ── Gate 4: schema drift detection ───────────────────────────────
        drift = self._detect_schema_drift(alias, df)
        if drift:
            self._drift_log.append(drift)
            msg = str(drift)
            if schema_drift_policy == 'raise':
                raise RuntimeError(f'  ❌ Schema drift — {msg}')
            elif schema_drift_policy == 'warn':
                print(f'  ⚠️  {msg}')
                print(f'     Silver SQL will produce NULLs for missing columns.')
                print(f'     Consider re-running Module [2] Pipeline Health after loading.')
            # 'ignore' → proceed silently

        # ── Register in DuckDB ────────────────────────────────────────────
        bronze_name = f'bronze_{alias}'
        self._db.register(bronze_name, df)
        self._registered[alias] = {
            'rows':        len(df),
            'cols':        list(df.columns),
            'bronze_name': bronze_name,
            'source':      'etl_push',
        }
        # Update schema baseline on first registration
        if alias not in self._schema_baseline:
            self._schema_baseline[alias] = {c: str(df[c].dtype) for c in df.columns}

        print(f'  ✅ Bronze "{alias}" registered → {bronze_name}  ({len(df):,} rows, {len(df.columns)} cols)')
        return True

    def pull_from_snowflake(
        self,
        conn,
        tables: Optional[list] = None,
        row_limit: Optional[int] = None,
    ) -> dict:
        """
        Pull mode: fetch tables directly from Snowflake and register them.

        Parameters
        ──────────
        conn      : active snowflake.connector connection
        tables    : list of aliases to pull (defaults to all ALLOWED_TABLES)
        row_limit : for sampling / testing (None = full table)

        Returns dict of {alias: row_count} for successfully pulled tables.
        """
        to_pull = [t for t in (tables or sorted(self.ALLOWED_TABLES))
                   if t in self.ALLOWED_TABLES]
        results = {}
        limit_sql = f' LIMIT {row_limit}' if row_limit else ''

        for alias in to_pull:
            raw_path = self._cfg.get('bronze_tables', {}).get(alias, '')
            if not raw_path or raw_path.startswith('silver_') or raw_path.startswith('gold_'):
                print(f'  ⚠️  Skipping "{alias}": no raw source path configured')
                continue
            try:
                cursor = conn.cursor()
                sql    = f'SELECT * FROM {raw_path}{limit_sql}'
                cursor.execute(sql)
                df_raw = cursor.fetch_pandas_all()
                cursor.close()
                ok = self.register_etl_push(alias, df_raw)
                if ok:
                    results[alias] = len(df_raw)
            except Exception as e:
                print(f'  ❌ Failed to pull "{alias}" from {raw_path}: {e}')

        return results

    def get_status(self) -> dict:
        """Return a summary of what has been registered vs what is missing."""
        registered  = set(self._registered.keys())
        missing     = self.ALLOWED_TABLES - registered
        status = {
            'mode':           'push' if self._push_mode else 'pull',
            'registered':     {k: v['rows'] for k, v in self._registered.items()},
            'missing':        sorted(missing),
            'drift_warnings': len(self._drift_log),
            'gateway_ready':  len(missing) == 0,
        }

        print()
        print('  ┌─ Bronze Gateway Status ──────────────────────────────────────')
        print(f'  │  Mode             : {status["mode"]}')
        for alias, rows in status['registered'].items():
            print(f'  │  ✅ {alias:<18} : {rows:>9,} rows')
        for alias in status['missing']:
            print(f'  │  ⚠️  {alias:<18} : NOT REGISTERED')
        if self._drift_log:
            print(f'  │  ⚠️  Schema drift warnings: {len(self._drift_log)}')
            for d in self._drift_log:
                print(f'  │      {str(d)[:80]}')
        print(f'  │  Gateway ready    : {"✅ YES" if status["gateway_ready"] else "❌ NO — missing tables above"}')
        print('  └─────────────────────────────────────────────────────────────')
        return status

    def add_allowed_table(self, alias: str, required_cols: list = None):
        """
        Extend the allowlist at runtime for client-specific tables.
        Required for any non-standard source before register_etl_push().

        Example
        ───────
            gateway.add_allowed_table('nps_scores', required_cols=['USER_ID','SCORE','DATE'])
            gateway.register_etl_push('nps_scores', df_nps)
        """
        self.ALLOWED_TABLES.add(alias.lower())
        if required_cols:
            self.REQUIRED_COLUMNS[alias.lower()] = required_cols
        print(f'  ✅ Added "{alias}" to allowlist  (required: {required_cols or "none"})')

    # ── Private helpers ──────────────────────────────────────────────────────

    def _detect_schema_drift(
        self,
        alias: str,
        df: 'pd.DataFrame',
    ) -> Optional[SchemaDriftWarning]:
        """Compare df schema against stored baseline. Returns drift report or None."""
        baseline = self._schema_baseline.get(alias)
        if not baseline:
            return None   # first registration → set baseline, no drift yet

        current_cols  = set(df.columns)
        baseline_cols = set(baseline.keys())

        added         = sorted(current_cols - baseline_cols)
        removed       = sorted(baseline_cols - current_cols)
        dtype_changes = {
            c: (baseline[c], str(df[c].dtype))
            for c in current_cols & baseline_cols
            if str(df[c].dtype) != baseline[c]
        }

        if added or removed or dtype_changes:
            return SchemaDriftWarning(alias, added, removed, dtype_changes)
        return None

# ── SILVER_CONFIG — separate from Bronze SOURCE_CONFIG ───────────────────────

SILVER_CONFIG = {
    # ── Transformation thresholds (Silver cleaning + module pre-checks) ───
    'winsorise_pct':      99,
    'min_segment_size':   30,
    'null_ior_default':   0.18,
    'null_aov_default':   5000.0,
    'null_daily_traffic': 300,

    # ── Segment / platform normalisation (applied in Silver SQL) ──────────
    'segment_map': {
        'Individuals':    'Individuals',
        'Small Business': 'SMB',
        'Medium Business':'Growth',
        'Large Business': 'Core',
        'Enterprise':     'Enterprise',
    },
    'platform_map': {
        'WEBAPP':     'web',
        'FUSION':     'desktop',
        'SOLIDWORKS': 'desktop',
    },

    # ── Exclusion filters ─────────────────────────────────────────────────
    'cancelled_order_statuses': ['Order Cancelled'],
    'internal_domains':         ['xometry.com', 'staff.xometry.com', 'xometry.eu'],

    # ── Dedup key for event-level data ────────────────────────────────────
    'dedup_key': 'quote_id',
}

print('✅ Cell 3b: BronzeIngestionGateway class + SILVER_CONFIG loaded')
print('   Usage (ETL push mode):')
print('     bronze_gateway = BronzeIngestionGateway(db, SOURCE_CONFIG)')
print('     bronze_gateway.register_etl_push("quotes",    df_raw_quotes)')
print('     bronze_gateway.register_etl_push("orders",    df_raw_orders)')
print('     bronze_gateway.register_etl_push("users",     df_raw_users)')
print('     bronze_gateway.get_status()   # ← shows what is missing')
print()
print('   Usage (Snowflake pull mode):')
print('     bronze_gateway.pull_from_snowflake(conn, tables=["quotes","orders","experiments"])')
print()
print('   Add a non-standard table:')
print('     bronze_gateway.add_allowed_table("nps_scores", required_cols=["USER_ID","SCORE"])')
print('     bronze_gateway.register_etl_push("nps_scores", df_nps)')

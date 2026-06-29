from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field, validator


# ─────────────────────────────────────────────────────────────────────────────
# INGESTION MODE
# ─────────────────────────────────────────────────────────────────────────────

class IngestionMode(str, Enum):
    CSV         = "csv"
    SNOWFLAKE   = "snowflake"
    BIGQUERY    = "bigquery"
    DATABRICKS  = "databricks"
    DUCKDB      = "duckdb"


# ─────────────────────────────────────────────────────────────────────────────
# BRONZE LAYER CONTRACT
# ─────────────────────────────────────────────────────────────────────────────

class SnowflakeConfig(BaseModel):
    account:   str
    user:      str
    password:  str
    warehouse: str = "COMPUTE_WH"
    role:      str = "ANALYST"
    database:  Optional[str] = None
    schema_:   Optional[str] = Field(None, alias="schema")

    class Config:
        populate_by_name = True


class BigQueryConfig(BaseModel):
    project:          str
    dataset:          str
    credentials_path: str = ""


class DatabricksConfig(BaseModel):
    host:      str
    http_path: str
    token:     str
    catalog:   str = "main"
    schema_:   str = Field("default", alias="schema")

    class Config:
        populate_by_name = True


class BronzeTableMap(BaseModel):
    quotes:      str = ""
    orders:      str = ""
    users:       str = ""
    accounts:    str = ""
    experiments: str = ""
    inquiries:   str = "silver_inquiries"
    traffic:     str = ""
    events:      str = ""
    feedback:    str = ""
    crm_notes:   str = ""

    def get(self, canonical: str, default: str = "") -> str:
        return getattr(self, canonical, default) or default


class BronzeColumnMap(BaseModel):
    # Quotes
    quote_id:            str = ""
    quote_user_id:       str = ""
    quote_account_id:    str = ""
    quote_created_at:    str = ""
    quote_source:        str = ""
    quote_processes:     str = ""
    quote_price:         str = ""
    quote_status:        str = ""
    # Orders
    order_id:            str = ""
    order_quote_id:      str = ""
    order_total:         str = ""
    order_bookings:      str = ""
    order_status:        str = ""
    order_time:          str = ""
    order_ship_date:     str = ""
    order_payment_type:  str = ""
    order_country:       str = ""
    # Users
    user_id:             str = ""
    user_account_id:     str = ""
    user_email_flag:     str = ""
    user_customer_flag:  str = ""
    # Accounts
    account_id:          str = ""
    account_segment:     str = ""
    account_vertical:    str = ""
    account_country:     str = ""
    account_employees:   str = ""
    # Experiments
    exp_user_id:         str = ""
    exp_group_name:      str = ""
    exp_experiment_id:   str = ""
    exp_experiment_name: str = ""
    exp_timestamp:       str = ""
    exp_account_domain:  str = ""
    # Canonical aliases (used by Silver SQL)
    inquiry_id:          str = "quote_id"
    buyer_id:            str = "user_id"
    converted:           str = "converted_to_order"
    order_value:         str = "order_value"
    platform:            str = "quote_source"
    category:            str = "quote_processes"
    variant:             str = "variant"
    experiment_name:     str = "experiment_name"

    def resolve(self, canonical: str) -> str:
        v = getattr(self, canonical, None)
        return v if v else canonical


class BronzeIngestionContract(BaseModel):
    client_name:                str
    mode:                       IngestionMode
    schema_version:             int                  = Field(default=1, ge=1)
    dedup_key:                  str                  = "inquiry_id"
    winsorise_pct:              int                  = Field(default=99, ge=90, le=100)
    min_segment_size:           int                  = Field(default=30, ge=5)
    null_ior_default:           float                = 0.18
    null_aov_default:           float                = 5000.0
    null_daily_traffic:         float                = 300.0
    cancelled_order_statuses:   List[str]            = Field(default_factory=list)
    internal_domains:           List[str]            = Field(default_factory=list)
    bronze_tables:              BronzeTableMap       = Field(default_factory=BronzeTableMap)
    column_map:                 BronzeColumnMap      = Field(default_factory=BronzeColumnMap)
    segment_map:                Dict[str, str]       = Field(default_factory=dict)
    platform_map:               Dict[str, str]       = Field(default_factory=dict)
    snowflake:                  Optional[SnowflakeConfig]  = None
    bigquery:                   Optional[BigQueryConfig]   = None
    databricks:                 Optional[DatabricksConfig] = None

    class Config:
        frozen = True


# ─────────────────────────────────────────────────────────────────────────────
# SILVER LAYER CONTRACT
# ─────────────────────────────────────────────────────────────────────────────

class SilverViewContract(BaseModel):
    guaranteed_columns: List[str] = [
        "inquiry_id", "buyer_id", "account_segment", "platform",
        "created_at", "converted_to_order", "order_value",
        "variant", "experiment_name", "category", "country",
    ]
    nullable_columns:        List[str] = ["order_value", "variant", "experiment_name"]
    non_nullable_columns:    List[str] = ["inquiry_id", "buyer_id", "created_at", "converted_to_order"]
    freshness_sla_hours:     int       = 24
    row_count_min:           Optional[int] = None
    schema_version:          int       = 1
    produced_at:             Optional[datetime] = None

    def validate_dataframe(self, df: Any) -> List[str]:
        violations = []
        for col in self.guaranteed_columns:
            if col not in df.columns:
                violations.append(f"[MISSING_COL] Guaranteed column absent: '{col}'")
        for col in self.non_nullable_columns:
            if col in df.columns:
                null_pct = df[col].isna().mean() * 100
                if null_pct > 1:
                    violations.append(f"[NULL_VIOLATION] {col}: {null_pct:.1f}% nulls (non-nullable)")
        if self.row_count_min is not None and len(df) < self.row_count_min:
            violations.append(f"[ROW_COUNT] Got {len(df):,}, need ≥ {self.row_count_min:,}")
        return violations


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA VERSIONING
# ─────────────────────────────────────────────────────────────────────────────

INGESTION_API_VERSION  = "2.0.0"
SILVER_SCHEMA_VERSION  = 3
GOLD_SCHEMA_VERSION    = 2

class SchemaVersion(BaseModel):
    subsystem:   str
    version:     int
    released_at: str
    breaking:    bool = False
    notes:       str  = ""


SCHEMA_VERSION_HISTORY = [
    SchemaVersion(subsystem="silver", version=1, released_at="2024-01-01",
                  notes="Initial schema"),
    SchemaVersion(subsystem="silver", version=2, released_at="2024-06-01", breaking=True,
                  notes="Added has_billing_profile, price_tier columns"),
    SchemaVersion(subsystem="silver", version=3, released_at="2025-01-01", breaking=False,
                  notes="Added semi-structured event + feedback sources"),
    SchemaVersion(subsystem="gold", version=1, released_at="2024-01-01",
                  notes="Initial gold layer"),
    SchemaVersion(subsystem="gold", version=2, released_at="2024-09-01", breaking=True,
                  notes="Added causal pre-period cohort columns"),
]


__all__ = [
    "IngestionMode",
    "SnowflakeConfig", "BigQueryConfig", "DatabricksConfig",
    "BronzeTableMap", "BronzeColumnMap", "BronzeIngestionContract",
    "SilverViewContract",
    "INGESTION_API_VERSION", "SILVER_SCHEMA_VERSION", "GOLD_SCHEMA_VERSION",
    "SchemaVersion", "SCHEMA_VERSION_HISTORY",
]

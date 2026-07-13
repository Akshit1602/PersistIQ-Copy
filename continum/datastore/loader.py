from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import duckdb
import pandas as pd

logger = logging.getLogger("continum.datastore.loader")


def load_csvs(data_dir: str) -> Dict[str, pd.DataFrame]:
    from continum.contextmate.synthetic_generator import ensure_sample_data

    ensure_sample_data(data_dir)
    p = Path(data_dir)
    datasets = {}
    for name in ["users", "accounts", "quotes", "orders", "experiments"]:
        path = p / f"{name}.csv"
        datasets[name] = pd.read_csv(path, dtype=str, low_memory=False)
        logger.info("Loaded %s: %d rows", name, len(datasets[name]))
    return datasets


def register_bronze(db: duckdb.DuckDBPyConnection, datasets: Dict[str, pd.DataFrame]) -> None:
    db.register("bronze_users_raw", datasets["users"])
    db.register("bronze_accounts_raw", datasets["accounts"])
    db.register("bronze_quotes_raw", datasets["quotes"])
    db.register("bronze_orders_raw", datasets["orders"])
    db.register("bronze_experiments_raw", datasets["experiments"])
    logger.info("Bronze layer registered (%d tables)", 5)


def build_silver_layer(db: duckdb.DuckDBPyConnection) -> None:
    logger.info("Building Silver layer")

    db.execute(
        """
    CREATE OR REPLACE TABLE silver_users AS
    SELECT
        _id AS user_id, _deleted AS is_deleted,
        _constructed AS user_created_at, _updated AS user_updated_at,
        email_address, billing_email_address, email_address_verified, email_flag,
        full_name, first_name, last_name,
        account AS erp_account_id, company, erp_company_name, phone_number,
        first_quote_time, first_quote_time_et, last_quote_time, last_quote_time_et,
        first_order_time, first_order_time_et, last_order_time, last_order_time_et,
        current_customer_flag, total_quotes, total_bookings, total_orders,
        is_instant_quote_user, is_instant_quote_customer_user,
        is_active_teamspace_user, is_created_teamspace_user,
        is_partner_user, is_staff_user, is_excluded_user, is_instant_quote_funnel_user,
        tax_exempt, accepted_teamspace_invitation_at, min_teamspace_created_at,
        split_part(email_address, '@', -1) AS email_domain
    FROM bronze_users_raw
    """
    )

    db.execute(
        """
    CREATE OR REPLACE TABLE silver_quotes AS
    SELECT
        _id AS quote_id, _deleted AS is_deleted,
        _constructed AS quote_created_at, _constructed_et AS quote_created_at_et,
        order_id, quote_order_id, order_time, order_time_et,
        "user" AS user_id, email_address, erp_account_id,
        last_history_status AS quote_last_history_status, order_last_history_status,
        quote_source, is_manually_quoted, is_manually_quoted_type,
        manual_quote_audit_segment, parts_should_rfq,
        selected_price_tier, customer_selectable_tiers,
        quote_total_price_bin, quote_total_price_bin_sales, quote_total_quantity_bin,
        is_0_bookings_flag, customer_flag, order_customer_flag, quoter_flag,
        quote_rank_customer, quote_rank_account,
        configuration_status, is_quote_fully_configured,
        has_multiple_parts, has_new_processes, processes,
        process_top_dollars, process_group_top_dollars, quote_part_processes,
        is_itar, xom_eu_quoted, allow_eu_quoting, requires_freight, shipping_method,
        TRY_CAST(subtotal AS DOUBLE) AS subtotal,
        TRY_CAST(total AS DOUBLE) AS total,
        TRY_CAST(total_etl AS DOUBLE) AS total_etl,
        TRY_CAST(bookings AS DOUBLE) AS bookings,
        TRY_CAST(bookings_with_shipping AS DOUBLE) AS bookings_with_shipping,
        TRY_CAST(line_items_discount AS DOUBLE) AS line_items_discount,
        TRY_CAST(line_items_shipping AS DOUBLE) AS line_items_shipping,
        TRY_CAST(line_items_tax AS DOUBLE) AS line_items_tax,
        TRY_CAST(part_count AS DOUBLE) AS part_count,
        TRY_CAST(num_parts_in_quote AS DOUBLE) AS num_parts_in_quote,
        TRY_CAST(total_quote_quantity AS DOUBLE) AS total_quote_quantity,
        lead_time_days, auto_quoted_lead_time,
        calendar_days_to_order_conversion, business_days_to_order_conversion
    FROM bronze_quotes_raw
    """
    )

    db.execute(
        """
    CREATE OR REPLACE TABLE silver_orders AS
    SELECT
        _id AS order_id, _deleted AS is_deleted, quote_id,
        "user" AS user_id, email_address, billing_account,
        order_time, order_time_et, last_history_status AS order_last_history_status,
        last_history_time, due_date, due_date_et, original_due_date, ship_date,
        min_cancelled_et AS order_cancelled_at_et,
        quote_source, is_manually_quoted, is_manually_quoted_type,
        coupon, selected_price_tier,
        order_total_price_bin, order_total_price_bin_sales, order_total_quantity_bin,
        customer_flag, customer_flag_aggregated, quoter_customer_flag,
        quote_rank_customer, quote_rank_account, order_rank_customer, order_rank_account,
        is_quote_reorder, quote_reorder_count,
        days_since_last_order, months_since_last_order,
        contains_fab5_process, contains_sheet_cutting_process,
        is_fully_outsourced, is_fully_shipped, is_unproven,
        order_ship_status, asana_late_shipment_category,
        has_new_processes, has_rma_job, payment_type,
        TRY_CAST(subtotal AS DOUBLE) AS subtotal,
        TRY_CAST(total AS DOUBLE) AS total,
        TRY_CAST(total_etl AS DOUBLE) AS total_etl,
        TRY_CAST(bookings AS DOUBLE) AS bookings,
        TRY_CAST(bookings_with_shipping AS DOUBLE) AS bookings_with_shipping,
        TRY_CAST(cancelled_part_bookings AS DOUBLE) AS cancelled_part_bookings,
        TRY_CAST(line_items_discount_total AS DOUBLE) AS line_items_discount_total,
        TRY_CAST(line_items_shipping_total AS DOUBLE) AS line_items_shipping_total,
        TRY_CAST(line_items_tax AS DOUBLE) AS line_items_tax,
        lead_time_days, TRY_CAST(part_count AS DOUBLE) AS part_count,
        TRY_CAST(total_order_quantity AS DOUBLE) AS total_order_quantity,
        days_from_quote_to_order, shipping_method,
        shipping_address_country, shipping_address_country_code,
        shipping_address_state, shipping_address_city
    FROM bronze_orders_raw
    """
    )

    db.execute(
        """
    CREATE OR REPLACE TABLE silver_experiments AS
    SELECT
        experiment_id, group_id, group_name,
        user_id, timestamp AS exposure_at,
        account_id, account_domain, quote_id, order_id,
        job_id, partner_id, user_dimensions
    FROM bronze_experiments_raw
    """
    )

    # Backward-compat inquiry view
    logger.info("Creating backward compatibility inquiry view")
    db.execute(
        """
    CREATE OR REPLACE VIEW silver_inquiries AS
    SELECT
        q.quote_id AS inquiry_id, q.user_id,
        q.quote_created_at AS inquiry_time, q.total_etl AS inquiry_value,
        q.quote_source, q.process_group_top_dollars, q.bookings_with_shipping,
        e.experiment_id AS experiment_name, e.group_name AS variant,
        MIN(e.exposure_at) OVER (PARTITION BY e.user_id, e.experiment_id) AS first_exposure_at,
        q.*
    FROM silver_quotes q
    LEFT JOIN silver_experiments e ON q.user_id = e.user_id
    """
    )
    logger.info("Silver layer built")


def build_gold_layer(db: duckdb.DuckDBPyConnection) -> None:
    logger.info("Building Gold experiment mart")

    db.execute(
        """
    CREATE OR REPLACE TABLE gold_experiment_mart AS
    WITH quotes_by_user AS (
        SELECT user_id,
            COUNT(*) AS quote_count,
            COUNT(CASE WHEN order_id IS NOT NULL THEN 1 END) AS quotes_with_orders,
            SUM(bookings_with_shipping) AS total_quote_bookings,
            SUM(total_etl) AS total_quote_value,
            MAX(quote_created_at) AS last_quote_at,
            FIRST(process_group_top_dollars) AS primary_process
        FROM silver_quotes GROUP BY user_id
    ),
    orders_by_user AS (
        SELECT user_id, COUNT(*) AS order_count,
            SUM(bookings_with_shipping) AS total_order_bookings,
            MAX(order_time) AS last_order_at
        FROM silver_orders GROUP BY user_id
    )
    SELECT
        u.user_id, u.email_domain, u.current_customer_flag,
        a.CONSOLIDATED_BUSINESS_SEGMENT AS account_segment,
        COALESCE(q.quote_count, 0) AS quote_count,
        COALESCE(q.quotes_with_orders, 0) AS quotes_with_orders,
        COALESCE(o.order_count, 0) AS order_count,
        COALESCE(q.total_quote_value, 0) AS total_quote_value,
        COALESCE(q.total_quote_bookings, 0) AS total_quote_bookings,
        COALESCE(o.total_order_bookings, 0) AS total_order_bookings,
        q.last_quote_at, o.last_order_at, q.primary_process
    FROM silver_users u
    LEFT JOIN bronze_accounts_raw a ON u.erp_account_id = a._id
    LEFT JOIN quotes_by_user q ON u.user_id = q.user_id
    LEFT JOIN orders_by_user o ON u.user_id = o.user_id
    """
    )

    logger.info("Building Gold experiment analysis table")
    db.execute(
        """
    CREATE OR REPLACE TABLE gold_experiment_analysis AS
    WITH exposures AS (
        SELECT e.user_id, e.experiment_id, e.group_name AS variant, e.exposure_at AS created_at,
               e.quote_id, e.order_id, e.account_id
        FROM silver_experiments e
        WHERE e.group_name IS NOT NULL
    ),
    joined AS (
        SELECT ex.user_id, ex.experiment_id, ex.variant, ex.created_at,
               q.total_etl AS quote_value, q.bookings_with_shipping AS quote_bookings,
               q.process_group_top_dollars, q.shipping_method,
               CASE WHEN ex.order_id IS NOT NULL THEN 1 ELSE 0 END AS converted_to_order,
               TRY_CAST(o.total_etl AS DOUBLE) AS order_value,
               o.bookings_with_shipping AS order_bookings,
               o.shipping_address_country, o.order_ship_status,
               u.email_domain, u.company, u.current_customer_flag,
               a.CONSOLIDATED_BUSINESS_SEGMENT AS account_segment
        FROM exposures ex
        LEFT JOIN silver_quotes  q ON ex.quote_id = q.quote_id
        LEFT JOIN silver_orders  o ON ex.order_id = o.order_id
        LEFT JOIN silver_users   u ON ex.user_id  = u.user_id
        LEFT JOIN bronze_accounts_raw a ON u.erp_account_id = a._id
    )
    SELECT j.*, j.experiment_id AS experiment_name
    FROM joined j
    WHERE j.variant IS NOT NULL
    """
    )

    n = db.execute("SELECT COUNT(*) FROM gold_experiment_analysis").fetchone()[0]
    logger.info("Gold mart ready: %d rows in gold_experiment_analysis", n)


def list_experiments(db: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    try:
        return db.execute(
            """
            SELECT experiment_name,
                   COUNT(DISTINCT variant)  AS n_variants,
                   COUNT(*)                 AS n_rows,
                   MIN(created_at)::DATE    AS start_date,
                   MAX(created_at)::DATE    AS end_date
            FROM gold_experiment_analysis
            WHERE experiment_name IS NOT NULL
            GROUP BY experiment_name
            ORDER BY n_rows DESC
        """
        ).df()
    except Exception as e:
        logger.warning("list_experiments failed: %s", e)
        return pd.DataFrame()


def setup_database(data_dir: str = "./sample_data") -> duckdb.DuckDBPyConnection:
    datasets = load_csvs(data_dir)
    db = duckdb.connect(":memory:")
    register_bronze(db, datasets)
    build_silver_layer(db)
    build_gold_layer(db)
    return db


__all__ = [
    "load_csvs",
    "register_bronze",
    "build_silver_layer",
    "build_gold_layer",
    "list_experiments",
    "setup_database",
]

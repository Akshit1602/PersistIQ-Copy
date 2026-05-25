from __future__ import annotations

import logging
import os
import random
from datetime import timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("continum.synthetic")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

SEGMENTS  = ["Core", "Growth", "Enterprise", "Individuals"]
PLATFORMS = ["web", "mobile"]
COUNTRIES = ["US", "UK", "CA", "AU", "IN"]
CATEGORIES = ["Category A", "Category B", "Category C", "Category D", "Category E"]

BASELINE_IOR = {"Core": 0.195, "Growth": 0.165, "Enterprise": 0.240, "Individuals": 0.130}
GMV_PER_ORDER = {"Core": 4800, "Growth": 2200, "Enterprise": 18000, "Individuals": 950}
SEGMENT_WEIGHTS = {"Core": 0.35, "Growth": 0.30, "Enterprise": 0.20, "Individuals": 0.15}

HIST_START = pd.Timestamp("2022-01-01")
EXP_START  = pd.Timestamp("2025-01-01")
EXP_END    = pd.Timestamp("2025-08-31")

EXPERIMENT_REGISTRY = [
    {"experiment_name": "billing_profile_confirmation_v2",
     "variants": ["control", "treatment"], "status": "concluded",
     "start_date": "2025-02-14", "end_date": "2025-06-30",
     "gt_uplift": {"Core": +0.014, "Growth": -0.015, "Enterprise": +0.006, "Individuals": -0.004}},
    {"experiment_name": "social_signin_v1",
     "variants": ["control", "google_only", "multi_provider"], "status": "shipped",
     "start_date": "2025-01-07", "end_date": "2025-03-31",
     "gt_uplift": {"Core": +0.009, "Growth": +0.014, "Enterprise": +0.004, "Individuals": +0.016}},
    {"experiment_name": "summary_page_cta_test",
     "variants": ["control", "treatment"], "status": "running",
     "start_date": "2025-05-01", "end_date": None,
     "gt_uplift": {"Core": +0.004, "Growth": -0.002, "Enterprise": +0.006, "Individuals": +0.001}},
    {"experiment_name": "pricing_display_4way",
     "variants": ["control", "bold_price", "anchoring", "urgency"], "status": "concluded",
     "start_date": "2024-10-01", "end_date": "2024-12-15",
     "gt_uplift": {"Core": +0.003, "Growth": +0.004, "Enterprise": +0.001, "Individuals": +0.003}},
    {"experiment_name": "mobile_nav_redesign",
     "variants": ["control", "treatment"], "status": "running",
     "start_date": "2025-06-15", "end_date": None,
     "gt_uplift": {"Core": +0.007, "Growth": +0.009, "Enterprise": +0.003, "Individuals": +0.006}},
    {"experiment_name": "enterprise_bulk_upload",
     "variants": ["control", "treatment"], "status": "stopped",
     "start_date": "2025-03-10", "end_date": "2025-04-02",
     "gt_uplift": {"Core": -0.002, "Growth": -0.004, "Enterprise": +0.008, "Individuals": -0.001}},
    {"experiment_name": "real_time_quote_preview",
     "variants": ["control", "treatment"], "status": "shipped",
     "start_date": "2024-11-01", "end_date": "2024-12-20",
     "gt_uplift": {"Core": +0.018, "Growth": +0.014, "Enterprise": +0.009, "Individuals": +0.012}},
    {"experiment_name": "chat_support_prompt",
     "variants": ["control", "treatment"], "status": "concluded",
     "start_date": "2025-04-01", "end_date": "2025-05-15",
     "gt_uplift": {"Core": +0.006, "Growth": +0.011, "Enterprise": +0.002, "Individuals": +0.013}},
    {"experiment_name": "personalised_recommendations_v1",
     "variants": ["control", "treatment"], "status": "not_started",
     "start_date": "2025-09-15", "end_date": None,
     "gt_uplift": {}},
    {"experiment_name": "loyalty_tier_upgrade",
     "variants": ["control", "treatment"], "status": "not_started",
     "start_date": "2025-10-01", "end_date": None,
     "gt_uplift": {}},
]


def generate_all(output_dir: str = "./sample_data", n_users: int = 25_000,
                 seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    random.seed(seed)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    logger.info("Generating synthetic datasets (n_users=%d)", n_users)

    accounts_df = _gen_accounts(rng, n_users)
    users_df    = _gen_users(rng, accounts_df, n_users)
    quotes_df, orders_df = _gen_quotes_orders(rng, users_df, accounts_df)
    experiments_df = _gen_experiments(rng, users_df, accounts_df)

    datasets = {
        "users":       users_df,
        "accounts":    accounts_df,
        "quotes":      quotes_df,
        "orders":      orders_df,
        "experiments": experiments_df,
    }

    for name, df in datasets.items():
        path = Path(output_dir) / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("  Wrote %s (%d rows)", path, len(df))

    logger.info("Synthetic data generation complete.")
    return datasets


# ─────────────────────────────────────────────────────────────────────────────
# GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def _gen_accounts(rng, n_users: int) -> pd.DataFrame:
    n_accounts = max(1, n_users // 8)
    seg_vals = rng.choice(SEGMENTS, size=n_accounts,
                          p=[SEGMENT_WEIGHTS[s] for s in SEGMENTS])
    return pd.DataFrame({
        "_id":                              [f"ACC{i:06d}" for i in range(n_accounts)],
        "CONSOLIDATED_BUSINESS_SEGMENT":    seg_vals,
        "company_name":                     [f"Company {i}" for i in range(n_accounts)],
        "country":                          rng.choice(COUNTRIES, size=n_accounts,
                                                        p=[0.55, 0.15, 0.12, 0.10, 0.08]),
    })


def _gen_users(rng, accounts_df: pd.DataFrame, n_users: int) -> pd.DataFrame:
    acc_ids = accounts_df["_id"].values
    account = rng.choice(acc_ids, size=n_users)
    acc_map = accounts_df.set_index("_id")

    created_at = pd.Timestamp("2020-01-01") + pd.to_timedelta(
        rng.integers(0, (EXP_END - pd.Timestamp("2020-01-01")).days, size=n_users), unit="D"
    )
    return pd.DataFrame({
        "_id":                     [f"USR{i:07d}" for i in range(n_users)],
        "_constructed":             created_at,
        "_updated":                 created_at + pd.to_timedelta(
                                        rng.integers(0, 90, size=n_users), unit="D"),
        "_deleted":                 False,
        "email_address":            [f"user{i}@example.com" for i in range(n_users)],
        "billing_email_address":    [f"billing{i}@example.com" for i in range(n_users)],
        "email_address_verified":   rng.choice([True, False], size=n_users, p=[0.85, 0.15]),
        "email_flag":               rng.choice(["COMPANY_EMAIL", "PERSONAL_EMAIL"],
                                               size=n_users, p=[0.60, 0.40]),
        "full_name":                [f"User {i}" for i in range(n_users)],
        "first_name":               [f"First{i}" for i in range(n_users)],
        "last_name":                [f"Last{i}" for i in range(n_users)],
        "account":                  account,
        "company":                  [acc_map.loc[a, "company_name"] for a in account],
        "erp_company_name":         [acc_map.loc[a, "company_name"] for a in account],
        "phone_number":             [f"+1555{i:07d}" for i in range(n_users)],
        "current_customer_flag":    rng.choice([True, False], size=n_users, p=[0.40, 0.60]),
        "total_quotes":             rng.integers(0, 25, size=n_users),
        "total_bookings":           rng.integers(0, 15, size=n_users),
        "total_orders":             rng.integers(0, 10, size=n_users),
        "is_instant_quote_user":    rng.choice([True, False], size=n_users, p=[0.55, 0.45]),
        "is_instant_quote_customer_user": rng.choice([True, False], size=n_users, p=[0.30, 0.70]),
        "is_active_teamspace_user": rng.choice([True, False], size=n_users, p=[0.20, 0.80]),
        "is_created_teamspace_user": rng.choice([True, False], size=n_users, p=[0.15, 0.85]),
        "is_partner_user":          rng.choice([True, False], size=n_users, p=[0.05, 0.95]),
        "is_staff_user":            rng.choice([True, False], size=n_users, p=[0.02, 0.98]),
        "is_excluded_user":         rng.choice([True, False], size=n_users, p=[0.01, 0.99]),
        "is_instant_quote_funnel_user": rng.choice([True, False], size=n_users, p=[0.45, 0.55]),
        "tax_exempt":               rng.choice([True, False], size=n_users, p=[0.10, 0.90]),
        "signup_date":              created_at,
        "first_quote_time":         None,
        "first_quote_time_et":      None,
        "last_quote_time":          None,
        "last_quote_time_et":       None,
        "first_order_time":         None,
        "first_order_time_et":      None,
        "last_order_time":          None,
        "last_order_time_et":       None,
        "accepted_teamspace_invitation_at": None,
        "min_teamspace_created_at": None,
    })


def _gen_quotes_orders(rng, users_df: pd.DataFrame,
                       accounts_df: pd.DataFrame):
    acc_map = accounts_df.set_index("_id")
    rows_q, rows_o = [], []
    q_idx = 0
    o_idx = 0

    for _, user in users_df.iterrows():
        user_id = user["_id"]
        acc_id  = user["account"]
        seg     = acc_map.loc[acc_id, "CONSOLIDATED_BUSINESS_SEGMENT"]
        base_ior = BASELINE_IOR.get(seg, 0.18)
        base_aov = GMV_PER_ORDER.get(seg, 3000)

        n_quotes = int(rng.integers(0, 8))
        for _ in range(n_quotes):
            created = pd.Timestamp("2022-06-01") + pd.to_timedelta(
                int(rng.integers(0, (EXP_END - pd.Timestamp("2022-06-01")).days)), unit="D")
            converted = bool(rng.random() < base_ior)
            order_id  = f"ORD{o_idx:08d}" if converted else None
            q_id = f"QT{q_idx:09d}"
            aov  = float(rng.normal(base_aov, base_aov * 0.4)) if converted else 0.0
            aov  = max(100.0, aov)
            total = float(rng.normal(aov * 0.85, aov * 0.15))
            total = max(50.0, total)

            rows_q.append({
                "_id":                          q_id,
                "_deleted":                     False,
                "_constructed":                 created,
                "_constructed_et":              created,
                "order_id":                     order_id,
                "quote_order_id":               order_id,
                "order_time":                   created + timedelta(days=int(rng.integers(1, 10))) if converted else None,
                "order_time_et":                None,
                "user":                         user_id,
                "email_address":                user["email_address"],
                "erp_account_id":               acc_id,
                "last_history_status":          "ordered" if converted else "quoted",
                "order_last_history_status":    "completed" if converted else None,
                "quote_source":                 rng.choice(["instant_quote", "manual", "rfq"],
                                                            p=[0.6, 0.25, 0.15]),
                "is_manually_quoted":           bool(rng.random() < 0.25),
                "is_manually_quoted_type":      None,
                "manual_quote_audit_segment":   None,
                "parts_should_rfq":             bool(rng.random() < 0.10),
                "selected_price_tier":          rng.choice(["standard", "premium", "economy"],
                                                            p=[0.6, 0.2, 0.2]),
                "customer_selectable_tiers":    None,
                "quote_total_price_bin":        "$1k-$5k" if total < 5000 else "$5k+",
                "quote_total_price_bin_sales":  None,
                "quote_total_quantity_bin":     "1-10",
                "is_0_bookings_flag":           not converted,
                "customer_flag":                "new" if rng.random() < 0.4 else "returning",
                "order_customer_flag":          "new" if rng.random() < 0.4 else "returning",
                "quoter_flag":                  None,
                "quote_rank_customer":          1,
                "quote_rank_account":           1,
                "configuration_status":         "complete",
                "is_quote_fully_configured":    True,
                "has_multiple_parts":           bool(rng.random() < 0.30),
                "has_new_processes":            bool(rng.random() < 0.15),
                "processes":                    "CNC,Sheet Metal",
                "process_top_dollars":          None,
                "process_group_top_dollars":    rng.choice(CATEGORIES),
                "quote_part_processes":         None,
                "is_itar":                      bool(rng.random() < 0.02),
                "xom_eu_quoted":                False,
                "allow_eu_quoting":             True,
                "requires_freight":             bool(rng.random() < 0.20),
                "shipping_method":              rng.choice(["standard", "expedited", "overnight"],
                                                            p=[0.7, 0.2, 0.1]),
                "subtotal":                     round(total * 0.90, 2),
                "total":                        round(total, 2),
                "total_etl":                    round(total, 2),
                "bookings":                     round(aov, 2) if converted else 0,
                "bookings_with_shipping":       round(aov * 1.05, 2) if converted else 0,
                "line_items_discount":          round(total * 0.05, 2),
                "line_items_shipping":          round(total * 0.03, 2),
                "line_items_tax":               round(total * 0.08, 2),
                "part_count":                   int(rng.integers(1, 12)),
                "num_parts_in_quote":           int(rng.integers(1, 12)),
                "total_quote_quantity":         int(rng.integers(1, 50)),
                "lead_time_days":               int(rng.integers(5, 30)),
                "auto_quoted_lead_time":        int(rng.integers(5, 20)),
                "calendar_days_to_order_conversion": int(rng.integers(1, 14)) if converted else None,
                "business_days_to_order_conversion": int(rng.integers(1, 10)) if converted else None,
            })
            q_idx += 1

            if converted:
                rows_o.append({
                    "_id":                          order_id,
                    "_deleted":                     False,
                    "quote_id":                     q_id,
                    "user":                         user_id,
                    "email_address":                user["email_address"],
                    "billing_account":              acc_id,
                    "order_time":                   created + timedelta(days=int(rng.integers(1, 10))),
                    "order_time_et":                None,
                    "last_history_status":          "completed",
                    "last_history_time":            None,
                    "due_date":                     created + timedelta(days=int(rng.integers(10, 30))),
                    "due_date_et":                  None,
                    "original_due_date":            None,
                    "ship_date":                    None,
                    "min_cancelled_et":             None,
                    "quote_source":                 "instant_quote",
                    "is_manually_quoted":           False,
                    "is_manually_quoted_type":      None,
                    "coupon":                       None,
                    "selected_price_tier":          "standard",
                    "order_total_price_bin":        "$1k-$5k",
                    "order_total_price_bin_sales":  None,
                    "order_total_quantity_bin":     "1-10",
                    "customer_flag":                "returning",
                    "customer_flag_aggregated":     "returning",
                    "quoter_customer_flag":         None,
                    "quote_rank_customer":          1,
                    "quote_rank_account":           1,
                    "order_rank_customer":          1,
                    "order_rank_account":           1,
                    "is_quote_reorder":             bool(rng.random() < 0.20),
                    "quote_reorder_count":          0,
                    "days_since_last_order":        int(rng.integers(0, 180)),
                    "months_since_last_order":      int(rng.integers(0, 12)),
                    "contains_fab5_process":        bool(rng.random() < 0.30),
                    "contains_sheet_cutting_process": bool(rng.random() < 0.20),
                    "is_fully_outsourced":          bool(rng.random() < 0.10),
                    "is_fully_shipped":             bool(rng.random() < 0.80),
                    "is_unproven":                  bool(rng.random() < 0.05),
                    "order_ship_status":            rng.choice(["On Time", "Late", "Early"],
                                                                p=[0.75, 0.15, 0.10]),
                    "asana_late_shipment_category": None,
                    "has_new_processes":            False,
                    "has_rma_job":                  False,
                    "payment_type":                 rng.choice(["credit_card", "net30", "po"],
                                                                p=[0.60, 0.30, 0.10]),
                    "subtotal":                     round(aov * 0.90, 2),
                    "total":                        round(aov, 2),
                    "total_etl":                    round(aov, 2),
                    "bookings":                     round(aov, 2),
                    "bookings_with_shipping":       round(aov * 1.05, 2),
                    "cancelled_part_bookings":      0,
                    "line_items_discount_total":    round(aov * 0.05, 2),
                    "line_items_shipping_total":    round(aov * 0.03, 2),
                    "line_items_tax":               round(aov * 0.08, 2),
                    "lead_time_days":               int(rng.integers(5, 30)),
                    "part_count":                   int(rng.integers(1, 12)),
                    "total_order_quantity":         int(rng.integers(1, 50)),
                    "total_quantity_unproven":      0,
                    "days_from_quote_to_order":     int(rng.integers(1, 14)),
                    "shipping_method":              "standard",
                    "shipping_address_country":     acc_map.loc[acc_id, "country"],
                    "shipping_address_country_code": acc_map.loc[acc_id, "country"],
                    "shipping_address_state":       "CA",
                    "shipping_address_city":        "San Francisco",
                })
                o_idx += 1

    return pd.DataFrame(rows_q), pd.DataFrame(rows_o)


def _gen_experiments(rng, users_df: pd.DataFrame,
                     accounts_df: pd.DataFrame) -> pd.DataFrame:
    acc_map = accounts_df.set_index("_id")
    rows = []
    user_ids = users_df["_id"].values
    user_accounts = users_df["account"].values

    for exp in EXPERIMENT_REGISTRY:
        if exp["status"] == "not_started":
            continue
        start = pd.Timestamp(exp["start_date"])
        end   = pd.Timestamp(exp["end_date"]) if exp["end_date"] else EXP_END

        # Sample ~3,000 users per experiment
        n_sample = min(3000, len(user_ids))
        sampled_idx = rng.choice(len(user_ids), size=n_sample, replace=False)

        for idx in sampled_idx:
            uid     = user_ids[idx]
            acc_id  = user_accounts[idx]
            seg     = acc_map.loc[acc_id, "CONSOLIDATED_BUSINESS_SEGMENT"]

            variant = rng.choice(exp["variants"])
            ts = start + pd.to_timedelta(
                int(rng.integers(0, max(1, (end - start).days))), unit="D")

            rows.append({
                "experiment_id": exp["experiment_name"],
                "group_id":      variant,
                "group_name":    variant,
                "user_id":       uid,
                "timestamp":     ts,
                "account_id":    acc_id,
                "account_domain": f"{seg.lower()}.com",
                "quote_id":      f"QT{rng.integers(0, 999999999):09d}",
                "order_id":      f"ORD{rng.integers(0, 99999999):08d}" if rng.random() < 0.18 else None,
                "job_id":        None,
                "partner_id":    None,
                "user_dimensions": f'{{"segment":"{seg}"}}',
            })

    return pd.DataFrame(rows)


def ensure_sample_data(output_dir: str = "./sample_data") -> bool:
    required = ["users.csv", "accounts.csv", "quotes.csv", "orders.csv", "experiments.csv"]
    p = Path(output_dir)
    if all((p / f).exists() for f in required):
        return True
    logger.info("sample_data not found — generating synthetic datasets...")
    generate_all(output_dir)
    return True


__all__ = ["generate_all", "ensure_sample_data", "EXPERIMENT_REGISTRY"]

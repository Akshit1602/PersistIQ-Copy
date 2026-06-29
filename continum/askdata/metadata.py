"""
Dataset metadata for the AskData LangGraph engine (ported from the upstream
AskData project).

Differences from upstream:
  * File paths are resolved against the bundled ``datasets/`` directory so the
    engine works regardless of the process working directory.
  * ``get_metadata`` returns a copy with absolute ``path`` values filled in.

To add a dataset: drop the file(s) in ``datasets/`` and add an entry to
``METADATA`` (see the upstream README, also bundled alongside this package).
The active dataset is chosen via the ``ACTIVE_DATASET`` env var (default
``sample`` — the A/B experimentation campaign data).
"""
import copy
import os
from pathlib import Path

_DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


METADATA = {
    "shell": {
        "domain_context": "expert data analyst for Shell Retail (India)",
        "files": [
            {
                "path": "Shell__dim_station__preview_.csv",
                "table": "dim_station",
                "format": "csv",
            },
            {
                "path": "Shell__fact_station_day_product__preview_.csv",
                "table": "fact_station",
                "format": "csv",
                "date_col": "date",
                "date_format": "%d-%m-%Y",
            },
        ],
        "table_descriptions": {
            "dim_station": "Contains master data about Shell fuel stations including location, facilities, and opening details.",
            "fact_station": "Contains daily transactional and operational data for each station and product family.",
        },
        "column_descriptions": {
            "dim_station": {
                "station_id": "Unique identifier for each Shell fuel station (e.g., BLR-001).",
                "station_name": "Display name of the station used for business reporting.",
                "city": "Metro/urban location where the station operates.",
                "cluster": "Operational grouping of stations for performance management.",
                "latitude": "Geographic latitude of the station, useful for mapping and routing.",
                "longitude": "Geographic longitude of the station.",
                "opened_year": "Year the station started operations, helpful for lifecycle and maturity analysis.",
                "has_ev_charger": "Indicates if the station supports EV charging (1 = Yes, 0 = No).",
                "cstore_size_sqft": "Size of the Shell convenience store in square feet, used for revenue potential analysis.",
            },
            "fact_station": {
                "date": "Daily date for transaction reporting in YYYY-MM-DD format.",
                "station_id": "Unique identifier linking to dim_station for each Shell site.",
                "city": "City-level filter for localized performance analytics.",
                "product_family": "Fuel type sold: Petrol, Diesel, or Premium.",
                "shell_price_inr_per_liter": "Shell retail selling price per liter in INR.",
                "comp_min_price_inr_per_liter_within_3km": "Minimum competitor price detected within a 3km radius.",
                "price_gap_inr_per_liter": "Pricing difference: Shell price minus competitor minimum price (positive -> Shell is pricier).",
                "liters_sold": "Total fuel volume sold for the product that day (in liters).",
                "revenue_inr": "Total revenue generated from fuel sales in INR.",
                "gross_margin_inr": "Gross margin earned on fuel sales for the day in INR.",
                "downtime_minutes": "Pump/equipment downtime duration impacting sales opportunity.",
                "stockout_flag": "Indicates if a product was unavailable for any duration (1 = Stockout, 0 = Normal).",
                "promo_active": "Indicates whether a discount/offer/promotion was active (1 = Yes, 0 = No).",
                "competitors_within_3km": "Number of competitor stations competing for the same catchment area.",
                "weather_heat_index": "Approximate temperature/humidity index that influences fuel demand.",
                "rainfall_mm": "Rainfall amount that may impact footfall and demand fluctuations.",
                "holiday_flag": "Marks national/major holidays that drive demand changes (1 = Holiday).",
                "footfall_estimate": "Estimated number of customers visiting the station on that day.",
                "cstore_transactions": "Number of completed transactions in the convenience store.",
                "cstore_revenue_inr": "Revenue generated from non-fuel C-store sales.",
                "loyalty_signups": "Number of new enrollments into Shell loyalty programmes.",
                "ev_charger_sessions": "Count of EV charging sessions (if facility exists).",
            },
        },
        "relationships": {
            "fact_station": {
                "station_id": {
                    "references": {"table": "dim_station", "column": "station_id"},
                    "relationship_type": "many_to_one",
                }
            }
        },
        "table_info_combined": (
            "dim_station(station_id, station_name, city, cluster, latitude, longitude, opened_year, has_ev_charger, cstore_size_sqft)\n"
            "fact_station(date, station_id, city, product_family, shell_price_inr_per_liter, "
            "comp_min_price_inr_per_liter_within_3km, price_gap_inr_per_liter, liters_sold, revenue_inr, gross_margin_inr, "
            "downtime_minutes, stockout_flag, promo_active, competitors_within_3km, weather_heat_index, rainfall_mm, "
            "holiday_flag, footfall_estimate, cstore_transactions, cstore_revenue_inr, loyalty_signups, ev_charger_sessions)\n"
        ),
        "suggested_questions": [
            "Which city has the highest total revenue?",
            "Compare gross margin by product family",
            "Show daily revenue trend for Bangalore",
        ],
    },
    "sample": {
        "domain_context": "expert business analyst for experimental retail campaign testing, specialized in A/B test analysis and cohort performance metrics",
        "files": [
            {
                "path": "Sample Dataset.xlsx",
                "table": "campaign_data",
                "format": "excel",
                "sheet_name": "Data",
            }
        ],
        "table_descriptions": {
            "campaign_data": "Contains experimental testing data for retail campaigns, including metrics for Treatment and Control groups across different customer cohorts and product hierarchy levels."
        },
        "column_descriptions": {
            "campaign_data": {
                "group_name": "The experimental group: 'Treatment' (received campaign) or 'Control' (baseline). Important for calculating incremental lift.",
                "cohort": "The customer segment targeted: 'Acquisition' (newly acquired) or 'Retention' (existing customers).",
                "frequency": "Customer shopping frequency category (e.g., how often they visit).",
                "HH_CNT": "Total Household count in this segment.",
                "L1_HH_CNT": "Household count at Level 1 (specific SKU/item level hierarchy).",
                "L1_HH_GMV": "Gross Merchandise Value (Revenue) generated at Level 1.",
                "L0_HH_CNT": "Household count at Level 0 (Category level hierarchy).",
                "L0_HH_GMV": "Gross Merchandise Value (Revenue) at Level 0.",
                "WMT_HH_CNT": "Household count at Walmart level (Total store/enterprise hierarchy).",
                "WMT_HH_GMV": "Gross Merchandise Value (Revenue) at Walmart level.",
                "New_L1": "Count of new customers who purchased at Level 1.",
                "Repeat_L1": "Count of repeat customers who purchased at Level 1.",
                "Reactivated_L1": "Count of reactivated (previously churned) customers who purchased at Level 1.",
                "Orders_L1": "Total number of orders at Level 1.",
                "Quantity_L1": "Total quantity of items sold at Level 1.",
                "New_L0": "Count of new customers who purchased at Level 0.",
                "Repeat_L0": "Count of repeat customers who purchased at Level 0.",
                "Reactivated_L0": "Count of reactivated customers who purchased at Level 0.",
                "Orders_L0": "Total number of orders at Level 0.",
                "Quantity_L0": "Total quantity of items sold at Level 0.",
                "New_WMT": "Count of new customers who purchased at Walmart level.",
                "Repeat_WMT": "Count of repeat customers who purchased at Walmart level.",
                "Reactivated_WMT": "Count of reactivated customers who purchased at Walmart level.",
                "Orders_WMT": "Total number of orders at Walmart level.",
                "Quantity_WMT": "Total quantity of items sold at Walmart level.",
            }
        },
        "relationships": {},
        "table_info_combined": (
            "campaign_data(group_name, cohort, frequency, HH_CNT, L1_HH_CNT, L1_HH_GMV, L0_HH_CNT, L0_HH_GMV, WMT_HH_CNT, WMT_HH_GMV, New_L1, Repeat_L1, Reactivated_L1, Orders_L1, Quantity_L1, New_L0, Repeat_L0, Reactivated_L0, Orders_L0, Quantity_L0, New_WMT, Repeat_WMT, Reactivated_WMT, Orders_WMT, Quantity_WMT)\n"
        ),
        "suggested_questions": [
            "Compare GMV between Treatment and Control groups",
            "What is the incremental lift for the Acquisition cohort?",
            "Which cohort responded best to the campaign?",
        ],
    },
    "experiments": {
        "source": "duckdb",
        "domain_context": (
            "expert experimentation analyst for MatchView web A/B tests "
            "(quote->order conversion funnel, control vs treatment variants)"
        ),
        "queries": {
            "experiment_results": "SELECT * FROM gold_experiment_analysis",
        },
        "table_descriptions": {
            "experiment_results": (
                "One row per user exposure to an experiment variant. Conversion rate = "
                "AVG(converted_to_order); compare variants within an experiment_name, or "
                "compare lift across experiments. created_at is the exposure date for trends."
            ),
        },
        "column_descriptions": {
            "experiment_results": {
                "experiment_name": "Experiment id, e.g. 'mobile_nav_redesign'. Filter or GROUP BY this.",
                "variant": "Experiment arm: 'control' vs one or more treatments (e.g. 'treatment', 'google_only', 'urgency').",
                "created_at": "Exposure date as YYYY-MM-DD text. Use for daily/weekly trends.",
                "converted_to_order": "1 if the exposed user placed an order, else 0. Conversion rate = AVG(converted_to_order).",
                "order_value": "Order revenue in USD when converted; NULL otherwise. AVG(order_value) = AOV among converters.",
                "quote_value": "Quoted amount in USD at exposure.",
                "quote_bookings": "Quote bookings amount (USD).",
                "order_bookings": "Order bookings amount (USD) when converted.",
                "account_segment": "Business segment of the user's account, e.g. 'Growth', 'Enterprise'.",
                "current_customer_flag": "Whether the user was already a customer at exposure.",
                "email_domain": "User's email domain.",
                "shipping_address_country": "Order shipping country (when converted).",
                "order_ship_status": "Order fulfilment status (when converted).",
                "process_group_top_dollars": "Top manufacturing process group for the quote.",
                "shipping_method": "Quote shipping method.",
                "company": "User's company name.",
                "user_id": "User id; use COUNT(DISTINCT user_id) for unique users.",
                "experiment_id": "Duplicate of experiment_name -- prefer experiment_name.",
            },
        },
        "relationships": {},
        "table_info_combined": (
            "experiment_results(user_id, experiment_id, experiment_name, variant, created_at, "
            "converted_to_order, order_value, quote_value, quote_bookings, order_bookings, "
            "account_segment, current_customer_flag, email_domain, company, "
            "shipping_address_country, order_ship_status, process_group_top_dollars, shipping_method)\n"
        ),
        "suggested_questions": [
            "Compare conversion rate by variant for mobile_nav_redesign",
            "Which experiment had the biggest conversion lift over control?",
            "Show the daily exposure count by variant for pricing_display_4way",
        ],
    },
}


def get_active_dataset_name() -> str:
    # Default to the live experiment warehouse (DuckDB-backed) so the Copilot
    # answers about the user's actual experiments, not the bundled retail demo.
    return os.getenv("ACTIVE_DATASET", "experiments")


def list_datasets() -> list:
    return list(METADATA.keys())


def get_metadata(dataset_name: str | None = None) -> dict:
    """Return metadata for the active (or named) dataset. File-backed datasets get
    absolute file paths; DuckDB-backed datasets (source="duckdb") carry SQL queries
    instead and skip path resolution."""
    name = dataset_name or get_active_dataset_name()
    meta = copy.deepcopy(METADATA.get(name, METADATA["sample"]))
    if meta.get("source") != "duckdb":
        for file_info in meta.get("files", []):
            file_info["path"] = str(_DATASETS_DIR / file_info["path"])
    return meta

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from continum.state import SchemaMetadata

# --- Omnichannel Dataset Metadata Registry ---
DATASET_METADATA: Dict[str, Dict[str, Any]] = {
    "ecomm": {
        "namespace_prefix": "ecomm_",
        "domain_name": "E-Commerce & Digital Marketplace",
        "tables": {
            "ecomm_accounts": "B2B accounts, buyer types, tiers, and industry classifications",
            "ecomm_users": "Individual user profiles linked to accounts with procurement roles",
            "ecomm_quotes": "Digital pricing quotes, total amounts, lead times, and approval statuses",
            "ecomm_quote_items": "Individual CAD parts, manufacturing processes, and materials",
            "ecomm_orders": "Completed e-commerce purchase orders and payment terms",
            "ecomm_user_events": "Web interaction logs (download_cad, request_checkout, view_quote)",
            "ecomm_experiments": "Online A/B test definitions, target metrics, and status",
            "ecomm_variants": "Traffic split variants (Control vs Treatment)",
            "ecomm_experiment_exposures": "Immutable point-in-time user unit exposure logs",
            "ecomm_experiment_results": "Calculated statistical lift, CUPED means, and p-values",
            "ecomm_learnings_archive": "Historical digital experiment outcomes and insights"
        },
        "joins": [
            "ecomm_users.account_id = ecomm_accounts.account_id",
            "ecomm_quotes.account_id = ecomm_accounts.account_id",
            "ecomm_quote_items.quote_id = ecomm_quotes.quote_id",
            "ecomm_orders.quote_id = ecomm_quotes.quote_id",
            "ecomm_user_events.user_id = ecomm_users.user_id",
            "ecomm_experiment_exposures.user_id = ecomm_users.user_id",
            "ecomm_experiment_results.experiment_id = ecomm_experiments.experiment_id"
        ],
        "default_metrics": ["Quote Approval Rate", "Average Order Value (AOV)", "CAD Download Engagement"]
    },
    "store": {
        "namespace_prefix": "store_",
        "domain_name": "Physical Retail Store",
        "tables": {
            "store_stores": "Physical store locations, regions, formats, and square footage",
            "store_customers": "Loyalty program members and primary store affiliations",
            "store_pos_transactions": "Point-of-sale register transaction records and payment methods",
            "store_pos_transaction_items": "Scanned SKUs, product categories, quantities, and prices",
            "store_foot_traffic_events": "In-store optical sensor zone dwell times and foot traffic",
            "store_experiments": "Store-level cluster-randomized trials and retail hypotheses",
            "store_variants": "In-store layout, kiosk, or display variant configurations",
            "store_experiment_assignments": "Store or customer unit assignment logs",
            "store_experiment_results": "Calculated store-level statistical lift and p-values",
            "store_learnings_archive": "Historical physical retail test outcomes and insights"
        },
        "joins": [
            "store_customers.primary_store_id = store_stores.store_id",
            "store_pos_transactions.store_id = store_stores.store_id",
            "store_pos_transactions.customer_id = store_customers.customer_id",
            "store_pos_transaction_items.transaction_id = store_pos_transactions.transaction_id",
            "store_foot_traffic_events.store_id = store_stores.store_id",
            "store_experiment_assignments.store_id = store_stores.store_id",
            "store_experiment_results.experiment_id = store_experiments.experiment_id"
        ],
        "default_metrics": ["Basket Size", "Endcap Dwell Time", "Self-Checkout Conversion", "Register Wait Time"]
    }
}


class IndexExperimentsInput(BaseModel):
    current_metadata: SchemaMetadata
    experiments: List[Dict[str, Any]] = Field(
        ..., description="List of experiment dictionaries to catalogue"
    )


def catalog_experiments(input_data: IndexExperimentsInput) -> SchemaMetadata:
    """
    Updates SchemaMetadata with discovered running or historical experiment logs.
    """
    meta = input_data.current_metadata
    meta.cataloged_experiments.extend(input_data.experiments)
    return meta
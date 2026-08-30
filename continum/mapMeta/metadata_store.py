from typing import Any, Dict, List

from pydantic import BaseModel, Field

from continum.state import SchemaMetadata

DATASET_METADATA: Dict[str, Dict[str, Any]] = {
    "ecomm": {
        "namespace": "ecomm",
        "table_prefix": "ecomm_",
        "description": "E-Commerce Digital Storefront Dataset",
        "tables": {
            "ecomm_accounts": "User organization accounts and subscription tier details",
            "ecomm_users": "Registered digital platform users and profiles",
            "ecomm_user_events": "Web and app activity clickstream telemetry",
            "ecomm_quotes": "Instant CAD price quotes generated",
            "ecomm_quote_items": "Line items per CAD pricing quote",
            "ecomm_orders": "Completed e-commerce purchases and orders",
            "ecomm_metric_catalog": "Catalog of digital KPI definitions",
            "ecomm_experiments": "Digital A/B test definitions",
            "ecomm_variants": "Digital experiment treatment variations",
            "ecomm_experiment_exposures": "User exposures to e-commerce experiment variants",
            "ecomm_experiment_results": "Aggregated statistical test results for e-commerce tests",
            "ecomm_learnings_archive": "Historical learnings and takeaways for digital tests",
        },
        "join_keys": {
            "ecomm_users.account_id": "ecomm_accounts.account_id",
            "ecomm_user_events.user_id": "ecomm_users.user_id",
            "ecomm_quotes.user_id": "ecomm_users.user_id",
            "ecomm_quote_items.quote_id": "ecomm_quotes.quote_id",
            "ecomm_orders.user_id": "ecomm_users.user_id",
            "ecomm_experiment_exposures.user_id": "ecomm_users.user_id",
            "ecomm_experiment_exposures.experiment_id": "ecomm_experiments.experiment_id",
            "ecomm_variants.experiment_id": "ecomm_experiments.experiment_id",
        },
        "default_metrics": [
            "conversion_rate",
            "average_order_value",
            "quote_approval_rate",
            "instant_cad_pricing_lift",
        ],
    },
    "store": {
        "namespace": "store",
        "table_prefix": "store_",
        "description": "Physical Retail Store & Omnichannel Dataset",
        "tables": {
            "store_stores": "Physical retail store locations, formats, and square footage",
            "store_customers": "Loyalty program and store customer profiles",
            "store_foot_traffic_events": "In-store traffic sensors, zone dwell time, endcap visits",
            "store_pos_transactions": "Point-of-sale checkout register transactions",
            "store_pos_transaction_items": "Items purchased at POS register",
            "store_metric_catalog": "Catalog of physical store KPI definitions",
            "store_experiments": "Store-level Cluster Randomized Trial (CRT) test definitions",
            "store_variants": "Physical store experiment treatment variations",
            "store_experiment_assignments": "Store-level cluster assignment to experiment variants",
            "store_experiment_results": "Aggregated statistical CRT test results for store tests",
            "store_learnings_archive": "Historical learnings for physical store tests",
        },
        "join_keys": {
            "store_foot_traffic_events.store_id": "store_stores.store_id",
            "store_pos_transactions.store_id": "store_stores.store_id",
            "store_pos_transactions.customer_id": "store_customers.customer_id",
            "store_pos_transaction_items.transaction_id": "store_pos_transactions.transaction_id",
            "store_experiment_assignments.store_id": "store_stores.store_id",
            "store_experiment_assignments.experiment_id": "store_experiments.experiment_id",
            "store_variants.experiment_id": "store_experiments.experiment_id",
        },
        "default_metrics": [
            "basket_size",
            "zone_dwell_time",
            "foot_traffic_count",
            "register_checkout_velocity",
        ],
    },
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

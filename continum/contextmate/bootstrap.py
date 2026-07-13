from __future__ import annotations

import logging

from continum.contextmate.contracts import IngestionMode
from continum.datastore.stores import ContinumState

logger = logging.getLogger("continum.bootstrap")


def bootstrap_from_connection(
    mode: str,
    client_name: str = "client",
    db=None,
    **credentials,
) -> ContinumState:
    import duckdb

    if db is None:
        db = duckdb.connect(":memory:")

    ingestion_mode = IngestionMode(mode)  # noqa: F841

    state = ContinumState()
    state.org.set_client_config(
        client_name=client_name,
        schema_version=3,
        column_map=credentials.get("column_map", {}),
        segment_map=credentials.get("segment_map", {}),
        platform_map=credentials.get("platform_map", {}),
        approved_by="bootstrap_connection",
    )
    state.execution.set_bootstrap_state(mode, __import__("datetime").datetime.utcnow().isoformat())

    logger.info("Bootstrapped from %s connection for client: %s", mode, client_name)
    return state


__all__ = ["bootstrap_from_connection"]

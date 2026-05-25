from __future__ import annotations

import logging
from typing import Optional

from continum.core.ingestion.contracts import BronzeIngestionContract, IngestionMode
from continum.core.memory.stores import ContinumState

logger = logging.getLogger("continum.bootstrap")


def bootstrap_from_csv(
    csv_path: str,
    client_name: str = "client",
    db=None,
) -> ContinumState:
    import duckdb
    if db is None:
        db = duckdb.connect(":memory:")

    contract = BronzeIngestionContract(
        client_name=client_name,
        mode=IngestionMode.CSV,
    )

    state = ContinumState()
    state.org.set_client_config(
        client_name=client_name,
        schema_version=1,
        column_map={},
        segment_map={},
        platform_map={},
        approved_by="bootstrap_csv",
    )
    state.execution.set_bootstrap_state("csv", __import__("datetime").datetime.utcnow().isoformat())
    logger.info("Bootstrapped from CSV: %s", csv_path)
    return state


def bootstrap_from_connection(
    mode: str,
    client_name: str = "client",
    db=None,
    **credentials,
) -> ContinumState:
    import duckdb
    if db is None:
        db = duckdb.connect(":memory:")

    ingestion_mode = IngestionMode(mode)

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


def validate_bootstrap(state: ContinumState, db=None) -> dict:

    errors   = []
    warnings = []

    if not state.org.get_client_name():
        errors.append("No client name set — run bootstrap first")

    if db is not None:
        try:
            tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
            required = {"silver_inquiries"}
            missing  = required - tables
            if missing:
                errors.append(f"Required tables missing: {missing}")
        except Exception as e:
            warnings.append(f"Could not validate tables: {e}")

    return {
        "ok":       len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
        "mode":     state.mode,
        "client":   state.org.get_client_name(),
    }


__all__ = [
    "bootstrap_from_csv",
    "bootstrap_from_connection",
    "validate_bootstrap",
]


def bootstrap_with_schema_discovery(
    mode: str,
    client_name: str = "client",
    db=None,
    llm=None,
    output_dir: str = ".",
    **credentials,
):
    state = bootstrap_from_connection(
        mode=mode, client_name=client_name, db=db, **credentials
    )

    schema_result = None
    try:
        from continum.modules.phase0.discovery import run_schema_discovery
        schema_result = run_schema_discovery(
            llm=llm, db=db,
            client_name=client_name,
            bootstrap_mode=True,
            output_dir=output_dir,
        )
        if schema_result:
            mapping = schema_result.get("mapping", {})
            col_map = mapping.get("column_mapping", {})
            state.org.set_client_config(
                client_name=client_name,
                schema_version=3,
                column_map=col_map,
                segment_map=credentials.get("segment_map", {}),
                platform_map=credentials.get("platform_map", {}),
                approved_by="schema_discovery",
            )
            logger.info("Schema discovery completed: confidence=%.0f%%",
                        mapping.get("confidence", 0) * 100)
    except Exception as e:
        logger.warning("Schema discovery failed (non-fatal): %s", e)

    return state, schema_result

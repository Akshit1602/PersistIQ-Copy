from typing import Any, Dict, List

from pydantic import BaseModel, Field

from continum.state import SchemaMetadata


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

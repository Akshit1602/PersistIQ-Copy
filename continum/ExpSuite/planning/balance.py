from typing import Dict, List
from pydantic import BaseModel, Field


class TrafficBalanceInput(BaseModel):
    num_variants: int = Field(2, description="Total number of variants (including Control)")
    variant_names: List[str] = Field(default_factory=lambda: ["Control", "Treatment"])
    control_split: float = Field(0.50, description="Target allocation ratio for Control (e.g. 0.50)")


class TrafficBalanceResult(BaseModel):
    variant_allocations: Dict[str, float]
    is_valid_split: bool
    summary: str


def calculate_traffic_balance(input_data: TrafficBalanceInput) -> TrafficBalanceResult:
    """
    Computes variant traffic allocation percentages and verifies split integrity.
    """
    if len(input_data.variant_names) != input_data.num_variants:
        names = ["Control"] + [f"Treatment_{i}" for i in range(1, input_data.num_variants)]
    else:
        names = input_data.variant_names

    remaining_traffic = 1.0 - input_data.control_split
    num_treatments = input_data.num_variants - 1
    treatment_split = remaining_traffic / num_treatments if num_treatments > 0 else 0.0

    allocations = {}
    for name in names:
        if name.lower() == "control":
            allocations[name] = float(input_data.control_split)
        else:
            allocations[name] = float(treatment_split)

    total_split = sum(allocations.values())
    is_valid = abs(total_split - 1.0) < 1e-4

    split_formatted = ", ".join([f"{k}: {v * 100:.1f}%" for k, v in allocations.items()])
    summary = f"Traffic Allocation Split: {split_formatted}. Split Integrity: {'VALID' if is_valid else 'INVALID'}"

    return TrafficBalanceResult(
        variant_allocations=allocations,
        is_valid_split=is_valid,
        summary=summary
    )
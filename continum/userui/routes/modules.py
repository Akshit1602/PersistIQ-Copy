from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from continum.orchestration.tools.registry import all_experimentation_tools
from continum.registry import get_module, list_modules

router = APIRouter(prefix="/api/modules", tags=["Analytics Lab Modules"])

_TOOL_NAMES = {tool.name for tool in all_experimentation_tools}


def _with_execution_status(module) -> Dict[str, Any]:
    """
    Adds whether the module's execution_handler resolves to a tool the agent can
    actually call. Exposed so the UI can distinguish "runnable" from "documented
    but not wired" instead of discovering it only when a run silently does nothing.
    """
    data = module.to_dict()
    data["is_executable"] = module.execution_handler in _TOOL_NAMES
    return data


@router.get("", response_model=List[Dict[str, Any]])
async def list_analytics_modules(phase: Optional[str] = None):
    """Returns the canonical Analytics Lab module contract, optionally by phase."""
    return [_with_execution_status(module) for module in list_modules(phase)]


@router.get("/{module_id}")
async def get_analytics_module(module_id: str):
    """Returns one module's full contract: inputs, outputs, dependencies, docs."""
    module = get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module_id}")
    return _with_execution_status(module)

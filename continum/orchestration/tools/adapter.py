from typing import Callable, Any, Dict, Type
from langchain_core.tools import tool
from pydantic import BaseModel
from continum.state import UIArtifact


def create_expsuite_tool(
    name: str,
    description: str,
    schema: Type[BaseModel],
    func: Callable[[Any], BaseModel],
    artifact_type: str = "stat_results_card"
):
    """
    Factory turning pure ExpSuite math functions into LangGraph tools
    with auto-generated UI artifacts.
    """
    @tool(name, description=description, args_schema=schema, return_direct=False)
    def wrapped_tool(**kwargs) -> Dict[str, Any]:
        try:
            input_obj = schema(**kwargs)
            result: BaseModel = func(input_obj)

            artifact = UIArtifact(
                artifact_id=f"art_{name}",
                type=artifact_type,
                title=name.replace("_", " ").title(),
                payload=result.model_dump()
            )

            return {
                "result": result.model_dump(),
                "ui_artifacts": [artifact],
                "status": "success"
            }
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed"
            }

    wrapped_tool.__doc__ = description
    return wrapped_tool
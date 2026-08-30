from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from continum.orchestration import app_graph

router = APIRouter(prefix="/api/approval", tags=["Human-in-the-Loop"])


class ApprovalRequest(BaseModel):
    thread_id: str = Field(..., description="Target thread ID to resume")
    approved: bool = Field(..., description="True to proceed, False to cancel action")
    user_feedback: str = Field("", description="Optional feedback or parameters provided by user")


@router.post("/resume")
async def resume_interrupted_graph(payload: ApprovalRequest):
    """
    Resumes a paused LangGraph thread following human approval or feedback.
    """
    config = {"configurable": {"thread_id": payload.thread_id}}

    if payload.approved:
        resume_message = (
            f"USER APPROVED: {payload.user_feedback}" if payload.user_feedback else "USER APPROVED."
        )
    else:
        resume_message = f"USER REJECTED ACTION: {payload.user_feedback}"

    # Resume graph execution with approval state
    updated_state = {"messages": [HumanMessage(content=resume_message)]}
    app_graph.invoke(updated_state, config)

    return {"status": "resumed", "approved": payload.approved}

import asyncio
import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from continum.orchestration import app_graph

router = APIRouter(prefix="/api/chat", tags=["Chat & Copilot"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="User prompt text")
    thread_id: str = Field("default_thread", description="Unique conversation thread ID")
    active_experiment_id: Optional[str] = Field(
        None, description="Currently selected experiment ID"
    )


@router.post("/stream")
async def chat_stream_endpoint(payload: ChatRequest):
    """
    Server-Sent Events (SSE) streaming endpoint emitting tokens, tool execution
    badges, and UIArtifact cards directly to the frontend.
    """
    config = {"configurable": {"thread_id": payload.thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=payload.message)],
        "active_experiment_id": payload.active_experiment_id,
        "ui_artifacts": [],
        "errors": [],
    }

    async def event_generator():
        has_streamed_tokens = False
        async for event in app_graph.astream_events(initial_state, config, version="v2"):
            kind = event["event"]

            # 1. Stream text token chunks from the LLM
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"].content
                if chunk:
                    has_streamed_tokens = True
                    yield f"data: {json.dumps({'type': 'text_token', 'content': chunk})}\n\n"

            # If no model tokens were streamed (e.g. fallback mode), stream supervisor node's output at end
            elif kind == "on_chain_end" and event["name"] == "supervisor":
                if not has_streamed_tokens:
                    output = event["data"].get("output")
                    if isinstance(output, dict) and "messages" in output and output["messages"]:
                        last_msg = output["messages"][-1]
                        content = getattr(last_msg, "content", str(last_msg))
                        for i in range(0, len(content), 12):
                            chunk = content[i : i + 12]
                            yield f"data: {json.dumps({'type': 'text_token', 'content': chunk})}\n\n"
                            await asyncio.sleep(0.01)

            # 2. Stream tool execution status
            elif kind == "on_tool_start":
                tool_name = event["name"]
                tool_display = tool_name.replace("_", " ").title()
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'message': f'Running {tool_display}...'})}\n\n"

            # 3. Stream completed UI artifacts
            elif kind == "on_tool_end":
                tool_output = event["data"].get("output")

                # Robust unwrap if LangGraph wrapped output in ToolMessage or JSON string
                if hasattr(tool_output, "content"):
                    tool_output = tool_output.content
                if isinstance(tool_output, str):
                    try:
                        tool_output = json.loads(tool_output)
                    except Exception:
                        pass

                if isinstance(tool_output, dict) and "ui_artifacts" in tool_output:
                    artifacts = tool_output["ui_artifacts"]
                    for art in artifacts:
                        art_dict = art.model_dump() if hasattr(art, "model_dump") else art
                        yield f"data: {json.dumps({'type': 'artifact', 'payload': art_dict})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

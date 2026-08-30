import asyncio
import json
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from continum.orchestration import app_graph

router = APIRouter(prefix="/api/chat", tags=["Chat & Copilot"])

DB_PATH = "matchview_omnichannel.db"

def _persist_user_message(thread_id: str, content: str) -> str:
    msg_id = f"msg_user_{int(time.time() * 1000)}"
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_messages (message_id, thread_id, role, content, kind, timestamp)
            VALUES (?, ?, 'user', ?, 'text', ?)
        """, (msg_id, thread_id, content, timestamp))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error persisting user message: {e}")
    return msg_id

def _persist_assistant_message(thread_id: str, content: str, artifacts: list = None) -> str:
    msg_id = f"msg_asst_{int(time.time() * 1000)}"
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    artifacts_json = json.dumps(artifacts) if artifacts else None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_messages (message_id, thread_id, role, content, kind, timestamp, artifacts_json)
            VALUES (?, ?, 'assistant', ?, 'text', ?, ?)
        """, (msg_id, thread_id, content, timestamp, artifacts_json))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error persisting assistant message: {e}")
    return msg_id


def _as_text(content) -> str:
    """
    Flattens LangChain message content to plain text.

    Gemini streams content-block lists (e.g. [{"type": "text", "text": "...",
    "extras": {"signature": ...}}]) rather than bare strings — usually only for
    the first chunk of a response. Forwarding the raw list let the frontend
    string-concatenate an object and render "[object Object]", so normalise here
    where the provider-specific shape is already known.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or ""
    if isinstance(content, list):
        return "".join(_as_text(block) for block in content)
    return str(content)


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
    _persist_user_message(payload.thread_id, payload.message)

    config = {"configurable": {"thread_id": payload.thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=payload.message)],
        "active_experiment_id": payload.active_experiment_id,
        "ui_artifacts": [],
        "errors": [],
    }

    async def event_generator():
        has_streamed_tokens = False
        has_streamed_artifacts = False
        accumulated_text = ""
        accumulated_artifacts = []

        async for event in app_graph.astream_events(initial_state, config, version="v2"):
            kind = event["event"]

            # 1. Stream text token chunks from the LLM
            if kind == "on_chat_model_stream":
                chunk = _as_text(event["data"]["chunk"].content)
                if chunk:
                    has_streamed_tokens = True
                    accumulated_text += chunk
                    yield f"data: {json.dumps({'type': 'text_token', 'content': chunk})}\n\n"

            # If no model tokens were streamed (e.g. fallback mode), stream supervisor node's output at end
            elif kind == "on_chain_end" and event["name"] == "supervisor":
                if not has_streamed_tokens:
                    output = event["data"].get("output")
                    if isinstance(output, dict) and "messages" in output and output["messages"]:
                        last_msg = output["messages"][-1]
                        content = _as_text(getattr(last_msg, "content", last_msg))
                        accumulated_text += content
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
                        has_streamed_artifacts = True
                        accumulated_artifacts.append(art_dict)
                        yield f"data: {json.dumps({'type': 'artifact', 'payload': art_dict})}\n\n"

        # A turn that emits neither text nor a card renders as an empty chat
        # bubble, which reads as "the copilot ignored me". Say something instead.
        if not has_streamed_tokens and not has_streamed_artifacts:
            notice = (
                "I wasn't able to produce a response for that message. "
                "Please rephrase it, or check the server logs if this repeats."
            )
            accumulated_text = notice
            yield f"data: {json.dumps({'type': 'text_token', 'content': notice})}\n\n"

        _persist_assistant_message(payload.thread_id, accumulated_text, accumulated_artifacts)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

    return StreamingResponse(event_generator(), media_type="text/event-stream")

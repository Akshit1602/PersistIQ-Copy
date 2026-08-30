import ast
import functools
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from continum.config import settings
from continum.orchestration.tools.registry import all_experimentation_tools
from continum.state import AgentState, PendingAction

logger = logging.getLogger(__name__)


# Built lazily (on first real request) rather than at import time, so the
# package stays importable without live credentials -- a fresh checkout, a CI
# runner, or a static-analysis pass must not crash just by importing this
# module. A missing/invalid key still surfaces, just at call time, where
# `supervisor_node`'s except block already turns it into a safe
# "Copilot unavailable" reply instead of an import-time crash.
@functools.lru_cache(maxsize=1)
def _get_llm_with_tools():
    return settings.get_llm().bind_tools(all_experimentation_tools)


# Second provider to retry with if the primary fails at request time (auth,
# quota, network, IP restriction) -- see Settings.get_fallback_llm(). None
# when no second provider is configured, in which case behaviour is
# unchanged: a primary failure goes straight to the safe "Copilot
# unavailable" message.
@functools.lru_cache(maxsize=1)
def _get_fallback_llm_with_tools():
    fallback_llm = settings.get_fallback_llm()
    return fallback_llm.bind_tools(all_experimentation_tools) if fallback_llm else None


def _is_blank(response) -> bool:
    """True when a model reply carries neither usable text nor a tool call."""
    if getattr(response, "tool_calls", None):
        return False
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        # Gemini content-block form: blocks may hold only a thought signature.
        return not any(
            str(block.get("text", "")).strip() for block in content if isinstance(block, dict)
        )
    return not content


def _invoke_with_blank_retry(client, messages: List[Any]) -> Optional[Any]:
    """
    Invokes `client`, retrying once with a nudge if the reply is blank (Gemini
    intermittently returns a STOP response with no text and no tool call).
    Returns the response, or None if it was still blank after the retry.
    """
    response = client.invoke(messages)
    if not _is_blank(response):
        return response

    logger.warning("LLM returned an empty response; retrying once")
    retry_nudge = SystemMessage(
        content=(
            "Your previous reply was empty. Respond now: either call the "
            "appropriate tool, or ask for the specific parameters you need."
        )
    )
    response = client.invoke(messages + [retry_nudge])
    return None if _is_blank(response) else response


def _invoke_with_fallback(messages: List[Any]) -> Optional[Any]:
    """
    Tries the primary LLM, then the fallback (if configured) when the primary
    either raises or returns nothing usable after its own blank-retry.

    Raises only when the primary fails and no fallback is configured, or when
    the fallback itself also raises -- both are handled by the caller's
    existing "Copilot unavailable" safety net. At most one fallback attempt is
    made per call, regardless of which of the two trigger conditions caused it.
    """
    fallback_llm_with_tools = _get_fallback_llm_with_tools()

    primary_failed = False
    try:
        response = _invoke_with_blank_retry(_get_llm_with_tools(), messages)
    except Exception as primary_error:
        response = None
        primary_failed = True
        if fallback_llm_with_tools is None:
            raise
        logger.warning(
            "Primary LLM call failed (%s: %s); retrying with the fallback provider",
            type(primary_error).__name__,
            primary_error,
        )

    if response is None and fallback_llm_with_tools is not None:
        if not primary_failed:
            logger.warning(
                "Primary LLM returned no usable response after retry; "
                "trying the fallback provider"
            )
        response = _invoke_with_blank_retry(fallback_llm_with_tools, messages)
        if response is not None:
            logger.info("Fallback provider produced a response")

    return response


def _missing_inputs_this_turn(messages: List[Any]) -> List[str]:
    """
    Collects `missing_inputs` reported by tools since the user's last message.

    Subgraph tools report a required parameter they were not given rather than
    defaulting it. ToolNode serialises a tool's dict return into ToolMessage
    text, so the value is recovered by parsing that text; if it is not parseable
    the field name is unavailable but the presence of the key still signals that
    clarification is needed.
    """
    missing: List[str] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage):
            continue
        content = message.content
        if not isinstance(content, str) or "missing_inputs" not in content:
            continue
        # LangChain JSON-encodes a dict tool return, falling back to its Python
        # repr when a value is not JSON-serialisable. Try both before giving up,
        # otherwise a parseable result is reported as an opaque one and the user
        # is told to "see tool output" instead of which field to supply.
        try:
            parsed = json.loads(content)
        except ValueError:
            try:
                parsed = ast.literal_eval(content)
            except (ValueError, SyntaxError):
                missing.append("(see tool output)")
                continue
        if isinstance(parsed, dict):
            missing.extend(str(name) for name in parsed.get("missing_inputs") or [])
    return list(dict.fromkeys(missing))


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    ReAct Supervisor Agent node that determines user intent, calls tools,
    and synthesizes results for the user with active experiment context.
    """
    active_exp = state.get("active_experiment_id") or "None Selected"
    active_proj = state.get("active_project_id") or "None Selected"

    system_prompt = (
        "You are Continum's A/B Testing & Retail Experimentation Copilot.\n"
        f"CURRENT CONTEXT -> Active Project: '{active_proj}', Active Experiment ID: '{active_exp}'.\n"
        "\n"
        "TOOL DISCIPLINE (non-negotiable):\n"
        "- You have NO arithmetic ability of your own. Every number you state — sample "
        "sizes, revenue, conversions, lift, p-values, confidence intervals, durations — "
        "must be copied verbatim from a tool result in this conversation.\n"
        "- When the user supplies the inputs for a calculation, CALL the matching tool. "
        "Do not compute the answer yourself, even when the arithmetic looks trivial and "
        "even when you already used a tool earlier in the conversation.\n"
        "- You may convert units to build tool arguments (e.g. annual_traffic = "
        "daily_traffic * 365), but a derived value may only be passed INTO a tool, never "
        "reported as a result.\n"
        "- If required parameters are missing, ask for exactly those parameters. Never "
        "fill them with assumed or illustrative values.\n"
        "- If no tool fits the request, say so plainly instead of estimating.\n"
        "\n"
        "VISUALIZATION:\n"
        "- The UI renders charts as cards next to your reply. Call "
        "`ask_data_visualize` whenever the user asks to see, show, plot, chart, "
        "graph, visualize, compare, trend, or break down something, and whenever "
        "your answer compares values across categories, arms, or time — a picture "
        "carries those better than a paragraph.\n"
        "- `ask_data_sql` charts its own results automatically; do not follow it "
        "with a chart call for the same rows.\n"
        "- Chart only figures a tool already returned in this conversation. If you "
        "lack the numbers, ask for them — never invent points to fill an axis.\n"
        "- Never draw ASCII art, markdown tables of bar characters, or image "
        "links. Describe the finding in words; the card shows the picture.\n"
        "\n"
        "Always reply with either a tool call or user-facing text — never an empty message."
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    # A tool that could not run because a required parameter was absent reports
    # it rather than defaulting. Turn that into an explicit clarification request
    # and mark the turn for human input, which is what `POST /api/approval/resume`
    # resumes from.
    missing_inputs = _missing_inputs_this_turn(state["messages"])
    if missing_inputs:
        messages = messages + [
            SystemMessage(
                content=(
                    "A tool could not run because these required parameters were "
                    f"not supplied: {', '.join(missing_inputs)}. Ask the user for "
                    "exactly these values. Do not call the tool again with guessed, "
                    "assumed, or illustrative values, and do not state any figure "
                    "as a result."
                )
            )
        ]

    try:
        response = _invoke_with_fallback(messages)

        if response is None:
            logger.error("LLM returned an empty response twice; surfacing notice")
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I didn't generate a reply for that message. Please "
                            "rephrase it, or state the values you want me to use."
                        )
                    )
                ],
                "errors": ["empty_llm_response"],
            }

        update: Dict[str, Any] = {"messages": [response]}
        if missing_inputs:
            update["requires_approval"] = True
            update["pending_action"] = PendingAction(
                action_type="SUPPLY_MISSING_PARAMETERS",
                description=(
                    "Waiting on required parameters before the analysis can run: "
                    + ", ".join(missing_inputs)
                ),
                payload={"missing_inputs": missing_inputs},
            )
        return update
    except Exception as e:
        # Never substitute fabricated statistics for a failed call — this agent's
        # own system prompt forbids inventing numbers, and a canned "HEALTHY" /
        # p-value block is indistinguishable from a real tool result downstream.
        # Log the real cause and surface an explicit failure instead.
        logger.exception("Supervisor LLM call failed")
        content = (
            f"⚠️ **Copilot unavailable** — the language model call failed "
            f"(`{type(e).__name__}`). No statistical analysis was run for this "
            "message, and no results below are to be trusted as computed. "
            "Check the server logs for the underlying error, then retry."
        )
        # `errors` uses an operator.add reducer — return only the new entry.
        return {
            "messages": [AIMessage(content=content)],
            "errors": [f"{type(e).__name__}: {e}"],
        }


# Construct LangGraph Workflow with ReAct Tool Loop
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("tools", ToolNode(all_experimentation_tools))

# Add Edges
workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges("supervisor", tools_condition)
workflow.add_edge("tools", "supervisor")

# Compile graph with thread checkpointer
memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory)

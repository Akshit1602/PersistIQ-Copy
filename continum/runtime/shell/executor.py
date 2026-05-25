from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger("continum.runtime.shell.executor")


def run_module(
    module_key: str,
    label: str,
    db: Any,
    state: Any,
    session: Any,
    bus: Any,
    memory: Any,
    **kwargs,
) -> Optional[Any]:
    from continum.api.dispatcher import run_module as _run, get_module, _build_registry
    from continum.runtime.intelligence import publish_next_steps, WORKFLOW_CHAIN
    from continum.runtime.shell.renderer import bold, green, red, yellow, dim, W

    _build_registry()
    spec = get_module(module_key)
    if spec is None:
        print(f"\n  {yellow('⚠️')}  Module '{module_key}' not available in this installation.")
        bus.warn("shell", f"Module '{module_key}' not available")
        return None

    print(f"\n  {'═' * W}")
    print(f"  {bold('▶ ' + label.upper())}")
    print(f"  {'═' * W}")

    t0 = time.monotonic()
    try:
        # Get LLM singleton (None if not available)
        try:
            from continum.core.llm.manager import get_llm
            llm_instance = get_llm()
        except Exception:
            llm_instance = None

        result  = _run(module_key, state=state, llm=llm_instance, db=db, **kwargs)
        elapsed = time.monotonic() - t0

        # Store in session
        session.set(f"{module_key}_result", result)
        session.set("experiment_result", result)

        # Record run
        summary = _summarise(result, module_key)
        session.record_run(
            module=module_key,
            phase=spec.phase,
            elapsed_s=elapsed,
            ok=True,
            summary=summary,
        )

        # Persist to cross-experiment memory
        if module_key in ("experiment_analysis",) and result:
            exp_name = session.active_experiment or "unknown"
            narrative_text = result.get("narrative", "") if isinstance(result, dict) else ""
            memory.record_experiment(exp_name, exp_name, result, narrative=narrative_text)

        # Intelligence + next steps
        bus.success(module_key, f"{label} completed in {elapsed:.2f}s")
        publish_next_steps(module_key, bus)

        # Narrative commentary — makes the shell feel alive
        try:
            from continum.runtime.narrative import get_narrative
            nr = get_narrative(bus=bus, session=session, memory=memory)
            nr.after_module(module_key, result)
        except Exception:
            pass

        # Wire session recommendations
        for next_mod, reason, priority in WORKFLOW_CHAIN.get(module_key, [])[:2]:
            session.add_recommendation(
                source=module_key, action=f"Run {next_mod}",
                reason=reason, module_key=next_mod, priority=priority,
            )

        session.save()
        _show_next_steps(module_key)
        return result

    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"\n  {red('❌')} {label} failed: {e}")
        logger.exception("Module %s failed", module_key)
        bus.warn(module_key, f"{label} failed: {str(e)[:80]}")
        session.record_run(module_key, spec.phase, elapsed, ok=False, error=str(e))
        session.save()
        return None


def _summarise(result: Any, module_key: str) -> str:
    if result is None:
        return ""
    try:
        if hasattr(result, "verdict") and hasattr(result, "primary_delta"):
            d = result.primary_delta
            return (f"Δ={d.delta_pp:+.3f}pp  p={d.p_value:.4f}  "
                    f"{'✅' if d.is_significant else '—'}  {result.verdict.value}")
        if isinstance(result, dict):
            r = result.get("result")
            if r and hasattr(r, "verdict"):
                d = r.primary_delta
                return f"Δ={d.delta_pp:+.3f}pp  p={d.p_value:.4f}  {r.verdict.value}"
            if "error" in result:
                return f"Error: {result['error']}"
            return str(list(result.keys()))[:60]
        return str(result)[:60]
    except Exception:
        return ""


def _show_next_steps(module_key: str) -> None:
    from continum.runtime.intelligence import WORKFLOW_CHAIN
    from continum.runtime.shell.renderer import bold, cyan, dim, W
    chain = WORKFLOW_CHAIN.get(module_key, [])
    if not chain:
        return
    print(f"\n  {'─' * 68}")
    print(f"  {bold('Recommended Next Steps:')}")
    for next_mod, reason, _ in chain[:3]:
        print(f"    {cyan('▶')}  {reason}  {dim('(' + next_mod + ')')}")
    print(f"  {'─' * 68}")


__all__ = ["run_module"]

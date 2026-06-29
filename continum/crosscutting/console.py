from __future__ import annotations

import sys
import time
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR CODES (graceful fallback if terminal doesn't support them)
# ─────────────────────────────────────────────────────────────────────────────

_COLORS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "red":     "\033[31m",
    "cyan":    "\033[36m",
    "magenta": "\033[35m",
    "blue":    "\033[34m",
    "white":   "\033[37m",
}


def _c(color: str, text: str, force: bool = False) -> str:
    if not sys.stdout.isatty() and not force:
        return text
    code = _COLORS.get(color, "")
    reset = _COLORS["reset"]
    return f"{code}{text}{reset}"


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION CONSOLE
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionConsole:

    def __init__(self, module_name: str = "continum", verbose: bool = True):
        self.module_name = module_name
        self.verbose     = verbose
        self._start      = time.monotonic()
        self._tasks:     List[dict] = []

    def _ts(self) -> str:
        elapsed = time.monotonic() - self._start
        return f"{elapsed:>6.2f}s"

    def _print(self, level: str, msg: str, color: str = "reset") -> None:
        if not self.verbose:
            return
        ts    = self._ts()
        label = _c(color, f"[{level:<4}]", force=False)
        print(f"  {label} {msg}", flush=True)

    def info(self, msg: str) -> None:
        self._print("INFO", msg, "cyan")

    def warn(self, msg: str) -> None:
        self._print("WARN", _c("yellow", msg), "yellow")

    def error(self, msg: str) -> None:
        self._print("ERR ", _c("red", msg), "red")

    def success(self, msg: str) -> None:
        self._print("OK  ", _c("green", msg), "green")

    def debug(self, msg: str) -> None:
        if self.verbose:
            self._print("DBG ", _c("dim", msg), "reset")

    def section(self, title: str) -> None:
        w = 68
        if self.verbose:
            print(f"\n  {'─' * w}\n  {_c('bold', title)}\n  {'─' * w}", flush=True)

    def banner(self, title: str) -> None:
        w = 72
        if self.verbose:
            print(f"\n  {'═' * w}\n  {_c('bold', '  ' + title)}\n  {'═' * w}", flush=True)

    # ── DAG execution display ──────────────────────────────────────────────────

    def start_task(self, task_name: str) -> None:
        self._tasks.append({"name": task_name, "start": time.monotonic(), "ok": None})
        self.info(f"Starting › {task_name}")

    def end_task(self, task_name: str, ok: bool = True, note: str = "") -> None:
        for t in self._tasks:
            if t["name"] == task_name and t["ok"] is None:
                t["ok"]      = ok
                t["elapsed"] = round(time.monotonic() - t["start"], 3)
                t["note"]    = note
                break
        icon = "✅" if ok else "❌"
        elapsed_str = ""
        for t in self._tasks:
            if t["name"] == task_name:
                elapsed_str = f"  ({t.get('elapsed', 0):.2f}s)"
                break
        suffix = f"  {_c('dim', note)}" if note else ""
        self.info(f"{icon} {task_name}{elapsed_str}{suffix}")

    def show_dag(self) -> None:
        if not self._tasks:
            return
        ok_count   = sum(1 for t in self._tasks if t.get("ok") is True)
        fail_count = sum(1 for t in self._tasks if t.get("ok") is False)
        total      = len(self._tasks)
        print(f"\n  {'─' * 68}", flush=True)
        print(f"  DAG Summary:  {ok_count}/{total} tasks OK  "
              f"{'⚠️  ' + str(fail_count) + ' failed' if fail_count else '✅ All clean'}", flush=True)
        for t in self._tasks:
            icon    = "✅" if t.get("ok") else ("❌" if t.get("ok") is False else "⏳")
            elapsed = f"{t.get('elapsed', 0):.3f}s" if "elapsed" in t else "…"
            note    = f"  {t.get('note', '')}" if t.get("note") else ""
            print(f"    {icon}  {t['name']:<32}  {elapsed}{note}", flush=True)
        print(f"  {'─' * 68}\n", flush=True)

    @contextmanager
    def task(self, name: str) -> Iterator[None]:
        self.start_task(name)
        try:
            yield
            self.end_task(name, ok=True)
        except Exception as e:
            self.end_task(name, ok=False, note=str(e)[:60])
            raise

    # ── Spinner (for long-running tasks) ──────────────────────────────────────

    @contextmanager
    def spinner(self, message: str) -> Iterator[None]:
        if not self.verbose or not sys.stdout.isatty():
            print(f"  [....] {message}", flush=True)
            yield
            return

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        running = threading.Event()
        running.set()

        def _spin():
            i = 0
            while running.is_set():
                frame = frames[i % len(frames)]
                print(f"\r  {frame} {message}", end="", flush=True)
                time.sleep(0.1)
                i += 1

        t = threading.Thread(target=_spin, daemon=True)
        t.start()
        try:
            yield
        finally:
            running.clear()
            t.join(timeout=0.3)
            print(f"\r  ✅ {message}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL CONSOLE (thin wrapper for module code to call without setup)
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_CONSOLE: Optional[ExecutionConsole] = None


def get_console(module_name: str = "continum") -> ExecutionConsole:
    global _GLOBAL_CONSOLE
    if _GLOBAL_CONSOLE is None:
        _GLOBAL_CONSOLE = ExecutionConsole(module_name)
    return _GLOBAL_CONSOLE


def reset_console(module_name: str = "continum") -> ExecutionConsole:
    global _GLOBAL_CONSOLE
    _GLOBAL_CONSOLE = ExecutionConsole(module_name)
    return _GLOBAL_CONSOLE


# Convenience module-level functions — modules can do:
#   from continum.crosscutting.console import con_info, con_warn
def con_info(msg: str)    -> None: get_console().info(msg)
def con_warn(msg: str)    -> None: get_console().warn(msg)
def con_error(msg: str)   -> None: get_console().error(msg)
def con_success(msg: str) -> None: get_console().success(msg)
def con_debug(msg: str)   -> None: get_console().debug(msg)


__all__ = [
    "ExecutionConsole",
    "get_console",
    "reset_console",
    "con_info",
    "con_warn",
    "con_error",
    "con_success",
    "con_debug",
]

from __future__ import annotations
import sys
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# ANSI COLOUR HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _tty() -> bool:
    return sys.stdout.isatty()

def bold(s: str)   -> str: return f"\033[1m{s}\033[0m"   if _tty() else s
def dim(s: str)    -> str: return f"\033[2m{s}\033[0m"   if _tty() else s
def cyan(s: str)   -> str: return f"\033[36m{s}\033[0m"  if _tty() else s
def green(s: str)  -> str: return f"\033[32m{s}\033[0m"  if _tty() else s
def yellow(s: str) -> str: return f"\033[33m{s}\033[0m"  if _tty() else s
def red(s: str)    -> str: return f"\033[31m{s}\033[0m"  if _tty() else s
def magenta(s: str)-> str: return f"\033[35m{s}\033[0m"  if _tty() else s


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

W = 72  # default console width


def os_banner() -> None:
    print(f"\n{'═' * W}")
    print(f"{bold('CONTINUM OS'):^{W + 8}}")
    print(f"{'Experimentation Intelligence Platform':^{W}}")
    print(f"{'═' * W}\n")


def section_header(title: str, w: int = W) -> None:
    print(f"\n  {'─' * (w - 4)}")
    print(f"  {bold(title.upper())}")
    print(f"  {'─' * (w - 4)}")


def phase_header(title: str, w: int = W) -> None:
    print(f"\n  {'═' * (w - 4)}")
    print(f"  {bold('▶ ' + title.upper())}")
    print(f"  {'═' * (w - 4)}")


def divider(w: int = W) -> None:
    print(f"  {'─' * (w - 4)}")


def menu_item(key: str, label: str, done: bool = False, note: str = "") -> None:
    check = f"  {dim('✓')}" if done else ""
    extra = f"  {dim(note)}" if note else ""
    print(f"    {bold('[' + key + ']')}  {label}{check}{extra}")


def status_bar(experiment: str, n_runs: int, intel_summary: str, w: int = W) -> None:
    print(f"\n  {'─' * (w - 4)}")
    print(f"  {bold('CONTINUM OS')}  |  Experiment: {cyan(experiment)}  |  Runs: {n_runs}")
    if intel_summary:
        print(intel_summary)
    print(f"  {'─' * (w - 4)}\n")


def result_line(icon: str, label: str, value: str) -> None:
    print(f"  {icon}  {label:<28}  {value}")


def prompt(label: str = "") -> str:
    prefix = f"  {cyan('CONTINUM')}"
    if label:
        prefix += f"/{label}"
    try:
        return input(f"{prefix} › ")
    except (KeyboardInterrupt, EOFError):
        return "Q"


__all__ = [
    "bold", "dim", "cyan", "green", "yellow", "red", "magenta",
    "os_banner", "section_header", "phase_header", "divider",
    "menu_item", "status_bar", "result_line", "prompt", "W",
]

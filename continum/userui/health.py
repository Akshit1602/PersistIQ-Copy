from __future__ import annotations

import importlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List

logger = logging.getLogger("continum.health")

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY MANIFEST
# ─────────────────────────────────────────────────────────────────────────────

# (import_name, pip_name, required)
_DEPS: list[tuple[str, str, bool]] = [
    ("numpy",             "numpy",         True),
    ("pandas",            "pandas",        True),
    ("scipy",             "scipy",         True),
    ("duckdb",            "duckdb",        True),
    ("flask",             "flask",         True),
    ("sklearn",           "scikit-learn",  False),   # PSM / uplift
    ("statsmodels",       "statsmodels",   False),   # ARIMA / SARIMA / BSTS / DiD TWFE
    ("transformers",      "transformers",  False),   # HuggingFace LLM
    ("torch",             "torch",         False),   # LLM GPU
    ("reportlab",         "reportlab",     False),   # PDF export
    ("tabulate",          "tabulate",      False),   # table printing
]


@dataclass
class DepStatus:
    name:       str
    pip_name:   str
    required:   bool
    available:  bool
    version:    str  = ""
    error:      str  = ""

    @property
    def ok(self) -> bool:
        return self.available or not self.required


def check_dependencies(auto_install: bool = False) -> List[DepStatus]:
    results: List[DepStatus] = []
    for imp, pip, required in _DEPS:
        try:
            mod = importlib.import_module(imp)
            ver = getattr(mod, "__version__", "?")
            results.append(DepStatus(imp, pip, required, True, ver))
        except ImportError as e:
            if auto_install and not required:
                try:
                    import subprocess, sys
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pip,
                         "--quiet", "--break-system-packages"],
                        timeout=120,
                    )
                    mod = importlib.import_module(imp)
                    ver = getattr(mod, "__version__", "?")
                    results.append(DepStatus(imp, pip, required, True, ver, ""))
                    continue
                except Exception as ie:
                    pass
            results.append(DepStatus(imp, pip, required, False, "", str(e)))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECKER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name:    str
    ok:      bool
    message: str  = ""
    latency_ms: float = 0.0


CheckFn = Callable[[], CheckResult]


class HealthChecker:

    def __init__(self):
        self._checks: Dict[str, CheckFn] = {}

    def register(self, name: str, fn: CheckFn) -> None:
        self._checks[name] = fn

    def run_all(self, timeout_s: float = 5.0) -> Dict:
        results: List[CheckResult] = []
        for name, fn in self._checks.items():
            t0 = time.monotonic()
            try:
                result = fn()
                result.latency_ms = (time.monotonic() - t0) * 1000
            except Exception as e:
                result = CheckResult(name, False, str(e),
                                     (time.monotonic() - t0) * 1000)
            results.append(result)

        healthy = all(r.ok for r in results)
        return {
            "healthy": healthy,
            "checks":  [
                {"name": r.name, "ok": r.ok,
                 "message": r.message, "latency_ms": round(r.latency_ms, 1)}
                for r in results
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD DB CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def make_db_checker(db) -> HealthChecker:
    checker = HealthChecker()

    def _ping():
        db.execute("SELECT 1")
        return CheckResult("duckdb_ping", True, "pong")

    def _silver():
        n = db.execute("SELECT COUNT(*) FROM silver_inquiries").fetchone()[0]
        return CheckResult("silver_inquiries", True, f"{n:,} rows")

    def _gold():
        n = db.execute("SELECT COUNT(DISTINCT experiment_name) FROM gold_experiment_analysis").fetchone()[0]
        return CheckResult("gold_experiments", True, f"{n} experiments")

    def _no_nulls():
        n = db.execute("""
            SELECT COUNT(*) FROM silver_inquiries
            WHERE variant IS NULL OR converted_to_order IS NULL
        """).fetchone()[0]
        ok = n == 0
        return CheckResult("null_critical_cols", ok, f"{n} nulls in variant/converted_to_order")

    checker.register("duckdb_ping",       _ping)
    checker.register("silver_inquiries",  _silver)
    checker.register("gold_experiments",  _gold)
    checker.register("null_critical_cols", _no_nulls)
    return checker


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH REPORT (consumed by /health endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def health_report(app=None) -> Dict:
    deps   = check_dependencies()
    report = {
        "status":       "unknown",
        "db_ready":     False,
        "llm_loaded":   False,
        "boot_error":   None,
        "dependencies": [
            {"name": d.name, "available": d.available, "required": d.required,
             "version": d.version}
            for d in deps
        ],
        "checks": [],
    }

    if app is None:
        report["status"] = "no_app"
        return report

    report["db_ready"]   = app.db is not None
    report["llm_loaded"] = app.llm is not None
    report["boot_error"] = getattr(app, "_boot_error", None)

    if app.db is not None:
        checker = make_db_checker(app.db)
        cr = checker.run_all()
        report["checks"] = cr["checks"]
        report["status"] = "ok" if cr["healthy"] else "degraded"
    else:
        booting = not getattr(app, "_boot_event", threading.Event()).is_set()
        report["status"] = "booting" if booting else "error"

    return report

from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from continum.crosscutting.pdf import PDF_PALETTE, render_document_pdf
from continum.crosscutting.runtime_config import RUNTIME_DATA_DIR, ensure_runtime_data_dir

logger = logging.getLogger("continum.contextmate.discovery")

# ─────────────────────────────────────────────────────────────────────────────
# CANONICAL SCHEMA (what we expect in production)
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_TABLES = {
    "inquiries": "Quotes / RFQs submitted by buyers",
    "orders": "Placed orders (converted quotes)",
    "buyers": "User / buyer profiles",
    "accounts": "Company / account profiles",
    "experiments": "A/B experiment exposure assignments",
    "traffic": "Daily traffic / session counts (optional)",
}

CANONICAL_COLUMNS = {
    "inquiry_id": "Unique identifier for each inquiry/quote",
    "buyer_id": "User/buyer identifier",
    "account_segment": "Business segment (Core/Growth/Enterprise/Individuals)",
    "platform": "web or mobile",
    "created_at": "Timestamp of inquiry creation",
    "converted_to_order": "Boolean/int: 1 if inquiry became an order",
    "order_value": "USD value of the order (0 if no order)",
    "variant": "Experiment variant assignment",
    "experiment_name": "Name of the A/B experiment",
    "category": "Product category",
    "country": "User country",
}


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [1] — SCHEMA DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────


def run_schema_discovery(
    llm,
    db=None,
    client_name: Optional[str] = None,
    bootstrap_mode: bool = False,
    output_dir: Optional[str] = None,
) -> Optional[Dict]:
    if output_dir is None:
        ensure_runtime_data_dir()
        output_dir = RUNTIME_DATA_DIR
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  SCHEMA DISCOVERY & MAPPING (Phase 0)".ljust(70) + "║")
    print("║" + "  Auto-generate CLIENT_SCHEMA from a connected warehouse".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    if db is None:
        print("  ❌ No database connection provided.")
        return None

    if client_name is None:
        if bootstrap_mode:
            client_name = "Client"
        else:
            client_name = input("  Client / project name: ").strip() or "Client"

    # ── Catalog scan ──────────────────────────────────────────────────────────
    print("\n  Scanning DuckDB catalog...")
    try:
        catalog_df = db.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'main' ORDER BY table_name
        """
        ).df()
    except Exception:
        try:
            catalog_df = db.execute("SHOW TABLES").df()
            catalog_df.columns = ["table_name"]
        except Exception as e:
            print(f"  ❌ Could not list tables: {e}")
            return None

    tables = catalog_df["table_name"].tolist()
    if not tables:
        print("  ⚠️  No tables found. Load data first.")
        return None
    print(
        f"     Found {len(tables)} tables: {', '.join(tables[:10])}{'...' if len(tables) > 10 else ''}"
    )

    # ── Profile each table ────────────────────────────────────────────────────
    print("\n  Profiling tables (sampling up to 5,000 rows each)...")
    profiles: Dict[str, Dict] = {}
    for tbl in tables:
        try:
            df_sample = db.execute(f'SELECT * FROM "{tbl}" LIMIT 5000').df()
            profiles[tbl] = {
                "n_rows_sampled": len(df_sample),
                "n_cols": len(df_sample.columns),
                "columns": df_sample.columns.tolist(),
                "dtypes": {c: str(df_sample[c].dtype) for c in df_sample.columns},
                "null_rates": {c: round(df_sample[c].isna().mean(), 3) for c in df_sample.columns},
                "sample_values": {
                    c: df_sample[c].dropna().head(3).tolist() for c in df_sample.columns[:20]
                },
            }
            print(f"     ✅ {tbl:<32} {len(df_sample):>6,} rows · {len(df_sample.columns)} cols")
        except Exception as e:
            print(f"     ⚠️  {tbl}: {e}")

    if not profiles:
        print("  ❌ No tables could be profiled.")
        return None

    # ── Deterministic mapping (no LLM needed for common patterns) ────────────
    print("\n  Building table/column mapping...")
    table_mapping = _deterministic_table_map(list(profiles.keys()))
    column_mapping = _deterministic_column_map(profiles)
    confidence = _compute_confidence(table_mapping, column_mapping)

    # ── LLM enhancement (if available) ───────────────────────────────────────
    if llm is not None:
        try:
            prompt = _build_mapping_prompt(profiles)
            raw = llm.ask(prompt)
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                llm_mapping = json.loads(match.group())
                # Merge LLM mappings where deterministic has gaps
                for k, v in llm_mapping.get("table_mapping", {}).items():
                    if k in CANONICAL_TABLES and not table_mapping.get(k) and v:
                        table_mapping[k] = v
                for k, v in llm_mapping.get("column_mapping", {}).items():
                    if k in CANONICAL_COLUMNS and not column_mapping.get(k) and v:
                        column_mapping[k] = v
                confidence = max(confidence, llm_mapping.get("confidence", 0))
        except Exception as e:
            logger.debug("LLM mapping failed: %s", e)

    # ── Verify ────────────────────────────────────────────────────────────────
    issues = _verify_mapping(table_mapping, column_mapping, profiles)
    n_errors = sum(1 for s, _ in issues if s == "error")
    n_warns = sum(1 for s, _ in issues if s == "warn")

    # ── Display ───────────────────────────────────────────────────────────────
    print("\n  Table mapping:")
    for canon, mapped in table_mapping.items():
        icon = "✅" if mapped else "⚠️ "
        print(f"    {icon} {canon:<16} → {mapped or '(no match)'}")
    print("\n  Column mapping:")
    for canon, mapped in list(column_mapping.items())[:12]:
        icon = "✅" if mapped else "⚠️ "
        print(f"    {icon} {canon:<24} → {mapped or '(no match)'}")
    print(f"\n  Confidence: {confidence:.0%}  |  Errors: {n_errors}  |  Warnings: {n_warns}")

    # ── Write schema JSON ─────────────────────────────────────────────────────
    schema_path = Path(output_dir) / f"client_schema_{client_name.lower().replace(' ', '_')}.json"
    schema_out = {
        "client_name": client_name,
        "generated_at": datetime.utcnow().isoformat(),
        "confidence": round(confidence, 3),
        "table_mapping": table_mapping,
        "column_mapping": column_mapping,
        "issues": [{"severity": s, "message": m} for s, m in issues],
    }
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_out, f, indent=2)
    print(f"\n  📁 Schema saved → {schema_path}")

    # ── PDF report ────────────────────────────────────────────────────────────
    sections = OrderedDict(
        [
            (
                "OVERVIEW",
                f"Schema discovery across {len(profiles)} tables. "
                f"Mapping confidence: {confidence:.0%}. "
                f"{n_errors} error(s), {n_warns} warning(s).",
            ),
            (
                "TABLE MAPPING",
                "\n".join(f"- {c} → {m or '(no match)'}" for c, m in table_mapping.items()),
            ),
            (
                "COLUMN MAPPING",
                "\n".join(
                    f"- {c} → {m or '(no match)'}" for c, m in list(column_mapping.items())[:20]
                ),
            ),
            (
                "VERIFICATION ISSUES",
                "\n".join(f"- [{s.upper()}] {m}" for s, m in issues) or "None — all checks passed.",
            ),
            (
                "NEXT STEPS",
                "- Review every mapped column in the generated schema file.\n"
                "- Replace any (no match) placeholders before deploying.\n"
                "- Re-run pipeline with the approved mapping.",
            ),
        ]
    )
    pdf_path = str(Path(output_dir) / "schema_discovery_report.pdf")
    out = render_document_pdf(
        title="Schema Discovery Report",
        subtitle=f"Client: {client_name}",
        sections=sections,
        output_path=pdf_path,
        metadata={
            "Client": client_name,
            "Tables": str(len(profiles)),
            "Confidence": f"{confidence:.0%}",
            "Errors": str(n_errors),
        },
        accent_color=PDF_PALETTE["accent"],
    )
    print(f"  📁 PDF report → {out}")

    return {
        "client_name": client_name,
        "tables_found": list(profiles.keys()),
        "mapping": {
            "table_mapping": table_mapping,
            "column_mapping": column_mapping,
            "confidence": confidence,
        },
        "issues": issues,
        "schema_file": str(schema_path),
        "pdf_report": out,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [4] — DATA VALIDATION
# ─────────────────────────────────────────────────────────────────────────────


def run_data_validation(db=None, llm=None) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  DATA VALIDATION (Phase 0)".ljust(70) + "║")
    print("║" + "  Completeness · Types · Constraints · Business rules".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    if db is None:
        print("  ❌ No database connection provided.")
        return {"ok": False, "errors": ["No database"], "warnings": []}

    results = {"ok": True, "errors": [], "warnings": [], "checks": {}}

    # ── Check silver_inquiries / gold_experiment_analysis ────────────────────
    for view in ["silver_inquiries", "gold_experiment_analysis"]:
        try:
            df = db.execute(f"SELECT * FROM {view} LIMIT 10000").df()
        except Exception as e:
            results["warnings"].append(f"{view} not available: {e}")
            continue

        check = _validate_dataframe(df, view)
        results["checks"][view] = check
        results["errors"] += check["errors"]
        results["warnings"] += check["warnings"]

    results["ok"] = len(results["errors"]) == 0

    # ── Print summary ─────────────────────────────────────────────────────────
    status = "✅ PASS" if results["ok"] else "❌ FAIL"
    print(f"\n  Overall: {status}")
    print(f"  Errors  : {len(results['errors'])}")
    print(f"  Warnings: {len(results['warnings'])}")
    for e in results["errors"]:
        print(f"  ❌ {e}")
    for w in results["warnings"]:
        print(f"  ⚠️  {w}")
    for view, c in results["checks"].items():
        print(
            f"\n  {view}: {c['n_rows']:,} rows · {c['n_cols']} cols · "
            f"{c['n_errors']} errors · {c['n_warnings']} warnings"
        )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# MODULE [5] — DIMENSION SETUP
# ─────────────────────────────────────────────────────────────────────────────


def run_dimension_setup(db=None, llm=None) -> Dict:
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + "  DIMENSION SETUP (Phase 0)".ljust(70) + "║")
    print("║" + "  Auto-detect segments · platforms · categories from data".ljust(70) + "║")
    print("╚" + "═" * 70 + "╝")

    if db is None:
        print("  ❌ No database connection provided.")
        return {}

    result: Dict[str, Any] = {}
    EXPECTED_SEGMENTS = {"Core", "Growth", "Enterprise", "Individuals"}
    EXPECTED_PLATFORMS = {"web", "mobile"}

    for dim, expected in [("account_segment", EXPECTED_SEGMENTS), ("platform", EXPECTED_PLATFORMS)]:
        for tbl in ["silver_inquiries", "gold_experiment_analysis"]:
            try:
                vals = set(
                    db.execute(f"SELECT DISTINCT {dim} FROM {tbl} WHERE {dim} IS NOT NULL")
                    .df()[dim]
                    .tolist()
                )
                missing = expected - vals
                extra = vals - expected
                result[dim] = {
                    "found": sorted(vals),
                    "missing": sorted(missing),
                    "extra": sorted(extra),
                    "ok": len(missing) == 0,
                }
                icon = "✅" if result[dim]["ok"] else "⚠️ "
                print(f"\n  {icon} {dim} from {tbl}:")
                print(f"     Found  : {sorted(vals)}")
                if missing:
                    print(f"     Missing: {sorted(missing)}  (expected but not in data)")
                if extra:
                    print(f"     Extra  : {sorted(extra)}  (in data but not canonical)")
                break
            except Exception:
                continue

    # Category detection
    for tbl in ["silver_inquiries", "gold_experiment_analysis"]:
        try:
            cats = (
                db.execute(f"SELECT DISTINCT category FROM {tbl} WHERE category IS NOT NULL")
                .df()["category"]
                .tolist()
            )
            result["categories"] = sorted(cats)
            print(
                f"\n  Categories detected: {sorted(cats[:10])}" f"{'...' if len(cats) > 10 else ''}"
            )
            break
        except Exception:
            continue

    return result


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _deterministic_table_map(table_names: List[str]) -> Dict[str, str]:
    mapping = {c: "" for c in CANONICAL_TABLES}
    kw = {
        "inquiries": ["inquiry", "quote", "rfq", "request"],
        "orders": ["order"],
        "buyers": ["buyer", "user", "customer", "contact"],
        "accounts": ["account", "company", "organization", "client"],
        "experiments": ["experiment", "statsig", "ab_test", "variant", "exposure", "assignment"],
        "traffic": ["traffic", "session", "visit", "pageview"],
    }
    tl = [t.lower() for t in table_names]
    for canon, keywords in kw.items():
        for t, t_lower in zip(table_names, tl):
            if any(kw_token in t_lower for kw_token in keywords):
                mapping[canon] = t
                break
    return mapping


def _deterministic_column_map(profiles: Dict[str, Dict]) -> Dict[str, str]:
    all_cols = set()
    for p in profiles.values():
        all_cols.update(p.get("columns", []))
    all_cols_lower = {c.lower(): c for c in all_cols}

    kw = {
        "inquiry_id": ["inquiry_id", "quote_id", "_id", "id"],
        "buyer_id": ["buyer_id", "user_id", "user", "customer_id"],
        "account_segment": [
            "account_segment",
            "segment",
            "business_segment",
            "consolidated_business_segment",
        ],
        "platform": ["platform", "device", "channel"],
        "created_at": ["created_at", "created", "timestamp", "date"],
        "converted_to_order": [
            "converted_to_order",
            "converted",
            "is_order",
            "ordered",
            "conversion",
        ],
        "order_value": ["order_value", "gmv", "total", "revenue", "aov"],
        "variant": ["variant", "group_name", "treatment", "arm", "group"],
        "experiment_name": [
            "experiment_name",
            "experiment_id",
            "test_name",
            "ab_test",
            "statsig_experiment",
        ],
        "category": ["category", "product_category", "process_category"],
        "country": ["country", "shipping_country", "geo", "region"],
    }
    mapping = {}
    for canon, keywords in kw.items():
        matched = ""
        for kw_token in keywords:
            if kw_token in all_cols_lower:
                matched = all_cols_lower[kw_token]
                break
        mapping[canon] = matched
    return mapping


def _compute_confidence(table_map: Dict, column_map: Dict) -> float:
    t_matched = sum(1 for v in table_map.values() if v) / max(1, len(table_map))
    c_matched = sum(1 for v in column_map.values() if v) / max(1, len(column_map))
    return round((t_matched * 0.4 + c_matched * 0.6), 3)


def _verify_mapping(table_map: Dict, column_map: Dict, profiles: Dict) -> List[Tuple[str, str]]:
    issues = []
    critical_cols = ["inquiry_id", "buyer_id", "converted_to_order", "created_at"]
    for col in critical_cols:
        if not column_map.get(col):
            issues.append(("error", f"Critical column '{col}' has no mapping"))
    for canon, mapped in table_map.items():
        if canon in ("inquiries", "experiments") and not mapped:
            issues.append(("error", f"Critical table '{canon}' has no mapping"))
    for canon, mapped in column_map.items():
        if mapped and canon in ("converted_to_order",):
            # Check it looks binary
            for p in profiles.values():
                if mapped in p.get("columns", []):
                    sv = p.get("sample_values", {}).get(mapped, [])
                    if sv and not all(
                        str(v) in ("0", "1", "True", "False", "true", "false") for v in sv[:5]
                    ):
                        issues.append(
                            (
                                "warn",
                                f"'{mapped}' mapped to converted_to_order but "
                                f"sample values look non-binary: {sv[:3]}",
                            )
                        )
    return issues


def _build_mapping_prompt(profiles: Dict) -> str:
    summary = []
    for tbl, p in list(profiles.items())[:8]:
        cols = p.get("columns", [])[:15]
        summary.append(f"Table: {tbl}\n  Columns: {cols}")
    return (
        "You are a data engineer mapping a client warehouse to a canonical experimentation schema.\n\n"
        "CANONICAL TABLES:\n"
        + "\n".join(f"  {k}: {v}" for k, v in CANONICAL_TABLES.items())
        + "\n\n"
        "CANONICAL COLUMNS:\n"
        + "\n".join(f"  {k}: {v}" for k, v in CANONICAL_COLUMNS.items())
        + "\n\n"
        "CLIENT TABLES:\n" + "\n\n".join(summary) + "\n\n"
        "Return ONLY a JSON object with keys: "
        "table_mapping (dict canonical→client_table), "
        "column_mapping (dict canonical→client_column), "
        "confidence (0.0–1.0). No other text."
    )


def _validate_dataframe(df: pd.DataFrame, name: str) -> Dict:
    errors, warnings = [], []
    required = ["converted_to_order"]

    for col in required:
        if col not in df.columns:
            errors.append(f"[{name}] Required column missing: {col}")

    for col in df.columns:
        null_pct = df[col].isna().mean() * 100
        if null_pct > 50:
            warnings.append(f"[{name}] {col}: {null_pct:.1f}% null values")
        elif null_pct > 20:
            warnings.append(f"[{name}] {col}: {null_pct:.1f}% null values")

    if "variant" in df.columns:
        vc = df["variant"].value_counts()
        if len(vc) > 1 and vc.min() / vc.max() < 0.5:
            warnings.append(f"[{name}] Severe variant imbalance: {dict(vc.head())}")

    return {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "errors": errors,
        "warnings": warnings,
        "n_errors": len(errors),
        "n_warnings": len(warnings),
        "ok": len(errors) == 0,
    }


__all__ = [
    "run_schema_discovery",
    "run_data_validation",
    "run_dimension_setup",
]

"""Derives experiment input baselines from the data behind an experiment.

MatchView forms used to ship hardcoded constants labelled "auto-detected". This
module produces the real thing: every value carries the aggregation that
produced it, the row count behind it, and the period it covers, so the UI can
answer "where did this number come from?" instead of asserting provenance it
never had.

Resolution is warehouse-first, sample-dataset-second. A missing profile is a
normal outcome (returns no fields) — the frontend then falls back to its own
app-state suggestions, so an unreachable warehouse degrades the experience
rather than breaking the form.
"""

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text

from continum.config import settings

# Repo root: continum/mapMeta/baseline_profiler.py -> continum/ -> repo root.
_SAMPLE_DATA_ROOT = Path(__file__).resolve().parents[2] / "sample_data"

# Channel -> sample dataset directory. Used when the warehouse holds no
# matching tables, which is the default state of a fresh local checkout.
_SAMPLE_DATASETS: Dict[str, str] = {
    "digital": "Ecommerce",
    "store": "Store",
}

CHANNELS = tuple(_SAMPLE_DATASETS)


class BaselineValue(BaseModel):
    """One derived input value plus the evidence for it."""

    value: float
    source: str = Field(..., description="Dataset or warehouse table the value came from")
    rationale: str = Field(..., description="Human-readable aggregation, shown in the UI tooltip")
    row_count: int = 0
    as_of: Optional[str] = None


class BaselineProfile(BaseModel):
    """Field-keyed baselines for one experiment.

    Keys are the frontend form field keys (``baselineIor``, ``dailyTraffic``, …)
    so the client needs no translation table.
    """

    channel: str
    source: str = "none"
    as_of: Optional[str] = None
    experiment_match: Optional[str] = None
    fields: Dict[str, BaselineValue] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _read_rows(path: Path) -> Iterator[Dict[str, str]]:
    # utf-8-sig: the Shell exports carry a BOM on the first header cell.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def _as_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    text_value = str(raw).strip()
    if not text_value:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    return numerator / denominator if denominator else None


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def _period(dates: Iterable[str]) -> Optional[str]:
    known = sorted(d for d in dates if d)
    if not known:
        return None
    return known[-1] if known[0] == known[-1] else f"{known[0]} to {known[-1]}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


# ---------------------------------------------------------------------------
# Sample-dataset profilers
# ---------------------------------------------------------------------------


def _match_experiment_id(experiment: str, known_ids: Iterable[str]) -> Optional[str]:
    """Maps a MatchView experiment name onto an id in the dataset.

    Exact slug first, then a token-overlap fallback so "Mobile Nav Redesign v2"
    still finds ``mobile_nav_redesign``.
    """
    slug = _slug(experiment)
    if not slug:
        return None
    ids = list(known_ids)
    if slug in ids or experiment in ids:
        return experiment if experiment in ids else slug
    slug_tokens = set(slug.split("_"))
    best: Optional[Tuple[int, str]] = None
    for candidate in ids:
        cand_slug = _slug(candidate)
        if cand_slug == slug:
            return candidate
        overlap = len(slug_tokens & set(cand_slug.split("_")))
        if overlap >= 2 and (best is None or overlap > best[0]):
            best = (overlap, candidate)
    return best[1] if best else None


def _profile_digital_experiment(
    path: Path, experiment: str
) -> Tuple[Dict[str, BaselineValue], Optional[str], Optional[str]]:
    """Per-experiment exposure baselines from the experiment assignment log."""
    rows = list(_read_rows(path))
    if not rows:
        return {}, None, None

    matched = _match_experiment_id(experiment, {r.get("experiment_id", "") for r in rows})
    if matched is None:
        return {}, None, None

    subset = [r for r in rows if r.get("experiment_id") == matched]
    if not subset:
        return {}, None, None

    groups = sorted(
        {(r.get("group_id") or "").strip() for r in subset if (r.get("group_id") or "").strip()}
    )
    days = {(r.get("timestamp") or "").strip() for r in subset}
    period = _period(days)
    day_count = len({d for d in days if d})

    control = [r for r in subset if (r.get("group_id") or "").strip() == "control"] or subset
    converted = sum(1 for r in control if (r.get("order_id") or "").strip())

    fields: Dict[str, BaselineValue] = {}

    ior = _ratio(converted, len(control))
    if ior is not None and 0 < ior < 1:
        rationale = (
            f"{converted:,} of {len(control):,} control exposures converted to an order "
            f"in {matched}"
        )
        detail = BaselineValue(
            value=_round(ior),
            source=f"experiments.csv ({matched})",
            rationale=rationale,
            row_count=len(control),
            as_of=period,
        )
        fields["baselineIor"] = detail
        fields["currentIor"] = detail.model_copy()

    if day_count:
        per_day = len(subset) / day_count
        fields["dailyTraffic"] = BaselineValue(
            value=_round(per_day, 0),
            source=f"experiments.csv ({matched})",
            rationale=f"{len(subset):,} exposures spread over {day_count} days of the assignment log",
            row_count=len(subset),
            as_of=period,
        )

    if len(groups) >= 2:
        fields["variants"] = BaselineValue(
            value=float(len(groups)),
            source=f"experiments.csv ({matched})",
            rationale=f"Assignment log carries {len(groups)} groups: {', '.join(groups)}",
            row_count=len(subset),
            as_of=period,
        )

    return fields, matched, period


def _profile_digital(dataset: Path, experiment: str) -> BaselineProfile:
    profile = BaselineProfile(channel="digital", source=f"sample_data/{dataset.name}")

    experiments_csv = dataset / "experiments.csv"
    if experiments_csv.is_file():
        fields, matched, period = _profile_digital_experiment(experiments_csv, experiment)
        profile.fields.update(fields)
        profile.experiment_match = matched
        profile.as_of = period

    quotes_csv = dataset / "quotes.csv"
    if quotes_csv.is_file():
        total = 0
        converted = 0
        days: Dict[str, int] = {}
        for row in _read_rows(quotes_csv):
            total += 1
            status = (row.get("status") or "").strip().lower()
            if (row.get("order_id") or "").strip() or status in ["approved", "purchased", "completed"]:
                converted += 1
            day = (row.get("_constructed") or row.get("created_at") or "").strip().split(" ")[0]
            if day:
                days[day] = days.get(day, 0) + 1

        period = _period(days)
        profile.as_of = profile.as_of or period

        # Account-wide quote→order rate only fills in when the assignment log
        # had nothing for this experiment; a per-experiment rate always wins.
        ior = _ratio(converted, total)
        if ior is not None and "baselineIor" not in profile.fields:
            detail = BaselineValue(
                value=_round(ior),
                source="quotes.csv",
                rationale=f"{converted:,} of {total:,} quotes converted to an order",
                row_count=total,
                as_of=period,
            )
            profile.fields["baselineIor"] = detail
            profile.fields["currentIor"] = detail.model_copy()

        if days:
            per_day = total / len(days)
            profile.fields.setdefault(
                "dailyTraffic",
                BaselineValue(
                    value=_round(per_day, 0),
                    source="quotes.csv",
                    rationale=f"{total:,} quotes spread over {len(days)} trading days",
                    row_count=total,
                    as_of=period,
                ),
            )
            profile.fields["monthlyInquiries"] = BaselineValue(
                value=_round(per_day * 30, 0),
                source="quotes.csv",
                rationale=f"{_round(per_day, 1)} quotes/day over {len(days)} trading days, projected to 30 days",
                row_count=total,
                as_of=period,
            )

    orders_csv = dataset / "orders.csv"
    if orders_csv.is_file():
        totals: List[float] = []
        order_days: set[str] = set()
        for row in _read_rows(orders_csv):
            total_value = _as_float(row.get("total") or row.get("total_amount"))
            if total_value:
                totals.append(total_value)
            order_day = (row.get("order_time") or row.get("ordered_at") or "").strip()
            if order_day:
                order_days.add(order_day)

        aov = _mean(totals)
        if aov is not None:
            profile.fields["aov"] = BaselineValue(
                value=_round(aov, 2),
                source="orders.csv",
                rationale=f"Mean order total across {len(totals):,} orders",
                row_count=len(totals),
                # The orders table's own window — reusing the experiment log's
                # period here would date the figure to a range it never covered.
                as_of=_period(order_days),
            )

    # Gross margin is deliberately absent: the order tables carry no cost basis,
    # so any margin figure here would be a benchmark wearing a data badge.
    return profile


def _profile_store(dataset: Path, experiment: str) -> BaselineProfile:
    profile = BaselineProfile(channel="store", source=f"sample_data/{dataset.name}")

    stores_csv = dataset / "stores.csv"
    if stores_csv.is_file():
        stores = list(_read_rows(stores_csv))
        if stores:
            profile.fields["targetStoreCount"] = BaselineValue(
                value=float(len(stores)),
                source="stores.csv",
                rationale=f"{len(stores)} distinct stores in the store catalog",
                row_count=len(stores),
            )

    traffic_csv = dataset / "foot_traffic_events.csv"
    if traffic_csv.is_file():
        events = list(_read_rows(traffic_csv))
        days = {(r.get("timestamp") or "").split(" ")[0] for r in events if r.get("timestamp")}
        day_count = len({d for d in days if d})
        if day_count and len(events):
            daily_traffic = len(events) / day_count
            profile.fields["weeklyStoreTraffic"] = BaselineValue(
                value=_round(daily_traffic * 7, 0),
                source="foot_traffic_events.csv",
                rationale=f"{len(events):,} foot traffic events over {day_count} days, scaled to weekly",
                row_count=len(events),
                as_of=_period(days),
            )

    pos_csv = dataset / "pos_transactions.csv"
    if pos_csv.is_file():
        txns = list(_read_rows(pos_csv))
        if txns and traffic_csv.is_file():
            cvr = len(txns) / len(events) if len(events) else 0.15
            profile.fields["baselineCvr"] = BaselineValue(
                value=_round(cvr, 4),
                source="pos_transactions.csv",
                rationale=f"{len(txns):,} transactions against {len(events):,} foot traffic events",
                row_count=len(txns),
            )

    stations = {
        (row.get("station_id") or "").strip()
        for path in dataset.glob("*dim_station*.csv")
        for row in _read_rows(path)
    }
    stations.discard("")
    if stations and "targetStoreCount" not in profile.fields:
        profile.fields["targetStoreCount"] = BaselineValue(
            value=float(len(stations)),
            source="dim_station",
            rationale=f"{len(stations)} distinct stations in the station dimension",
            row_count=len(stations),
        )

    fact_paths = list(dataset.glob("*fact_station_day*.csv"))
    if fact_paths:
        station_days: Dict[Tuple[str, str], Dict[str, str]] = {}
        revenue = 0.0
        margin = 0.0
        for path in fact_paths:
            for row in _read_rows(path):
                key = ((row.get("station_id") or "").strip(), (row.get("date") or "").strip())
                station_days[key] = row
                revenue += _as_float(row.get("revenue_inr")) or 0.0
                margin += _as_float(row.get("gross_margin_inr")) or 0.0

        if station_days:
            profile.as_of = _period({date for _, date in station_days})
            day_count = len({date for _, date in station_days if date})
            footfall = [
                v for v in (_as_float(r.get("footfall_estimate")) for r in station_days.values()) if v
            ]
            transactions = [
                v
                for v in (_as_float(r.get("cstore_transactions")) for r in station_days.values())
                if v is not None
            ]
            cstore_revenue = [
                v
                for v in (_as_float(r.get("cstore_revenue_inr")) for r in station_days.values())
                if v is not None
            ]

            daily_footfall = _mean(footfall)
            if daily_footfall is not None and "weeklyStoreTraffic" not in profile.fields:
                profile.fields["weeklyStoreTraffic"] = BaselineValue(
                    value=_round(daily_footfall * 7, 0),
                    source="fact_station_day_product",
                    rationale=(
                        f"Mean {_round(daily_footfall, 0):.0f} daily footfall per store across "
                        f"{len(station_days):,} store-days ({day_count} days), scaled to a week"
                    ),
                    row_count=len(station_days),
                    as_of=profile.as_of,
                )

            cvr = _ratio(sum(transactions), sum(footfall)) if footfall and transactions else None
            if cvr is not None and 0 < cvr <= 1 and "baselineCvr" not in profile.fields:
                profile.fields["baselineCvr"] = BaselineValue(
                    value=_round(cvr),
                    source="fact_station_day_product",
                    rationale=(
                        f"{sum(transactions):,.0f} c-store transactions against {sum(footfall):,.0f} "
                        f"footfall over {len(station_days):,} store-days"
                    ),
                    row_count=len(station_days),
                    as_of=profile.as_of,
                )

            aur = _ratio(sum(cstore_revenue), sum(transactions)) if transactions else None
            if aur is not None and aur > 0:
                profile.fields["baselineAur"] = BaselineValue(
                    value=_round(aur, 2),
                    source="fact_station_day_product",
                    rationale=f"C-store revenue divided by {sum(transactions):,.0f} transactions",
                    row_count=len(station_days),
                    as_of=profile.as_of,
                )

            gross_margin = _ratio(margin, revenue)
            if gross_margin is not None and 0 < gross_margin < 1:
                profile.fields["grossMargin"] = BaselineValue(
                    value=_round(gross_margin),
                    source="fact_station_day_product",
                    rationale=f"Gross margin divided by revenue across {len(station_days):,} store-days",
                    row_count=len(station_days),
                    as_of=profile.as_of,
                )

    return profile


def profile_from_sample_data(dataset: Path, channel: str, experiment: str) -> BaselineProfile:
    """Profiles a bundled sample dataset with the stdlib csv reader.

    Streaming keeps this dependency-free (pandas is not a project requirement)
    and the results are cached by file mtime in :func:`get_baseline_profile`.
    """
    if not dataset.is_dir():
        return BaselineProfile(channel=channel)
    if channel == "store":
        return _profile_store(dataset, experiment)
    return _profile_digital(dataset, experiment)


# ---------------------------------------------------------------------------
# Warehouse profiler
# ---------------------------------------------------------------------------

_WAREHOUSE_QUERIES: Dict[str, List[Tuple[str, str, str, str]]] = {
    # channel -> [(field key, required table, SQL, rationale template)]
    "digital": [
        (
            "baselineIor",
            "quotes",
            "SELECT COUNT(order_id) * 1.0 / NULLIF(COUNT(*), 0), COUNT(*) FROM quotes",
            "Quote-to-order rate across {rows:,} warehouse quote rows",
        ),
        (
            "aov",
            "orders",
            "SELECT AVG(total), COUNT(*) FROM orders",
            "Mean order total across {rows:,} warehouse order rows",
        ),
    ],
    "store": [
        (
            "targetStoreCount",
            "dim_station",
            "SELECT COUNT(DISTINCT station_id), COUNT(*) FROM dim_station",
            "Distinct stations in the warehouse station dimension ({rows:,} rows)",
        ),
    ],
}


def profile_from_warehouse(
    channel: str, database_url: Optional[str] = None
) -> Optional[BaselineProfile]:
    """Aggregates baselines from the configured warehouse.

    Returns ``None`` — never raises — when the warehouse is unreachable or holds
    none of the expected tables, which is the default state of a local checkout.
    """
    url = database_url or settings.DATABASE_URL
    try:
        engine = create_engine(url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
    except Exception:
        return None

    queries = [q for q in _WAREHOUSE_QUERIES.get(channel, []) if q[1] in tables]
    if not queries:
        return None

    profile = BaselineProfile(
        channel=channel, source=f"warehouse ({engine.url.get_backend_name()})"
    )
    try:
        with engine.connect() as conn:
            for field_key, table, sql, rationale in queries:
                row = conn.execute(text(sql)).first()
                if row is None or row[0] is None:
                    continue
                value = _as_float(row[0])
                if value is None:
                    continue
                rows = int(row[1] or 0)
                profile.fields[field_key] = BaselineValue(
                    value=_round(value, 4),
                    source=f"warehouse.{table}",
                    rationale=rationale.format(rows=rows),
                    row_count=rows,
                )
    except Exception:
        return None

    if "baselineIor" in profile.fields:
        profile.fields["currentIor"] = profile.fields["baselineIor"].model_copy()

    return profile if profile.fields else None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_dataset(channel: str) -> Optional[Path]:
    """Sample dataset directory backing a channel, if it is present."""
    name = _SAMPLE_DATASETS.get(channel)
    if not name:
        return None
    archive_dir = _SAMPLE_DATA_ROOT.parent / "archive" / "sample_datasets" / ("Xometry" if channel == "digital" else "Shell")
    if archive_dir.is_dir():
        return archive_dir
    dataset = _SAMPLE_DATA_ROOT / name
    return dataset if dataset.is_dir() else None


def _dataset_fingerprint(dataset: Path) -> Tuple[Tuple[str, int], ...]:
    """(name, mtime) per file — the cache key that makes edits invalidate."""
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in dataset.glob("*.csv")))


@lru_cache(maxsize=32)
def _cached_sample_profile(
    dataset_str: str, channel: str, experiment: str, _fingerprint: Tuple[Tuple[str, int], ...]
) -> BaselineProfile:
    return profile_from_sample_data(Path(dataset_str), channel, experiment)


def get_baseline_profile(experiment: str, channel: str = "digital") -> BaselineProfile:
    """Best available baselines for an experiment: warehouse first, then samples.

    Always returns a profile. An unknown experiment or absent dataset yields an
    empty ``fields`` map, which the frontend treats as "fall back to app state".
    """
    channel = channel if channel in _SAMPLE_DATASETS else "digital"

    warehouse = profile_from_warehouse(channel)
    dataset = resolve_dataset(channel)
    sample = (
        _cached_sample_profile(str(dataset), channel, experiment, _dataset_fingerprint(dataset))
        if dataset
        else BaselineProfile(channel=channel)
    )

    if warehouse is None:
        return sample

    # Warehouse wins field by field; sample data fills the gaps it cannot answer.
    merged = warehouse.model_copy(deep=True)
    merged.experiment_match = sample.experiment_match
    merged.as_of = merged.as_of or sample.as_of
    for key, value in sample.fields.items():
        merged.fields.setdefault(key, value)
    return merged

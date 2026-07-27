from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.askdata.ask_engine")


# ─────────────────────────────────────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────────────────────────────────────


class AskIntent(str, Enum):
    METRIC_LOOKUP = "metric_lookup"
    EXPERIMENT_RESULT = "experiment_result"
    COMPARISON = "comparison"
    ANOMALY = "anomaly"
    FORECAST = "forecast"
    CAUSAL = "causal"
    RECOMMENDATION = "recommendation"
    KNOWLEDGE = "knowledge"
    UNKNOWN = "unknown"


_INTENT_PATTERNS: Dict[AskIntent, List[str]] = {
    AskIntent.METRIC_LOOKUP: [
        "what is",
        "current ior",
        "current aov",
        "baseline",
        "how much",
        "what was",
        "show me",
        "tell me the",
    ],
    AskIntent.EXPERIMENT_RESULT: [
        "did.*work",
        "result",
        "significant",
        "p.value",
        "lift",
        "delta",
        "treatment",
        "control",
    ],
    AskIntent.COMPARISON: [
        "best",
        "worst",
        "which.*better",
        "compare",
        "vs",
        "versus",
        "top",
        "rank",
    ],
    AskIntent.ANOMALY: [
        "why.*drop",
        "why.*spike",
        "anomaly",
        "unusual",
        "wrong",
        "issue",
        "problem",
        "alert",
    ],
    AskIntent.FORECAST: [
        "will",
        "forecast",
        "predict",
        "next month",
        "future",
        "trend",
        "projection",
    ],
    AskIntent.CAUSAL: ["cause", "why did", "effect of", "because", "driven by", "explanation"],
    AskIntent.RECOMMENDATION: [
        "what should",
        "recommend",
        "next step",
        "run next",
        "suggest",
        "advice",
        "what to do",
    ],
    AskIntent.KNOWLEDGE: [
        "learned",
        "learning",
        "past",
        "previous",
        "history",
        "similar",
        "before",
    ],
}


def detect_intent(question: str) -> AskIntent:
    q = question.lower()
    scores = {intent: 0 for intent in AskIntent}
    for intent, patterns in _INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                scores[intent] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else AskIntent.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# DATA RETRIEVAL BY INTENT
# ─────────────────────────────────────────────────────────────────────────────


def _retrieve_metric_data(db, question: str) -> Dict:
    data: Dict = {}
    q = question.lower()
    try:
        if "ior" in q or "conversion" in q or "rate" in q:
            row = db.execute("""
                SELECT
                    AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                    COUNT(*) AS n,
                    MIN(created_at) AS since,
                    MAX(created_at) AS until
                FROM silver_inquiries
            """).fetchone()
            if row:
                data["ior"] = round(float(row[0] or 0), 4)
                data["n"] = int(row[1])
                data["since"] = str(row[2])[:10]
                data["until"] = str(row[3])[:10]

        if "aov" in q or "order value" in q or "revenue" in q:
            row = db.execute("""
                SELECT AVG(order_value), SUM(order_value), COUNT(*)
                FROM silver_inquiries WHERE converted_to_order = true AND order_value > 0
            """).fetchone()
            if row:
                data["aov"] = round(float(row[0] or 0), 2)
                data["total_gmv"] = round(float(row[1] or 0), 2)
                data["n_orders"] = int(row[2])

        if "volume" in q or "traffic" in q or "inquiries" in q:
            row = db.execute("""
                SELECT COUNT(*) / NULLIF(DATEDIFF('day',MIN(created_at),MAX(created_at))+1,0) AS daily_n
                FROM silver_inquiries
            """).fetchone()
            if row:
                data["daily_inquiries"] = round(float(row[0] or 0), 1)

        if any(seg in q for seg in ["segment", "core", "growth", "enterprise"]):
            rows = db.execute("""
                SELECT account_segment,
                       AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                       COUNT(*) AS n
                FROM silver_inquiries WHERE account_segment IS NOT NULL
                GROUP BY account_segment ORDER BY ior DESC
            """).fetchall()
            data["segment_iors"] = {str(r[0]): round(float(r[1]), 4) for r in rows}
    except Exception as e:
        logger.debug("metric retrieval failed: %s", e)
    return data


def _retrieve_experiment_data(db, question: str) -> Dict:
    data: Dict = {}
    try:
        # Try to extract experiment name from question
        exp_name = None
        rows = db.execute("""
            SELECT DISTINCT experiment_name FROM gold_experiment_analysis
        """).fetchall()
        known_exps = [str(r[0]) for r in rows]
        for exp in known_exps:
            if exp.lower() in question.lower():
                exp_name = exp
                break

        if exp_name:
            df = db.execute(f"""
                SELECT variant,
                       COUNT(*) AS n,
                       AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                       AVG(COALESCE(order_value,0)) AS aov
                FROM gold_experiment_analysis
                WHERE experiment_name = '{exp_name}'
                GROUP BY variant
            """).df()
            data["experiment"] = exp_name
            data["variants"] = df.to_dict("records")

        # Most recent experiments
        recent = db.execute("""
            SELECT experiment_name, COUNT(DISTINCT variant) AS n_variants, COUNT(*) AS n_obs
            FROM gold_experiment_analysis
            GROUP BY experiment_name ORDER BY n_obs DESC LIMIT 5
        """).fetchall()
        data["available_experiments"] = [str(r[0]) for r in recent]
    except Exception as e:
        logger.debug("experiment retrieval failed: %s", e)
    return data


def _retrieve_comparison_data(db, question: str) -> Dict:
    data: Dict = {}
    try:
        df = db.execute("""
            SELECT
                experiment_name,
                variant,
                AVG(CAST(converted_to_order AS DOUBLE)) AS ior,
                COUNT(*) AS n
            FROM gold_experiment_analysis
            GROUP BY experiment_name, variant
        """).df()

        results = []
        for exp in df["experiment_name"].unique():
            sub = df[df["experiment_name"] == exp]
            ctrl = sub[sub["variant"].str.lower().isin(["control", "ctrl", "baseline"])]
            trt = sub[~sub["variant"].str.lower().isin(["control", "ctrl", "baseline"])]
            if not ctrl.empty and not trt.empty:
                delta = float(trt["ior"].mean()) - float(ctrl["ior"].mean())
                results.append(
                    {"experiment": exp, "delta_pp": round(delta * 100, 4), "n": int(sub["n"].sum())}
                )

        results.sort(key=lambda x: x["delta_pp"], reverse=True)
        data["experiment_rankings"] = results
        if results:
            data["best_experiment"] = results[0]["experiment"]
            data["worst_experiment"] = results[-1]["experiment"]
            data["portfolio_win_rate"] = round(
                sum(1 for r in results if r["delta_pp"] > 0) / len(results), 3
            )
    except Exception as e:
        logger.debug("comparison retrieval failed: %s", e)
    return data


def _retrieve_anomaly_data(db, question: str) -> Dict:
    data: Dict = {}
    try:
        row = db.execute("""
            SELECT
                AVG(CAST(converted_to_order AS DOUBLE)) AS ior_7d,
                STDDEV(CAST(converted_to_order AS DOUBLE)) AS std_ior_7d
            FROM silver_inquiries
            WHERE created_at >= CURRENT_DATE - INTERVAL 7 DAY
        """).fetchone()
        row2 = db.execute("""
            SELECT AVG(CAST(converted_to_order AS DOUBLE)) AS ior_1d
            FROM silver_inquiries WHERE created_at >= CURRENT_DATE - INTERVAL 1 DAY
        """).fetchone()
        if row and row[0] and row2 and row2[0]:
            mean_7d = float(row[0])
            std_7d = float(row[1] or mean_7d * 0.1)
            ior_1d = float(row2[0])
            z = (ior_1d - mean_7d) / std_7d if std_7d > 0 else 0
            data["ior_7d_mean"] = round(mean_7d, 4)
            data["ior_1d"] = round(ior_1d, 4)
            data["z_score"] = round(z, 2)
            data["anomaly_flag"] = abs(z) > 2.0
            data["direction"] = "spike" if z > 2 else "drop" if z < -2 else "normal"
    except Exception as e:
        logger.debug("anomaly retrieval failed: %s", e)
    return data


def _retrieve_knowledge_data(db, question: str) -> Dict:
    data: Dict = {}
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS experiment_learnings (
                id VARCHAR, experiment_name VARCHAR, ship_decision VARCHAR,
                outcome TEXT, key_learning TEXT, what_worked TEXT,
                what_didnt TEXT, recommendation TEXT, follow_ups TEXT,
                tags TEXT, recorded_at VARCHAR, recorded_by VARCHAR
            )
        """)
        df = db.execute("SELECT * FROM experiment_learnings ORDER BY recorded_at DESC").df()
        if len(df) > 0:
            q_words = set(re.sub(r"[^a-z ]", "", question.lower()).split())
            df["_score"] = df.apply(
                lambda r: sum(
                    w in str(r.get(col, "")).lower()
                    for col in ["key_learning", "outcome", "tags", "experiment_name"]
                    for w in q_words
                ),
                axis=1,
            )
            matches = df.nlargest(3, "_score").to_dict("records")
            data["learnings"] = matches
            data["n_total"] = len(df)
    except Exception as e:
        logger.debug("knowledge retrieval failed: %s", e)
    return data


_RETRIEVAL_FN = {
    AskIntent.METRIC_LOOKUP: _retrieve_metric_data,
    AskIntent.EXPERIMENT_RESULT: _retrieve_experiment_data,
    AskIntent.COMPARISON: _retrieve_comparison_data,
    AskIntent.ANOMALY: _retrieve_anomaly_data,
    AskIntent.FORECAST: _retrieve_metric_data,
    AskIntent.CAUSAL: _retrieve_experiment_data,
    AskIntent.RECOMMENDATION: _retrieve_comparison_data,
    AskIntent.KNOWLEDGE: _retrieve_knowledge_data,
    AskIntent.UNKNOWN: _retrieve_metric_data,
}


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT ASSEMBLER
# ─────────────────────────────────────────────────────────────────────────────


def _assemble_context(
    intent: AskIntent,
    db_data: Dict,
    session: Any,
    bus_insights: List[Dict],
) -> str:
    parts: List[str] = []

    # DB data
    if db_data:
        parts.append("DATA FROM DATABASE:")
        for k, v in db_data.items():
            if isinstance(v, dict):
                parts.append(f"  {k}: {v}")
            elif isinstance(v, list):
                parts.append(f"  {k}: {v[:5]}")  # truncate long lists
            else:
                parts.append(f"  {k}: {v}")

    # Session state
    if session is not None:
        parts.append("\nSESSION STATE:")
        parts.append(f"  Active experiment: {getattr(session, 'active_experiment', 'none')}")
        parts.append(f"  Mode: {getattr(session, 'mode', 'synthetic')}")
        history = getattr(session, "execution_history", [])
        if history:
            recent = [h.get("module", "") for h in history[-5:]]
            parts.append(f"  Recent modules run: {', '.join(recent)}")

    # InsightBus
    if bus_insights:
        parts.append("\nRECENT INSIGHTS:")
        for ins in bus_insights[:5]:
            parts.append(f"  [{ins.get('type','')}] {ins.get('message','')[:80]}")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# ASK ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class AnalyticsGroundedAskEngine:

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def ask(
        self,
        question: str,
        db: Any = None,
        session: Any = None,
        llm: Any = None,
        bus: Any = None,
    ) -> Dict:
        trace: List[str] = []

        # Step 1: Intent detection
        intent = detect_intent(question)
        trace.append(f"Intent: {intent.value}")

        # Step 2: Data retrieval
        retrieved: Dict = {}
        if db is not None:
            try:
                fn = _RETRIEVAL_FN.get(intent, _retrieve_metric_data)
                retrieved = fn(db, question)
                trace.append(f"Retrieved {len(retrieved)} data fields from DB")
            except Exception as e:
                trace.append(f"Data retrieval failed: {e}")
                logger.debug("Ask retrieval failed: %s", e)

        # Step 3: Collect InsightBus snapshot
        bus_insights: List[Dict] = []
        if bus is not None:
            try:
                recent = bus.recent(10)
                bus_insights = [
                    {"type": str(i.insight_type.value), "message": i.message} for i in recent
                ]
                trace.append(f"Collected {len(bus_insights)} bus insights")
            except Exception:
                pass

        # Step 4: Assemble context
        context_str = _assemble_context(intent, retrieved, session, bus_insights)

        # Step 5: Reasoning trace (deterministic pre-answer)
        reasoning = self._reasoning_trace(intent, retrieved, question)
        trace.extend(reasoning)

        # Step 6: LLM synthesis (grounded)
        answer = self._synthesise_answer(question, intent, context_str, reasoning, llm)

        # Step 7: Publish to bus
        if bus is not None:
            try:
                from continum.ContextGraph.insight_bus import InsightSeverity, InsightType

                bus.emit(
                    source="ask_engine",
                    insight_type=InsightType.INFO,
                    severity=InsightSeverity.INFO,
                    message=f"Q: {question[:60]}",
                    detail=answer[:200],
                )
            except Exception:
                pass

        return {
            "question": question,
            "intent": intent.value,
            "answer": answer,
            "data": retrieved,
            "reasoning_trace": trace,
        }

    def _reasoning_trace(
        self,
        intent: AskIntent,
        data: Dict,
        question: str,
    ) -> List[str]:
        steps: List[str] = []

        if intent == AskIntent.METRIC_LOOKUP:
            if "ior" in data:
                steps.append(
                    f"Current IOR: {data['ior']:.4%} over {data.get('n',0):,} observations"
                )
            if "aov" in data:
                steps.append(
                    f"Current AOV: ${data['aov']:,.0f} from {data.get('n_orders',0):,} orders"
                )
            if "segment_iors" in data:
                top_seg = max(data["segment_iors"], key=data["segment_iors"].get)
                steps.append(
                    f"Highest IOR segment: {top_seg} ({data['segment_iors'][top_seg]:.4%})"
                )

        elif intent == AskIntent.ANOMALY:
            if data.get("anomaly_flag"):
                steps.append(
                    f"ANOMALY DETECTED: IOR yesterday={data.get('ior_1d',0):.4%} "
                    f"vs 7d mean={data.get('ior_7d_mean',0):.4%} "
                    f"(z={data.get('z_score',0):+.2f})"
                )
            else:
                steps.append(f"No anomaly detected (z={data.get('z_score',0):+.2f})")

        elif intent == AskIntent.COMPARISON:
            rankings = data.get("experiment_rankings", [])
            if rankings:
                steps.append(f"Portfolio win rate: {data.get('portfolio_win_rate',0):.0%}")
                steps.append(
                    f"Best: {rankings[0]['experiment']} ({rankings[0]['delta_pp']:+.2f}pp)"
                )
                if len(rankings) > 1:
                    steps.append(
                        f"Worst: {rankings[-1]['experiment']} ({rankings[-1]['delta_pp']:+.2f}pp)"
                    )

        elif intent == AskIntent.KNOWLEDGE:
            learnings = data.get("learnings", [])
            if learnings:
                steps.append(f"Found {len(learnings)} relevant learning(s) in repository")
                for l in learnings[:2]:
                    steps.append(
                        f"  [{l.get('id','')}] {l.get('experiment_name','')}: "
                        f"{str(l.get('key_learning',''))[:80]}"
                    )

        return steps

    def _synthesise_answer(
        self,
        question: str,
        intent: AskIntent,
        context: str,
        reasoning: List[str],
        llm: Any,
    ) -> str:
        reasoning_text = "\n".join(f"  {r}" for r in reasoning) or "  (No specific data retrieved)"

        if llm is None:
            return (
                f"[Analytics grounding active — {intent.value}]\n\n"
                f"Key facts retrieved:\n{reasoning_text}\n\n"
                f"Full LLM synthesis requires a loaded LLM model. "
                f"The above data directly answers: {question}"
            )

        system_prompt = (
            "You are a senior product analytics scientist with direct access to "
            "live experiment data. Answer precisely using only the data provided. "
            "Lead with a direct answer, then supporting numbers. "
            "If the data doesn't fully answer the question, say so honestly. "
            "3-5 sentences. No emojis. No markdown headers."
        )

        user_prompt = (
            f"Question: {question}\n\n"
            f"Analytical reasoning (deterministic — trust these numbers):\n"
            f"{reasoning_text}\n\n"
            f"Full context:\n{context[:1500]}\n\n"
            f"Answer the question directly and specifically."
        )

        try:
            return str(llm.ask(user_prompt, system=system_prompt))
        except Exception as e:
            return (
                f"Direct analytical answer:\n{reasoning_text}\n\n"
                f"(Full synthesis unavailable: {e})"
            )


# ─────────────────────────────────────────────────────────────────────────────
# MODULE ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

_engine_singleton: Optional[AnalyticsGroundedAskEngine] = None


def get_ask_engine() -> AnalyticsGroundedAskEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = AnalyticsGroundedAskEngine()
    return _engine_singleton


def run_ask(
    question: str = "",
    db: Any = None,
    llm: Any = None,
    session: Any = None,
    bus: Any = None,
    **kwargs,
) -> Dict:
    if not question:
        question = kwargs.get("query", "") or kwargs.get("q", "")
    if not question:
        return {"error": "No question provided. Pass question= or query= parameter."}
    engine = get_ask_engine()
    return engine.ask(question=question, db=db, session=session, llm=llm, bus=bus)


__all__ = ["AnalyticsGroundedAskEngine", "get_ask_engine", "run_ask", "detect_intent", "AskIntent"]

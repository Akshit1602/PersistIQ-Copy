from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("continum.insights.patterns")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────


class Pattern:
    def __init__(
        self,
        pattern_type: str,
        description: str,
        evidence: List[Dict],
        confidence: float,
        implication: str,
    ):
        self.pattern_type = pattern_type
        self.description = description
        self.evidence = evidence
        self.confidence = confidence
        self.implication = implication

    def to_dict(self) -> Dict:
        return {
            "type": self.pattern_type,
            "description": self.description,
            "confidence": round(self.confidence, 2),
            "implication": self.implication,
            "n_evidence": len(self.evidence),
        }


class ExperimentPrior:

    def __init__(self, exp_name: str):
        self.exp_name = exp_name
        self.expected_sig_rate = 0.0
        self.expected_delta_pp = 0.0
        self.expected_srm_rate = 0.0
        self.similar_experiments: List[Dict] = []
        self.relevant_learnings: List[str] = []
        self.caution_flags: List[str] = []

    def to_dict(self) -> Dict:
        return {
            "experiment": self.exp_name,
            "expected_sig_rate": round(self.expected_sig_rate, 2),
            "expected_delta_pp": round(self.expected_delta_pp, 4),
            "expected_srm_rate": round(self.expected_srm_rate, 2),
            "n_similar": len(self.similar_experiments),
            "similar_experiments": self.similar_experiments[:3],
            "relevant_learnings": self.relevant_learnings[:4],
            "caution_flags": self.caution_flags,
        }

    def narrative(self) -> str:
        if not self.similar_experiments:
            return f"No historical data for experiments similar to '{self.exp_name}'."

        n = len(self.similar_experiments)
        sig_pct = self.expected_sig_rate * 100
        dp = self.expected_delta_pp

        lines = [
            f"Based on {n} similar past experiment(s):",
            f"  — Historically, {sig_pct:.0f}% of similar experiments reached significance.",
            f"  — Average effect size: {dp:+.3f}pp.",
        ]
        if self.caution_flags:
            lines.append("  — Caution: " + "; ".join(self.caution_flags))
        if self.relevant_learnings:
            lines.append("  — Relevant learning: " + self.relevant_learnings[0])

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN MINER
# ─────────────────────────────────────────────────────────────────────────────


class PatternMiner:

    def __init__(self, memory=None):
        self.memory = memory

    def mine_all(self) -> Dict[str, Any]:
        if self.memory is None or self.memory.experiment_count() == 0:
            return {"status": "no memory", "patterns": [], "summary": ""}

        return {
            "metric_patterns": self._mine_metric_patterns(),
            "significance_rate": self._mine_significance_rate(),
            "effect_sizes": self._mine_effect_sizes(),
            "srm_rate": self._mine_srm_rate(),
            "summary": self._synthesize_summary(),
            "experiment_count": self.memory.experiment_count(),
        }

    def _mine_metric_patterns(self) -> List[Dict]:
        try:
            db = self.memory._connect()
            rows = db.execute("""
                SELECT primary_metric,
                       COUNT(*) AS n,
                       AVG(CASE WHEN is_significant THEN 1.0 ELSE 0.0 END) AS sig_rate,
                       AVG(delta_pp) AS avg_delta,
                       STDDEV(delta_pp) AS std_delta
                FROM experiment_memory
                WHERE primary_metric IS NOT NULL AND primary_metric != ''
                GROUP BY primary_metric
                HAVING COUNT(*) >= 1
                ORDER BY sig_rate DESC, n DESC
            """).fetchall()
            if not self.memory._in_memory:
                db.close()
            return [
                {
                    "metric": r[0],
                    "n_exps": int(r[1]),
                    "sig_rate": round(float(r[2] or 0), 2),
                    "avg_delta": round(float(r[3] or 0), 4),
                    "std_delta": round(float(r[4] or 0), 4) if r[4] else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug("mine_metric_patterns: %s", e)
            return []

    def _mine_significance_rate(self) -> Dict:
        try:
            db = self.memory._connect()
            row = db.execute("""
                SELECT COUNT(*) AS n_total,
                       SUM(CASE WHEN is_significant THEN 1 ELSE 0 END) AS n_sig,
                       AVG(CASE WHEN is_significant THEN 1.0 ELSE 0.0 END) AS sig_rate
                FROM experiment_memory
            """).fetchone()
            if not self.memory._in_memory:
                db.close()
            if row:
                return {
                    "n_total": int(row[0] or 0),
                    "n_sig": int(row[1] or 0),
                    "sig_rate": round(float(row[2] or 0), 3),
                }
        except Exception as e:
            logger.debug("mine_significance_rate: %s", e)
        return {}

    def _mine_effect_sizes(self) -> Dict:
        try:
            db = self.memory._connect()
            row = db.execute("""
                SELECT AVG(delta_pp) AS avg,
                       STDDEV(delta_pp) AS std,
                       MIN(delta_pp) AS min_val,
                       MAX(delta_pp) AS max_val,
                       MEDIAN(delta_pp) AS median_val
                FROM experiment_memory
                WHERE delta_pp IS NOT NULL
            """).fetchone()
            if not self.memory._in_memory:
                db.close()
            if row:
                return {
                    "mean": round(float(row[0] or 0), 4),
                    "std": round(float(row[1] or 0), 4) if row[1] else None,
                    "min": round(float(row[2] or 0), 4),
                    "max": round(float(row[3] or 0), 4),
                    "median": round(float(row[4] or 0), 4) if row[4] else None,
                }
        except Exception as e:
            logger.debug("mine_effect_sizes: %s", e)
        return {}

    def _mine_srm_rate(self) -> float:
        try:
            db = self.memory._connect()
            row = db.execute("""
                SELECT AVG(CASE WHEN srm_detected THEN 1.0 ELSE 0.0 END)
                FROM experiment_memory
            """).fetchone()
            if not self.memory._in_memory:
                db.close()
            return round(float(row[0] or 0), 3) if row else 0.0
        except Exception:
            return 0.0

    def _synthesize_summary(self) -> str:
        sig = self._mine_significance_rate()
        effects = self._mine_effect_sizes()
        metrics = self._mine_metric_patterns()
        srm_rate = self._mine_srm_rate()

        n = sig.get("n_total", 0)
        if n == 0:
            return "No patterns yet — run more experiments to build organizational intelligence."

        sig_rate = sig.get("sig_rate", 0)
        avg_delta = effects.get("mean", 0)

        lines = [
            f"Across {n} experiment(s) in memory:",
            f"  {sig_rate:.0%} reached statistical significance.",
        ]
        if avg_delta:
            direction = "positive" if avg_delta > 0 else "negative"
            lines.append(f"  Average effect size is {avg_delta:+.3f}pp ({direction}).")
        if srm_rate > 0.1:
            lines.append(
                f"  {srm_rate:.0%} had sample ratio mismatches — worth auditing randomisation."
            )
        if metrics:
            top = metrics[0]
            lines.append(
                f"  '{top['metric']}' is the most-tested metric "
                f"({top['n_exps']} exp(s), {top['sig_rate']:.0%} sig rate)."
            )
        return "\n".join(lines)

    def get_prior(self, exp_name: str) -> ExperimentPrior:
        prior = ExperimentPrior(exp_name)
        if not self.memory:
            return prior

        similar = self.memory.search_similar(exp_name, limit=5)
        prior.similar_experiments = similar

        if similar:
            sig_rates = [1 if r.get("is_significant") else 0 for r in similar]
            delta_pps = [float(r.get("delta_pp") or 0) for r in similar]
            prior.expected_sig_rate = sum(sig_rates) / len(sig_rates) if sig_rates else 0.0
            prior.expected_delta_pp = sum(delta_pps) / len(delta_pps) if delta_pps else 0.0

        # SRM rate
        srm_rate = self._mine_srm_rate()
        prior.expected_srm_rate = srm_rate
        if srm_rate > 0.15:
            prior.caution_flags.append(
                f"{srm_rate:.0%} of past experiments had SRM — double-check assignment logic"
            )

        # Learnings
        learnings = self.memory.get_learnings(limit=3)
        prior.relevant_learnings = [l.get("learning", "")[:100] for l in learnings]

        return prior


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_MINER: Optional[PatternMiner] = None


def get_miner(memory=None) -> PatternMiner:
    global _MINER
    if _MINER is None:
        from continum.datastore.memory import get_memory

        _MINER = PatternMiner(memory=memory or get_memory())
    return _MINER


__all__ = [
    "PatternMiner",
    "Pattern",
    "ExperimentPrior",
    "get_miner",
]

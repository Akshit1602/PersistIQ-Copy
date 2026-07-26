"""Learnings Repository phase — the institutional-memory layer: learnings CRUD,
cross-experiment learning, and historical-learning retrieval.

The implementations live in :mod:`continum.ExpSuite.analysis.post_analysis`
(``run_learnings_repository``) and :mod:`continum.ExpSuite.analysis.synthesis`
(``run_historical_learning_retrieval`` / ``run_cross_experiment_learning``); they
are re-exported here so the phase reads as a coherent unit and are registered
under this phase in :mod:`continum.ExpSuite.registry`.
"""


def run_learnings_repository(*args, **kwargs):
    from continum.ExpSuite.analysis.post_analysis import run_learnings_repository as _f

    return _f(*args, **kwargs)


def run_historical_learning_retrieval(*args, **kwargs):
    from continum.ExpSuite.analysis.synthesis import run_historical_learning_retrieval as _f

    return _f(*args, **kwargs)


def run_cross_experiment_learning(*args, **kwargs):
    from continum.ExpSuite.analysis.synthesis import run_cross_experiment_learning as _f

    return _f(*args, **kwargs)


__all__ = [
    "run_learnings_repository",
    "run_historical_learning_retrieval",
    "run_cross_experiment_learning",
]

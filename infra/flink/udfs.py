from __future__ import annotations
"""Stateless, deterministic scoring functions run by Flink Python workers."""
import math
from pyflink.table import DataTypes
from pyflink.table.udf import udf


def weight_value(action: str) -> float:
    return {'view': .2, 'complete': 1., 'like': 3., 'favorite': 4., 'follow': 2.,
            'unlike': -3., 'unfavorite': -4., 'unfollow': -2., 'skip': -.5}.get(action, 0.)


def decay_value(weight: float, elapsed_hours: float) -> float:
    return float(weight) * math.exp(-max(0., float(elapsed_hours)) / 24.)

behavior_weight = udf(weight_value, input_types=[DataTypes.STRING()], result_type=DataTypes.DOUBLE())
time_decay = udf(decay_value, input_types=[DataTypes.DOUBLE(), DataTypes.DOUBLE()], result_type=DataTypes.DOUBLE())

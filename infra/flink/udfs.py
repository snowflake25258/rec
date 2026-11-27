from __future__ import annotations

"""Stateless, deterministic scoring functions run by Flink Python workers."""
import math
from pyflink.table import DataTypes
from pyflink.table.udf import udf


def weight_value(action: str) -> float:
    # 将行为类型转换成确定性权重，与 backend.algorithms.WEIGHTS 保持一致。
    # 取消操作使用相反权重；未知行为返回零，SQL 上游还会过滤非法行为。
    weight = {'view': .2,
              'complete': 1.,
              'like': 3.,
              'favorite': 4.,
              'follow': 2.,
              'unlike': -3.,
              'unfavorite': -4.,
              'unfollow': -2.,
              'skip': -.5}
    return weight.get(action, 0.)


def decay_value(weight: float, elapsed_hours: float) -> float:
    # 按 24 小时指数衰减；elapsed_hours 是事件距窗口结束的小时数。
    # 负间隔按零处理，避免未来时间戳把权重意外放大。
    return float(weight) * math.exp(-max(0., float(elapsed_hours)) / 24.)


behavior_weight = udf(weight_value, input_types=[DataTypes.STRING()], result_type=DataTypes.DOUBLE())
time_decay = udf(decay_value, input_types=[DataTypes.DOUBLE(), DataTypes.DOUBLE()], result_type=DataTypes.DOUBLE())
